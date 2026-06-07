"""
Utility functions for Bybit API operations.

Authentication, rate limiting, time helpers, and caching.
"""

import hmac
import hashlib
import asyncio
import os
import json
import logging
import pandas as pd
from datetime import datetime, timedelta, UTC
from typing import Dict, Any, Optional

from .types import ApiCredentials, RequestConfig
from .constants import TIMEFRAME_INTERVALS, CACHE_DIR

logger = logging.getLogger(__name__)


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float, handling empty strings and None."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_float_optional(value: Any) -> Optional[float]:
    """Safely convert value to float, returning None for missing/invalid values."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def generate_signature(
    api_secret: str,
    timestamp: str,
    api_key: str,
    params_str: str,
    recv_window: int = 5000,
) -> str:
    """Generate HMAC SHA256 signature for Bybit API."""
    signature_payload = f"{timestamp}{api_key}{recv_window}{params_str}"
    return hmac.new(
        api_secret.encode("utf-8"), signature_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def get_timestamp() -> str:
    """Get current timestamp in milliseconds as string."""
    return str(int(datetime_to_ms(now_utc())))


def build_auth_headers(
    credentials: ApiCredentials, params_str: str, config: RequestConfig
) -> Dict[str, str]:
    """Build authentication headers for private API requests."""
    timestamp = get_timestamp()
    signature = generate_signature(
        credentials.api_secret,
        timestamp,
        credentials.api_key,
        params_str,
        config.recv_window,
    )
    return {
        "X-BAPI-API-KEY": credentials.api_key,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": str(config.recv_window),
        "X-BAPI-SIGN": signature,
        "Content-Type": "application/json",
    }


def encode_params(params: Dict[str, Any]) -> str:
    """Encode parameters for URL or signature generation."""
    if not params:
        return ""
    sorted_params = sorted(params.items())
    encoded_pairs = []
    for key, value in sorted_params:
        if value is not None:
            encoded_pairs.append(f"{key}={value}")
    return "&".join(encoded_pairs)


def validate_symbol(symbol: str, category: str = None) -> bool:
    """Validate symbol format for Bybit."""
    if not symbol or not isinstance(symbol, str):
        return False

    if category == "option":
        parts = symbol.split("-")
        if len(parts) != 4:
            return False
        base_coin, expiry, strike, option_type = parts
        if not base_coin.isalpha():
            return False
        if option_type not in ["C", "P"]:
            return False
        try:
            float(strike)
        except ValueError:
            return False
        return True
    elif category == "linear":
        return symbol.isalnum() and len(symbol) >= 3

    return symbol.replace("-", "").replace(".", "").isalnum()


def parse_bybit_error(response_data: Dict[str, Any]) -> Optional[str]:
    """Parse error message from Bybit API response."""
    if not isinstance(response_data, dict):
        return "Invalid response format"
    ret_code = response_data.get("retCode", 0)
    ret_msg = response_data.get("retMsg", "")
    if ret_code != 0:
        return f"Bybit API Error {ret_code}: {ret_msg}"
    return None


def calculate_rate_limit_delay(
    requests_per_second: float, last_request_time: Optional[datetime] = None
) -> float:
    """Calculate delay needed to respect rate limits."""
    if requests_per_second <= 0 or last_request_time is None:
        return 0.0
    min_interval = 1.0 / requests_per_second
    time_since_last = (
        now_utc() - ensure_utc_datetime(last_request_time)
    ).total_seconds()
    if time_since_last >= min_interval:
        return 0.0
    return min_interval - time_since_last


async def rate_limited_sleep(delay_seconds: float):
    """Sleep for rate limiting with async support."""
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)


def sanitize_float_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize parameters by converting floats to strings."""
    sanitized = {}
    for key, value in params.items():
        if isinstance(value, float):
            sanitized[key] = f"{value:.8f}".rstrip("0").rstrip(".")
        elif isinstance(value, int) and key in ["qty", "price"]:
            sanitized[key] = str(value)
        else:
            sanitized[key] = value
    return sanitized


def is_retryable_error(ret_code: int) -> bool:
    """Check if error code indicates a retryable condition."""
    retryable_codes = {10018, 10019, 10020, 10021, 3}
    return ret_code in retryable_codes


