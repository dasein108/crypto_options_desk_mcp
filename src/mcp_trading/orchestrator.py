"""
MCP Services Orchestrator — delegates tool requests to existing business logic.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, UTC
import logging

from options_lib.flow.gex import GammaExposure
from options_lib.flow.vanna import VannaAnalyzer
from options_lib.flow.flow import OptionsFlow
from options_lib.flow.skew import SkewAnalysis
from options_lib.flow.types import OptionsFlowConfig, OptionsChainData, OptionType

from indicators_lib import TechnicalIndicators, IndicatorConfig
from indicators_lib.sentiment import SentimentAnalyzer
from .volatility_analyzer import VolatilityAnalyzer
from bybit_api import BybitClient
from portfolio_lib import PortfolioEngine, PortfolioAnalyzer

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_position(pos) -> Dict[str, Any]:
    """Convert a Position object to a serializable dict."""
    return {
        "symbol": pos.symbol,
        "side": pos.side,
        "size": pos.size,
        "avg_price": pos.avg_price,
        "mark_price": pos.mark_price,
        "unrealised_pnl": pos.unrealised_pnl,
        "leverage": pos.leverage,
        "position_value": pos.position_value,
        "category": pos.category,
        "exchange": pos.exchange,
    }


def _error_response(error_msg: str, context: str) -> Dict[str, Any]:
    return {
        "success": False,
        "error": error_msg,
        "context": context,
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }


def _success_response(analysis_type: str, data: Any, **extra) -> Dict[str, Any]:
    result = {
        "success": True,
        "analysis_type": analysis_type,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "data": data,
    }
    result.update(extra)
    return result


class MCPOrchestrator:
    """Orchestrates MCP tool requests by delegating to existing business logic."""

    def __init__(self):
        self.api = BybitClient.from_env(use_cache=True)
        self.gex_analyzer = GammaExposure()
        self.vanna_analyzer = VannaAnalyzer()
        self.flow_analyzer = OptionsFlow()
        self.skew_analyzer = SkewAnalysis()
        self.technical = TechnicalIndicators()
        self.sentiment_analyzer = SentimentAnalyzer(self.api)
        self.volatility_analyzer = VolatilityAnalyzer(self.api)
        self.portfolio_engine = PortfolioEngine()
        self.portfolio_analyzer = PortfolioAnalyzer(self.portfolio_engine)

        self.flow_config = OptionsFlowConfig(
            volume_threshold=3.0,
            oi_change_threshold=0.5,
        )

    # ── Helpers ──

    def _convert_chain_data(
        self, options_data: List[Dict[str, Any]], base_coin: str
    ) -> List[OptionsChainData]:
        """Convert raw API options data into OptionsChainData objects."""
        chain_data: List[OptionsChainData] = []
        for opt in options_data:
            try:
                symbol = opt.get("symbol", "")
                if not symbol:
                    continue

                expiry_date = opt.get("expiry_date", "")
                if not expiry_date:
                    parts = symbol.split("-")
                    if len(parts) >= 2:
                        expiry_date = parts[1]

                option_type_str = str(opt.get("option_type", ""))
                if option_type_str in ("Call", "C", "CALL"):
                    option_type = OptionType.CALL
                elif option_type_str in ("Put", "P", "PUT"):
                    option_type = OptionType.PUT
                elif symbol.endswith("-C"):
                    option_type = OptionType.CALL
                elif symbol.endswith("-P"):
                    option_type = OptionType.PUT
                else:
                    continue

                chain_data.append(
                    OptionsChainData(
                        symbol=symbol,
                        underlying_symbol=base_coin,
                        strike=_safe_float(opt.get("strike")),
                        expiry_date=expiry_date,
                        option_type=option_type,
                        underlying_price=_safe_float(opt.get("underlying_price")),
                        mark_price=_safe_float(opt.get("mark_price")),
                        mark_iv=_safe_float(opt.get("mark_iv")),
                        delta=_safe_float(opt.get("delta")),
                        gamma=_safe_float(opt.get("gamma")),
                        theta=_safe_float(opt.get("theta")),
                        vega=_safe_float(opt.get("vega")),
                        volume=_safe_float(opt.get("volume_24h")),
                        open_interest=_safe_float(opt.get("open_interest")),
                        bid_price=_safe_float(opt.get("bid_price")),
                        ask_price=_safe_float(opt.get("ask_price")),
                        bid_iv=_safe_float(opt.get("bid_iv")),
                        ask_iv=_safe_float(opt.get("ask_iv")),
                    )
                )
            except Exception as exc:
                logger.debug(f"Skipping invalid options record: {exc}")
        return chain_data

    async def _get_chain_and_price(self, base_coin: str, context: str):
        """Fetch options chain + underlying price. Returns (chain_data, price) or raises."""
        raw = await self.api.get_options_chain_data(base_coin)
        chain_data = self._convert_chain_data(raw, base_coin) if raw else []
        if not chain_data:
            return (
                None,
                None,
                _error_response(f"No options data for {base_coin}", context),
            )

        price = await self.api.get_asset_price(f"{base_coin}USDT")
        if not price:
            return (
                None,
                None,
                _error_response(f"No price data for {base_coin}", context),
            )

        return chain_data, price, None

    # ── Options flow analysis ──

    async def get_gex_analysis(
        self, base_coin: str, min_oi: float = 1.0
    ) -> Dict[str, Any]:
        try:
            chain_data, price, err = await self._get_chain_and_price(
                base_coin, "gex_analysis"
            )
            if err:
                return err
            gex_levels = self.gex_analyzer.calculate_gex_by_strike(chain_data)
            gex_result = self.gex_analyzer.analyze_gex_impact(
                gex_levels, price, self.flow_config
            )
            return _success_response(
                "gamma_exposure",
                self.gex_analyzer.get_compact_gex_summary(gex_result),
                symbol=base_coin,
            )
        except Exception as e:
            logger.error(f"GEX analysis error for {base_coin}: {e}")
            return _error_response(str(e), "gex_analysis")

    async def get_vanna_analysis(
        self, base_coin: str, price_move: float = 0.05
    ) -> Dict[str, Any]:
        try:
            chain_data, price, err = await self._get_chain_and_price(
                base_coin, "vanna_analysis"
            )
            if err:
                return err
            exposures = self.vanna_analyzer.calculate_vanna_by_strike(
                chain_data, self.flow_config
            )
            result = self.vanna_analyzer.analyze_vanna_impact(
                exposures, price, base_coin
            )
            return _success_response(
                "vanna_exposure",
                self.vanna_analyzer.get_compact_vanna_summary(result),
                symbol=base_coin,
            )
        except Exception as e:
            logger.error(f"Vanna analysis error for {base_coin}: {e}")
            return _error_response(str(e), "vanna_analysis")

    async def get_flow_analysis(self, base_coin: str) -> Dict[str, Any]:
        try:
            raw = await self.api.get_options_chain_data(base_coin)
            chain_data = self._convert_chain_data(raw, base_coin) if raw else []
            if not chain_data:
                return _error_response(
                    f"No options data for {base_coin}", "flow_analysis"
                )
            delta_imbalance = self.flow_analyzer.calculate_delta_imbalance(
                chain_data, self.flow_config
            )
            flow_metrics = self.flow_analyzer.analyze_volume_imbalance(chain_data)
            unusual = self.flow_analyzer.detect_unusual_activity(
                chain_data, self.flow_config
            )
            summary = self.flow_analyzer.get_compact_flow_summary(
                delta_imbalance, flow_metrics, unusual
            )
            return _success_response("options_flow", summary, symbol=base_coin)
        except Exception as e:
            logger.error(f"Flow analysis error for {base_coin}: {e}")
            return _error_response(str(e), "flow_analysis")

    async def get_skew_analysis(self, base_coin: str) -> Dict[str, Any]:
        try:
            chain_data, price, err = await self._get_chain_and_price(
                base_coin, "skew_analysis"
            )
            if err:
                return err
            ts = self.skew_analyzer.analyze_term_structure(chain_data, price, base_coin)
            return _success_response(
                "volatility_skew",
                self.skew_analyzer.get_compact_skew_summary(ts),
                symbol=base_coin,
            )
        except Exception as e:
            logger.error(f"Skew analysis error for {base_coin}: {e}")
            return _error_response(str(e), "skew_analysis")

    # ── Volatility surface ──

    async def get_vol_surface_metrics(self, base_coin: str) -> Dict[str, Any]:
        try:
            profile = await self.volatility_analyzer.get_volatility_profile(base_coin)
            return _success_response(
                "vol_surface_metrics",
                {
                    "realized_vol_7d": profile.realized_vol_7d,
                    "realized_vol_30d": profile.realized_vol_30d,
                    "implied_vol_avg": profile.implied_vol_avg,
                    "risk_reversal_25d": profile.risk_reversal_25d,
                    "skew_10d": profile.skew_10d,
                    "vol_of_vol": profile.vol_of_vol,
                    "realized_implied_spread": profile.realized_implied_spread,
                    "vol_risk_premium": profile.vol_risk_premium,
                    "units": {
                        "volatility": "annualized_decimal",
                        "risk_reversal_25d": "iv_points",
                        "skew_10d": "iv_points",
                        "vol_of_vol": "iv_points",
                        "realized_implied_spread": "iv_points",
                        "vol_risk_premium": "ratio_minus_one",
                    },
                },
                symbol=base_coin,
            )
        except Exception as e:
            logger.error(f"Vol surface metrics error for {base_coin}: {e}")
            return _error_response(str(e), "vol_surface_metrics")

    # ── Technical analysis ──

    async def get_technical_indicators(
        self, symbol: str, interval: str = "1h", hours_back: int = 100
    ) -> Dict[str, Any]:
        try:
            klines = await self.api.get_klines(symbol, interval, hours_back=hours_back)
            if not klines:
                return _error_response(
                    f"No historical data for {symbol}", "technical_indicators"
                )
            summary = self.technical.get_comprehensive_analysis(
                klines, symbol, IndicatorConfig()
            )
            summary.timeframe = interval
            return _success_response(
                "technical_indicators",
                {
                    **self.technical.get_compact_summary(summary),
                    "data_points": len(klines),
                },
                symbol=symbol,
                interval=interval,
            )
        except Exception as e:
            logger.error(f"Technical indicators error for {symbol}: {e}")
            return _error_response(str(e), "technical_indicators")

    # ── Portfolio ──

    async def analyze_portfolio_greeks(
        self, portfolio_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            result = self.portfolio_analyzer.analyze_portfolio_greeks(portfolio_data)
            return _success_response("portfolio_greeks", result)
        except Exception as e:
            logger.error(f"Portfolio analysis error: {e}")
            return _error_response(str(e), "portfolio_analysis")

    async def run_scenario_analysis(
        self, portfolio_data: Dict[str, Any], scenarios: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        try:
            config = self._build_scenario_config(portfolio_data, scenarios)
            result = self.portfolio_analyzer.analyze_scenarios(portfolio_data, config)
            return _success_response("scenario_analysis", result)
        except Exception as e:
            logger.error(f"Scenario analysis error: {e}")
            return _error_response(str(e), "scenario_analysis")

    def _build_scenario_config(
        self, portfolio_data: Dict[str, Any], scenarios: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        price_scenarios: List[float] = []
        vol_scenarios: List[float] = []
        days_forward: Optional[int] = None
        underlying_price = portfolio_data.get("underlying_price", 0)

        for s in scenarios or []:
            if "price_change_pct" in s:
                price_scenarios.append(float(s["price_change_pct"]))
            elif "new_underlying_price" in s and underlying_price:
                price_scenarios.append(
                    (float(s["new_underlying_price"]) - underlying_price)
                    / underlying_price
                    * 100
                )
            if "vol_change_pct" in s:
                vol_scenarios.append(float(s["vol_change_pct"]))
            if days_forward is None:
                days_forward = (
                    int(s.get("days_forward", s.get("days_passed", 0))) or None
                )

        return {
            "price_scenarios": price_scenarios or [-10, -5, 0, 5, 10],
            "vol_scenarios": vol_scenarios or [-20, -10, 0, 10, 20],
            "days_forward": days_forward if days_forward is not None else 1,
        }

    # ── Sentiment ──

    async def get_market_sentiment_analysis(self, symbol: str) -> Dict[str, Any]:
        try:
            return await self.sentiment_analyzer.get_market_sentiment_analysis(symbol)
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return _error_response(str(e), "market_sentiment_analysis")

    async def get_open_interest_analysis(self, symbol: str) -> Dict[str, Any]:
        try:
            return await self.sentiment_analyzer.get_open_interest_analysis(symbol)
        except Exception as e:
            logger.error(f"OI analysis error: {e}")
            return _error_response(str(e), "open_interest_analysis")

    async def get_funding_rate_analysis(self, symbol: str) -> Dict[str, Any]:
        try:
            return await self.sentiment_analyzer.get_funding_rate_analysis(symbol)
        except Exception as e:
            logger.error(f"Funding analysis error: {e}")
            return _error_response(str(e), "funding_rate_analysis")

    # ── Covered call ──

    async def get_iv_rv_spread(
        self, base_coin: str, rv_window: int = 30
    ) -> Dict[str, Any]:
        """Compute IV-RV spread for covered call / vol-selling assessment."""
        try:
            from options_lib.strategy.covered_call import CoveredCallAnalyzer

            chain_data, price, err = await self._get_chain_and_price(
                base_coin, "iv_rv_spread"
            )
            if err:
                return err

            klines = await self.api.get_klines(
                f"{base_coin}USDT",
                "4h",
                hours_back=rv_window * 24,
            )
            if not klines:
                return _error_response(
                    f"No kline data for {base_coin}USDT", "iv_rv_spread"
                )

            iv_rv = CoveredCallAnalyzer.compute_iv_rv_spread(
                chain_data,
                price,
                klines,
                asset=base_coin,
                rv_window=rv_window * 6,
            )

            signal = (
                "SELL_VOL"
                if iv_rv.spread > 10
                else "HOLD"
                if iv_rv.spread > 5
                else "NO_EDGE"
            )
            return _success_response(
                "iv_rv_spread",
                {
                    "asset": base_coin,
                    "atm_iv_pct": round(iv_rv.atm_iv * 100, 2),
                    "realized_vol_pct": round(iv_rv.realized_vol * 100, 2),
                    "spread_vol_pts": round(iv_rv.spread, 2),
                    "spread_ratio": round(iv_rv.spread_ratio, 2),
                    "rv_estimator": iv_rv.rv_estimator,
                    "rv_window_days": rv_window,
                    "signal": signal,
                    "spot_price": price,
                },
                symbol=base_coin,
            )
        except Exception as e:
            logger.error(f"IV-RV spread error for {base_coin}: {e}")
            return _error_response(str(e), "iv_rv_spread")

    async def get_covered_call_signal(
        self,
        base_coin: str,
        target_delta: float = 0.10,
        iv_rv_threshold: float = 10.0,
        max_dte: int = 14,
    ) -> Dict[str, Any]:
        """Evaluate covered call entry signal with full analysis."""
        try:
            from options_lib.strategy.covered_call import CoveredCallAnalyzer

            chain_data, price, err = await self._get_chain_and_price(
                base_coin, "covered_call_signal"
            )
            if err:
                return err

            klines = await self.api.get_klines(
                f"{base_coin}USDT",
                "4h",
                hours_back=30 * 24,
            )
            if not klines:
                return _error_response(
                    f"No kline data for {base_coin}USDT", "covered_call_signal"
                )

            signal = CoveredCallAnalyzer.evaluate_signal(
                chain_data,
                price,
                klines,
                asset=base_coin,
                iv_rv_threshold=iv_rv_threshold,
                target_delta=target_delta,
                max_dte=max_dte,
            )

            return _success_response(
                "covered_call_signal",
                CoveredCallAnalyzer.format_signal_summary(signal),
                symbol=base_coin,
            )
        except Exception as e:
            logger.error(f"Covered call signal error for {base_coin}: {e}")
            return _error_response(str(e), "covered_call_signal")

    # ── Strategy analysis ──

    async def analyze_strategy(
        self,
        base_coin: str,
        strategy_type: str,
        min_oi: float = 10.0,
        spread_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Unified strategy analysis — handles straddles, strangles, and spreads."""
        try:
            from options_lib.strategy import StrategyAnalyzer

            analyzer = StrategyAnalyzer()

            raw = await self.api.get_options_chain_data(base_coin)
            if not raw:
                return _error_response(
                    f"No options data for {base_coin}", f"{strategy_type}_analysis"
                )
            price = await self.api.get_asset_price(f"{base_coin}USDT")
            if not price:
                return _error_response(
                    f"No price data for {base_coin}", f"{strategy_type}_analysis"
                )

            if strategy_type == "straddle":
                return await analyzer.analyze_straddles(base_coin, raw, price, min_oi)
            elif strategy_type == "strangle":
                return await analyzer.analyze_strangles(base_coin, raw, price, min_oi)
            elif strategy_type == "spread":
                types = spread_types or ["call_spread", "put_spread"]
                return await analyzer.analyze_spreads(base_coin, raw, price, types)
            else:
                return _error_response(
                    f"Unknown strategy type: {strategy_type}", "strategy_analysis"
                )
        except Exception as e:
            logger.error(f"{strategy_type} analysis error: {e}")
            return _error_response(str(e), f"{strategy_type}_analysis")


# Singleton
_orchestrator = None


def get_orchestrator() -> MCPOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MCPOrchestrator()
    return _orchestrator
