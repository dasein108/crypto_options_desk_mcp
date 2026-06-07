"""
Indicators CLI — Technical analysis, volatility, regime detection from terminal.

Usage:
    python -m indicators_lib technical BTCUSDT [--interval 4h] [--hours 24]
    python -m indicators_lib volatility BTCUSDT [--interval 4h] [--hours 168]
    python -m indicators_lib regime BTCUSDT [--interval 4h] [--hours 168]
    python -m indicators_lib sentiment BTCUSDT
    python -m indicators_lib summary BTCUSDT [--interval 4h] [--hours 24]

All output is JSON. Fetches klines from Bybit automatically.
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import List

from .types import Kline


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


def _fetch_klines(symbol: str, interval: str, hours: int) -> List[Kline]:
    """Fetch klines from Bybit and convert to indicators_lib Kline objects."""
    from bybit_api import BybitPublicClient
    from bybit_api.utils import safe_float

    async def _do():
        client = BybitPublicClient()
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        return await client.get_klines(symbol, interval, limit=500, start_time=start, end_time=end)

    raw = asyncio.run(_do())

    klines = []
    for k in raw:
        ts = k.get("timestamp") or k.get("t")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
        elif isinstance(ts, (int, float)):
            ts = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)

        klines.append(Kline(
            symbol=symbol,
            timestamp=ts,
            open=safe_float(k.get("open") or k.get("o", 0)),
            high=safe_float(k.get("high") or k.get("h", 0)),
            low=safe_float(k.get("low") or k.get("l", 0)),
            close=safe_float(k.get("close") or k.get("c", 0)),
            volume=safe_float(k.get("volume") or k.get("v", 0)),
        ))

    return klines


def cmd_technical(args):
    """Comprehensive technical analysis: RSI, MACD, ATR, BB, ADX, signals."""
    from .technical import TechnicalIndicators

    klines = _fetch_klines(args.symbol, args.interval, args.hours)
    if len(klines) < 30:
        _output(False, error=f"Insufficient data: {len(klines)} klines (need 30+)")
        return

    analysis = TechnicalIndicators.get_comprehensive_analysis(klines, args.symbol)
    _output(True, {
        "symbol": args.symbol,
        "interval": args.interval,
        "candles": len(klines),
        "analysis": asdict(analysis),
    })


def cmd_volatility(args):
    """Volatility analysis: realized vol, Garman-Klass, cone, regime."""
    from .volatility import VolatilityAnalysis

    klines = _fetch_klines(args.symbol, args.interval, args.hours)
    if len(klines) < 20:
        _output(False, error=f"Insufficient data: {len(klines)} klines (need 20+)")
        return

    metrics = VolatilityAnalysis.calculate_comprehensive_metrics(klines)
    cone = VolatilityAnalysis.calculate_volatility_cone(klines)

    _output(True, {
        "symbol": args.symbol,
        "interval": args.interval,
        "candles": len(klines),
        "metrics": asdict(metrics),
        "cone": cone,
    })


def cmd_regime(args):
    """Market regime detection: trend direction, vol regime, mean-reversion signals."""
    from .summary import SummaryIndicators

    klines = _fetch_klines(args.symbol, args.interval, args.hours)
    if len(klines) < 50:
        _output(False, error=f"Insufficient data: {len(klines)} klines (need 50+)")
        return

    regime = SummaryIndicators.get_market_regime_analysis(klines, args.symbol)
    _output(True, {
        "symbol": args.symbol,
        "interval": args.interval,
        "candles": len(klines),
        "regime": regime,
    })


def cmd_sentiment(args):
    """Market sentiment: long/short ratio, OI trends, funding rate analysis."""
    from .sentiment import SentimentAnalyzer
    from bybit_api import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        analyzer = SentimentAnalyzer(client)
        return await analyzer.get_market_sentiment_analysis(args.symbol)

    result = asyncio.run(_do())
    _output(True, {
        "symbol": args.symbol,
        "sentiment": result,
    })


def cmd_summary(args):
    """Volatility intelligence summary: regime, options bias, strategy hints."""
    from .summary import SummaryIndicators

    klines = _fetch_klines(args.symbol, args.interval, args.hours)
    if len(klines) < 20:
        _output(False, error=f"Insufficient data: {len(klines)} klines (need 20+)")
        return

    intel = SummaryIndicators.get_volatility_intelligence(klines, args.symbol)
    _output(True, {
        "symbol": args.symbol,
        "interval": args.interval,
        "candles": len(klines),
        "intelligence": intel,
    })


def cmd_levels(args):
    """Key S/R levels: POC, VAH/VAL, swing S/R, MAs."""
    from .levels import compute_levels

    klines = _fetch_klines(args.symbol, args.interval, args.hours)
    if len(klines) < 20:
        _output(False, error=f"Insufficient data: {len(klines)} klines (need 20+)")
        return

    levels = compute_levels(klines, args.symbol)
    _output(True, data=levels.to_dict())


def main():
    parser = argparse.ArgumentParser(
        description="Technical Indicators CLI",
        prog="python -m indicators_lib",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # technical
    p = sub.add_parser("technical", help="Full TA: RSI, MACD, ATR, BB, ADX, signals")
    p.add_argument("symbol", help="e.g. BTCUSDT")
    p.add_argument("--interval", default="4h", help="Kline interval (default: 4h)")
    p.add_argument("--hours", type=int, default=168, help="Hours of data (default: 168 = 1 week)")

    # volatility
    p = sub.add_parser("volatility", help="Volatility: realized, GK, cone, regime")
    p.add_argument("symbol")
    p.add_argument("--interval", default="4h")
    p.add_argument("--hours", type=int, default=168)

    # regime
    p = sub.add_parser("regime", help="Market regime: trend, vol, mean-reversion")
    p.add_argument("symbol")
    p.add_argument("--interval", default="4h")
    p.add_argument("--hours", type=int, default=168)

    # sentiment
    p = sub.add_parser("sentiment", help="Sentiment: long/short, OI, funding")
    p.add_argument("symbol", help="e.g. BTCUSDT")

    # summary
    p = sub.add_parser("summary", help="Volatility intelligence + strategy hints")
    p.add_argument("symbol")
    p.add_argument("--interval", default="4h")
    p.add_argument("--hours", type=int, default=24)

    # levels
    p = sub.add_parser("levels", help="Key S/R levels: POC, VAH/VAL, swing S/R, MAs")
    p.add_argument("symbol")
    p.add_argument("--interval", default="4h")
    p.add_argument("--hours", type=int, default=168)

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    commands = {
        "technical": cmd_technical,
        "volatility": cmd_volatility,
        "regime": cmd_regime,
        "sentiment": cmd_sentiment,
        "summary": cmd_summary,
        "levels": cmd_levels,
    }

    try:
        commands[args.command](args)
    except Exception as e:
        _output(False, error=str(e))
        sys.exit(1)
