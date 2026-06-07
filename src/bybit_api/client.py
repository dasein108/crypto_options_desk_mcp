"""
Unified Bybit Client - Combines public and private operations.
"""

import logging
import math
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .models import Balance, Instrument, Kline, OptionPrice, OrderInfo, Position
from .types import (
    ApiCredentials,
    RequestConfig,
    RateLimitConfig,
    OrderParams,
    HealthCheck,
    InstrumentSpec,
)
from .public import BybitPublicClient
from .private import BybitPrivateClient
from .utils import now_utc, ensure_utc_datetime, safe_float, ms_to_datetime

logger = logging.getLogger(__name__)


class BybitClient:
    """Unified client combining public and private operations.

    Delegates to BybitPublicClient and BybitPrivateClient.
    Access sub-clients directly via .public and .private for full API.
    """

    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        testnet: bool = False,
        config: RequestConfig = None,
        rate_limit: RateLimitConfig = None,
        use_cache: bool = True,
    ):
        self.public = BybitPublicClient(
            testnet=testnet, config=config, rate_limit=rate_limit, use_cache=use_cache
        )

        self.private: Optional[BybitPrivateClient] = None
        if api_key and api_secret:
            credentials = ApiCredentials(
                api_key=api_key, api_secret=api_secret, testnet=testnet
            )
            self.private = BybitPrivateClient(
                credentials=credentials, config=config, rate_limit=rate_limit
            )

    @classmethod
    def from_env(
        cls,
        testnet: bool = False,
        config: RequestConfig = None,
        rate_limit: RateLimitConfig = None,
        use_cache: bool = True,
    ) -> "BybitClient":
        """Create client from environment variables."""
        return cls(
            api_key=os.getenv("BYBIT_API_KEY"),
            api_secret=os.getenv("BYBIT_API_SECRET"),
            testnet=testnet,
            config=config,
            rate_limit=rate_limit,
            use_cache=use_cache,
        )

    async def close(self):
        """Close all HTTP connections."""
        await self.public.close()
        if self.private:
            await self.private.close()

    def has_private_access(self) -> bool:
        return self.private is not None

    # Public API — delegate to self.public

    async def get_instruments(
        self,
        category: str,
        symbol: str = None,
        base_coin: str = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        return await self.public.get_instruments(category, symbol, base_coin, limit)

    async def get_options_chain(self, base_coin: str) -> List[Dict[str, Any]]:
        return await self.public.get_instruments(category="option", base_coin=base_coin)

    async def get_options_tickers(
        self, base_coin: str, symbol: str = None
    ) -> List[Dict[str, Any]]:
        return await self.public.get_options_tickers(base_coin, symbol)

    async def get_options_chain_data(self, base_coin: str) -> List[Dict[str, Any]]:
        return await self.public.get_options_chain_data(base_coin)

    async def get_spot_price(self, symbol: str) -> float:
        return await self.public.get_spot_price(symbol)

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: datetime = None,
        end_time: datetime = None,
        hours_back: int = None,
        category: str = "spot",
    ) -> List[Kline]:
        """Get klines as typed Kline objects.

        category: 'spot' (default) | 'linear' | 'inverse'. Cross-pair perps
        like ETHBTCUSDT live in 'linear' — pass `category='linear'`.
        """
        if hours_back is not None:
            end_time = now_utc()
            start_time = end_time - timedelta(hours=hours_back)
        raw = await self.public.get_klines(
            symbol, interval, limit, start_time, end_time, category=category
        )
        return [
            Kline(
                timestamp=ensure_utc_datetime(item["timestamp"]),
                symbol=symbol,
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]),
                turnover=float(item.get("turnover", 0)),
            )
            for item in raw
        ]

    async def get_historical_volatility(
        self,
        base_coin: str,
        start_time: datetime = None,
        end_time: datetime = None,
        period: Optional[int] = 7,
        hours_back: int = None,
    ) -> List[Dict[str, Any]]:
        if hours_back is not None:
            end_time = now_utc()
            start_time = end_time - timedelta(hours=hours_back)
        return await self.public.get_historical_volatility(
            base_coin, start_time, end_time, period
        )

    async def get_orderbook(
        self, category: str, symbol: str, limit: int = 25
    ) -> Dict[str, Any]:
        return await self.public.get_orderbook(category, symbol, limit)

    async def get_recent_trades(
        self, category: str, symbol: str, limit: int = 60
    ) -> List[Dict[str, Any]]:
        return await self.public.get_recent_trades(category, symbol, limit)

    async def get_linear_ticker(self, symbol: str) -> Dict[str, Any]:
        return await self.public.get_linear_ticker(symbol)

    async def get_open_interest(
        self,
        category: str = "linear",
        symbol: str = "BTCUSDT",
        interval_time: str = "5min",
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 200,
        hours_back: int = None,
    ) -> List[Dict[str, Any]]:
        if hours_back is not None:
            end_time = now_utc()
            start_time = end_time - timedelta(hours=hours_back)
        return await self.public.get_open_interest(
            category, symbol, interval_time, start_time, end_time, limit
        )

    async def get_long_short_ratio(
        self,
        category: str = "linear",
        symbol: str = "BTCUSDT",
        period: str = "5min",
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 500,
        hours_back: int = None,
    ) -> List[Dict[str, Any]]:
        if hours_back is not None:
            end_time = now_utc()
            start_time = end_time - timedelta(hours=hours_back)
        return await self.public.get_long_short_ratio(
            category, symbol, period, start_time, end_time, limit
        )

    async def get_funding_history(
        self,
        category: str = "linear",
        symbol: str = "BTCUSDT",
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 200,
        hours_back: int = None,
    ) -> List[Dict[str, Any]]:
        if hours_back is not None:
            end_time = now_utc()
            start_time = end_time - timedelta(hours=hours_back)
        return await self.public.get_funding_history(
            category, symbol, start_time, end_time, limit
        )

    async def get_server_time(self) -> Dict[str, Any]:
        return await self.public.get_server_time()

    # Private API — delegate to self.private

    def _ensure_private_access(self):
        if not self.has_private_access():
            raise ValueError("Private operations require API credentials")

    async def get_positions(
        self,
        category: str,
        symbol: str = None,
        base_coin: str = None,
        settle_coin: str = None,
    ) -> List[Position]:
        self._ensure_private_access()
        return await self.private.get_positions(
            category, symbol, base_coin, settle_coin
        )

    async def get_account_balance(
        self, account_type: str = "UNIFIED", coin: str = None
    ) -> List[Balance]:
        self._ensure_private_access()
        return await self.private.get_account_balance(account_type, coin)

    async def place_order(
        self,
        category: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        price: float = None,
        time_in_force: str = "GTC",
        client_order_id: str = None,
    ) -> Dict[str, Any]:
        self._ensure_private_access()
        order_params = OrderParams(
            category=category,
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            price=price,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
        )
        return await self.private.place_order(order_params)

    async def cancel_order(
        self,
        category: str,
        symbol: str,
        order_id: str = None,
        client_order_id: str = None,
    ) -> Dict[str, Any]:
        self._ensure_private_access()
        return await self.private.cancel_order(
            category, symbol, order_id, client_order_id
        )

    async def get_open_orders(
        self,
        category: str,
        symbol: str = None,
        base_coin: str = None,
        order_id: str = None,
        client_order_id: str = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_private_access()
        return await self.private.get_open_orders(
            category, symbol, base_coin, order_id, client_order_id
        )

    async def get_order_history(
        self,
        category: str,
        symbol: str = None,
        base_coin: str = None,
        order_id: str = None,
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        self._ensure_private_access()
        return await self.private.get_order_history(
            category, symbol, base_coin, order_id, start_time, end_time, limit
        )

    async def get_trade_history(
        self,
        category: str,
        symbol: str = None,
        base_coin: str = None,
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        self._ensure_private_access()
        return await self.private.get_trade_history(
            category, symbol, base_coin, start_time, end_time, limit
        )

    async def amend_order(
        self,
        category: str,
        symbol: str,
        order_id: str = None,
        client_order_id: str = None,
        qty: float = None,
        price: float = None,
    ) -> Dict[str, Any]:
        self._ensure_private_access()
        return await self.private.amend_order(
            category,
            symbol,
            order_id,
            client_order_id,
            qty=str(qty) if qty is not None else None,
            price=str(price) if price is not None else None,
        )

    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Any]:
        self._ensure_private_access()
        return await self.private.get_wallet_balance(account_type)

    async def get_account_info(self) -> Dict[str, Any]:
        self._ensure_private_access()
        return await self.private.get_account_info()

    # Convenience aliases

    async def get_asset_price(self, symbol: str) -> float:
        return await self.get_spot_price(symbol)

    async def get_index_price(self, base_coin: str) -> float:
        return await self.get_spot_price(f"{base_coin}USDT")

    async def get_option_prices(self, base_coin: str) -> List[OptionPrice]:
        """Get option prices as typed OptionPrice objects."""
        result = await self.get_options_tickers(base_coin)
        return [
            OptionPrice(
                symbol=item["symbol"],
                mark_iv=safe_float(item.get("markIv")),
                mark_price=safe_float(item.get("markPrice")),
                underlying_price=safe_float(item.get("underlyingPrice")),
                volume_24h=safe_float(item.get("totalVolume")),
                open_interest=safe_float(item.get("openInterest", 0)),
                delta=safe_float(item.get("delta")),
                gamma=safe_float(item.get("gamma")),
                theta=safe_float(item.get("theta")),
                vega=safe_float(item.get("vega")),
                bid_iv=safe_float(item.get("bid1Iv", 0)),
                ask_iv=safe_float(item.get("ask1Iv", 0)),
                bid_price=safe_float(item.get("bid1Price", 0)),
                ask_price=safe_float(item.get("ask1Price", 0)),
            )
            for item in result
        ]

    async def get_option_chain(self, base_coin: str) -> List[Instrument]:
        """Get option chain as typed Instrument objects."""
        result = await self.get_instruments(category="option", base_coin=base_coin)
        instruments = []
        for item in result:
            try:
                instruments.append(
                    Instrument(
                        symbol=item["symbol"],
                        base_coin=item["baseCoin"],
                        quote_coin=item["quoteCoin"],
                        strike_price=float(item["displayName"].split("-")[2]),
                        option_type=item["optionsType"],
                        status=item["status"],
                        launch_time=int(item["launchTime"]),
                        delivery_time=int(item["deliveryTime"]),
                        exchange="bybit",
                    )
                )
            except (KeyError, IndexError, ValueError):
                continue
        return instruments

    async def get_open_interest_data(
        self, symbol: str = "BTCUSDT", interval: str = "5min", hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """Convenience alias for get_open_interest with hours_back."""
        return await self.get_open_interest(
            category="linear",
            symbol=symbol,
            interval_time=interval,
            hours_back=hours_back,
        )

    async def get_long_short_ratio_data(
        self, symbol: str = "BTCUSDT", period: str = "5min", hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """Convenience alias for get_long_short_ratio with hours_back."""
        return await self.get_long_short_ratio(
            category="linear",
            symbol=symbol,
            period=period,
            hours_back=hours_back,
        )

    async def get_funding_rate_history(
        self, symbol: str = "BTCUSDT", hours_back: int = 168
    ) -> List[Dict[str, Any]]:
        """Convenience alias for get_funding_history with hours_back."""
        return await self.get_funding_history(
            category="linear",
            symbol=symbol,
            hours_back=hours_back,
        )

    async def get_historical_vol(
        self,
        base_coin: str,
        start_time: datetime = None,
        end_time: datetime = None,
        hours_back: int = None,
        period: Optional[int] = 7,
    ) -> List[Dict[str, Any]]:
        """Convenience alias for get_historical_volatility with hours_back."""
        return await self.get_historical_volatility(
            base_coin,
            start_time,
            end_time,
            period,
            hours_back=hours_back,
        )

    async def get_tickers(
        self, category: str, symbol: str = None, base_coin: str = None
    ) -> Dict:
        """Get tickers for any category."""
        if category == "option":
            result = await self.get_options_tickers(base_coin, symbol)
            return {"list": result}
        elif category == "spot" and symbol:
            price = await self.get_spot_price(symbol)
            return {
                "list": [
                    {"symbol": symbol, "lastPrice": str(price), "markPrice": str(price)}
                ]
            }
        return {"list": []}

    # Instrument specifications

    async def get_instrument_specs(
        self, category: str, symbol: str = None, base_coin: str = None
    ) -> List[InstrumentSpec]:
        """Get instrument specifications as typed InstrumentSpec objects."""
        raw_instruments = await self.get_instruments(category, symbol, base_coin)
        specs = []
        for inst in raw_instruments:
            price_filter = inst.get("priceFilter", {})
            lot_filter = inst.get("lotSizeFilter", {})
            tick_size = float(price_filter.get("tickSize", 0.01))
            min_qty = float(lot_filter.get("minOrderQty", 0.001))
            max_qty = float(lot_filter.get("maxOrderQty", 1000000))
            qty_step = float(lot_filter.get("qtyStep", 0.001))
            price_precision = max(
                0, -int(math.log10(tick_size)) if tick_size > 0 else 1
            )
            qty_precision = max(0, -int(math.log10(qty_step)) if qty_step > 0 else 3)
            specs.append(
                InstrumentSpec(
                    symbol=inst.get("symbol"),
                    tick_size=tick_size,
                    min_order_qty=min_qty,
                    max_order_qty=max_qty,
                    lot_size_filter=qty_step,
                    price_precision=price_precision,
                    qty_precision=qty_precision,
                )
            )
        return specs

    async def get_instrument(
        self, symbol: str, category: str = "linear"
    ) -> Optional[InstrumentSpec]:
        """Get single instrument specification."""
        try:
            specs = await self.get_instrument_specs(category=category, symbol=symbol)
            return specs[0] if specs else None
        except Exception as e:
            logger.warning(f"Error fetching instrument spec for {symbol}: {e}")
            return None

    # Aggregated positions

    async def get_spot_balance(self, coin: str = None) -> List[Balance]:
        """Get spot balance — alias for get_account_balance('UNIFIED')."""
        self._ensure_private_access()
        return await self.private.get_account_balance("UNIFIED", coin)

    async def get_all_positions(
        self, asset: Optional[str] = None
    ) -> Dict[str, List[Position]]:
        """Load aggregated positions across all categories for a given asset."""
        self._ensure_private_access()
        results: Dict[str, List[Position]] = {
            "spot": [],
            "linear": [],
            "inverse": [],
            "option": [],
            "delivery": [],
        }
        try:
            spot_balances = await self.get_spot_balance(asset)
            for balance in spot_balances:
                if balance.wallet_balance > 0:
                    try:
                        mark_price = (
                            await self.get_spot_price(f"{balance.coin}USDT")
                            if balance.coin != "USDT"
                            else 1.0
                        )
                    except Exception:
                        mark_price = 1.0
                    results["spot"].append(
                        Position(
                            symbol=balance.coin,
                            side="Buy",
                            size=balance.wallet_balance,
                            avg_price=mark_price,
                            mark_price=mark_price,
                            unrealised_pnl=0.0,
                            realised_pnl=0.0,
                            category="spot",
                            exchange="bybit",
                        )
                    )

            assets = [asset] if asset else ["BTC", "ETH", "SOL"]
            for base_asset in assets:
                linear = await self.get_positions(category="linear", settle_coin="USDT")
                results["linear"].extend(
                    p for p in linear if p.symbol.startswith(base_asset)
                )

                inverse = await self.get_positions(
                    category="inverse", settle_coin=base_asset
                )
                for pos in inverse:
                    if pos.symbol == f"{base_asset}USD":
                        results["inverse"].append(pos)
                    elif any(c.isdigit() for c in pos.symbol):
                        pos.category = "delivery"
                        results["delivery"].append(pos)

                options = await self.get_positions(
                    category="option", base_coin=base_asset
                )
                results["option"].extend(options)
        except Exception as e:
            logger.error(f"Error fetching aggregated positions: {e}")

        return results

    async def get_my_positions(
        self, category: str, asset: Optional[str] = None
    ) -> List[Position]:
        """Simplified position fetching by category."""
        self._ensure_private_access()
        if category == "spot":
            balances = await self.get_spot_balance(asset)
            positions = []
            for balance in balances:
                if balance.wallet_balance > 0:
                    try:
                        mark_price = (
                            await self.get_spot_price(f"{balance.coin}USDT")
                            if balance.coin != "USDT"
                            else 1.0
                        )
                    except Exception:
                        mark_price = 1.0
                    positions.append(
                        Position(
                            symbol=balance.coin,
                            side="Buy",
                            size=balance.wallet_balance,
                            avg_price=mark_price,
                            mark_price=mark_price,
                            unrealised_pnl=0.0,
                            realised_pnl=0.0,
                            category="spot",
                            exchange="bybit",
                        )
                    )
            return positions
        elif category == "option":
            if not asset:
                raise ValueError("Asset (base_coin) is required for option positions")
            return await self.get_positions(category="option", base_coin=asset)
        elif category == "linear":
            all_pos = await self.get_positions(category="linear", settle_coin="USDT")
            return (
                [p for p in all_pos if p.symbol.startswith(asset)] if asset else all_pos
            )
        elif category == "inverse":
            if asset:
                all_pos = await self.get_positions(
                    category="inverse", settle_coin=asset
                )
                return [p for p in all_pos if p.symbol == f"{asset}USD"]
            return await self.get_positions(category="inverse", settle_coin="BTC")
        elif category == "delivery":
            if not asset:
                raise ValueError("Asset (base_coin) is required for delivery positions")
            all_pos = await self.get_positions(category="inverse", settle_coin=asset)
            delivery = []
            for pos in all_pos:
                if pos.symbol != f"{asset}USD" and any(c.isdigit() for c in pos.symbol):
                    pos.category = "delivery"
                    delivery.append(pos)
            return delivery
        return await self.get_positions(category=category)

    def get_my_positions_sync(
        self, category: str, asset: Optional[str] = None
    ) -> List[Position]:
        """Synchronous wrapper for get_my_positions."""
        import asyncio

        return asyncio.run(self.get_my_positions(category, asset))

    # Unified health check

    async def health_check(self) -> HealthCheck:
        public_health = await self.public.check_health()

        private_health = None
        if self.has_private_access():
            private_health = await self.private.check_health()

        public_status = public_health.get("status", "unknown")
        private_status = (
            private_health.get("status", "unknown") if private_health else "disabled"
        )

        return HealthCheck(
            is_healthy=(
                public_status == "healthy" and private_status in ["healthy", "disabled"]
            ),
            timestamp=now_utc(),
            public_api_status=public_status,
            private_api_status=private_status,
            latency_ms=public_health.get("latency_ms"),
            error_message=public_health.get("error")
            or (private_health.get("error") if private_health else None),
        )

    def get_connection_stats(self) -> Dict[str, Any]:
        stats = {"public": self.public.get_connection_stats(), "private": None}
        if self.has_private_access():
            stats["private"] = self.private.get_connection_stats()
        return stats

    def get_client_info(self) -> Dict[str, Any]:
        return {
            "has_private_access": self.has_private_access(),
            "testnet": self.private.credentials.testnet if self.private else False,
            "public_base_url": self.public.base_url,
            "private_base_url": self.private.base_url if self.private else None,
            "rate_limit_rps": self.public.rate_limit.requests_per_second,
            "timeout_seconds": self.public.config.timeout,
            "max_retries": self.public.config.max_retries,
        }
