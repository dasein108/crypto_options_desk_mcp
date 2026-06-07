"""
Constants for Bybit API client.
"""

from pathlib import Path

# Timeframe intervals in minutes
TIMEFRAME_INTERVALS = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "12h": 720,
    "1d": 1440,
    "1w": 10080,
    "1M": 43200,
}

CACHE_DIR = str(Path.home() / ".cache" / "bybit-api")
