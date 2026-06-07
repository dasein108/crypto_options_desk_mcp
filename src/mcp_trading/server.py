"""
MCP Server for Quantitative Options Trading
"""

import logging
from datetime import datetime
from typing import Dict, List, Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .orchestrator import get_orchestrator, _format_position

logger = logging.getLogger(__name__)

mcp = FastMCP("Quant Trading Server")
orchestrator = get_orchestrator()


# ── Param models ──


class OptionsAnalysisParams(BaseModel):
    base_coin: str = Field(
        default="BTC", description="Base cryptocurrency (BTC, ETH, SOL)"
    )
    min_oi: float = Field(default=1.0, description="Minimum open interest filter")


class TechnicalParams(BaseModel):
    symbol: str = Field(description="Trading symbol (e.g., BTCUSDT)")
    interval: str = Field(default="1h", description="Timeframe (1m, 5m, 1h, 4h, 1d)")
    hours_back: int = Field(default=30 * 24, description="Hours of history")


class VannaParams(BaseModel):
    base_coin: str = Field(default="BTC", description="Base cryptocurrency")
    price_move: float = Field(default=0.05, description="Price move % for analysis")


class VolSurfaceParams(BaseModel):
    base_coin: str = Field(default="BTC", description="Base cryptocurrency")


class PortfolioParams(BaseModel):
    portfolio_data: Dict[str, Any] = Field(description="Portfolio positions data")


class ScenarioParams(BaseModel):
    portfolio_data: Dict[str, Any] = Field(description="Portfolio positions data")
    scenarios: List[Dict[str, Any]] = Field(description="Price/vol scenarios to test")


class SymbolParams(BaseModel):
    symbol: str = Field(default="BTCUSDT", description="Trading symbol")


class UserPositionsParams(BaseModel):
    base_coin: str = Field(default="BTC", description="Base crypto or 'all'")
    position_type: str = Field(
        default="option", description="option, linear, inverse, or all"
    )


class MarketDataParams(BaseModel):
    symbol: str = Field(description="Trading symbol (e.g., BTCUSDT)")
    interval: str = Field(default="1h", description="Timeframe")
    hours_back: int = Field(default=30 * 24, description="Hours of history")


class StrategyParams(BaseModel):
    base_coin: str = Field(default="BTC", description="Base cryptocurrency")
    min_oi: float = Field(default=10.0, description="Minimum open interest")
    spread_types: List[str] = Field(
        default=["call_spread", "put_spread"], description="Spread types"
    )


class PortfolioStrategyParams(BaseModel):
    portfolio_positions: Dict[str, Any] = Field(description="Portfolio positions data")


class IVRVSpreadParams(BaseModel):
    base_coin: str = Field(
        default="BTC", description="Base cryptocurrency (BTC, ETH, SOL)"
    )
    rv_window: int = Field(default=30, description="Realized vol lookback in days")


class CoveredCallSignalParams(BaseModel):
    base_coin: str = Field(
        default="BTC", description="Base cryptocurrency (BTC, ETH, SOL)"
    )
    target_delta: float = Field(
        default=0.10, description="Target call delta (0.05-0.20)"
    )
    iv_rv_threshold: float = Field(
        default=10.0, description="Min IV-RV spread in vol points to trigger signal"
    )
    max_dte: int = Field(
        default=14, description="Max days to expiry for strike selection"
    )


# ── Options flow tools ──


@mcp.tool(description="Analyze Gamma Exposure (GEX) levels and market impact")
async def get_gex_analysis(params: OptionsAnalysisParams) -> Dict[str, Any]:
    return await orchestrator.get_gex_analysis(params.base_coin, params.min_oi)


@mcp.tool(description="Analyze Vanna exposure and volatility impact from price moves")
async def get_vanna_analysis(params: VannaParams) -> Dict[str, Any]:
    return await orchestrator.get_vanna_analysis(params.base_coin, params.price_move)


@mcp.tool(
    description="Analyze options flow including volume, put/call ratios, and unusual activity"
)
async def get_flow_analysis(params: OptionsAnalysisParams) -> Dict[str, Any]:
    return await orchestrator.get_flow_analysis(params.base_coin)


@mcp.tool(
    description="Analyze volatility skew and term structure across strikes and expiries"
)
async def get_skew_analysis(params: OptionsAnalysisParams) -> Dict[str, Any]:
    return await orchestrator.get_skew_analysis(params.base_coin)


@mcp.tool(description="Get volatility surface diagnostics (RR, skew, vol-of-vol, VRP)")
async def get_vol_surface_metrics(params: VolSurfaceParams) -> Dict[str, Any]:
    return await orchestrator.get_vol_surface_metrics(params.base_coin)


