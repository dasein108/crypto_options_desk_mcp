"""Systematic covered call carry strategy.

Harvests variance risk premium (IV > RV) by selling weekly OTM calls
against spot/perp holdings. Fully collateralized = zero liquidation risk.

Signal logic:
    1. Compute IV-RV spread (ATM IV from chain vs Garman-Klass RV)
    2. Gate on vol regime (skip EXTREME), term structure (want contango),
       and skew (don't sell when calls are cheap)
    3. Select strike at ~0.10 delta (10-15% OTM)
    4. Weekly roll cycle

Usage:
    from options_lib.strategy.covered_call import CoveredCallAnalyzer
    analyzer = CoveredCallAnalyzer()
    signal = await analyzer.evaluate_signal("BTC")
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from ..flow.types import (
    OptionsChainData,
    OptionType,
    VolatilityRegime,
)

logger = logging.getLogger(__name__)


@dataclass
class StrikeCandidate:
    """A candidate strike for selling a covered call."""

    symbol: str
    strike: float
    expiry_date: str
    delta: float
    mark_iv: float
    mark_price: float
    bid_price: float
    ask_price: float
    mid_price: float
    open_interest: float
    volume: float
    premium_pct: float  # premium as % of underlying
    otm_pct: float  # how far OTM as % of underlying
    spread_pct: float  # bid-ask spread as % of mid
    score: float  # composite ranking score


@dataclass
class IVRVSpread:
    """IV vs RV spread analysis."""

    asset: str
    atm_iv: float  # decimal (e.g. 0.55 = 55%)
    realized_vol: float  # annualized decimal
    spread: float  # IV - RV in vol points (percentage points)
    spread_ratio: float  # IV / RV
    rv_estimator: str  # which RV estimator was used
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CoveredCallSignal:
    """Go/no-go signal for covered call entry."""

    asset: str
    go: bool
    reasons: List[str]  # why go or no-go

    # Components
    iv_rv_spread: Optional[IVRVSpread] = None
    vol_regime: Optional[str] = None
    term_structure: Optional[str] = None  # "contango" or "backwardation"
    term_structure_slope: float = 0.0
    skew_direction: Optional[str] = None

    # Selected strike (if go=True)
    strike: Optional[StrikeCandidate] = None
    candidates: List[StrikeCandidate] = field(default_factory=list)

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CoveredCallAnalyzer:
    """Analyzes market conditions for systematic covered call writing.

    All methods are stateless — pass in data, get analysis back.
    Designed for CLI and bot consumption.
    """

    # Configurable thresholds
    DEFAULT_IV_RV_THRESHOLD = 10.0  # minimum spread in vol points
    DEFAULT_TARGET_DELTA = 0.10  # target call delta
    DEFAULT_DELTA_RANGE = (0.05, 0.20)  # acceptable delta range
    DEFAULT_MIN_DTE = 3  # minimum days to expiry
    DEFAULT_MAX_DTE = 14  # maximum days to expiry (weekly focus)
    DEFAULT_MIN_OI = 5.0  # minimum open interest
    DEFAULT_MAX_SPREAD_PCT = 0.15  # max bid-ask spread as % of mid

    @staticmethod
    def compute_iv_rv_spread(
        chain: List[OptionsChainData],
        underlying_price: float,
        klines: list,
        asset: str = "BTC",
        rv_window: int = 30,
    ) -> IVRVSpread:
        """Compute IV-RV spread from live chain and kline data.

        Args:
            chain: Options chain data from Bybit
            underlying_price: Current spot price
            klines: List of Kline objects (need .high, .low, .open, .close)
            asset: Asset name for logging
            rv_window: Lookback period for RV calculation

        Returns:
            IVRVSpread with the spread analysis
        """
        from ..flow.skew import SkewAnalysis

        # Get ATM IV from chain
        calls = [o for o in chain if o.option_type == OptionType.CALL and o.mark_iv > 0]
        puts = [o for o in chain if o.option_type == OptionType.PUT and o.mark_iv > 0]
        call_iv, put_iv, _ = SkewAnalysis._find_atm_iv_same_strike(
            calls, puts, underlying_price
        )
        atm_iv = (
            (call_iv + put_iv) / 2
            if call_iv > 0 and put_iv > 0
            else max(call_iv, put_iv)
        )

        # Compute RV using Garman-Klass (more efficient estimator)
        rv = CoveredCallAnalyzer._garman_klass_rv(klines, rv_window)

        spread = (atm_iv - rv) * 100  # convert to vol points

        return IVRVSpread(
            asset=asset,
            atm_iv=atm_iv,
            realized_vol=rv,
            spread=spread,
            spread_ratio=atm_iv / rv if rv > 0 else 0,
            rv_estimator="garman_klass",
        )

    @staticmethod
    def _garman_klass_rv(klines: list, window: int = 30) -> float:
        """Compute Garman-Klass realized volatility from klines.

        Returns annualized volatility as decimal (e.g. 0.45 = 45%).
        """
        import math

        if len(klines) < window:
            window = len(klines)
        if window < 5:
            return 0.0

        recent = klines[-window:]
        gk_values = []
        for k in recent:
            high = float(k.high) if hasattr(k, "high") else float(k["high"])
            low = float(k.low) if hasattr(k, "low") else float(k["low"])
            opn = float(k.open) if hasattr(k, "open") else float(k["open"])
            cls = float(k.close) if hasattr(k, "close") else float(k["close"])
            if high <= 0 or low <= 0 or opn <= 0 or cls <= 0 or high == low:
                continue
            gk = (
                0.5 * math.log(high / low) ** 2
                - (2 * math.log(2) - 1) * math.log(cls / opn) ** 2
            )
            gk_values.append(gk)

        if not gk_values:
            return 0.0

        # Determine annualization factor from kline interval
        # Default to daily (365), detect hourly if timestamps are close
        if len(klines) >= 2:
            t0 = klines[-2].timestamp if hasattr(klines[-2], "timestamp") else None
            t1 = klines[-1].timestamp if hasattr(klines[-1], "timestamp") else None
            if t0 and t1:
                diff = (t1 - t0).total_seconds()
                if diff <= 3700:  # ~1 hour
                    ann_factor = 365 * 24
                elif diff <= 14500:  # ~4 hours
                    ann_factor = 365 * 6
                elif diff <= 90000:  # ~1 day
                    ann_factor = 365
                else:
                    ann_factor = 365
            else:
                ann_factor = 365
        else:
            ann_factor = 365

        mean_gk = sum(gk_values) / len(gk_values)
        return math.sqrt(max(mean_gk * ann_factor, 0))

    @staticmethod
    def select_strikes(
        chain: List[OptionsChainData],
        underlying_price: float,
        target_delta: float = 0.10,
        delta_range: tuple = (0.05, 0.20),
        min_dte: int = 3,
        max_dte: int = 14,
        min_oi: float = 5.0,
        max_spread_pct: float = 0.15,
    ) -> List[StrikeCandidate]:
        """Select and rank OTM call strikes for covered call writing.

        Filters for calls within delta range, sufficient liquidity,
        and ranks by premium-to-risk ratio.

        Returns:
            Sorted list of StrikeCandidate (best first)
        """

        candidates = []

        for opt in chain:
            if opt.option_type != OptionType.CALL:
                continue
            if opt.strike <= underlying_price:
                continue  # must be OTM
            if opt.mark_iv <= 0 or opt.mark_price <= 0:
                continue

            # Delta filter (Bybit call deltas are positive)
            abs_delta = abs(opt.delta)
            if abs_delta < delta_range[0] or abs_delta > delta_range[1]:
                continue

            # DTE filter — parse expiry from symbol
            dte = CoveredCallAnalyzer._estimate_dte(opt.expiry_date)
            if dte is None or dte < min_dte or dte > max_dte:
                continue

            # Liquidity filters
            if opt.open_interest < min_oi:
                continue

            # Bid-ask spread
            mid = (
                (opt.bid_price + opt.ask_price) / 2
                if opt.bid_price > 0 and opt.ask_price > 0
                else opt.mark_price
            )
            spread_pct = (
                (opt.ask_price - opt.bid_price) / mid
                if mid > 0 and opt.bid_price > 0
                else 1.0
            )
            if spread_pct > max_spread_pct:
                continue

            otm_pct = (opt.strike - underlying_price) / underlying_price
            premium_pct = mid / underlying_price

            # Score: premium relative to delta risk, penalize wide spreads
            # Higher premium per unit delta = better risk/reward
            score = (
                (premium_pct / abs_delta)
                * (1.0 - spread_pct)
                * (1.0 + opt.open_interest / 100)
            )

            candidates.append(
                StrikeCandidate(
                    symbol=opt.symbol,
                    strike=opt.strike,
                    expiry_date=opt.expiry_date,
                    delta=abs_delta,
                    mark_iv=opt.mark_iv,
                    mark_price=opt.mark_price,
                    bid_price=opt.bid_price,
                    ask_price=opt.ask_price,
                    mid_price=mid,
                    open_interest=opt.open_interest,
                    volume=opt.volume,
                    premium_pct=premium_pct,
                    otm_pct=otm_pct,
                    spread_pct=spread_pct,
                    score=score,
                )
            )

        # Sort by delta proximity to target first, then by score
        candidates.sort(key=lambda c: (abs(c.delta - target_delta), -c.score))
        return candidates

    @staticmethod
    def evaluate_signal(
        chain: List[OptionsChainData],
        underlying_price: float,
        klines: list,
        asset: str = "BTC",
        iv_rv_threshold: float = DEFAULT_IV_RV_THRESHOLD,
        target_delta: float = DEFAULT_TARGET_DELTA,
        delta_range: tuple = DEFAULT_DELTA_RANGE,
        min_dte: int = DEFAULT_MIN_DTE,
        max_dte: int = DEFAULT_MAX_DTE,
    ) -> CoveredCallSignal:
        """Evaluate whether to enter a covered call position.

        Checks:
            1. IV-RV spread > threshold
            2. Vol regime != EXTREME
            3. Term structure in contango
            4. Skew: calls not abnormally cheap
            5. Suitable strike available

        Args:
            chain: Full options chain from Bybit
            underlying_price: Current spot price
            klines: Kline data for RV calculation (daily or 4h)
            asset: "BTC", "ETH", etc.
            iv_rv_threshold: Minimum IV-RV spread in vol points

        Returns:
            CoveredCallSignal with go/no-go and details
        """
        from ..flow.skew import SkewAnalysis
        from ..flow.flow import OptionsFlow
        from ..flow.regimes import VolatilityRegimes

        reasons = []
        go = True

        # 1. IV-RV spread
        iv_rv = CoveredCallAnalyzer.compute_iv_rv_spread(
            chain, underlying_price, klines, asset
        )
        if iv_rv.spread < iv_rv_threshold:
            go = False
            reasons.append(
                f"IV-RV spread too narrow: {iv_rv.spread:.1f} vol pts < {iv_rv_threshold} threshold"
            )
        else:
            reasons.append(
                f"IV-RV spread OK: {iv_rv.spread:.1f} vol pts (IV={iv_rv.atm_iv * 100:.1f}%, RV={iv_rv.realized_vol * 100:.1f}%)"
            )

        # 2. Term structure — want contango (back > front)
        term = SkewAnalysis.analyze_term_structure(chain, underlying_price, asset)
        ts_regime = "contango" if term.term_structure_slope > 0 else "backwardation"
        if term.term_structure_slope < -0.02:  # significant backwardation
            go = False
            reasons.append(
                f"Term structure in backwardation: slope={term.term_structure_slope * 100:.1f}% — elevated near-term risk"
            )
        else:
            reasons.append(
                f"Term structure OK: {ts_regime} (slope={term.term_structure_slope * 100:.1f}%)"
            )

        # 3. Vol regime — skip EXTREME
        flow_metrics = OptionsFlow.analyze_volume_imbalance(chain)
        regime_analysis = VolatilityRegimes.detect_current_regime(
            chain, flow_metrics, term
        )
        vol_regime = regime_analysis.current_regime.value
        if regime_analysis.current_regime == VolatilityRegime.EXTREME:
            go = False
            reasons.append("Vol regime EXTREME — too risky to sell calls")
        else:
            reasons.append(f"Vol regime OK: {vol_regime}")

        # 4. Skew — don't sell calls when call wing is already cheap
        skew_direction = "flat"
        if term.expiry_analysis:
            # Check nearest expiry skew
            nearest = term.expiry_analysis[0]
            skew_direction = nearest.skew_direction
            if nearest.skew_direction == "call_heavy" and nearest.skew_extremeness > 70:
                reasons.append(
                    f"Warning: call-heavy skew (extremeness={nearest.skew_extremeness:.0f}) — calls may be overpriced, good for selling"
                )
            elif nearest.risk_reversal_skew < -0.10:
                # Calls significantly cheaper than puts — less premium to collect
                go = False
                reasons.append(
                    f"Calls cheap vs puts (RR skew={nearest.risk_reversal_skew * 100:.1f}%) — poor premium for call selling"
                )
            else:
                reasons.append(f"Skew OK: {skew_direction}")

        # 5. Select strike
        candidates = CoveredCallAnalyzer.select_strikes(
            chain, underlying_price, target_delta, delta_range, min_dte, max_dte
        )
        best_strike = candidates[0] if candidates else None
        if not best_strike:
            go = False
            reasons.append(
                "No suitable strikes found within delta/DTE/liquidity filters"
            )
        else:
            reasons.append(
                f"Best strike: {best_strike.symbol} "
                f"(delta={best_strike.delta:.3f}, premium={best_strike.premium_pct * 100:.2f}%, "
                f"OTM={best_strike.otm_pct * 100:.1f}%, spread={best_strike.spread_pct * 100:.1f}%)"
            )

        return CoveredCallSignal(
            asset=asset,
            go=go,
            reasons=reasons,
            iv_rv_spread=iv_rv,
            vol_regime=vol_regime,
            term_structure=ts_regime,
            term_structure_slope=term.term_structure_slope,
            skew_direction=skew_direction,
            strike=best_strike,
            candidates=candidates[:5],  # top 5
        )

    @staticmethod
    def _estimate_dte(expiry_str: str) -> Optional[int]:
        """Estimate days to expiry from Bybit expiry string like '05APR26'."""

        now = datetime.now(timezone.utc)
        # Try parsing Bybit format: DDMMMYY (e.g., 05APR26)
        try:
            expiry = datetime.strptime(expiry_str, "%d%b%y").replace(
                tzinfo=timezone.utc
            )
            return max(0, (expiry - now).days)
        except ValueError:
            pass
        # Try ISO format
        try:
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            return max(0, (expiry - now).days)
        except ValueError:
            pass
        return None

    @staticmethod
    def format_signal_summary(signal: CoveredCallSignal) -> dict:
        """Format signal as JSON-friendly dict for CLI output."""
        result = {
            "asset": signal.asset,
            "go": signal.go,
            "reasons": signal.reasons,
            "timestamp": signal.timestamp.isoformat(),
        }
        if signal.iv_rv_spread:
            result["iv_rv"] = {
                "atm_iv_pct": round(signal.iv_rv_spread.atm_iv * 100, 2),
                "realized_vol_pct": round(signal.iv_rv_spread.realized_vol * 100, 2),
                "spread_vol_pts": round(signal.iv_rv_spread.spread, 2),
                "spread_ratio": round(signal.iv_rv_spread.spread_ratio, 2),
                "rv_estimator": signal.iv_rv_spread.rv_estimator,
            }
        result["vol_regime"] = signal.vol_regime
        result["term_structure"] = signal.term_structure
        result["term_structure_slope_pct"] = round(signal.term_structure_slope * 100, 2)
        result["skew_direction"] = signal.skew_direction

        if signal.strike:
            s = signal.strike
            result["recommended_strike"] = {
                "symbol": s.symbol,
                "strike": s.strike,
                "expiry": s.expiry_date,
                "delta": round(s.delta, 4),
                "mark_iv_pct": round(s.mark_iv * 100, 2),
                "premium_usd": round(s.mid_price, 4),
                "premium_pct": round(s.premium_pct * 100, 3),
                "otm_pct": round(s.otm_pct * 100, 2),
                "bid_ask_spread_pct": round(s.spread_pct * 100, 2),
                "open_interest": s.open_interest,
                "volume": s.volume,
            }
        if signal.candidates:
            result["alternative_strikes"] = [
                {
                    "symbol": c.symbol,
                    "strike": c.strike,
                    "delta": round(c.delta, 4),
                    "premium_pct": round(c.premium_pct * 100, 3),
                    "otm_pct": round(c.otm_pct * 100, 2),
                }
                for c in signal.candidates[1:5]
            ]
        return result
