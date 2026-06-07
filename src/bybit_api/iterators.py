"""
Time range iteration utilities for chunked data fetching.
"""

from typing import Tuple, Generator
from datetime import datetime, timedelta

from .utils import ensure_utc_datetime


def get_interval_seconds(interval_str: str) -> float:
    """Convert an interval string to seconds."""
    if interval_str.isdigit():
        return int(interval_str) * 60
    if interval_str.endswith("m") and interval_str[:-1].isdigit():
        return int(interval_str[:-1]) * 60
    if interval_str.endswith("h") and interval_str[:-1].isdigit():
        return int(interval_str[:-1]) * 60 * 60
    if interval_str == "1d":
        return timedelta(days=1).total_seconds()
    if interval_str == "1w":
        return timedelta(weeks=1).total_seconds()
    if interval_str == "1M":
        return timedelta(days=30).total_seconds()
    if interval_str in {"D", "W", "M"}:
        return get_interval_seconds({"D": "1d", "W": "1w", "M": "1M"}[interval_str])
    raise ValueError(f"Unsupported interval string: {interval_str}")


def time_range_iterator(
    start_time: datetime, end_time: datetime, limit: int, interval: str
) -> Generator[Tuple[datetime, datetime], None, None]:
    """Simple time range iterator for fetching data in chunks."""
    interval_seconds = get_interval_seconds(interval)
    interval_delta = timedelta(seconds=interval_seconds)

    start_time = ensure_utc_datetime(start_time)
    end_time = ensure_utc_datetime(end_time)

    if start_time >= end_time or limit <= 0 or interval_seconds <= 0:
        return

    current_start_time = start_time

    while current_start_time < end_time:
        chunk_duration = limit * interval_delta
        current_end_time = current_start_time + chunk_duration
        if current_end_time > end_time:
            current_end_time = end_time
        yield current_start_time, current_end_time
        current_start_time = current_end_time
