"""
Bybit Public Client - Handles all public market data.

No API keys required. Provides access to market data, options chains,
historical data, and other public information from Bybit.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Callable, Awaitable

from .base_client import BaseClient
from .types import RequestConfig, ConnectionStats, RateLimitConfig
from .constants import TIMEFRAME_INTERVALS
from .utils import (
    encode_params,
    format_bybit_timestamp,
    safe_float,
    round_to_timeframe,
    get_cache_filepath,
    load_cache_metadata,
    save_cache_metadata,
    load_cache_data,
    save_cache_data,
    now_utc,
    datetime_to_ms,
    ms_to_datetime,
    ensure_utc_datetime,
    datetime_to_iso_utc,
    convert_interval_to_bybit_format,
)
from .iterators import time_range_iterator
import pandas as pd

logger = logging.getLogger(__name__)


class BybitPublicClient(BaseClient):
    """Handles all public market data - no API keys required."""

    def __init__(
        self,
        testnet: bool = False,
        config: RequestConfig = None,
        rate_limit: RateLimitConfig = None,
        use_cache: bool = True,
    ):
        base_url = (
            "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"
        )
        super().__init__(base_url=base_url, config=config, rate_limit=rate_limit)
        self.use_cache = use_cache

    async def _make_request(
        self, endpoint: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Make HTTP GET request with rate limiting and error handling."""
        if params is None:
            params = {}

        params_str = encode_params(params)
        url = f"{self.base_url}{endpoint}"
        if params_str:
            url += f"?{params_str}"

        async def do_request(client):
            return await client.get(url, timeout=self.config.timeout)

        return await self._request_with_retries(do_request)

    # Cache helpers

    def _parse_metadata_datetime(self, value: Any) -> Optional[datetime]:
        """Parse cache metadata timestamps to UTC datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return ensure_utc_datetime(value)
        if isinstance(value, (int, float)):
            return ms_to_datetime(int(value))
        if isinstance(value, str):
            return format_bybit_timestamp(value)
        return None

    def _coerce_datetime_column(self, df: pd.DataFrame, column: str) -> pd.DataFrame:
        """Ensure DataFrame column is naive UTC datetime."""
        if df.empty or column not in df.columns:
            return df
        if not pd.api.types.is_datetime64_any_dtype(df[column]):
            if pd.api.types.is_numeric_dtype(df[column]):
                df[column] = pd.to_datetime(
                    df[column], unit="ms", utc=True, errors="coerce"
                ).dt.tz_convert(None)
            else:
                df[column] = pd.to_datetime(
                    df[column], utc=True, errors="coerce"
                ).dt.tz_convert(None)
        else:
            if getattr(df[column].dt, "tz", None) is not None:
                df[column] = df[column].dt.tz_convert(None)
        return df

    def _find_boundary_gaps(
        self,
        cached_df: pd.DataFrame,
        start_time: datetime,
        end_time: datetime,
        time_col: str = "time",
    ) -> List[Tuple[datetime, datetime]]:
        """Find gaps at the boundaries of cached data for the requested time range."""
        gaps = []
        if cached_df.empty:
            return [(start_time, end_time)]
        cache_start = cached_df[time_col].min()
        cache_end = cached_df[time_col].max()
        if start_time < cache_start:
            gaps.append((start_time, min(cache_start - timedelta(seconds=1), end_time)))
        if end_time > cache_end:
            gaps.append((max(cache_end + timedelta(seconds=1), start_time), end_time))
        return gaps

    async def _get_with_cache(
        self,
        cache_key: str,
        filepath: str,
        time_col: str,
        dedup_cols: List[str],
        start_time: datetime,
        end_time: datetime,
        current_time: datetime,
        freshness_seconds: float,
        fetch_fn: Callable[[datetime, datetime], Awaitable[List[Dict[str, Any]]]],
        extra_metadata: Optional[Dict[str, Any]] = None,
        extra_filter: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = None,
    ) -> List[Dict[str, Any]]:
        """Generic cached data fetcher that eliminates repeated cache logic.

        Args:
            cache_key: Key for the metadata dict.
            filepath: Parquet file path.
            time_col: Column name for time in the DataFrame.
            dedup_cols: Columns to deduplicate on.
            start_time: Requested start.
            end_time: Requested end.
            current_time: Current UTC time.
            freshness_seconds: Max age before refetch.
            fetch_fn: async (start, end) -> list of dicts.
            extra_metadata: Additional keys to write into metadata.
            extra_filter: Additional filter to apply to results (e.g. period filter).
        """
        metadata = load_cache_metadata()
        cache_info = metadata.get(cache_key, {})
        cached_df = load_cache_data(filepath)
        cached_df = self._coerce_datetime_column(cached_df, time_col)

        need_fetch = True
        if not cached_df.empty:
            cache_start = self._parse_metadata_datetime(
                cache_info.get("start_time") or cache_info.get("start_ms")
            )
            cache_end = self._parse_metadata_datetime(
                cache_info.get("end_time") or cache_info.get("end_ms")
            )
            last_data_time = cached_df[time_col].max()
            cache_covers_range = (
                cache_start is not None
                and cache_end is not None
                and cache_start <= start_time
                and cache_end >= end_time
            )
            data_is_fresh = (
                current_time - last_data_time
            ).total_seconds() < freshness_seconds
            if cache_covers_range and data_is_fresh:
                need_fetch = False

        if need_fetch:
            gaps = self._find_boundary_gaps(cached_df, start_time, end_time, time_col)
            if gaps:
                new_data = []
                for gap_start, gap_end in gaps:
                    gap_data = await fetch_fn(gap_start, gap_end)
                    new_data.extend(gap_data)

                if new_data:
                    new_df = pd.DataFrame(new_data)
                    combined_df = (
                        pd.concat([cached_df, new_df], ignore_index=True)
                        if not cached_df.empty
                        else new_df
                    )
                    combined_df = combined_df.drop_duplicates(
                        subset=dedup_cols, keep="last"
                    )
                    combined_df = combined_df.sort_values(by=time_col).reset_index(
                        drop=True
                    )
                    save_cache_data(combined_df, filepath)

                    meta_entry = {
                        "last_update_time": datetime_to_iso_utc(current_time),
                        "start_time": datetime_to_iso_utc(combined_df[time_col].min()),
                        "end_time": datetime_to_iso_utc(combined_df[time_col].max()),
                        "record_count": len(combined_df),
                    }
                    if extra_metadata:
                        meta_entry.update(extra_metadata)
                    metadata[cache_key] = meta_entry
                    save_cache_metadata(metadata)
                    cached_df = combined_df

        if not cached_df.empty:
            filtered_df = cached_df[
                (cached_df[time_col] >= start_time) & (cached_df[time_col] <= end_time)
            ]
            if extra_filter is not None:
                filtered_df = extra_filter(filtered_df)
            return filtered_df.sort_values(by=time_col).to_dict("records")

        return []

    # Kline helpers

    def _filter_closed_candles(
        self, klines: List[Dict[str, Any]], interval: str, current_time: datetime
    ) -> List[Dict[str, Any]]:
        """Only return completed/closed candles, exclude current incomplete candle."""
        current_boundary = round_to_timeframe(current_time, interval)
        return [k for k in klines if k["timestamp"] < current_boundary]

    async def _fetch_single_chunk(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        category: str = "spot",
    ) -> List[Dict[str, Any]]:
        """Fetch a single chunk of kline data from API."""
        params = {
            "category": category,
            "symbol": symbol,
            "interval": convert_interval_to_bybit_format(interval),
            "limit": 1000,
            "start": datetime_to_ms(start_time),
            "end": datetime_to_ms(end_time),
        }

        response = await self._make_request("/v5/market/kline", params)
        raw_klines = response.get("result", {}).get("list", [])

        return [
            {
                "timestamp": ms_to_datetime(int(item[0])),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "turnover": float(item[6]),
            }
            for item in raw_klines
        ]

    async def _fetch_time_range(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        category: str = "spot",
    ) -> List[Dict[str, Any]]:
        """Use time_range_iterator to fetch large time ranges."""
        all_klines = []
        for chunk_start, chunk_end in time_range_iterator(
            start_time, end_time, 1000, interval
        ):
            chunk_data = await self._fetch_single_chunk(
                symbol, interval, chunk_start, chunk_end, category=category
            )
            all_klines.extend(chunk_data)
            await asyncio.sleep(0.1)
        return all_klines

    # Public API methods

    async def get_instruments(
        self,
        category: str,
        symbol: str = None,
        base_coin: str = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get instrument information for trading rules and specifications."""
        params = {"category": category, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if base_coin and category == "option":
            params["baseCoin"] = base_coin

        response = await self._make_request("/v5/market/instruments-info", params)
        return response.get("result", {}).get("list", [])

    async def get_options_tickers(
        self, base_coin: str, symbol: str = None
    ) -> List[Dict[str, Any]]:
        """Get options prices and Greeks."""
        params = {"category": "option", "baseCoin": base_coin}
        if symbol:
            params["symbol"] = symbol

        response = await self._make_request("/v5/market/tickers", params)
        return response.get("result", {}).get("list", [])

    async def get_options_chain_data(self, base_coin: str) -> List[Dict[str, Any]]:
        """Get complete options chain data with prices and Greeks combined."""
        instruments_task = self.get_instruments(category="option", base_coin=base_coin)
        prices_task = self.get_options_tickers(base_coin)

        try:
            instruments, prices = await asyncio.gather(instruments_task, prices_task)
        except Exception as e:
            raise Exception(f"Failed to fetch options data for {base_coin}: {e}")

        if not instruments or not prices:
            return []

        price_dict = {p["symbol"]: p for p in prices if p.get("symbol")}

        options_data = []
        for instrument in instruments:
            symbol = instrument.get("symbol")
            if not symbol:
                continue

            price_info = price_dict.get(symbol)
            if not price_info:
                continue

            mark_iv = safe_float(price_info.get("markIv"))
            if mark_iv <= 0:
                continue

            try:
                if "strike" in instrument:
                    strike = float(instrument["strike"])
                else:
                    symbol_parts = symbol.split("-")
                    if len(symbol_parts) >= 3:
                        strike = float(symbol_parts[2])
                    else:
                        continue
            except (ValueError, IndexError):
                continue

            option_type = instrument.get("optionsType", "")
            if not option_type and symbol.endswith(("-C", "-P")):
                option_type = "Call" if symbol.endswith("-C") else "Put"

            options_data.append(
                {
                    "symbol": symbol,
                    "strike": strike,
                    "option_type": option_type,
                    "underlying_price": safe_float(price_info.get("underlyingPrice")),
                    "mark_price": safe_float(price_info.get("markPrice")),
                    "mark_iv": mark_iv,
                    "delta": safe_float(price_info.get("delta")),
                    "gamma": safe_float(price_info.get("gamma")),
                    "theta": safe_float(price_info.get("theta")),
                    "vega": safe_float(price_info.get("vega")),
                    "volume_24h": safe_float(price_info.get("totalVolume")),
                    "open_interest": safe_float(price_info.get("openInterest")),
                    "bid_price": safe_float(price_info.get("bid1Price")),
                    "ask_price": safe_float(price_info.get("ask1Price")),
                    "bid_iv": safe_float(price_info.get("bid1Iv")),
                    "ask_iv": safe_float(price_info.get("ask1Iv")),
                    "expiry_date": instrument.get("deliveryTime", ""),
                    "launch_time": int(instrument.get("launchTime", 0)),
                    "delivery_time": int(instrument.get("deliveryTime", 0)),
                }
            )

        return options_data

    async def get_spot_price(self, symbol: str) -> float:
        """Current spot price."""
        params = {"category": "spot", "symbol": symbol}
        response = await self._make_request("/v5/market/tickers", params)
        result_list = response.get("result", {}).get("list", [])
        if result_list:
            return float(result_list[0].get("lastPrice", 0))
        return 0.0

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: datetime = None,
        end_time: datetime = None,
        category: str = "spot",
    ) -> List[Dict[str, Any]]:
        """Unified K-line data fetching with intelligent caching.

        category: 'spot' (default) | 'linear' | 'inverse'. Linear perps like
        ETHBTCUSDT, AEROUSDT, etc. require category='linear'.
        """
        current_time = now_utc()

        if start_time is not None:
            start_time = ensure_utc_datetime(start_time)
        if end_time is not None:
            end_time = ensure_utc_datetime(end_time)

        if not start_time or not end_time:
            interval_delta = timedelta(minutes=TIMEFRAME_INTERVALS[interval])
            if not start_time and not end_time:
                end_time = round_to_timeframe(current_time, interval)
                start_time = end_time - (limit * interval_delta)
            elif start_time and not end_time:
                end_time = current_time
            elif end_time and not start_time:
                start_time = end_time - (limit * interval_delta)

        aligned_start = round_to_timeframe(start_time, interval)
        aligned_end = round_to_timeframe(end_time, interval)

        if not self.use_cache:
            klines = await self._fetch_time_range(
                symbol, interval, aligned_start, aligned_end, category=category
            )
            return self._filter_closed_candles(klines, interval, current_time)

        cache_key = f"{symbol}_{interval}_klines"
        filepath = get_cache_filepath(symbol, interval, "klines")
        metadata = load_cache_metadata()
        cache_info = metadata.get(cache_key, {})
        cached_df = load_cache_data(filepath)
        cached_df = self._coerce_datetime_column(cached_df, "timestamp")

        if cached_df.empty:
            fetched = await self._fetch_time_range(
                symbol, interval, aligned_start, aligned_end, category=category
            )
            closed_klines = self._filter_closed_candles(fetched, interval, current_time)
            combined_df = pd.DataFrame(closed_klines)
        else:
            cache_start = (
                self._parse_metadata_datetime(
                    cache_info.get("start_time") or cache_info.get("start_ms")
                )
                or cached_df["timestamp"].min()
            )
            cache_end = (
                self._parse_metadata_datetime(
                    cache_info.get("end_time") or cache_info.get("end_ms")
                )
                or cached_df["timestamp"].max()
            )

            fetch_ranges = []
            if aligned_start < cache_start:
                fetch_ranges.append((aligned_start, cache_start))
            if aligned_end > cache_end:
                fetch_ranges.append((cache_end, aligned_end))

            new_klines = []
            for fetch_start, fetch_end in fetch_ranges:
                if fetch_start >= fetch_end:
                    continue
                fetched = await self._fetch_time_range(
                    symbol, interval, fetch_start, fetch_end, category=category
                )
                new_klines.extend(fetched)

            if new_klines:
                closed_klines = self._filter_closed_candles(
                    new_klines, interval, current_time
                )
                new_df = pd.DataFrame(closed_klines)
                combined_df = pd.concat([cached_df, new_df], ignore_index=True)
            else:
                combined_df = cached_df

        if not combined_df.empty:
            combined_df = combined_df.drop_duplicates(subset=["timestamp"], keep="last")
            combined_df = combined_df.sort_values(by="timestamp").reset_index(drop=True)
            save_cache_data(combined_df, filepath)

            metadata[cache_key] = {
                "last_update_time": datetime_to_iso_utc(current_time),
                "start_time": datetime_to_iso_utc(combined_df["timestamp"].min()),
                "end_time": datetime_to_iso_utc(combined_df["timestamp"].max()),
                "record_count": len(combined_df),
            }
            save_cache_metadata(metadata)

            mask = (combined_df["timestamp"] >= aligned_start) & (
                combined_df["timestamp"] <= aligned_end
            )
            return combined_df[mask].to_dict("records")

        return []

    # Volatility

    async def _fetch_volatility_chunk(
        self, base_coin: str, period: int, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Fetch a single chunk of historical volatility data from API."""
        params = {
            "category": "option",
            "baseCoin": base_coin,
            "period": period,
            "startTime": datetime_to_ms(start_time),
            "endTime": datetime_to_ms(end_time),
        }

        response = await self._make_request("/v5/market/historical-volatility", params)

        if "result" in response:
            result = response["result"]
            if isinstance(result, list):
                raw_data = result
            elif isinstance(result, dict) and "list" in result:
                raw_data = result["list"]
            else:
                raw_data = []
        else:
            raw_data = []

        return [
            {
                "time": ms_to_datetime(int(item["time"])),
                "value": float(item["value"]),
                "period": period,
            }
            for item in raw_data
            if isinstance(item, dict)
        ]

    async def _fetch_volatility_range(
        self, base_coin: str, period: int, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Chunked fetching for large volatility time ranges."""
        all_data = []
        chunk_size = timedelta(days=30)
        current_start = start_time

        while current_start < end_time:
            chunk_end = min(current_start + chunk_size, end_time)
            chunk_data = await self._fetch_volatility_chunk(
                base_coin, period, current_start, chunk_end
            )
            all_data.extend(chunk_data)
            current_start = chunk_end + timedelta(milliseconds=1)
            await asyncio.sleep(0.1)

        return all_data

    async def get_historical_volatility(
        self,
        base_coin: str,
        start_time: datetime = None,
        end_time: datetime = None,
        period: Optional[int] = 7,
    ) -> List[Dict[str, Any]]:
        """Historical volatility data with intelligent caching."""
        current_time = now_utc()
        if start_time is not None:
            start_time = ensure_utc_datetime(start_time)
        if end_time is not None:
            end_time = ensure_utc_datetime(end_time)
        if not end_time:
            end_time = current_time
        if not start_time:
            start_time = current_time - timedelta(days=30)
        if not period or period <= 0:
            period = 7

        if not self.use_cache:
            return await self._fetch_volatility_range(
                base_coin, period, start_time, end_time
            )

        freshness_seconds = timedelta(days=period).total_seconds()
        return await self._get_with_cache(
            cache_key=f"{base_coin}_{period}d_volatility",
            filepath=get_cache_filepath(base_coin, f"{period}d", "volatility"),
            time_col="time",
            dedup_cols=["time", "period"],
            start_time=start_time,
            end_time=end_time,
            current_time=current_time,
            freshness_seconds=freshness_seconds,
            fetch_fn=lambda s, e: self._fetch_volatility_range(base_coin, period, s, e),
            extra_filter=lambda df: df[df["period"] == period],
        )

    # Sentiment endpoints

    async def _fetch_chunked_data(
        self,
        endpoint: str,
        base_params: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        chunk_days: int,
        parse_item: Callable[[Dict], Dict[str, Any]],
        use_time_params: bool = True,
    ) -> List[Dict[str, Any]]:
        """Generic chunked data fetcher for sentiment endpoints."""
        all_data = []
        chunk_size = timedelta(days=chunk_days)
        current_start = start_time

        while current_start < end_time:
            chunk_end = min(current_start + chunk_size, end_time)
            try:
                params = dict(base_params)
                if use_time_params:
                    params["startTime"] = datetime_to_ms(current_start)
                    params["endTime"] = datetime_to_ms(chunk_end)

                response = await self._make_request(endpoint, params)

                if "result" in response and "list" in response["result"]:
                    for item in response["result"]["list"]:
                        data_point = parse_item(item)
                        if (
                            data_point
                            and current_start <= data_point["time"] <= chunk_end
                        ):
                            all_data.append(data_point)
            except Exception as e:
                logger.warning(
                    f"Error fetching {endpoint} for chunk {current_start}-{chunk_end}: {e}"
                )

            current_start = chunk_end + timedelta(milliseconds=1)
            await asyncio.sleep(0.1)

        return all_data

    def _parse_long_short_item(
        self, item: Dict, period: str, symbol_override: str = None
    ) -> Dict[str, Any]:
        sell_ratio = safe_float(item.get("sellRatio"))
        return {
            "timestamp": int(item["timestamp"]),
            "time": ms_to_datetime(int(item["timestamp"])),
            "symbol": item.get("symbol", symbol_override or ""),
            "long_ratio": safe_float(item.get("buyRatio")),
            "short_ratio": sell_ratio,
            "ls_ratio": safe_float(item.get("buyRatio")) / sell_ratio
            if sell_ratio > 0
            else 1.0,
            "period": period,
        }

    async def get_long_short_ratio(
        self,
        category: str = "linear",
        symbol: str = "BTCUSDT",
        period: str = "5min",
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get long-short ratio data with intelligent caching."""
        current_time = now_utc()
        if start_time is not None:
            start_time = ensure_utc_datetime(start_time)
        if end_time is not None:
            end_time = ensure_utc_datetime(end_time)
        if not end_time:
            end_time = current_time
        if not start_time:
            start_time = current_time - timedelta(hours=24)

        async def fetch_fn(s, e):
            return await self._fetch_chunked_data(
                endpoint="/v5/market/account-ratio",
                base_params={
                    "category": category,
                    "symbol": symbol,
                    "period": period,
                    "limit": 500,
                },
                start_time=s,
                end_time=e,
                chunk_days=7,
                parse_item=lambda item: self._parse_long_short_item(item, period),
                use_time_params=True,
            )

        if not self.use_cache:
            return await fetch_fn(start_time, end_time)

        return await self._get_with_cache(
            cache_key=f"{symbol}_{period}_long_short_ratio",
            filepath=get_cache_filepath(symbol, period, "long_short_ratio"),
            time_col="time",
            dedup_cols=["timestamp"],
            start_time=start_time,
            end_time=end_time,
            current_time=current_time,
            freshness_seconds=300,
            fetch_fn=fetch_fn,
            extra_metadata={
                "symbol": symbol,
                "period": period,
                "data_type": "long_short_ratio",
            },
        )

    async def get_long_short_ratio_data(
        self, symbol: str = "BTCUSDT", period: str = "5min", hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """Convenience wrapper with hours_back instead of start/end time."""
        end_time = now_utc()
        start_time = end_time - timedelta(hours=hours_back)
        return await self.get_long_short_ratio(
            category="linear",
            symbol=symbol,
            period=period,
            start_time=start_time,
            end_time=end_time,
        )

    async def get_open_interest_data(
        self, symbol: str = "BTCUSDT", interval_time: str = "5min", hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """Convenience wrapper with hours_back instead of start/end time."""
        end_time = now_utc()
        start_time = end_time - timedelta(hours=hours_back)
        return await self.get_open_interest(
            category="linear",
            symbol=symbol,
            interval_time=interval_time,
            start_time=start_time,
            end_time=end_time,
        )

    async def get_funding_rate_history(
        self, symbol: str = "BTCUSDT", hours_back: int = 168
    ) -> List[Dict[str, Any]]:
        """Convenience wrapper with hours_back instead of start/end time."""
        end_time = now_utc()
        start_time = end_time - timedelta(hours=hours_back)
        return await self.get_funding_history(
            category="linear",
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )

    async def get_open_interest(
        self,
        category: str = "linear",
        symbol: str = "BTCUSDT",
        interval_time: str = "5min",
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Get open interest data with intelligent caching."""
        current_time = now_utc()
        if start_time is not None:
            start_time = ensure_utc_datetime(start_time)
        if end_time is not None:
            end_time = ensure_utc_datetime(end_time)
        if not end_time:
            end_time = current_time
        if not start_time:
            start_time = current_time - timedelta(hours=24)

        async def fetch_fn(s, e):
            return await self._fetch_chunked_data(
                endpoint="/v5/market/open-interest",
                base_params={
                    "category": category,
                    "symbol": symbol,
                    "intervalTime": interval_time,
                    "limit": 200,
                },
                start_time=s,
                end_time=e,
                chunk_days=7,
                parse_item=lambda item: {
                    "timestamp": int(item["timestamp"]),
                    "time": ms_to_datetime(int(item["timestamp"])),
                    "symbol": symbol,
                    "open_interest": safe_float(item.get("openInterest")),
                    "interval": interval_time,
                },
            )

        if not self.use_cache:
            return await fetch_fn(start_time, end_time)

        return await self._get_with_cache(
            cache_key=f"{symbol}_{interval_time}_open_interest",
            filepath=get_cache_filepath(symbol, interval_time, "open_interest"),
            time_col="time",
            dedup_cols=["timestamp"],
            start_time=start_time,
            end_time=end_time,
            current_time=current_time,
            freshness_seconds=300,
            fetch_fn=fetch_fn,
            extra_metadata={
                "symbol": symbol,
                "interval": interval_time,
                "data_type": "open_interest",
            },
        )

    async def get_funding_history(
        self,
        category: str = "linear",
        symbol: str = "BTCUSDT",
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Get funding history data with intelligent caching."""
        current_time = now_utc()
        if start_time is not None:
            start_time = ensure_utc_datetime(start_time)
        if end_time is not None:
            end_time = ensure_utc_datetime(end_time)
        if not end_time:
            end_time = current_time
        if not start_time:
            start_time = current_time - timedelta(days=7)

        async def fetch_fn(s, e):
            return await self._fetch_chunked_data(
                endpoint="/v5/market/funding/history",
                base_params={"category": category, "symbol": symbol, "limit": 200},
                start_time=s,
                end_time=e,
                chunk_days=30,
                parse_item=lambda item: {
                    "timestamp": int(item["fundingRateTimestamp"]),
                    "time": ms_to_datetime(int(item["fundingRateTimestamp"])),
                    "symbol": item["symbol"],
                    "funding_rate": safe_float(item.get("fundingRate")),
                    "annualized_rate": safe_float(item.get("fundingRate")) * 365 * 3,
                },
            )

        if not self.use_cache:
            return await fetch_fn(start_time, end_time)

        return await self._get_with_cache(
            cache_key=f"{symbol}_funding_history",
            filepath=get_cache_filepath(symbol, "8h", "funding_history"),
            time_col="time",
            dedup_cols=["timestamp"],
            start_time=start_time,
            end_time=end_time,
            current_time=current_time,
            freshness_seconds=3600,
            fetch_fn=fetch_fn,
            extra_metadata={"symbol": symbol, "data_type": "funding_history"},
        )

    async def get_orderbook(
        self, category: str, symbol: str, limit: int = 25
    ) -> Dict[str, Any]:
        """Order book snapshot."""
        params = {"category": category, "symbol": symbol, "limit": limit}
        response = await self._make_request("/v5/market/orderbook", params)
        return response.get("result", {})

    async def get_recent_trades(
        self, category: str, symbol: str, limit: int = 60
    ) -> List[Dict[str, Any]]:
        """Recent public trades. Each entry: execId, T (ms), p, v, S (Buy/Sell)."""
        params = {"category": category, "symbol": symbol, "limit": limit}
        response = await self._make_request("/v5/market/recent-trade", params)
        return response.get("result", {}).get("list", [])

    async def get_linear_ticker(self, symbol: str) -> Dict[str, Any]:
        """Single linear ticker (mark, index, funding, OI, 24h turnover)."""
        params = {"category": "linear", "symbol": symbol}
        response = await self._make_request("/v5/market/tickers", params)
        items = response.get("result", {}).get("list", [])
        return items[0] if items else {}

    async def get_server_time(self) -> Dict[str, Any]:
        """Get server time for synchronization."""
        response = await self._make_request("/v5/market/time")
        result = response.get("result", {})
        if "timeSecond" in result:
            result["datetime"] = format_bybit_timestamp(
                int(result["timeSecond"]) * 1000
            )
        return result

    async def check_health(self) -> Dict[str, Any]:
        """Check API health status."""
        return await self.health_check(self.get_server_time)
