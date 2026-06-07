"""
Bybit Private Client - Handles private account operations.

Requires API keys. Provides access to account data, trading operations,
order management, and other private account functions.
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from .base_client import BaseClient, BybitApiError
from .types import (
    ApiCredentials,
    RequestConfig,
    ConnectionStats,
    RateLimitConfig,
    OrderParams,
)
from .models import Position, Balance
from .utils import (
    build_auth_headers,
    encode_params,
    sanitize_float_params,
    now_utc,
    datetime_to_ms,
    ensure_utc_datetime,
    safe_float,
    safe_float_optional,
)


class BybitException(Exception):
    """Custom exception for Bybit API errors."""

    pass


class OrderNotFoundException(BybitException):
    """Exception raised when an order is not found."""

    pass


class BybitPrivateClient(BaseClient):
    """Handles private account operations - requires API keys."""

    def __init__(
        self,
        credentials: ApiCredentials,
        config: RequestConfig = None,
        rate_limit: RateLimitConfig = None,
    ):
        super().__init__(
            base_url=credentials.base_url, config=config, rate_limit=rate_limit
        )
        self.credentials = credentials

    async def _make_request(
        self, method: str, endpoint: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Make authenticated HTTP request with retries."""
        if params is None:
            params = {}
        params = sanitize_float_params(params)

        if method.upper() == "GET":
            params_str = encode_params(params)

            async def do_request(client):
                headers = build_auth_headers(self.credentials, params_str, self.config)
                url = f"{self.base_url}{endpoint}"
                if params_str:
                    url += f"?{params_str}"
                return await client.get(
                    url, headers=headers, timeout=self.config.timeout
                )
        else:

            async def do_request(client):
                params_str = json.dumps(params, separators=(",", ":")) if params else ""
                headers = build_auth_headers(self.credentials, params_str, self.config)
                return await client.post(
                    f"{self.base_url}{endpoint}",
                    json=params,
                    headers=headers,
                    timeout=self.config.timeout,
                )

        try:
            return await self._request_with_retries(do_request)
        except BybitApiError as e:
            error_msg = str(e)
            if "110001" in error_msg:
                raise OrderNotFoundException(error_msg) from e
            raise

    async def get_positions(
        self,
        category: str,
        symbol: str = None,
        base_coin: str = None,
        settle_coin: str = None,
    ) -> List[Position]:
        """Fetch account positions."""
        if category == "option" and not symbol and not base_coin:
            raise ValueError("base_coin is required for option category")

        # limit=200 is Bybit's max for /v5/position/list. Default is 20 — too low
        # once an account holds 21+ positions across strategies (would silently
        # drop entries from page 2). Single page covers all real-world cases for
        # a perp trading account.
        params = {"category": category, "limit": 200}
        if symbol:
            params["symbol"] = symbol
        elif base_coin:
            params["baseCoin"] = base_coin
        elif settle_coin:
            params["settleCoin"] = settle_coin

        response = await self._make_request("GET", "/v5/position/list", params)
        raw_positions = response.get("result", {}).get("list", [])
        # Defensive pagination — fetch remaining pages if cursor returned.
        cursor = response.get("result", {}).get("nextPageCursor", "")
        while cursor:
            page_params = dict(params)
            page_params["cursor"] = cursor
            page = await self._make_request("GET", "/v5/position/list", page_params)
            raw_positions.extend(page.get("result", {}).get("list", []))
            cursor = page.get("result", {}).get("nextPageCursor", "")

        positions = []
        for item in raw_positions:
            if safe_float(item.get("size", 0)) == 0:
                continue

            position = Position(
                symbol=item.get("symbol", ""),
                side=item.get("side", ""),
                size=safe_float(item.get("size", 0)),
                avg_price=safe_float(item.get("avgPrice", 0)),
                mark_price=safe_float(item.get("markPrice", 0)),
                unrealised_pnl=safe_float(item.get("unrealisedPnl", 0)),
                realised_pnl=safe_float(item.get("cumRealisedPnl", 0)),
                category=category,
                exchange="bybit",
                liquidation_price=safe_float_optional(
                    item.get("liqPrice", item.get("liquidationPrice"))
                ),
                leverage=safe_float_optional(item.get("leverage")),
                position_value=safe_float_optional(item.get("positionValue")),
                initial_margin=safe_float_optional(item.get("positionIM")),
                maintenance_margin=safe_float_optional(item.get("positionMM")),
            )
            positions.append(position)

        return positions

    async def get_account_balance(
        self, account_type: str = "UNIFIED", coin: str = None
    ) -> List[Balance]:
        """Account balance information."""
        params = {"accountType": account_type}
        if coin:
            params["coin"] = coin

        response = await self._make_request("GET", "/v5/account/wallet-balance", params)

        balances = []
        for account in response.get("result", {}).get("list", []):
            for coin_info in account.get("coin", []):
                wallet_balance = safe_float(coin_info.get("walletBalance", 0))
                if wallet_balance > 0:
                    balance = Balance(
                        coin=coin_info.get("coin", ""),
                        wallet_balance=wallet_balance,
                        available_balance=safe_float(
                            coin_info.get("availableToWithdraw", 0)
                        ),
                        exchange="bybit",
                    )
                    balances.append(balance)

        return balances

    async def place_order(self, order_params: OrderParams) -> Dict[str, Any]:
        """Place new order."""
        params = {
            "category": order_params.category,
            "symbol": order_params.symbol,
            "side": order_params.side,
            "orderType": order_params.order_type,
            "qty": str(order_params.qty),
        }
        if order_params.price is not None:
            params["price"] = str(order_params.price)
        if order_params.time_in_force:
            params["timeInForce"] = order_params.time_in_force
        if order_params.client_order_id:
            params["orderLinkId"] = order_params.client_order_id

        response = await self._make_request("POST", "/v5/order/create", params)
        return response.get("result", {})

    async def cancel_order(
        self,
        category: str,
        symbol: str,
        order_id: str = None,
        client_order_id: str = None,
    ) -> Dict[str, Any]:
        """Cancel existing order."""
        if not order_id and not client_order_id:
            raise ValueError("Either order_id or client_order_id must be provided")

        params = {"category": category, "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["orderLinkId"] = client_order_id

        response = await self._make_request("POST", "/v5/order/cancel", params)
        return response.get("result", {})

    async def amend_order(
        self,
        category: str,
        symbol: str,
        order_id: str = None,
        client_order_id: str = None,
        qty: str = None,
        price: str = None,
        trigger_price: str = None,
        take_profit: str = None,
        stop_loss: str = None,
    ) -> Dict[str, Any]:
        """Amend existing order."""
        if not order_id and not client_order_id:
            raise ValueError("Either order_id or client_order_id must be provided")

        params = {"category": category, "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["orderLinkId"] = client_order_id
        if qty:
            params["qty"] = str(qty)
        if price:
            params["price"] = str(price)
        if trigger_price:
            params["triggerPrice"] = str(trigger_price)
        if take_profit:
            params["takeProfit"] = str(take_profit)
        if stop_loss:
            params["stopLoss"] = str(stop_loss)

        response = await self._make_request("POST", "/v5/order/amend", params)
        return response.get("result", {})

    async def get_open_orders(
        self,
        category: str,
        symbol: str = None,
        base_coin: str = None,
        order_id: str = None,
        client_order_id: str = None,
    ) -> List[Dict[str, Any]]:
        """Get open orders."""
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        if base_coin:
            params["baseCoin"] = base_coin
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["orderLinkId"] = client_order_id

        response = await self._make_request("GET", "/v5/order/realtime", params)
        return response.get("result", {}).get("list", [])

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
        """Order execution history."""
        params = {"category": category, "limit": min(limit, 50)}
        if symbol:
            params["symbol"] = symbol
        if base_coin:
            params["baseCoin"] = base_coin
        if order_id:
            params["orderId"] = order_id
        if start_time:
            params["startTime"] = datetime_to_ms(ensure_utc_datetime(start_time))
        if end_time:
            params["endTime"] = datetime_to_ms(ensure_utc_datetime(end_time))

        response = await self._make_request("GET", "/v5/order/history", params)
        return response.get("result", {}).get("list", [])

    async def get_trade_history(
        self,
        category: str,
        symbol: str = None,
        base_coin: str = None,
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Trade execution history."""
        params = {"category": category, "limit": min(limit, 50)}
        if symbol:
            params["symbol"] = symbol
        if base_coin:
            params["baseCoin"] = base_coin
        if start_time:
            params["startTime"] = datetime_to_ms(ensure_utc_datetime(start_time))
        if end_time:
            params["endTime"] = datetime_to_ms(ensure_utc_datetime(end_time))

        response = await self._make_request("GET", "/v5/execution/list", params)
        return response.get("result", {}).get("list", [])

    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Any]:
        """Get detailed wallet balance."""
        params = {"accountType": account_type}
        response = await self._make_request("GET", "/v5/account/wallet-balance", params)
        return response.get("result", {})

    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information and configuration."""
        response = await self._make_request("GET", "/v5/account/info")
        return response.get("result", {})

    async def set_leverage(
        self,
        category: str,
        symbol: str,
        buy_leverage: float,
        sell_leverage: float = None,
    ) -> Dict[str, Any]:
        """Set per-symbol leverage. Required before opening leveraged positions.

        For one-way mode use the same value for buy and sell. For hedge mode
        each side can be set separately.
        """
        params = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(buy_leverage),
            "sellLeverage": str(
                sell_leverage if sell_leverage is not None else buy_leverage
            ),
        }
        response = await self._make_request("POST", "/v5/position/set-leverage", params)
        return response.get("result", {})

    async def switch_isolated_margin(
        self,
        category: str,
        symbol: str,
        trade_mode: int,
        buy_leverage: float,
        sell_leverage: float = None,
    ) -> Dict[str, Any]:
        """Switch margin mode. trade_mode: 0=cross, 1=isolated."""
        params = {
            "category": category,
            "symbol": symbol,
            "tradeMode": trade_mode,
            "buyLeverage": str(buy_leverage),
            "sellLeverage": str(
                sell_leverage if sell_leverage is not None else buy_leverage
            ),
        }
        response = await self._make_request(
            "POST", "/v5/position/switch-isolated", params
        )
        return response.get("result", {})

    async def set_position_mode(
        self, category: str, symbol: str, mode: int
    ) -> Dict[str, Any]:
        """Set position mode. mode: 0=one-way, 3=hedge (both sides). Linear only."""
        params = {
            "category": category,
            "symbol": symbol,
            "mode": mode,
        }
        response = await self._make_request("POST", "/v5/position/switch-mode", params)
        return response.get("result", {})

    async def check_health(self) -> Dict[str, Any]:
        """Check private API health status."""
        return await self.health_check(self.get_account_info)
