"""
Bybit API CLI — Market data, trading, and account management.

Usage:
    # Market data (no API keys)
    python -m bybit_api price BTCUSDT
    python -m bybit_api prices BTC ETH SOL
    python -m bybit_api klines BTCUSDT --interval 4h --hours 24
    python -m bybit_api options BTC [--min-oi 1]
    python -m bybit_api orderbook BTCUSDT [--depth 25]
    python -m bybit_api recent-trades BTCUSDT [--limit 60]
    python -m bybit_api funding BTCUSDT [--hours 168]
    python -m bybit_api oi BTCUSDT [--hours 168]

    # Trading (requires BYBIT_API_KEY + BYBIT_API_SECRET)
    python -m bybit_api order BTCUSDT Buy 0.001 --type Market
    python -m bybit_api order BTCUSDT Sell 0.001 --type Limit --price 100000
    python -m bybit_api order BTC-30MAY25-80000-C Buy 0.01 --category option
    python -m bybit_api cancel BTCUSDT <order_id>
    python -m bybit_api close-position RECALLUSDT
    python -m bybit_api close-all [--base-coin BTC]

    # Account (requires API keys)
    python -m bybit_api positions [--category linear]
    python -m bybit_api orders [--category linear]
    python -m bybit_api order-history [--symbol BTCUSDT]
    python -m bybit_api trades [--symbol BTCUSDT]
    python -m bybit_api wallet [--account-type UNIFIED]
    python -m bybit_api account

All output is JSON: {"success": bool, "data": ..., "timestamp": "..."}.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone

from .utils import safe_float


def _output(success: bool, data=None, error=None):
    """Print JSON result to stdout."""
    result = {
        "success": success,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if error:
        result["error"] = str(error)
    print(json.dumps(result, indent=2, default=str))


def _run(coro):
    """Run async coroutine in sync CLI context."""
    return asyncio.run(coro)


def _first_present(mapping, *keys):
    """Return first present key from mapping (supports normalized + raw fields)."""
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def _assert_nonzero_integrity(payload, values, metric: str, metric_keys):
    """Fail loudly when non-empty upstream payload collapses to all-zero metrics."""
    if not payload:
        return
    missing_metric_keys = all(
        _first_present(row, *metric_keys) is None for row in payload
    )
    if values and all(abs(v) == 0 for v in values) and missing_metric_keys:
        raise ValueError(
            f"{metric} integrity check failed: non-empty upstream payload parsed as all zeros."
        )


def _normalize_option_type(option_type: str, symbol: str) -> str:
    """Normalize option type to C/P using metadata first, then symbol suffix."""
    opt = str(option_type or "").strip().upper()
    if opt in {"CALL", "C"}:
        return "C"
    if opt in {"PUT", "P"}:
        return "P"

    suffix = str(symbol or "").split("-")[-1].upper()
    if suffix in {"C", "P"}:
        return suffix
    return "UNKNOWN"


def cmd_price(args):
    """Get current spot price for a symbol."""
    from .public import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        price = await client.get_spot_price(args.symbol)
        return price

    price = _run(_do())
    _output(True, {"symbol": args.symbol, "price": price})


def cmd_prices(args):
    """Get spot prices for multiple symbols."""
    from .public import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        results = {}
        for sym in args.symbols:
            symbol = (
                sym.upper() + "USDT"
                if not sym.upper().endswith("USDT")
                else sym.upper()
            )
            price = await client.get_spot_price(symbol)
            results[symbol] = price
        return results

    prices = _run(_do())
    _output(True, prices)


def cmd_klines(args):
    """Get OHLCV kline data."""
    from .public import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=args.hours)
        klines = await client.get_klines(
            args.symbol,
            args.interval,
            limit=args.limit,
            start_time=start_time,
            end_time=end_time,
        )
        # Return compact format
        compact = []
        for k in klines:
            compact.append(
                {
                    "t": k.get("timestamp") or k.get("t"),
                    "o": safe_float(k.get("open") or k.get("o", 0)),
                    "h": safe_float(k.get("high") or k.get("h", 0)),
                    "l": safe_float(k.get("low") or k.get("l", 0)),
                    "c": safe_float(k.get("close") or k.get("c", 0)),
                    "v": safe_float(k.get("volume") or k.get("v", 0)),
                }
            )
        return compact

    klines = _run(_do())
    _output(
        True,
        {
            "symbol": args.symbol,
            "interval": args.interval,
            "count": len(klines),
            "klines": klines,
        },
    )


def cmd_options(args):
    """Get options chain with Greeks and IV."""
    from .public import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        chain = await client.get_options_chain_data(args.base_coin)
        # Filter by min OI
        if args.min_oi > 0:
            chain = [
                o for o in chain if safe_float(o.get("open_interest", 0)) >= args.min_oi
            ]
        # Get spot price
        spot_symbol = args.base_coin.upper() + "USDT"
        spot = await client.get_spot_price(spot_symbol)
        return chain, spot

    chain, spot = _run(_do())
    compact = []
    for o in chain:
        symbol = o.get("symbol", "")
        compact.append(
            {
                "symbol": symbol,
                "strike": safe_float(o.get("strike", 0)),
                "type": _normalize_option_type(o.get("option_type", ""), symbol),
                "bid": safe_float(o.get("bid_price", 0)),
                "ask": safe_float(o.get("ask_price", 0)),
                "mark": safe_float(o.get("mark_price", 0)),
                "iv": safe_float(o.get("mark_iv", 0)),
                "delta": safe_float(o.get("delta", 0)),
                "gamma": safe_float(o.get("gamma", 0)),
                "theta": safe_float(o.get("theta", 0)),
                "vega": safe_float(o.get("vega", 0)),
                "oi": safe_float(o.get("open_interest", 0)),
                "volume": safe_float(o.get("volume_24h", 0)),
            }
        )
    _output(
        True,
        {
            "base_coin": args.base_coin,
            "spot_price": spot,
            "contracts": len(compact),
            "chain": compact,
        },
    )


def cmd_orderbook(args):
    """Get order book snapshot."""
    from .public import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        return await client.get_orderbook("linear", args.symbol, args.depth)

    book = _run(_do())
    _output(
        True,
        {
            "symbol": args.symbol,
            "bids": len(book.get("b", [])),
            "asks": len(book.get("a", [])),
            "orderbook": book,
        },
    )


def cmd_recent_trades(args):
    """Get recent public trades."""
    from .public import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        return await client.get_recent_trades(args.category, args.symbol, args.limit)

    trades = _run(_do())
    rows = []
    for t in trades:
        rows.append(
            {
                "ts_ms": int(t.get("time") or t.get("T") or 0),
                "price": safe_float(t.get("price") or t.get("p"), 0),
                "size": safe_float(t.get("size") or t.get("v"), 0),
                "side": t.get("side") or t.get("S"),
            }
        )
    _output(
        True,
        {
            "symbol": args.symbol,
            "category": args.category,
            "count": len(rows),
            "trades": rows,
        },
    )


def cmd_funding(args):
    """Get funding rate history."""
    from .public import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=args.hours)
        return await client.get_funding_history("linear", args.symbol, start, end)

    data = _run(_do())
    compact = []
    for d in data:
        compact.append(
            {
                "time": _first_present(d, "timestamp", "fundingRateTimestamp", "time"),
                "rate": safe_float(_first_present(d, "funding_rate", "fundingRate"), 0),
            }
        )
    _assert_nonzero_integrity(
        data, [r["rate"] for r in compact], "Funding", ("funding_rate", "fundingRate")
    )
    _output(
        True,
        {
            "symbol": args.symbol,
            "hours": args.hours,
            "count": len(compact),
            "current_rate": compact[0]["rate"] if compact else None,
            "avg_rate": sum(r["rate"] for r in compact) / len(compact)
            if compact
            else 0,
            "annual_pct": (
                sum(r["rate"] for r in compact) / len(compact) * 3 * 365 * 100
            )
            if compact
            else 0,
            "history": compact,
        },
    )


def cmd_oi(args):
    """Get open interest data."""
    from .public import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=args.hours)
        return await client.get_open_interest("linear", args.symbol, "1h", start, end)

    data = _run(_do())
    compact = []
    for d in data:
        compact.append(
            {
                "time": _first_present(d, "timestamp", "time"),
                "oi": safe_float(_first_present(d, "open_interest", "openInterest"), 0),
            }
        )
    _assert_nonzero_integrity(
        data,
        [r["oi"] for r in compact],
        "Open interest",
        ("open_interest", "openInterest"),
    )
    latest = compact[0]["oi"] if compact else 0
    oldest = compact[-1]["oi"] if compact else 0
    change_pct = ((latest - oldest) / oldest * 100) if oldest > 0 else 0
    _output(
        True,
        {
            "symbol": args.symbol,
            "hours": args.hours,
            "count": len(compact),
            "latest_oi": latest,
            "change_pct": round(change_pct, 2),
            "history": compact,
        },
    )


def cmd_positions(args):
    """Get account positions (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        base_coin = getattr(args, "base_coin", None)
        positions = await client.get_positions(
            args.category,
            symbol=args.symbol,
            base_coin=base_coin,
        )
        return positions

    positions = _run(_do())
    compact = []
    for p in positions:
        compact.append(
            {
                "symbol": p.symbol,
                "side": p.side,
                "size": p.size,
                "avg_price": p.avg_price,
                "mark_price": p.mark_price,
                "unrealised_pnl": p.unrealised_pnl,
                "category": p.category,
                "position_value": p.position_value,
            }
        )
    _output(
        True,
        {
            "category": args.category,
            "count": len(compact),
            "positions": compact,
        },
    )


def cmd_order(args):
    """Place an order (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        result = await client.place_order(
            category=args.category,
            symbol=args.symbol,
            side=args.side,
            order_type=args.order_type,
            qty=args.qty,
            price=args.price,
        )
        await client.close()
        return result

    result = _run(_do())
    _output(True, {"action": "order_placed", **result})


def cmd_cancel(args):
    """Cancel an order (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        result = await client.cancel_order(
            category=args.category,
            symbol=args.symbol,
            order_id=args.order_id,
        )
        await client.close()
        return result

    result = _run(_do())
    _output(True, {"action": "order_cancelled", **result})


def cmd_close_position(args):
    """Close a position by placing opposite market order (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        positions = await client.get_positions(args.category, symbol=args.symbol)
        closed = []
        for p in positions:
            size = float(getattr(p, "size", 0))
            side = getattr(p, "side", "")
            if size > 0:
                close_side = "Buy" if side == "Sell" else "Sell"
                result = await client.place_order(
                    category=args.category,
                    symbol=args.symbol,
                    side=close_side,
                    order_type="Market",
                    qty=size,
                )
                closed.append(
                    {"symbol": args.symbol, "side": close_side, "qty": size, **result}
                )
        await client.close()
        return closed

    closed = _run(_do())
    _output(True, {"action": "positions_closed", "closed": closed})


def cmd_close_all(args):
    """Close ALL open positions across categories (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        closed = []
        for cat in ["linear", "option"]:
            try:
                positions = await client.get_positions(
                    cat,
                    base_coin=args.base_coin if args.base_coin else None,
                )
            except Exception:
                continue
            for p in positions:
                size = float(getattr(p, "size", 0))
                side = getattr(p, "side", "")
                symbol = getattr(p, "symbol", "")
                if size > 0:
                    close_side = "Buy" if side == "Sell" else "Sell"
                    try:
                        result = await client.place_order(
                            category=cat,
                            symbol=symbol,
                            side=close_side,
                            order_type="Market",
                            qty=size,
                        )
                        closed.append(
                            {
                                "symbol": symbol,
                                "category": cat,
                                "side": close_side,
                                "qty": size,
                                **result,
                            }
                        )
                    except Exception as e:
                        closed.append(
                            {
                                "symbol": symbol,
                                "category": cat,
                                "error": str(e),
                            }
                        )
        await client.close()
        return closed

    closed = _run(_do())
    _output(
        True, {"action": "all_positions_closed", "count": len(closed), "closed": closed}
    )


def cmd_orders(args):
    """Get open orders (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        orders = await client.get_open_orders(
            args.category,
            symbol=args.symbol,
            base_coin=args.base_coin,
        )
        await client.close()
        return orders

    orders = _run(_do())
    _output(True, {"category": args.category, "count": len(orders), "orders": orders})


def cmd_order_history(args):
    """Get order history (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        history = await client.get_order_history(
            args.category,
            symbol=args.symbol,
            base_coin=args.base_coin,
            limit=args.limit,
        )
        await client.close()
        return history

    history = _run(_do())
    _output(True, {"category": args.category, "count": len(history), "orders": history})


def cmd_trades(args):
    """Get trade/fill history (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        trades = await client.get_trade_history(
            args.category,
            symbol=args.symbol,
            base_coin=args.base_coin,
            limit=args.limit,
        )
        await client.close()
        return trades

    trades = _run(_do())
    _output(True, {"category": args.category, "count": len(trades), "trades": trades})


def cmd_wallet(args):
    """Get wallet balance (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        balance = await client.get_wallet_balance(args.account_type)
        await client.close()
        return balance

    balance = _run(_do())
    _output(True, balance)


def cmd_account(args):
    """Get account info (requires API keys)."""
    from .client import BybitClient

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        client = BybitClient.from_env()
        info = await client.get_account_info()
        await client.close()
        return info

    info = _run(_do())
    _output(True, info)


def main():
    parser = argparse.ArgumentParser(
        description="Bybit API CLI — Market data, trading, and account management",
        prog="python -m bybit_api.cli",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # price
    p = sub.add_parser("price", help="Current spot price")
    p.add_argument("symbol", help="e.g. BTCUSDT")

    # prices
    p = sub.add_parser("prices", help="Spot prices for multiple assets")
    p.add_argument(
        "symbols", nargs="+", help="e.g. BTC ETH SOL (appends USDT if needed)"
    )

    # klines
    p = sub.add_parser("klines", help="OHLCV candle data")
    p.add_argument("symbol", help="e.g. BTCUSDT")
    p.add_argument(
        "--interval", default="1h", help="1m,5m,15m,30m,1h,4h,1d (default: 1h)"
    )
    p.add_argument(
        "--hours", type=int, default=24, help="Hours of history (default: 24)"
    )
    p.add_argument("--limit", type=int, default=200, help="Max candles (default: 200)")

    # options
    p = sub.add_parser("options", help="Options chain with Greeks/IV")
    p.add_argument("base_coin", help="e.g. BTC, ETH, SOL")
    p.add_argument("--min-oi", type=float, default=0, help="Min open interest filter")

    # orderbook
    p = sub.add_parser("orderbook", help="Order book snapshot")
    p.add_argument("symbol", help="e.g. BTCUSDT")
    p.add_argument("--depth", type=int, default=25, help="Depth (default: 25)")

    # recent-trades — public trade tape
    p = sub.add_parser("recent-trades", help="Recent public trades (tape)")
    p.add_argument("symbol", help="e.g. BTCUSDT")
    p.add_argument("--category", default="linear", help="linear, spot, option")
    p.add_argument("--limit", type=int, default=60, help="Max trades (default: 60)")

    # funding
    p = sub.add_parser("funding", help="Funding rate history")
    p.add_argument("symbol", help="e.g. BTCUSDT")
    p.add_argument(
        "--hours",
        type=int,
        default=168,
        help="Hours of history (default: 168 = 1 week)",
    )

    # oi
    p = sub.add_parser("oi", help="Open interest data")
    p.add_argument("symbol", help="e.g. BTCUSDT")
    p.add_argument(
        "--hours", type=int, default=24, help="Hours of history (default: 24)"
    )

    # positions
    p = sub.add_parser("positions", help="Account positions (needs API keys)")
    p.add_argument("--category", default="linear", help="linear, option, spot")
    p.add_argument("--symbol", default=None, help="Filter by symbol")
    p.add_argument(
        "--base-coin", default=None, help="Base coin for options (e.g. BTC, ETH)"
    )

    # order — place an order
    p = sub.add_parser("order", help="Place order (needs API keys)")
    p.add_argument("symbol", help="e.g. BTCUSDT, BTC-30MAY25-80000-C")
    p.add_argument("side", choices=["Buy", "Sell"], help="Buy or Sell")
    p.add_argument("qty", type=float, help="Order quantity")
    p.add_argument(
        "--type",
        dest="order_type",
        default="Market",
        help="Market or Limit (default: Market)",
    )
    p.add_argument(
        "--price",
        type=float,
        default=None,
        help="Limit price (required for Limit orders)",
    )
    p.add_argument("--category", default="linear", help="linear, option, spot")

    # cancel — cancel an order
    p = sub.add_parser("cancel", help="Cancel order (needs API keys)")
    p.add_argument("symbol", help="e.g. BTCUSDT")
    p.add_argument("order_id", help="Order ID to cancel")
    p.add_argument("--category", default="linear", help="linear, option, spot")

    # close-position — close a specific position
    p = sub.add_parser(
        "close-position", help="Close position by symbol (needs API keys)"
    )
    p.add_argument("symbol", help="e.g. BTCUSDT, RECALLUSDT")
    p.add_argument("--category", default="linear", help="linear, option, spot")

    # close-all — close ALL positions
    p = sub.add_parser("close-all", help="Close ALL open positions (needs API keys)")
    p.add_argument("--base-coin", default=None, help="Filter by base coin (e.g. BTC)")

    # orders — open orders
    p = sub.add_parser("orders", help="Open orders (needs API keys)")
    p.add_argument("--category", default="linear", help="linear, option, spot")
    p.add_argument("--symbol", default=None, help="Filter by symbol")
    p.add_argument("--base-coin", default=None, help="Base coin filter")

    # order-history
    p = sub.add_parser("order-history", help="Order history (needs API keys)")
    p.add_argument("--category", default="linear", help="linear, option, spot")
    p.add_argument("--symbol", default=None, help="Filter by symbol")
    p.add_argument("--base-coin", default=None, help="Base coin filter")
    p.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")

    # trades — fill history
    p = sub.add_parser("trades", help="Trade/fill history (needs API keys)")
    p.add_argument("--category", default="linear", help="linear, option, spot")
    p.add_argument("--symbol", default=None, help="Filter by symbol")
    p.add_argument("--base-coin", default=None, help="Base coin filter")
    p.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")

    # wallet
    p = sub.add_parser("wallet", help="Wallet balance (needs API keys)")
    p.add_argument("--account-type", default="UNIFIED", help="UNIFIED, CONTRACT, SPOT")

    # account
    p = sub.add_parser("account", help="Account info (needs API keys)")

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    commands = {
        "price": cmd_price,
        "prices": cmd_prices,
        "klines": cmd_klines,
        "options": cmd_options,
        "orderbook": cmd_orderbook,
        "recent-trades": cmd_recent_trades,
        "funding": cmd_funding,
        "oi": cmd_oi,
        "positions": cmd_positions,
        "order": cmd_order,
        "cancel": cmd_cancel,
        "close-position": cmd_close_position,
        "close-all": cmd_close_all,
        "orders": cmd_orders,
        "order-history": cmd_order_history,
        "trades": cmd_trades,
        "wallet": cmd_wallet,
        "account": cmd_account,
    }

    try:
        commands[args.command](args)
    except Exception as e:
        _output(False, error=str(e))
        sys.exit(1)
