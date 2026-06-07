"""
Generic exchange data models.

These types are exchange-agnostic and can be reused across different exchange clients.
"""

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional


@dataclass
class Position:
    """Normalized structure for an account position."""

    symbol: str
    side: str
    size: float
    avg_price: float
    mark_price: float
    unrealised_pnl: float
    realised_pnl: float
    category: str  # e.g., 'option', 'linear', 'inverse'
    exchange: str
    liquidation_price: Optional[float] = None
    leverage: Optional[float] = None
    position_value: Optional[float] = None
    initial_margin: Optional[float] = None
    maintenance_margin: Optional[float] = None


@dataclass
class Balance:
    """Normalized structure for an account balance."""

    coin: str
    wallet_balance: float
    available_balance: float
    exchange: str


@dataclass
class Instrument:
    """Normalized structure for instrument details."""

    symbol: str
    base_coin: str
    quote_coin: str
    strike_price: float
    option_type: str  # 'Call' or 'Put'
    status: str
    exchange: str
    launch_time: Optional[int] = None
    delivery_time: Optional[int] = None


@dataclass
class OptionPrice:
    """Normalized structure for option price and greeks data."""

    symbol: str
    mark_iv: float
    mark_price: float
    underlying_price: float
    volume_24h: float
    open_interest: float
    delta: float
    gamma: float
    theta: float
    vega: float
    bid_iv: Optional[float] = None
    ask_iv: Optional[float] = None
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    exchange: str = "bybit"


@dataclass
class Kline:
    """Normalized structure for a single kline/candlestick."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float = 0.0
    exchange: str = "bybit"
    symbol: Optional[str] = None

    @property
    def timestamp_int(self) -> int:
        """Get timestamp as integer (milliseconds) for legacy compatibility."""
        return int(self.timestamp.timestamp() * 1000)

    @classmethod
    def from_timestamp_int(cls, timestamp_int: int, **kwargs):
        """Create Kline from integer timestamp (milliseconds)."""
        timestamp = datetime.fromtimestamp(timestamp_int / 1000, tz=UTC).replace(
            tzinfo=None
        )
        return cls(timestamp=timestamp, **kwargs)


@dataclass
class OrderInfo:
    """Track active order information."""

    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    timestamp: datetime
    client_order_id: Optional[str] = None
    order_type: str = "Limit"
    status: str = "New"


@dataclass
class ExecutionResult:
    """Result of order execution with detailed information."""

    status: str  # 'executed', 'placed', 'skipped', 'replaced', 'error', 'blocked'
    order_info: Optional[OrderInfo] = None
    reason: Optional[str] = None
    error_message: Optional[str] = None
    old_order_id: Optional[str] = None
    traceback: Optional[str] = None