# ── Technical analysis ──


@mcp.tool(
    description="Calculate technical indicators (RSI, MACD, ATR, Bollinger Bands)"
)
async def get_technical_indicators(params: TechnicalParams) -> Dict[str, Any]:
    return await orchestrator.get_technical_indicators(
        params.symbol, params.interval, params.hours_back
    )


# ── Portfolio analysis ──


@mcp.tool(description="Analyze portfolio Greeks and risk metrics for options positions")
async def analyze_portfolio_greeks(params: PortfolioParams) -> Dict[str, Any]:
    return await orchestrator.analyze_portfolio_greeks(params.portfolio_data)


@mcp.tool(
    description="Run scenario analysis for portfolio PnL across price and volatility moves"
)
async def run_scenario_analysis(params: ScenarioParams) -> Dict[str, Any]:
    return await orchestrator.run_scenario_analysis(
        params.portfolio_data, params.scenarios
    )


# ── Market data ──


@mcp.tool(description="Get historical price data with basic metrics")
async def get_historical_data(params: MarketDataParams) -> Dict[str, Any]:
    try:
        klines = await orchestrator.api.get_klines(
            params.symbol, params.interval, hours_back=params.hours_back
        )
        if not klines:
            return {"success": False, "error": f"No data for {params.symbol}"}
        return {
            "success": True,
            "symbol": params.symbol,
            "interval": params.interval,
            "data_points": len(klines),
            "latest_price": klines[-1].close if klines else 0,
            "timestamp": klines[-1].timestamp_int if klines else 0,
            "klines": [
                {
                    "timestamp": k.timestamp_int,
                    "open": k.open,
                    "high": k.high,
                    "low": k.low,
                    "close": k.close,
                    "volume": k.volume,
                }
                for k in klines[-10:]
            ],
        }
    except Exception as e:
        logger.error(f"Historical data error: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool(description="Get current options chain data")
async def get_options_chain(params: OptionsAnalysisParams) -> Dict[str, Any]:
    try:
        chain_data = await orchestrator.api.get_options_chain_data(params.base_coin)
        if not chain_data:
            return {
                "success": False,
                "error": f"No options data for {params.base_coin}",
            }
        filtered = [o for o in chain_data if o.get("open_interest", 0) >= params.min_oi]
        return {
            "success": True,
            "symbol": params.base_coin,
            "total_options": len(chain_data),
            "filtered_options": len(filtered),
            "min_oi_filter": params.min_oi,
            "sample_data": filtered[:5],
        }
    except Exception as e:
        logger.error(f"Options chain error: {e}")
        return {"success": False, "error": str(e)}


# ── Sentiment ──


@mcp.tool(
    description="Get comprehensive market sentiment analysis including long-short ratios"
)
async def get_market_sentiment_analysis(params: SymbolParams) -> Dict[str, Any]:
    return await orchestrator.get_market_sentiment_analysis(params.symbol)


@mcp.tool(description="Get open interest analysis and trends")
async def get_open_interest_analysis(params: SymbolParams) -> Dict[str, Any]:
    return await orchestrator.get_open_interest_analysis(params.symbol)


@mcp.tool(description="Get funding rate analysis and extremes")
async def get_funding_rate_analysis(params: SymbolParams) -> Dict[str, Any]:
    return await orchestrator.get_funding_rate_analysis(params.symbol)


# ── User positions ──


async def _fetch_positions_for_category(
    category: str, base_coin: str
) -> Dict[str, Any]:
    """Fetch and format positions for one category.

    Per-category Bybit requirements:
    - `option`:  requires `base_coin` (one of BTC/ETH/SOL). When the caller
      passes "all" we iterate over the supported base coins and aggregate.
    - `linear`/`inverse`: require either a `symbol` or a `settleCoin`. We
      default to `USDT` (linear) / `BTC` (inverse) when the caller doesn't
      narrow the query.
    """
    try:
        positions = []
        is_all = base_coin.lower() == "all"
        if category == "option":
            if is_all:
                for bc in ("BTC", "ETH", "SOL"):
                    try:
                        positions.extend(
                            await orchestrator.api.get_positions(
                                category="option", base_coin=bc,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"Error fetching option/{bc}: {e}")
            else:
                positions = await orchestrator.api.get_positions(
                    category="option", base_coin=base_coin,
                )
        else:
            # linear/inverse — Bybit requires symbol or settleCoin. base_coin
            # is not a valid filter for these categories, so we always query
            # by settleCoin (USDT for linear, BTC for inverse) and aggregate
            # all positions. Users who want a specific symbol should use
            # the Bybit CLI directly.
            settle = "USDT" if category == "linear" else "BTC"
            positions = await orchestrator.api.get_positions(
                category=category,
                settle_coin=settle,
            )

        formatted = [_format_position(p) for p in positions]
        pnl = sum(float(p.unrealised_pnl or 0) for p in positions)
        return {"count": len(formatted), "unrealised_pnl": pnl, "positions": formatted}
    except Exception as e:
        logger.warning(f"Error fetching {category} positions: {e}")
        return {"count": 0, "error": str(e), "positions": []}


@mcp.tool(
    description="Get user's options positions from Bybit for any asset (BTC, ETH, SOL)"
)
async def get_user_options_positions(params: UserPositionsParams) -> Dict[str, Any]:
    try:
        result = await _fetch_positions_for_category("option", params.base_coin)
        # Surface the real fetch error (e.g. auth/missing API key) instead of
        # masking it with a KeyError on the absent 'unrealised_pnl' field.
        if result.get("error"):
            return {
                "success": False,
                "error": result["error"],
                "base_coin": params.base_coin,
                "category": "option",
                "hint": "auth errors usually mean BYBIT_API_KEY / BYBIT_API_SECRET are unset",
            }
        return {
            "success": True,
            "base_coin": params.base_coin,
            "category": "option",
            "total_positions": result["count"],
            "total_unrealised_pnl": result.get("unrealised_pnl", 0.0),
            "positions": result["positions"],
        }
    except Exception as e:
        logger.error(f"Error fetching options positions: {e}")
        return {"success": False, "error": str(e), "base_coin": params.base_coin}


@mcp.tool(description="Get all user positions from Bybit (options, linear, inverse)")
async def get_user_all_positions(params: UserPositionsParams) -> Dict[str, Any]:
    try:
        categories = (
            ["option", "linear", "inverse"]
            if params.position_type == "all"
            else [params.position_type]
        )
        details = {}
        total_pnl = 0.0
        total_count = 0

        for cat in categories:
            result = await _fetch_positions_for_category(cat, params.base_coin)
            details[cat] = result
            total_pnl += result.get("unrealised_pnl", 0)
            total_count += result["count"]

        return {
            "success": True,
            "base_coin": params.base_coin,
            "position_type": params.position_type,
            "summary": {
                "total_positions": total_count,
                "total_unrealised_pnl": total_pnl,
                "categories_fetched": categories,
            },
            "details": details,
        }
    except Exception as e:
        logger.error(f"Error fetching all positions: {e}")
        return {"success": False, "error": str(e)}


# ── Covered call ──


@mcp.tool(
    description="Compute IV-RV spread (ATM implied vol vs Garman-Klass realized vol) — key metric for vol-selling strategies"
)
async def get_iv_rv_spread(params: IVRVSpreadParams) -> Dict[str, Any]:
    return await orchestrator.get_iv_rv_spread(params.base_coin, params.rv_window)


@mcp.tool(
    description="Evaluate covered call entry signal: go/no-go with IV-RV spread, vol regime, term structure, skew check, and recommended OTM strike"
)
async def get_covered_call_signal(params: CoveredCallSignalParams) -> Dict[str, Any]:
    return await orchestrator.get_covered_call_signal(
        params.base_coin,
        params.target_delta,
        params.iv_rv_threshold,
        params.max_dte,
    )


# ── Strategy analysis ──


@mcp.tool(description="Comprehensive straddle analysis with profitability ranking")
async def analyze_straddles(params: StrategyParams) -> Dict[str, Any]:
    return await orchestrator.analyze_strategy(
        params.base_coin, "straddle", params.min_oi
    )


@mcp.tool(description="Comprehensive strangle analysis with optimization")
async def analyze_strangles(params: StrategyParams) -> Dict[str, Any]:
    return await orchestrator.analyze_strategy(
        params.base_coin, "strangle", params.min_oi
    )


@mcp.tool(description="Vertical spread analysis (call and put spreads)")
async def analyze_spreads(params: StrategyParams) -> Dict[str, Any]:
    return await orchestrator.analyze_strategy(
        params.base_coin, "spread", params.min_oi, spread_types=params.spread_types
    )


@mcp.tool(description="Identify and analyze existing option strategies in portfolio")
async def analyze_portfolio_strategies(
    params: PortfolioStrategyParams,
) -> Dict[str, Any]:
    try:
        from options_lib.strategy import StrategyClassifier

        classifier = StrategyClassifier()
        strategies = classifier.classify_portfolio(params.portfolio_positions)
        return {
            "success": True,
            "analysis_type": "portfolio_strategy_analysis",
            "timestamp": datetime.now().isoformat(),
            "strategies_identified": len(strategies),
            "strategies": [
                {
                    "strategy_type": s.strategy_type.value,
                    "legs": [
                        {
                            "symbol": leg.symbol,
                            "strike": leg.strike,
                            "expiry": leg.expiry,
                            "option_type": leg.option_type,
                            "side": leg.side,
                            "quantity": leg.quantity,
                            "current_price": leg.current_price,
                            "delta": leg.delta,
                            "theta": leg.theta,
                        }
                        for leg in s.legs
                    ],
                    "confidence": s.confidence,
                    "description": s.description,
                    "net_cost": s.net_cost,
                    "breakeven_points": s.breakeven_points,
                }
                for s in strategies
            ],
        }
    except Exception as e:
        logger.error(f"Portfolio strategy analysis error: {e}")
        return {"success": False, "error": str(e)}


# ── Server info ──


@mcp.tool(description="Get server information and available tools")
async def get_server_info() -> Dict[str, Any]:
    return {
        "server_name": "Quant Trading Server",
        "version": "2.1.0",
        "tools_count": 22,
        "categories": [
            "Options Flow (GEX, Vanna, Flow, Skew, Vol Surface)",
            "Technical Analysis",
            "Portfolio (Greeks, Scenarios)",
            "Market Data (Klines, Options Chain)",
            "Sentiment (Long/Short, OI, Funding)",
            "User Positions",
            "Covered Call (IV-RV Spread, Signal)",
            "Strategy Analysis (Straddles, Strangles, Spreads)",
        ],
    }


# ── Prompts ──


@mcp.prompt(
    description="Senior quant options/futures research workflow for a given crypto asset."
)
def quant_research_prompt(asset: str) -> List[Dict[str, Any]]:
    symbol = f"{asset.upper()}USDT"
    content = (
        "You are a senior quant researcher and options/futures trader at a small algorithmic hedge fund "
        "focused exclusively on crypto derivatives. Produce a professional, data-driven market memo for "
        f"{asset.upper()} (spot symbol {symbol}).\n\n"
        "Objectives:\n"
        "1) Fetch the full options market context and relevant technical indicators.\n"
        "2) Quantify market state: volatility regime, skew/term structure, flow, and key levels.\n"
        "3) Propose low-risk, high-probability options/futures strategies with clear risk controls.\n\n"
        "Use the available tools (call them, do not hallucinate data):\n"
        "- get_options_chain (availability + sample visibility)\n"
        "- get_gex_analysis (gamma exposure and key levels)\n"
        "- get_vanna_analysis (vanna impact from price moves; units provided)\n"
        "- get_flow_analysis (flow/volume imbalance and unusual activity)\n"
        "- get_skew_analysis (term structure and skew diagnostics)\n"
        "- get_vol_surface_metrics (25d RR, 10d skew, vol-of-vol, VRP)\n"
        "- get_technical_indicators (EMA stack, Z-score, trend persistence, ADX, Hurst, plus RSI/MACD/ATR/Bollinger)\n"
        "- get_market_sentiment_analysis (positioning bias via long-short ratios, sentiment extremes)\n"
        "- get_open_interest_analysis (market engagement, liquidity depth, participation trends)\n"
        "- get_funding_rate_analysis (carry costs, funding extremes, market stress indicators)\n"
        "- get_historical_data (recent price/vol context; choose interval as needed)\n"
        "- get_iv_rv_spread (IV vs realized vol spread — vol-selling edge assessment)\n"
        "- get_covered_call_signal (covered call go/no-go with strike recommendation)\n\n"
        "Analysis requirements:\n"
        "- Identify regime: trending vs mean-reverting, vol expanding vs contracting.\n"
        "- Assess positioning extremes and contrarian opportunities via sentiment analysis.\n"
        "- Evaluate funding conditions and carry trade potential.\n"
        "- Monitor market engagement through open interest trends.\n"
        "- Highlight actionable price levels and expected volatility behavior.\n"
        "- Explain how gamma/vanna/flow/skew shape hedging pressure and likely path.\n"
        "- Propose 2-3 strategies with entry, sizing logic, hedge triggers, and invalidation.\n"
        "- Include risk notes: liquidity, tail risk, positioning crowding, and event-driven risk.\n\n"
        "Output format:\n"
        "A) Market Snapshot (price, trend, vol regime, key levels)\n"
        "B) Sentiment & Flow Analysis (positioning, OI trends, funding, contrarian signals)\n"
        "C) Options Microstructure (GEX, Vanna, Flow, Skew)\n"
        "D) Strategy Proposals (2-3 ideas with rationale + risk controls)\n"
        "E) Risk Checklist (liquidity, crowding, funding extremes, tail risks)\n"
    )
    return [{"role": "user", "content": content}]


# ── Main ──

if __name__ == "__main__":
    mcp.run()