def format_bybit_timestamp(timestamp: Any) -> Optional[datetime]:
    """Convert Bybit timestamp to datetime."""
    if timestamp is None:
        return None
    try:
        if isinstance(timestamp, (int, float)):
            if timestamp > 1e12:
                return ms_to_datetime(int(timestamp))
            else:
                return datetime.fromtimestamp(timestamp, tz=UTC).replace(tzinfo=None)
        elif isinstance(timestamp, str):
            if "T" in timestamp:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return ensure_utc_datetime(parsed)
            ts_float = float(timestamp)
            if ts_float > 1e12:
                return ms_to_datetime(int(ts_float))
            else:
                return datetime.fromtimestamp(ts_float, tz=UTC).replace(tzinfo=None)
    except (ValueError, TypeError, OSError):
        pass
    return None


# Time conversion utilities


def now_utc() -> datetime:
    """Return current UTC time as naive datetime."""
    return datetime.now(UTC).replace(tzinfo=None)


def ensure_utc_datetime(value: datetime) -> datetime:
    """Normalize a datetime to naive UTC."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def datetime_to_ms(value: datetime) -> int:
    """Convert datetime to Unix timestamp in milliseconds (UTC).

    Treats naive datetimes as UTC.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return int(value.timestamp() * 1000)


def ms_to_datetime(timestamp_ms: int) -> datetime:
    """Convert Unix timestamp in milliseconds to naive UTC datetime."""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).replace(tzinfo=None)


def datetime_to_iso_utc(value: datetime) -> str:
    """Serialize datetime as ISO-8601 string in UTC with Z suffix."""
    dt = ensure_utc_datetime(value).replace(tzinfo=UTC)
    return dt.isoformat().replace("+00:00", "Z")


def round_to_timeframe(timestamp: datetime, interval: str) -> datetime:
    """Round timestamp to timeframe boundary in UTC."""
    dt = ensure_utc_datetime(timestamp)
    interval_minutes = TIMEFRAME_INTERVALS.get(interval, 60)

    if interval == "1d":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif interval == "1w":
        days_since_monday = dt.weekday()
        return (dt - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif interval == "1M":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        minutes_from_midnight = dt.hour * 60 + dt.minute
        rounded_minutes = (minutes_from_midnight // interval_minutes) * interval_minutes
        rounded_hour = rounded_minutes // 60
        rounded_minute = rounded_minutes % 60
        return dt.replace(
            hour=rounded_hour, minute=rounded_minute, second=0, microsecond=0
        )


def is_cache_fresh(
    last_update_time: datetime, interval: str, current_time: datetime
) -> bool:
    """Check if cache is fresh (current timeframe hasn't completed yet)."""
    current_boundary = round_to_timeframe(current_time, interval)
    last_boundary = round_to_timeframe(last_update_time, interval)
    return current_boundary == last_boundary


def convert_interval_to_bybit_format(interval: str) -> str:
    """Convert normalized interval strings to Bybit API interval format."""
    interval_mapping = {
        "1m": "1",
        "3m": "3",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "2h": "120",
        "4h": "240",
        "6h": "360",
        "12h": "720",
        "1d": "D",
        "1w": "W",
        "1M": "M",
    }
    return interval_mapping.get(interval, interval)


# Cache utilities


def get_cache_filepath(symbol: str, interval: str, data_type: str = "klines") -> str:
    """Generate cache file path."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{symbol}_{interval}_{data_type}.parquet")


def get_metadata_filepath() -> str:
    """Get cache metadata file path."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, "cache_metadata.json")


def load_cache_metadata() -> dict:
    """Load cache metadata."""
    metadata_file = get_metadata_filepath()
    if os.path.exists(metadata_file):
        with open(metadata_file, "r") as f:
            return json.load(f)
    return {}


def save_cache_metadata(metadata: dict):
    """Save cache metadata."""
    metadata_file = get_metadata_filepath()
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)


def load_cache_data(filepath: str) -> pd.DataFrame:
    """Load cached DataFrame from parquet."""
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()


def save_cache_data(df: pd.DataFrame, filepath: str):
    """Save DataFrame to parquet cache."""
    df.to_parquet(filepath)
