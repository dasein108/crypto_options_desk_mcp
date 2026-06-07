"""
Base HTTP client with shared connection pooling, rate limiting, retries, and stats.
"""

import httpx
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from .types import RequestConfig, ConnectionStats, RateLimitConfig
from .utils import (
    parse_bybit_error,
    calculate_rate_limit_delay,
    rate_limited_sleep,
    is_retryable_error,
    now_utc,
)

logger = logging.getLogger(__name__)


class BybitApiError(Exception):
    """Non-retryable Bybit API error. Raised to break out of the retry loop."""

    pass


class BaseClient:
    """Shared HTTP infrastructure for public and private clients."""

    def __init__(
        self,
        base_url: str,
        config: RequestConfig = None,
        rate_limit: RateLimitConfig = None,
    ):
        self.base_url = base_url
        self.config = config or RequestConfig()
        self.rate_limit = rate_limit or RateLimitConfig()
        self.stats = ConnectionStats()
        self._last_request_time: Optional[datetime] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create a long-lived HTTP client with connection pooling."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self.config.timeout)
        return self._http_client

    async def close(self):
        """Close the HTTP client and release connections."""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    def _update_response_time(self, response_time_ms: float):
        if self.stats.avg_response_time_ms == 0:
            self.stats.avg_response_time_ms = response_time_ms
        else:
            self.stats.avg_response_time_ms = (
                self.stats.avg_response_time_ms * 0.9
            ) + (response_time_ms * 0.1)

    async def _request_with_retries(self, request_fn) -> Dict[str, Any]:
        """Execute a request function with rate limiting, retries, and stats tracking.

        Args:
            request_fn: async callable(client) -> httpx.Response
        """
        last_exception = None

        for attempt in range(self.config.max_retries):
            # Rate limit per attempt
            delay = calculate_rate_limit_delay(
                self.rate_limit.requests_per_second, self._last_request_time
            )
            if delay > 0:
                await rate_limited_sleep(delay)

            try:
                self._last_request_time = now_utc()
                self.stats.total_requests += 1

                client = self._get_http_client()
                response = await request_fn(client)

                response_time = (
                    now_utc() - self._last_request_time
                ).total_seconds() * 1000
                self._update_response_time(response_time)

                data = response.json()

                error_msg = parse_bybit_error(data)
                if error_msg:
                    ret_code = data.get("retCode", 0)

                    if ret_code == 10020:
                        self.stats.rate_limited_requests += 1
                        if attempt < self.config.max_retries - 1:
                            await rate_limited_sleep(
                                self.rate_limit.retry_after_seconds
                            )
                            continue

                    if (
                        is_retryable_error(ret_code)
                        and attempt < self.config.max_retries - 1
                    ):
                        await asyncio.sleep(self.config.retry_delay * (2**attempt))
                        continue

                    self.stats.failed_requests += 1
                    raise BybitApiError(error_msg)

                self.stats.successful_requests += 1
                return data

            except BybitApiError:
                raise

            except httpx.TimeoutException as e:
                last_exception = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2**attempt))
                    continue

            except Exception as e:
                last_exception = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (2**attempt))
                    continue

        self.stats.failed_requests += 1
        raise Exception(
            f"Request failed after {self.config.max_retries} attempts: {last_exception}"
        )

    async def health_check(self, probe_fn) -> Dict[str, Any]:
        """Run a health check using the given probe function."""
        try:
            start_time = now_utc()
            await probe_fn()
            end_time = now_utc()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "timestamp": end_time,
                "stats": {
                    "total_requests": self.stats.total_requests,
                    "success_rate": self.stats.success_rate,
                    "avg_response_time_ms": self.stats.avg_response_time_ms,
                },
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": now_utc(),
                "stats": {
                    "total_requests": self.stats.total_requests,
                    "success_rate": self.stats.success_rate,
                    "error_rate": self.stats.error_rate,
                },
            }

    def get_connection_stats(self) -> ConnectionStats:
        return self.stats
