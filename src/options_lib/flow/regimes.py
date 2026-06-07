"""Volatility regime detection and analysis."""

import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .types import (
    OptionsChainData, RegimeAnalysis, VolatilityRegime, 
    FlowMetrics, TermStructure, OptionsFlowConfig
)


class VolatilityRegimes:
    """Advanced volatility regime detection and analysis."""
    
    @staticmethod
    def detect_current_regime(options_data: List[OptionsChainData],
                            flow_metrics: FlowMetrics,
                            term_structure: TermStructure,
                            historical_data: Optional[Dict[str, Any]] = None,
                            config: Optional[OptionsFlowConfig] = None) -> RegimeAnalysis:
        """Detect current volatility regime using multiple indicators."""
        if config is None:
            config = OptionsFlowConfig()
        
        if not options_data:
            return RegimeAnalysis(
                current_regime=VolatilityRegime.NORMAL,
                regime_probability=50,
                time_in_regime=0,
                regime_change_probability=50,
                next_likely_regime=VolatilityRegime.NORMAL,
                vix_level=0,
                realized_vs_implied=0,
                vol_of_vol=0,
                put_call_ratio=1.0,
                skew_level=0,
                term_structure_slope=0
            )
        
        # Calculate key regime indicators
        regime_indicators = VolatilityRegimes._calculate_regime_indicators(
            options_data, flow_metrics, term_structure
        )
        
        # Determine current regime
        current_regime, regime_probability = VolatilityRegimes._classify_regime(regime_indicators)
        
        # Estimate time in regime (would need historical data)
        time_in_regime = 1  # Default - would calculate from historical data
        
        # Predict regime change probability
        regime_change_probability = VolatilityRegimes._calculate_regime_change_probability(
            regime_indicators, current_regime
        )
        
        # Predict next likely regime
        next_likely_regime = VolatilityRegimes._predict_next_regime(
            current_regime, regime_indicators
        )
        
        return RegimeAnalysis(
            current_regime=current_regime,
            regime_probability=regime_probability,
            time_in_regime=time_in_regime,
            regime_change_probability=regime_change_probability,
            next_likely_regime=next_likely_regime,
            vix_level=regime_indicators["vix_proxy"],
            realized_vs_implied=regime_indicators["realized_vs_implied"],
            vol_of_vol=regime_indicators["vol_of_vol"],
            put_call_ratio=regime_indicators["put_call_ratio"],
            skew_level=regime_indicators["skew_level"],
            term_structure_slope=regime_indicators["term_structure_slope"]
        )
    
    @staticmethod
    def _calculate_regime_indicators(options_data: List[OptionsChainData],
                                   flow_metrics: FlowMetrics,
                                   term_structure: TermStructure) -> Dict[str, float]:
        """Calculate key indicators for regime detection."""
        indicators = {}
        
        # VIX proxy (ATM IV of front month)
        if term_structure.expiry_analysis:
            indicators["vix_proxy"] = term_structure.front_month_iv * 100
        else:
            indicators["vix_proxy"] = 20.0  # Default VIX level
        
        # Put-call ratio
        indicators["put_call_ratio"] = flow_metrics.call_put_ratio
        
        # Volatility skew level (average put-call skew)
        if term_structure.expiry_analysis:
            avg_skew = np.mean([exp.put_call_skew for exp in term_structure.expiry_analysis])
            indicators["skew_level"] = avg_skew * 100
        else:
            indicators["skew_level"] = 0
        
        # Term structure slope
        indicators["term_structure_slope"] = term_structure.term_structure_slope * 100
        
        # Realized vs implied volatility (simplified - would need historical spot data)
        # For now, use skew as proxy
        indicators["realized_vs_implied"] = -abs(indicators["skew_level"])  # Negative = implied > realized typically
        
        # Vol of vol (volatility clustering indicator)
        indicators["vol_of_vol"] = VolatilityRegimes._estimate_vol_of_vol(options_data)
        
        # Options positioning intensity
        total_oi = sum(opt.open_interest for opt in options_data)
        total_volume = sum(opt.volume for opt in options_data)
        indicators["positioning_intensity"] = total_volume / total_oi if total_oi > 0 else 0
        
        return indicators
    
    @staticmethod
    def _estimate_vol_of_vol(options_data: List[OptionsChainData]) -> float:
        """Estimate volatility of volatility from options chain."""
        if len(options_data) < 5:
            return 0
        
        # Calculate IV dispersion across strikes as proxy for vol of vol
        ivs = [opt.mark_iv for opt in options_data if opt.mark_iv > 0]
        if len(ivs) < 3:
            return 0
        
        iv_mean = np.mean(ivs)
        iv_std = np.std(ivs)
        
        # Vol of vol as coefficient of variation
        vol_of_vol = (iv_std / iv_mean) * 100 if iv_mean > 0 else 0
        
        return vol_of_vol
    
    @staticmethod
    def _classify_regime(indicators: Dict[str, float]) -> tuple[VolatilityRegime, float]:
        """Classify volatility regime based on indicators."""
        vix_level = indicators["vix_proxy"]
        put_call_ratio = indicators["put_call_ratio"]
        skew_level = abs(indicators["skew_level"])
        vol_of_vol = indicators["vol_of_vol"]
        
        # Scoring system for regime classification
        regime_scores = {
            VolatilityRegime.LOW: 0,
            VolatilityRegime.NORMAL: 0,
            VolatilityRegime.HIGH: 0,
            VolatilityRegime.EXTREME: 0
        }
        
        # IV-based classification (crypto-calibrated: BTC baseline 60-80%, ETH 80-120%)
        if vix_level < 40:
            regime_scores[VolatilityRegime.LOW] += 40
        elif vix_level < 80:
            regime_scores[VolatilityRegime.NORMAL] += 40
        elif vix_level < 120:
            regime_scores[VolatilityRegime.HIGH] += 40
        else:
            regime_scores[VolatilityRegime.EXTREME] += 40
        
        # Put-call ratio contribution
        if put_call_ratio < 0.7:  # Call heavy
            regime_scores[VolatilityRegime.LOW] += 20
            regime_scores[VolatilityRegime.NORMAL] += 10
        elif put_call_ratio > 1.5:  # Put heavy
            regime_scores[VolatilityRegime.HIGH] += 20
            regime_scores[VolatilityRegime.EXTREME] += 10
        else:  # Balanced
            regime_scores[VolatilityRegime.NORMAL] += 20
        
        # Skew contribution
        if skew_level > 8:  # High skew = fear
            regime_scores[VolatilityRegime.HIGH] += 25
            regime_scores[VolatilityRegime.EXTREME] += 15
        elif skew_level < 3:  # Low skew = complacency
            regime_scores[VolatilityRegime.LOW] += 25
            regime_scores[VolatilityRegime.NORMAL] += 15
        else:
            regime_scores[VolatilityRegime.NORMAL] += 25
        
        # Vol of vol contribution
        if vol_of_vol > 20:  # High dispersion
            regime_scores[VolatilityRegime.EXTREME] += 15
            regime_scores[VolatilityRegime.HIGH] += 10
        elif vol_of_vol < 5:  # Low dispersion
            regime_scores[VolatilityRegime.LOW] += 15
            regime_scores[VolatilityRegime.NORMAL] += 10
        
        # Find regime with highest score
        best_regime = max(regime_scores.items(), key=lambda x: x[1])
        regime = best_regime[0]
        confidence = min(best_regime[1], 100)
        
        return regime, confidence
    
    @staticmethod
    def _calculate_regime_change_probability(indicators: Dict[str, float], 
                                           current_regime: VolatilityRegime) -> float:
        """Calculate probability of regime change."""
        vix_level = indicators["vix_proxy"]
        vol_of_vol = indicators["vol_of_vol"]
        skew_level = abs(indicators["skew_level"])
        positioning_intensity = indicators["positioning_intensity"]
        
        change_probability = 0
        
        # High vol of vol = higher regime change probability
        change_probability += min(vol_of_vol * 2, 30)
        
        # Extreme IV levels = higher probability of change (crypto-calibrated)
        if vix_level > 120 or vix_level < 30:
            change_probability += 25
        
        # Extreme skew = potential regime shift
        if skew_level > 10:
            change_probability += 20
        
        # High positioning intensity = potential inflection
        if positioning_intensity > 0.5:
            change_probability += 15
        
        # Mean reversion tendency
        if current_regime in [VolatilityRegime.EXTREME, VolatilityRegime.LOW]:
            change_probability += 20  # Extreme regimes tend to revert
        
        return min(change_probability, 95)  # Cap at 95%
    
    @staticmethod
    def _predict_next_regime(current_regime: VolatilityRegime, 
                           indicators: Dict[str, float]) -> VolatilityRegime:
        """Predict most likely next regime."""
        vix_level = indicators["vix_proxy"]
        put_call_ratio = indicators["put_call_ratio"]
        term_structure_slope = indicators["term_structure_slope"]
        
        # Regime transition logic
        if current_regime == VolatilityRegime.LOW:
            # From low vol, usually goes to normal or high
            if put_call_ratio > 1.2 or term_structure_slope < -2:
                return VolatilityRegime.HIGH
            else:
                return VolatilityRegime.NORMAL
        
        elif current_regime == VolatilityRegime.NORMAL:
            # From normal, can go either direction
            if vix_level > 30 or put_call_ratio > 1.5:
                return VolatilityRegime.HIGH
            elif vix_level < 15 and put_call_ratio < 0.8:
                return VolatilityRegime.LOW
            else:
                return VolatilityRegime.NORMAL
        
        elif current_regime == VolatilityRegime.HIGH:
            # From high vol, usually goes to normal or extreme
            if vix_level > 40 or put_call_ratio > 2.0:
                return VolatilityRegime.EXTREME
            else:
                return VolatilityRegime.NORMAL
        
        elif current_regime == VolatilityRegime.EXTREME:
            # From extreme, usually reverts to high or normal
            if vix_level > 50:
                return VolatilityRegime.EXTREME  # Stay extreme
            else:
                return VolatilityRegime.HIGH
        
        return VolatilityRegime.NORMAL  # Default
    
    @staticmethod
    def predict_regime_change(current_analysis: RegimeAnalysis,
                            trend_indicators: Dict[str, float]) -> Dict[str, Any]:
        """Predict timing and direction of regime change."""
        prediction = {
            "change_expected_days": None,
            "confidence": current_analysis.regime_change_probability,
            "catalysts": [],
            "warning_signals": []
        }
        
        # Analyze potential catalysts
        catalysts = []
        warning_signals = []
        
        # VIX level analysis
        if current_analysis.vix_level > 35:
            catalysts.append("extreme_vix_exhaustion")
            warning_signals.append("vix_mean_reversion_due")
        elif current_analysis.vix_level < 12:
            catalysts.append("complacency_buildup")
            warning_signals.append("volatility_pickup_due")
        
        # Skew analysis
        if abs(current_analysis.skew_level) > 8:
            catalysts.append("extreme_skew")
            warning_signals.append("skew_normalization_expected")
        
        # Put-call ratio analysis
        if current_analysis.put_call_ratio > 1.8:
            catalysts.append("excessive_put_buying")
            warning_signals.append("potential_squeeze")
        elif current_analysis.put_call_ratio < 0.6:
            catalysts.append("excessive_call_buying")
            warning_signals.append("potential_correction")
        
        # Term structure analysis
        if current_analysis.term_structure_slope < -3:
            catalysts.append("inverted_term_structure")
            warning_signals.append("backwardation_unsustainable")
        
        # Estimate timing (simplified)
        if current_analysis.regime_change_probability > 70:
            prediction["change_expected_days"] = 7  # High probability = near term
        elif current_analysis.regime_change_probability > 50:
            prediction["change_expected_days"] = 21  # Medium probability = medium term
        else:
            prediction["change_expected_days"] = None  # Low probability
        
        prediction["catalysts"] = catalysts
        prediction["warning_signals"] = warning_signals
        
        return prediction
    
    @staticmethod
    def get_regime_trading_implications(regime_analysis: RegimeAnalysis) -> Dict[str, Any]:
        """Generate trading implications based on regime analysis."""
        implications = {
            "preferred_strategies": [],
            "risk_management": [],
            "market_expectations": [],
            "position_adjustments": []
        }
        
        if regime_analysis.current_regime == VolatilityRegime.LOW:
            implications["preferred_strategies"] = [
                "sell_volatility", "short_straddles", "iron_condors"
            ]
            implications["risk_management"] = [
                "tight_stop_losses", "position_sizing_conservative"
            ]
            implications["market_expectations"] = [
                "range_bound_trading", "vol_expansion_risk"
            ]
        
        elif regime_analysis.current_regime == VolatilityRegime.NORMAL:
            implications["preferred_strategies"] = [
                "directional_trades", "moderate_vol_selling"
            ]
            implications["risk_management"] = [
                "standard_position_sizing", "dynamic_hedging"
            ]
            implications["market_expectations"] = [
                "normal_price_action", "moderate_volatility"
            ]
        
        elif regime_analysis.current_regime == VolatilityRegime.HIGH:
            implications["preferred_strategies"] = [
                "buy_volatility", "long_straddles", "protective_puts"
            ]
            implications["risk_management"] = [
                "wider_stops", "reduced_position_size"
            ]
            implications["market_expectations"] = [
                "increased_volatility", "trending_moves"
            ]
        
        elif regime_analysis.current_regime == VolatilityRegime.EXTREME:
            implications["preferred_strategies"] = [
                "mean_reversion_trades", "vol_selling_at_extremes"
            ]
            implications["risk_management"] = [
                "maximum_caution", "minimal_exposure"
            ]
            implications["market_expectations"] = [
                "extreme_moves", "regime_change_imminent"
            ]
        
        return implications
    
    @staticmethod
    def get_compact_regime_summary(regime_analysis: RegimeAnalysis) -> Dict[str, Any]:
        """Generate compact regime summary for LLM consumption."""
        return {
            "current_regime": regime_analysis.current_regime.value,
            "regime_confidence": round(regime_analysis.regime_probability, 1),
            "change_probability": round(regime_analysis.regime_change_probability, 1),
            "next_likely_regime": regime_analysis.next_likely_regime.value,
            "vix_proxy": round(regime_analysis.vix_level, 1),
            "put_call_ratio": round(regime_analysis.put_call_ratio, 2),
            "skew_level": round(regime_analysis.skew_level, 1),
            "vol_of_vol": round(regime_analysis.vol_of_vol, 1),
            "regime_stability": "stable" if regime_analysis.regime_change_probability < 30 else "unstable"
        }