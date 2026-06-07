"""
Options CLI — GEX, vanna, flow, skew, pricing, covered call from terminal.

Usage:
    python -m options_lib gex BTC [--min-oi 1]
    python -m options_lib vanna BTC [--min-oi 1]
    python -m options_lib flow BTC [--min-oi 1]
    python -m options_lib skew BTC
    python -m options_lib price BTC-28MAR26-100000-C [--iv 0.65]
    python -m options_lib iv-rv BTC [--rv-window 30]
    python -m options_lib strike-select BTC [--target-delta 0.10 --max-dte 14]
    python -m options_lib cc-signal BTC [--iv-rv-threshold 10]

All output is JSON. Fetches options chain from Bybit automatically.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import List

from .flow.types import OptionsChainData, OptionType


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


def _safe_float(value) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fetch_chain(
    base_coin: str, min_oi: float = 0
) -> tuple[List[OptionsChainData], float]:
    """Fetch options chain from Bybit and convert to OptionsChainData."""
    from bybit_api import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        raw = await client.get_options_chain_data(base_coin)
        spot = await client.get_spot_price(f"{base_coin}USDT")
        return raw, spot

    raw, spot = asyncio.run(_do())

    chain = []
    for opt in raw:
        symbol = opt.get("symbol", "")
        if not symbol:
            continue

        # Parse option type
        opt_type_str = str(opt.get("option_type", ""))
        if (
            opt_type_str in ("Call", "C", "CALL")
            or symbol.endswith("-C")
            or "-C-" in symbol
        ):
            option_type = OptionType.CALL
        elif (
            opt_type_str in ("Put", "P", "PUT")
            or symbol.endswith("-P")
            or "-P-" in symbol
        ):
            option_type = OptionType.PUT
        else:
            continue

        # Parse expiry from symbol (e.g., BTC-28MAR26-100000-C or BTC-28MAR26-100000-P-USDT)
        parts = symbol.split("-")
        expiry_date = parts[1] if len(parts) >= 2 else ""

        oi = _safe_float(opt.get("open_interest") or opt.get("openInterest", 0))
        if min_oi > 0 and oi < min_oi:
            continue

        chain.append(
            OptionsChainData(
                symbol=symbol,
                underlying_symbol=base_coin,
                strike=_safe_float(opt.get("strike")),
                expiry_date=expiry_date,
                option_type=option_type,
                underlying_price=spot,
                mark_price=_safe_float(
                    opt.get("mark_price") or opt.get("markPrice", 0)
                ),
                mark_iv=_safe_float(opt.get("mark_iv") or opt.get("markIv", 0)),
                delta=_safe_float(opt.get("delta", 0)),
                gamma=_safe_float(opt.get("gamma", 0)),
                theta=_safe_float(opt.get("theta", 0)),
                vega=_safe_float(opt.get("vega", 0)),
                volume=_safe_float(opt.get("volume_24h") or opt.get("volume24h", 0)),
                open_interest=oi,
                bid_price=_safe_float(opt.get("bid_price") or opt.get("bid1Price", 0)),
                ask_price=_safe_float(opt.get("ask_price") or opt.get("ask1Price", 0)),
                bid_iv=_safe_float(opt.get("bid_iv") or opt.get("bidIv", 0)),
                ask_iv=_safe_float(opt.get("ask_iv") or opt.get("askIv", 0)),
            )
        )

    return chain, spot


def _fetch_klines(symbol: str, interval: str = "4h", hours_back: int = 720) -> list:
    """Fetch kline data from Bybit for RV calculation."""
    from bybit_api import BybitPublicClient

    async def _do():
        client = BybitPublicClient()
        from datetime import timedelta

        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours_back)
        raw = await client.get_klines(
            symbol, interval, limit=200, start_time=start, end_time=end
        )
        return raw

    return asyncio.run(_do())


def cmd_iv_rv(args):
    """IV-RV spread analysis: ATM implied vol vs Garman-Klass realized vol."""
    from .strategy.covered_call import CoveredCallAnalyzer

    chain, spot = _fetch_chain(args.base_coin)
    if not chain:
        _output(False, error=f"No options data for {args.base_coin}")
        return

    klines = _fetch_klines(
        f"{args.base_coin}USDT", interval="4h", hours_back=args.rv_window * 24
    )
    if not klines:
        _output(False, error=f"No kline data for {args.base_coin}USDT")
        return

    iv_rv = CoveredCallAnalyzer.compute_iv_rv_spread(
        chain, spot, klines, asset=args.base_coin, rv_window=args.rv_window * 6
    )

    _output(
        True,
        {
            "asset": iv_rv.asset,
            "atm_iv_pct": round(iv_rv.atm_iv * 100, 2),
            "realized_vol_pct": round(iv_rv.realized_vol * 100, 2),
            "spread_vol_pts": round(iv_rv.spread, 2),
            "spread_ratio": round(iv_rv.spread_ratio, 2),
            "rv_estimator": iv_rv.rv_estimator,
            "rv_window_days": args.rv_window,
            "signal": "SELL_VOL"
            if iv_rv.spread > 10
            else "HOLD"
            if iv_rv.spread > 5
            else "NO_EDGE",
            "spot_price": spot,
        },
    )


def cmd_strike_select(args):
    """Select and rank OTM call strikes for covered call writing."""
    from .strategy.covered_call import CoveredCallAnalyzer

    chain, spot = _fetch_chain(args.base_coin)
    if not chain:
        _output(False, error=f"No options data for {args.base_coin}")
        return

    candidates = CoveredCallAnalyzer.select_strikes(
        chain,
        spot,
        target_delta=args.target_delta,
        delta_range=(args.min_delta, args.max_delta),
        min_dte=args.min_dte,
        max_dte=args.max_dte,
        min_oi=args.min_oi,
    )

    if not candidates:
        _output(True, {"candidates": [], "message": "No strikes match filters"})
        return

    _output(
        True,
        {
            "asset": args.base_coin,
            "spot_price": spot,
            "target_delta": args.target_delta,
            "candidates": [
                {
                    "symbol": c.symbol,
                    "strike": c.strike,
                    "expiry": c.expiry_date,
                    "delta": round(c.delta, 4),
                    "mark_iv_pct": round(c.mark_iv * 100, 2),
                    "premium_usd": round(c.mid_price, 4),
                    "premium_pct": round(c.premium_pct * 100, 3),
                    "otm_pct": round(c.otm_pct * 100, 2),
                    "bid_ask_spread_pct": round(c.spread_pct * 100, 2),
                    "open_interest": c.open_interest,
                    "volume": c.volume,
                    "score": round(c.score, 4),
                }
                for c in candidates[:10]
            ],
        },
    )


def cmd_cc_signal(args):
    """Covered call signal: go/no-go with IV-RV, regime, skew, and strike selection."""
    from .strategy.covered_call import CoveredCallAnalyzer

    chain, spot = _fetch_chain(args.base_coin)
    if not chain:
        _output(False, error=f"No options data for {args.base_coin}")
        return

    klines = _fetch_klines(f"{args.base_coin}USDT", interval="4h", hours_back=30 * 24)
    if not klines:
        _output(False, error=f"No kline data for {args.base_coin}USDT")
        return

    signal = CoveredCallAnalyzer.evaluate_signal(
        chain,
        spot,
        klines,
        asset=args.base_coin,
        iv_rv_threshold=args.iv_rv_threshold,
        target_delta=args.target_delta,
        max_dte=args.max_dte,
    )

    _output(True, CoveredCallAnalyzer.format_signal_summary(signal))


def cmd_gex(args):
    """Gamma exposure analysis: dealer hedging walls, vol suppression, flip level."""
    from .flow import GammaExposure

    chain, spot = _fetch_chain(args.base_coin, args.min_oi)
    if not chain:
        _output(False, error=f"No options data for {args.base_coin}")
        return

    gex_levels = GammaExposure.calculate_gex_by_strike(chain)
    analysis = GammaExposure.analyze_gex_impact(
        gex_levels, spot, base_coin=args.base_coin
    )
    summary = GammaExposure.get_compact_gex_summary(analysis)

    _output(
        True,
        {
            "base_coin": args.base_coin,
            "spot_price": spot,
            "contracts": len(chain),
            "summary": summary,
        },
    )


def cmd_vanna(args):
    """Vanna exposure: flow prediction from vol changes, squeeze detection."""
    from .flow import VannaAnalyzer

    chain, spot = _fetch_chain(args.base_coin, args.min_oi)
    if not chain:
        _output(False, error=f"No options data for {args.base_coin}")
        return

    vanna_data = VannaAnalyzer.calculate_vanna_by_strike(chain)
    analysis = VannaAnalyzer.analyze_vanna_impact(vanna_data, spot)
    summary = VannaAnalyzer.get_compact_vanna_summary(analysis)

    _output(
        True,
        {
            "base_coin": args.base_coin,
            "spot_price": spot,
            "contracts": len(chain),
            "summary": summary,
        },
    )


def cmd_flow(args):
    """Options flow: delta imbalance, volume analysis, unusual activity."""
    from .flow import OptionsFlow

    chain, spot = _fetch_chain(args.base_coin, args.min_oi)
    if not chain:
        _output(False, error=f"No options data for {args.base_coin}")
        return

    delta_imb = OptionsFlow.calculate_delta_imbalance(chain, spot)
    flow_metrics = OptionsFlow.analyze_volume_imbalance(chain)
    unusual = OptionsFlow.detect_unusual_activity(chain)
    summary = OptionsFlow.get_compact_flow_summary(delta_imb, flow_metrics, unusual)

    _output(
        True,
        {
            "base_coin": args.base_coin,
            "spot_price": spot,
            "contracts": len(chain),
            "summary": summary,
        },
    )


def cmd_skew(args):
    """Volatility skew and term structure analysis."""
    from .flow import SkewAnalysis

    chain, spot = _fetch_chain(args.base_coin)
    if not chain:
        _output(False, error=f"No options data for {args.base_coin}")
        return

    term = SkewAnalysis.analyze_term_structure(
        chain,
        underlying_price=spot,
        base_coin=args.base_coin,
    )
    summary = SkewAnalysis.get_compact_skew_summary(term)
    skew_by_expiry = [
        {
            "expiry_date": exp.expiry_date,
            "put_call_skew_pct": round(exp.put_call_skew * 100, 2),
            "risk_reversal_skew_pct": round(exp.risk_reversal_skew * 100, 2),
            "atm_iv_pct": round(exp.atm_iv * 100, 2),
            "iv_slope": round(exp.iv_slope, 6),
            "skew_direction": exp.skew_direction,
            "skew_extremeness": round(exp.skew_extremeness, 1),
        }
        for exp in term.expiry_analysis
    ]

    _output(
        True,
        {
            "base_coin": args.base_coin,
            "spot_price": spot,
            "contracts": len(chain),
            "summary": summary,
            "term_structure": {
                "front_month_iv_pct": round(term.front_month_iv * 100, 2),
                "back_month_iv_pct": round(term.back_month_iv * 100, 2),
                "term_structure_slope_pct": round(term.term_structure_slope * 100, 2),
                "calendar_opportunities": term.calendar_spread_opportunities,
                "expiries_analyzed": len(term.expiry_analysis),
            },
            "skew_by_expiry": skew_by_expiry,
        },
    )


def cmd_price(args):
    """Price a single option with Black-Scholes."""
    from .pricing import ProfessionalOptionsEngine, OptionSpec

    # Parse symbol or use explicit args
    engine = ProfessionalOptionsEngine(risk_free_rate=0.05)

    spec = OptionSpec(
        symbol=args.symbol,
        underlying_price=args.underlying,
        strike=args.strike,
        expiration_date=datetime.strptime(args.expiry, "%Y-%m-%d"),
        option_type="call" if args.type.upper() == "C" else "put",
        implied_volatility=args.iv,
    )

    result = engine.calculate_greeks(spec)
    _output(
        True,
        {
            "symbol": args.symbol,
            "underlying": args.underlying,
            "strike": args.strike,
            "type": args.type.upper(),
            "expiry": args.expiry,
            "iv": args.iv,
            "greeks": {
                "price": round(result.price, 4),
                "delta": round(result.delta, 4),
                "gamma": round(result.gamma, 6),
                "theta": round(result.theta, 4),
                "vega": round(result.vega, 4),
            },
        },
    )


def cmd_portfolio(args):
    """Compute portfolio Greeks from Bybit option positions."""
    from .portfolio_greeks import compute_options_portfolio_greeks
    from dataclasses import asdict

    async def _do():
        from dotenv import load_dotenv

        load_dotenv()
        from bybit_api import BybitClient

        client = BybitClient.from_env()

        all_positions = []
        for coin in args.base_coin:
            positions = await client.get_positions("option", base_coin=coin)
            # Enrich with Greeks from tickers
            tickers = await client.get_options_tickers(coin)
            ticker_map = {t["symbol"]: t for t in tickers}

            for pos in positions:
                ticker = ticker_map.get(pos.symbol, {})
                all_positions.append(
                    {
                        "symbol": pos.symbol,
                        "side": pos.side,
                        "size": pos.size,
                        "strike": float(pos.symbol.split("-")[2])
                        if len(pos.symbol.split("-")) >= 3
                        else 0,
                        "delta": float(ticker.get("delta", 0)),
                        "gamma": float(ticker.get("gamma", 0)),
                        "theta": float(ticker.get("theta", 0)),
                        "vega": float(ticker.get("vega", 0)),
                        "mark_iv": float(ticker.get("markIv", 0)),
                        "mark_price": float(ticker.get("markPrice", 0)),
                        "underlying_price": float(ticker.get("underlyingPrice", 0)),
                    }
                )

        return all_positions

    try:
        loop = asyncio.new_event_loop()
        all_positions = loop.run_until_complete(_do())
    finally:
        loop.close()

    result = compute_options_portfolio_greeks(all_positions)
    out = {
        "positions": [asdict(p) for p in result.positions],
        "net_delta": result.net_delta,
        "net_gamma": result.net_gamma,
        "net_theta": result.net_theta,
        "net_vega": result.net_vega,
    }
    _output(True, out)


def main():
    parser = argparse.ArgumentParser(
        description="Options Analysis CLI",
        prog="python -m options_lib",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # gex
    p = sub.add_parser("gex", help="Gamma exposure by strike")
    p.add_argument("base_coin", help="BTC, ETH, or SOL")
    p.add_argument(
        "--min-oi", type=float, default=1.0, help="Min OI filter (default: 1)"
    )

    # vanna
    p = sub.add_parser("vanna", help="Vanna exposure analysis")
    p.add_argument("base_coin")
    p.add_argument("--min-oi", type=float, default=1.0)

    # flow
    p = sub.add_parser("flow", help="Options flow: delta imbalance, unusual activity")
    p.add_argument("base_coin")
    p.add_argument("--min-oi", type=float, default=1.0)

    # skew
    p = sub.add_parser("skew", help="Volatility skew + term structure")
    p.add_argument("base_coin")

    # price
    p = sub.add_parser("price", help="Price single option (Black-Scholes)")
    p.add_argument("symbol", help="e.g. BTC-28MAR26-100000-C")
    p.add_argument("--underlying", type=float, required=True, help="Underlying price")
    p.add_argument("--strike", type=float, required=True, help="Strike price")
    p.add_argument("--type", required=True, choices=["C", "P"], help="Call or Put")
    p.add_argument("--expiry", required=True, help="Expiry date YYYY-MM-DD")
    p.add_argument(
        "--iv", type=float, required=True, help="Implied volatility (decimal)"
    )

    p = sub.add_parser("portfolio", help="Portfolio Greeks from Bybit positions")
    p.add_argument(
        "--base-coin",
        nargs="+",
        default=["BTC", "ETH"],
        help="Base coins (default: BTC ETH)",
    )

    # iv-rv
    p = sub.add_parser(
        "iv-rv", help="IV-RV spread analysis (ATM IV vs Garman-Klass RV)"
    )
    p.add_argument("base_coin", help="BTC, ETH, or SOL")
    p.add_argument(
        "--rv-window", type=int, default=30, help="RV lookback in days (default: 30)"
    )

    # strike-select
    p = sub.add_parser("strike-select", help="Select OTM call strikes for covered call")
    p.add_argument("base_coin", help="BTC, ETH, or SOL")
    p.add_argument(
        "--target-delta", type=float, default=0.10, help="Target delta (default: 0.10)"
    )
    p.add_argument(
        "--min-delta", type=float, default=0.05, help="Min delta (default: 0.05)"
    )
    p.add_argument(
        "--max-delta", type=float, default=0.20, help="Max delta (default: 0.20)"
    )
    p.add_argument(
        "--min-dte", type=int, default=3, help="Min days to expiry (default: 3)"
    )
    p.add_argument(
        "--max-dte", type=int, default=14, help="Max days to expiry (default: 14)"
    )
    p.add_argument(
        "--min-oi", type=float, default=5.0, help="Min open interest (default: 5)"
    )

    # cc-signal
    p = sub.add_parser(
        "cc-signal", help="Covered call signal: go/no-go with full analysis"
    )
    p.add_argument("base_coin", help="BTC, ETH, or SOL")
    p.add_argument(
        "--iv-rv-threshold",
        type=float,
        default=10.0,
        help="Min IV-RV spread in vol pts (default: 10)",
    )
    p.add_argument(
        "--target-delta",
        type=float,
        default=0.10,
        help="Target call delta (default: 0.10)",
    )
    p.add_argument(
        "--max-dte", type=int, default=14, help="Max days to expiry (default: 14)"
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    commands = {
        "gex": cmd_gex,
        "vanna": cmd_vanna,
        "flow": cmd_flow,
        "skew": cmd_skew,
        "price": cmd_price,
        "portfolio": cmd_portfolio,
        "iv-rv": cmd_iv_rv,
        "strike-select": cmd_strike_select,
        "cc-signal": cmd_cc_signal,
    }

    try:
        commands[args.command](args)
    except Exception as e:
        _output(False, error=str(e))
        sys.exit(1)
