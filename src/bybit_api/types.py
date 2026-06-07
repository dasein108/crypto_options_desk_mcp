"""
Bybit-specific types for API requests and responses.
"""

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any, Optional


@dataclass
class BybitResponse:
    """Base response structure from Bybit API."""

    ret_code: int
    ret_msg: str
    result: Any
    time: Optional[int] = None

    def __post_init__(self):
        self.ret_code = int(self.ret_code)

    @property
    def is_success(self) -> bool:
        return self.ret_code == 0


@dataclass
class OrderParams:
    """Parameters for placing orders."""

    category: str
    symbol: str
    side: str  # 'Buy' or 'Sell'
    order_type: str  # 'Market' or 'Limit'
    qty: float
    price: Optional[float] = None
    time_in_force: str = "GTC"
    client_order_id: Optional[str] = None

    def __post_init__(self):
        self.qty = float(self.qty)
        if self.price is not None:
            self.price = float(self.price)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    requests_per_second: float = 10.0
    burst_size: int = 20
    retry_after_seconds: float = 1.0
    max_retries: int = 3
    backoff_factor: float = 2.0


@dataclass
class ApiCredentials:
    """API credentials container."""

    api_key: str
    api_secret: str
    testnet: bool = False

    @property
    def base_url(self) -> str:
        if self.testnet:
            return "https://api-testnet.bybit.com"
        return "https://api.bybit.com"


@dataclass
class RequestConfig:
    """Configuration for HTTP requests."""

    timeout: float = 30.0
    recv_window: int = 5000
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class ApiError:
    """Standardized API error information."""

    error_code: int
    error_message: str
    endpoint: str
    timestamp: datetime
    retry_after: Optional[float] = None

    def __post_init__(self):
        if isinstance(self.timestamp, str):
            parsed = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(UTC).replace(tzinfo=None)
            self.timestamp = parsed


@dataclass
class ConnectionStats:
    """Connection statistics and health metrics."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited_requests: int = 0
    avg_response_time_ms: float = 0.0
    last_request_time: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100


@dataclass
class InstrumentSpec:
    """Trading specifications for an instrument."""

    symbol: str
    tick_size: float
    min_order_qty: float
    max_order_qty: float
    lot_size_filter: float
    price_precision: int
    qty_precision: int

    def round_price(self, price: float) -> float:
        if self.tick_size <= 0:
            return round(price, 1)
        rounded = round(price / self.tick_size) * self.tick_size
        return round(rounded, self.price_precision)

    def round_quantity(self, qty: float) -> float:
        if self.lot_size_filter <= 0:
            return round(qty, 3)
        rounded = round(qty / self.lot_size_filter) * self.lot_size_filter
        rounded = max(self.min_order_qty, min(self.max_order_qty, rounded))
        return round(rounded, self.qty_precision)


@dataclass
class HealthCheck:
    """Health check result for Bybit connections."""

    is_healthy: bool
    timestamp: datetime
    public_api_status: str = "unknown"
    private_api_status: str = "unknown"
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.timestamp, str):
            parsed = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(UTC).replace(tzinfo=None)
            self.timestamp = parsed
