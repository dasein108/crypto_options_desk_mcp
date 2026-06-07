"""
Option Strategy Analyzer

Comprehensive analysis of option strategies including profitability,
risk metrics, and recommendations.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from .classifier import StrategyClassifier, StrategyType


@dataclass
class StrategyMetrics:
    """Comprehensive strategy analysis metrics."""
    strategy_name: str
    strategy_type: StrategyType
    net_cost: float
    max_profit: Optional[float]
    max_loss: Optional[float]
    breakeven_points: List[float]
    profit_range: Tuple[float, float]

    # Risk metrics
    prob_profit: Optional[float]
    expected_return: Optional[float]
    risk_reward_ratio: Optional[float]

    # Greeks
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float

    # Market context
    implied_vol_avg: float
    realized_vol_comparison: Optional[float]
    days_to_expiry: int

    # Liquidity metrics
    avg_bid_ask_spread: float
    total_open_interest: float
    liquidity_score: float


@dataclass
class StrategyRecommendation:
    """Strategy recommendation with reasoning."""
    strategy_config: Dict[str, Any]
    metrics: StrategyMetrics
    recommendation_score: float
    pros: List[str]
    cons: List[str]
    market_outlook: str
    risk_level: str


# Helpers to extract real values from option chain dicts

def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == '':
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _days_to_expiry(expiry: str) -> int:
    """Parse expiry string and compute days to expiry."""
    for fmt in ('%Y-%m-%d', '%d%b%y'):
        try:
            expiry_date = datetime.strptime(expiry.upper(), fmt)
            return max(0, (expiry_date - datetime.now()).days)
        except ValueError:
            continue
    return 0


def _option_greeks(option: Dict) -> Tuple[float, float, float, float]:
    """Extract (delta, gamma, theta, vega) from an option dict."""
    return (
        _safe_float(option.get('delta')),
        _safe_float(option.get('gamma')),
        _safe_float(option.get('theta')),
        _safe_float(option.get('vega')),
    )


def _option_liquidity(option: Dict) -> Tuple[float, float]:
    """Return (bid_ask_spread, open_interest) from an option dict."""
    bid = _safe_float(option.get('bid_price', option.get('bid1Price')))
    ask = _safe_float(option.get('ask_price', option.get('ask1Price')))
    spread = (ask - bid) if (ask > 0 and bid > 0) else 0.0
    oi = _safe_float(option.get('open_interest', option.get('openInterest')))
    return spread, oi


def _compute_liquidity_score(avg_spread: float, total_oi: float, mark_price: float) -> float:
    """Score 0-100 based on spread tightness and open interest depth."""
    score = 50.0
    # Spread component: tight spread relative to price is good
    if mark_price > 0 and avg_spread > 0:
        spread_pct = avg_spread / mark_price
        if spread_pct < 0.02:
            score += 25
        elif spread_pct < 0.05:
            score += 15
        elif spread_pct < 0.10:
            score += 5
        else:
            score -= 15
    # OI component
    if total_oi > 500:
        score += 25
    elif total_oi > 100:
        score += 15
    elif total_oi > 10:
        score += 5
    else:
        score -= 10
    return max(0.0, min(100.0, score))


def _find_option_in_chain(options_chain: List[Dict], symbol: str) -> Optional[Dict]:
    """Find an option by symbol in the chain."""
    for opt in options_chain:
        if opt.get('symbol') == symbol:
            return opt
    return None


class StrategyAnalyzer:
    """Analyzes option strategies for profitability and risk.

    Args:
        vol_context: Optional volatility context dict with keys like
                     'rv_7d', 'rv_30d', 'vol_risk_premium'.
    """

    def __init__(self, vol_context: Optional[Dict[str, Any]] = None):
        self.classifier = StrategyClassifier()
        self.vol_context = vol_context

    # ── Straddles ──

    async def analyze_straddles(self, base_coin: str, options_chain: List[Dict],
                              underlying_price: float, min_oi: float = 10,
                              vol_context: Optional[Dict] = None) -> Dict[str, Any]:
        """Comprehensive straddle analysis with profitability ranking."""
        try:
            ctx = vol_context or self.vol_context

            straddles = self.classifier.find_potential_strategies(
                options_chain, underlying_price, [StrategyType.STRADDLE]
            )

            analyzed_straddles = []
            for config in straddles:
                if config.get('strategy_type') == 'straddle':
                    metrics = self._analyze_straddle_config(config, underlying_price, ctx, options_chain)
                    if metrics.total_open_interest >= min_oi:
                        analyzed_straddles.append({
                            'config': config,
                            'metrics': metrics,
                            'recommendation': self._score_straddle(metrics, ctx)
                        })

            analyzed_straddles.sort(key=lambda x: x['recommendation']['score'], reverse=True)

            return {
                'success': True,
                'symbol': base_coin,
                'analysis_type': 'straddle_analysis',
                'timestamp': datetime.now().isoformat(),
                'market_context': {'spot_price': underlying_price, 'volatility_context': ctx},
                'straddles_analyzed': len(analyzed_straddles),
                'top_opportunities': analyzed_straddles[:10],
                'summary': self._create_straddle_summary(analyzed_straddles, ctx)
            }
        except Exception as e:
            return {'success': False, 'error': f"Straddle analysis failed: {str(e)}", 'symbol': base_coin}

    def _analyze_straddle_config(self, config: Dict, underlying_price: float,
                               vol_context: Optional[Dict],
                               options_chain: Optional[List[Dict]] = None) -> StrategyMetrics:
        strike = config['strike']
        cost = config['cost']
        expiry = config['expiry']

        breakevens = [strike - cost, strike + cost]
        implied_move = config.get('implied_move_pct', 0) / 100
        profit_range = (
            underlying_price * (1 - implied_move * 2),
            underlying_price * (1 + implied_move * 2)
        )

        days = _days_to_expiry(expiry)

        # Extract real Greeks from the chain options
        call_opt = _find_option_in_chain(options_chain or [], config.get('call_symbol', ''))
        put_opt = _find_option_in_chain(options_chain or [], config.get('put_symbol', ''))

        cd, cg, ct, cv = _option_greeks(call_opt) if call_opt else (0.5, 0, 0, 0)
        pd, pg, pt, pv = _option_greeks(put_opt) if put_opt else (-0.5, 0, 0, 0)

        net_delta = cd + pd
        net_gamma = cg + pg
        net_theta = ct + pt
        net_vega = cv + pv

        # Liquidity from real data
        c_spread, c_oi = _option_liquidity(call_opt) if call_opt else (0, 0)
        p_spread, p_oi = _option_liquidity(put_opt) if put_opt else (0, 0)
        total_oi = c_oi + p_oi
        avg_spread = (c_spread + p_spread) / 2

        # IV from chain
        c_iv = _safe_float(call_opt.get('mark_iv')) if call_opt else 0
        p_iv = _safe_float(put_opt.get('mark_iv')) if put_opt else 0
        avg_iv = (c_iv + p_iv) / 2 if (c_iv > 0 and p_iv > 0) else max(c_iv, p_iv)

        iv_rv_spread = None
        if vol_context and avg_iv > 0:
            iv_rv_spread = avg_iv - vol_context.get('rv_30d', 0)

        # Probability of profit estimate based on ATM distance
        atm_distance_pct = config.get('atm_distance_pct', 0)
        prob_profit = max(0.1, 0.6 - (atm_distance_pct / 100))

        return StrategyMetrics(
            strategy_name=f"Straddle @ {strike}",
            strategy_type=StrategyType.STRADDLE,
            net_cost=cost,
            max_profit=None,
            max_loss=cost,
            breakeven_points=breakevens,
            profit_range=profit_range,
            prob_profit=prob_profit,
            expected_return=None,
            risk_reward_ratio=None,
            net_delta=net_delta,
            net_gamma=net_gamma,
            net_theta=net_theta,
            net_vega=net_vega,
            implied_vol_avg=avg_iv,
            realized_vol_comparison=iv_rv_spread,
            days_to_expiry=days,
            avg_bid_ask_spread=avg_spread,
            total_open_interest=total_oi,
            liquidity_score=_compute_liquidity_score(avg_spread, total_oi, cost)
        )

    def _score_straddle(self, metrics: StrategyMetrics, vol_context: Optional[Dict]) -> Dict[str, Any]:
        score = 50
        pros = []
        cons = []

        if vol_context and metrics.realized_vol_comparison is not None:
            if metrics.realized_vol_comparison < -10:
                score += 20
                pros.append(f"IV {abs(metrics.realized_vol_comparison):.1f}% below realized vol")
            elif metrics.realized_vol_comparison > 15:
                score -= 15
                cons.append(f"IV {metrics.realized_vol_comparison:.1f}% above realized vol")

        # ATM proximity: for straddles, strike ≈ midpoint of breakevens
        if len(metrics.breakeven_points) >= 2:
            strike = (metrics.breakeven_points[0] + metrics.breakeven_points[1]) / 2
            center = (metrics.profit_range[0] + metrics.profit_range[1]) / 2
            if center > 0 and abs(strike - center) / center < 0.01:
                score += 10
                pros.append("Near ATM for maximum gamma")

        if metrics.days_to_expiry < 7:
            score -= 20
            cons.append("High time decay risk (< 7 DTE)")
        elif metrics.days_to_expiry > 45:
            score -= 5
            cons.append("High time premium (> 45 DTE)")
        else:
            score += 5
            pros.append("Optimal time to expiry")

        if metrics.liquidity_score > 80:
            score += 10
            pros.append("High liquidity")
        elif metrics.liquidity_score < 40:
            score -= 10
            cons.append("Low liquidity")

        return {'score': max(0, min(100, score)), 'pros': pros, 'cons': cons,
                'risk_level': 'medium', 'outlook': 'volatile'}

    def _create_straddle_summary(self, analyzed: List[Dict], vol_context: Optional[Dict]) -> Dict[str, Any]:
        if not analyzed:
            return {'message': 'No viable straddle opportunities found'}

        best = analyzed[0]
        summary: Dict[str, Any] = {
            'total_analyzed': len(analyzed),
            'average_cost': float(np.mean([s['metrics'].net_cost for s in analyzed])),
            'best_opportunity': {
                'strike': best['config']['strike'],
                'cost': best['metrics'].net_cost,
                'score': best['recommendation']['score'],
                'breakevens': best['metrics'].breakeven_points
            }
        }
        if vol_context:
            summary['market_assessment'] = {
                'iv_environment': 'rich' if vol_context.get('vol_risk_premium', 0) > 0.2 else 'normal',
                'rv_7d': vol_context.get('rv_7d'),
                'rv_30d': vol_context.get('rv_30d')
            }
        return summary

    # ── Strangles ──

    async def analyze_strangles(self, base_coin: str, options_chain: List[Dict],
                              underlying_price: float, min_oi: float = 10,
                              vol_context: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            ctx = vol_context or self.vol_context

            strangles = self.classifier.find_potential_strategies(
                options_chain, underlying_price, [StrategyType.STRANGLE]
            )

            analyzed = []
            for config in strangles:
                if config.get('strategy_type') == 'strangle':
                    metrics = self._analyze_strangle_config(config, underlying_price, ctx, options_chain)
                    analyzed.append({
                        'config': config,
                        'metrics': metrics,
                        'recommendation': self._score_strangle(metrics, ctx)
                    })

            analyzed.sort(key=lambda x: x['recommendation']['score'], reverse=True)

            return {
                'success': True, 'symbol': base_coin,
                'analysis_type': 'strangle_analysis',
                'timestamp': datetime.now().isoformat(),
                'market_context': {'spot_price': underlying_price, 'volatility_context': ctx},
                'strangles_analyzed': len(analyzed),
                'top_opportunities': analyzed[:10],
                'summary': self._create_strangle_summary(analyzed, ctx)
            }
        except Exception as e:
            return {'success': False, 'error': f"Strangle analysis failed: {str(e)}", 'symbol': base_coin}

    def _analyze_strangle_config(self, config: Dict, underlying_price: float,
                               vol_context: Optional[Dict],
                               options_chain: Optional[List[Dict]] = None) -> StrategyMetrics:
        put_strike = config['put_strike']
        call_strike = config['call_strike']
        cost = config['cost']
        expiry = config.get('expiry', '')
        breakevens = config['breakevens']

        days = _days_to_expiry(expiry)

        call_opt = _find_option_in_chain(options_chain or [], config.get('call_symbol', ''))
        put_opt = _find_option_in_chain(options_chain or [], config.get('put_symbol', ''))

        cd, cg, ct, cv = _option_greeks(call_opt) if call_opt else (0.3, 0, 0, 0)
        pd, pg, pt, pv = _option_greeks(put_opt) if put_opt else (-0.3, 0, 0, 0)

        c_spread, c_oi = _option_liquidity(call_opt) if call_opt else (0, 0)
        p_spread, p_oi = _option_liquidity(put_opt) if put_opt else (0, 0)
        total_oi = c_oi + p_oi
        avg_spread = (c_spread + p_spread) / 2

        c_iv = _safe_float(call_opt.get('mark_iv')) if call_opt else 0
        p_iv = _safe_float(put_opt.get('mark_iv')) if put_opt else 0
        avg_iv = (c_iv + p_iv) / 2 if (c_iv > 0 and p_iv > 0) else max(c_iv, p_iv)

        iv_rv_spread = None
        if vol_context and avg_iv > 0:
            iv_rv_spread = avg_iv - vol_context.get('rv_30d', 0)

        # Width-based prob estimate: wider strangle = lower probability but cheaper
        width_pct = abs(call_strike - put_strike) / underlying_price
        prob_profit = max(0.1, min(0.5, 0.55 - width_pct))

        return StrategyMetrics(
            strategy_name=f"Strangle {put_strike}/{call_strike}",
            strategy_type=StrategyType.STRANGLE,
            net_cost=cost,
            max_profit=None,
            max_loss=cost,
            breakeven_points=breakevens,
            profit_range=(breakevens[0], breakevens[1]),
            prob_profit=prob_profit,
            expected_return=None,
            risk_reward_ratio=None,
            net_delta=cd + pd,
            net_gamma=cg + pg,
            net_theta=ct + pt,
            net_vega=cv + pv,
            implied_vol_avg=avg_iv,
            realized_vol_comparison=iv_rv_spread,
            days_to_expiry=days,
            avg_bid_ask_spread=avg_spread,
            total_open_interest=total_oi,
            liquidity_score=_compute_liquidity_score(avg_spread, total_oi, cost)
        )

    def _score_strangle(self, metrics: StrategyMetrics, vol_context: Optional[Dict]) -> Dict[str, Any]:
        score = 45
        pros = []
        cons = []

        profit_zone = metrics.profit_range[1] - metrics.profit_range[0]
        if profit_zone > metrics.net_cost * 6:
            score += 15
            pros.append("Wide profit zone")
        elif profit_zone < metrics.net_cost * 3:
            score -= 10
            cons.append("Narrow profit zone")

        if metrics.profit_range[0] > 0 and metrics.net_cost < metrics.profit_range[0] * 0.03:
            score += 10
            pros.append("Low cost relative to strikes")

        if vol_context and metrics.realized_vol_comparison is not None:
            if metrics.realized_vol_comparison < -10:
                score += 15
                pros.append("IV cheap vs realized vol")
            elif metrics.realized_vol_comparison > 15:
                score -= 10
                cons.append("IV expensive vs realized vol")

        if metrics.days_to_expiry < 7:
            score -= 15
            cons.append("High time decay risk")
        elif 14 <= metrics.days_to_expiry <= 45:
            score += 5
            pros.append("Good time horizon")

        if metrics.liquidity_score > 80:
            score += 10
            pros.append("High liquidity")
        elif metrics.liquidity_score < 40:
            score -= 10
            cons.append("Low liquidity")

        return {'score': max(0, min(100, score)), 'pros': pros, 'cons': cons,
                'risk_level': 'medium', 'outlook': 'volatile'}

    def _create_strangle_summary(self, analyzed: List[Dict], vol_context: Optional[Dict]) -> Dict[str, Any]:
        if not analyzed:
            return {'message': 'No viable strangle opportunities found'}
        best = analyzed[0]
        return {
            'total_analyzed': len(analyzed),
            'best_opportunity': {
                'strikes': f"{best['config']['put_strike']}/{best['config']['call_strike']}",
                'cost': best['metrics'].net_cost,
                'score': best['recommendation']['score'],
                'width': best['config']['width']
            }
        }

    # ── Spreads ──

    async def analyze_spreads(self, base_coin: str, options_chain: List[Dict],
                            underlying_price: float, spread_types: Optional[List[str]] = None) -> Dict[str, Any]:
        if spread_types is None:
            spread_types = ['call_spread', 'put_spread']
        try:
            strategy_types = []
            if 'call_spread' in spread_types:
                strategy_types.append(StrategyType.CALL_SPREAD)
            if 'put_spread' in spread_types:
                strategy_types.append(StrategyType.PUT_SPREAD)

            spreads = self.classifier.find_potential_strategies(
                options_chain, underlying_price, strategy_types
            )

            analyzed = []
            for config in spreads:
                metrics = self._analyze_spread_config(config, underlying_price, options_chain)
                analyzed.append({
                    'config': config,
                    'metrics': metrics,
                    'recommendation': self._score_spread(metrics, underlying_price)
                })

            analyzed.sort(key=lambda x: x['recommendation']['score'], reverse=True)

            return {
                'success': True, 'symbol': base_coin,
                'analysis_type': 'spread_analysis',
                'timestamp': datetime.now().isoformat(),
                'spreads_analyzed': len(analyzed),
                'top_opportunities': analyzed[:15],
                'summary': self._create_spread_summary(analyzed)
            }
        except Exception as e:
            return {'success': False, 'error': f"Spread analysis failed: {str(e)}", 'symbol': base_coin}

    def _analyze_spread_config(self, config: Dict, underlying_price: float,
                              options_chain: Optional[List[Dict]] = None) -> StrategyMetrics:
        strategy_type = config['strategy_type']
        expiry = config.get('expiry', '')
        days = _days_to_expiry(expiry)

        if 'call' in strategy_type:
            long_strike = config['long_strike']
            short_strike = config['short_strike']
            net_cost = config.get('net_cost', 0)
            max_profit = config.get('max_profit', 0)
            max_loss = config.get('max_loss', net_cost)
            breakeven = config.get('breakeven', long_strike + net_cost)
        else:
            long_strike = config['long_strike']
            short_strike = config['short_strike']
            net_credit = config.get('net_credit', 0)
            max_profit = config.get('max_profit', net_credit)
            max_loss = config.get('max_loss', 0)
            breakeven = config.get('breakeven', short_strike - net_credit)
            net_cost = -net_credit

        # Look up real Greeks from chain — spreads have a long and short leg
        # Net Greeks = long_greeks - short_greeks
        chain = options_chain or []
        long_sym = config.get('long_symbol', '')
        short_sym = config.get('short_symbol', '')
        # If symbols not in config, try to find by strike
        long_opt = _find_option_in_chain(chain, long_sym) if long_sym else None
        short_opt = _find_option_in_chain(chain, short_sym) if short_sym else None

        ld, lg, lt, lv = _option_greeks(long_opt) if long_opt else (0, 0, 0, 0)
        sd, sg, st, sv = _option_greeks(short_opt) if short_opt else (0, 0, 0, 0)

        net_delta = ld - sd
        net_gamma = lg - sg
        net_theta = lt - st
        net_vega = lv - sv

        # Liquidity
        l_spread, l_oi = _option_liquidity(long_opt) if long_opt else (0, 0)
        s_spread, s_oi = _option_liquidity(short_opt) if short_opt else (0, 0)
        total_oi = l_oi + s_oi
        avg_spread = (l_spread + s_spread) / 2

        # IV
        l_iv = _safe_float(long_opt.get('mark_iv')) if long_opt else 0
        s_iv = _safe_float(short_opt.get('mark_iv')) if short_opt else 0
        avg_iv = (l_iv + s_iv) / 2 if (l_iv > 0 and s_iv > 0) else max(l_iv, s_iv)

        # Probability: approximate from delta of the long leg
        # For a bull call spread, P(profit) ≈ delta of long call
        prob_profit = abs(ld) if ld != 0 else 0.5

        mark = abs(net_cost) if net_cost != 0 else (max_loss if max_loss else 1)

        return StrategyMetrics(
            strategy_name=f"{strategy_type.replace('_', ' ').title()} {long_strike}/{short_strike}",
            strategy_type=StrategyType.CALL_SPREAD if 'call' in strategy_type else StrategyType.PUT_SPREAD,
            net_cost=net_cost,
            max_profit=max_profit,
            max_loss=max_loss,
            breakeven_points=[breakeven],
            profit_range=(0, max_profit) if max_profit else (0, 0),
            prob_profit=prob_profit,
            expected_return=None,
            risk_reward_ratio=max_profit / max_loss if max_loss and max_loss > 0 else None,
            net_delta=net_delta,
            net_gamma=net_gamma,
            net_theta=net_theta,
            net_vega=net_vega,
            implied_vol_avg=avg_iv,
            realized_vol_comparison=None,
            days_to_expiry=days,
            avg_bid_ask_spread=avg_spread,
            total_open_interest=total_oi,
            liquidity_score=_compute_liquidity_score(avg_spread, total_oi, mark)
        )

    def _score_spread(self, metrics: StrategyMetrics, underlying_price: float) -> Dict[str, Any]:
        score = 50
        pros = []
        cons = []

        if metrics.risk_reward_ratio and metrics.risk_reward_ratio > 2:
            score += 20
            pros.append(f"Excellent R:R ratio ({metrics.risk_reward_ratio:.1f}:1)")
        elif metrics.risk_reward_ratio and metrics.risk_reward_ratio < 1:
            score -= 15
            cons.append(f"Poor R:R ratio ({metrics.risk_reward_ratio:.1f}:1)")

        if metrics.prob_profit and metrics.prob_profit > 0.6:
            score += 15
            pros.append("High probability of profit")
        elif metrics.prob_profit and metrics.prob_profit < 0.4:
            score -= 10
            cons.append("Lower probability trade")

        if metrics.days_to_expiry < 7:
            score -= 10
            cons.append("Close to expiry")
        elif 14 <= metrics.days_to_expiry <= 45:
            score += 5
            pros.append("Good time horizon")

        if metrics.liquidity_score > 80:
            score += 10
            pros.append("High liquidity")
        elif metrics.liquidity_score < 40:
            score -= 10
            cons.append("Low liquidity")

        return {
            'score': max(0, min(100, score)), 'pros': pros, 'cons': cons,
            'risk_level': 'low' if metrics.max_loss and metrics.max_loss < 100 else 'medium',
            'outlook': 'directional'
        }

    def _create_spread_summary(self, analyzed: List[Dict]) -> Dict[str, Any]:
        if not analyzed:
            return {'message': 'No viable spread opportunities found'}

        call_spreads = [s for s in analyzed if 'call' in s['config']['strategy_type']]
        put_spreads = [s for s in analyzed if 'put' in s['config']['strategy_type']]

        return {
            'total_analyzed': len(analyzed),
            'call_spreads': len(call_spreads),
            'put_spreads': len(put_spreads),
            'best_call_spread': call_spreads[0]['config'] if call_spreads else None,
            'best_put_spread': put_spreads[0]['config'] if put_spreads else None,
        }

    # ── Compare ──

    async def compare_strategies(self, strategies: List[Dict]) -> Dict[str, Any]:
        """Compare multiple analyzed strategies side by side.

        Each item in strategies should have 'metrics' (StrategyMetrics) and 'config'.
        """
        if not strategies:
            return {'strategies': [], 'comparison_matrix': {}, 'recommendations': []}

        metrics_list = [s['metrics'] for s in strategies if 'metrics' in s]
        if not metrics_list:
            return {'strategies': strategies, 'comparison_matrix': {}, 'recommendations': []}

        # Build comparison matrix
        matrix = {}
        for m in metrics_list:
            matrix[m.strategy_name] = {
                'type': m.strategy_type.value,
                'cost': m.net_cost,
                'max_profit': m.max_profit,
                'max_loss': m.max_loss,
                'risk_reward': m.risk_reward_ratio,
                'prob_profit': m.prob_profit,
                'net_delta': m.net_delta,
                'net_theta': m.net_theta,
                'net_vega': m.net_vega,
                'days_to_expiry': m.days_to_expiry,
                'liquidity_score': m.liquidity_score,
            }

        # Rank by composite score
        scored = []
        for s in strategies:
            m = s.get('metrics')
            if not m:
                continue
            composite = 0.0
            # Favor high R:R
            if m.risk_reward_ratio and m.risk_reward_ratio > 0:
                composite += min(m.risk_reward_ratio, 5) * 10
            # Favor high prob
            if m.prob_profit:
                composite += m.prob_profit * 30
            # Favor liquidity
            composite += m.liquidity_score * 0.2
            # Penalize extreme time decay
            if m.days_to_expiry < 7:
                composite -= 15
            scored.append({'strategy': m.strategy_name, 'composite_score': round(composite, 1)})

        scored.sort(key=lambda x: x['composite_score'], reverse=True)

        return {
            'strategies': [s.get('config', {}) for s in strategies],
            'comparison_matrix': matrix,
            'recommendations': scored
        }
