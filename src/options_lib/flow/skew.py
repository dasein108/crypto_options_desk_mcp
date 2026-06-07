"""Volatility skew analysis for options flow."""

import logging
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from .types import (
    OptionsChainData, VolatilitySkew, TermStructure, OptionType, OptionsFlowConfig
)


logger = logging.getLogger(__name__)


class SkewAnalysis:
    """Professional volatility skew and term structure analysis."""
    
    @staticmethod
    def validate_crypto_iv_range(iv_decimal: float, asset: str = "BTC") -> bool:
        """Validate that IV is within realistic crypto ranges.
        
        Args:
            iv_decimal: IV in decimal format (0.25 = 25%)
            asset: Crypto asset name
            
        Returns:
            True if IV is within realistic range
        """
        iv_percent = iv_decimal * 100
        
        # Crypto-specific IV ranges
        if asset.upper() == "BTC":
            return 15.0 <= iv_percent <= 300.0  # BTC: 15-300%
        elif asset.upper() == "ETH":
            return 20.0 <= iv_percent <= 400.0  # ETH: 20-400% 
        elif asset.upper() == "SOL":
            return 30.0 <= iv_percent <= 500.0  # SOL: 30-500%
        else:
            return 10.0 <= iv_percent <= 500.0  # Generic crypto range
    
    @staticmethod
    def calculate_volatility_skew(options_data: List[OptionsChainData], 
                                 expiry_date: str,
                                 underlying_price: float) -> VolatilitySkew:
        """Calculate volatility skew for a specific expiry."""
        # Filter options for this expiry
        expiry_options = [opt for opt in options_data if opt.expiry_date == expiry_date]
        
        if len(expiry_options) < 3:
            return VolatilitySkew(
                expiry_date=expiry_date,
                put_call_skew=0,
                risk_reversal_skew=0,
                atm_iv=0,
                iv_slope=0,
                skew_direction="flat",
                skew_extremeness=50
            )
        
        # Separate calls and puts
        calls = [opt for opt in expiry_options if opt.option_type == OptionType.CALL]
        puts = [opt for opt in expiry_options if opt.option_type == OptionType.PUT]
        
        # ATM IVs at SAME strike — used only for atm_iv. Bybit publishes ONE mark_iv
        # per (expiry, strike) so call_iv == put_iv at same strike → same-strike
        # put-call skew is structurally 0 and meaningless. Use risk-reversal (OTM
        # call vs OTM put) as the canonical put-call skew measure.
        atm_call_iv, atm_put_iv, atm_strike = SkewAnalysis._find_atm_iv_same_strike(
            calls, puts, underlying_price
        )

        # Risk reversal: OTM put IV - OTM call IV (proper directional skew)
        risk_reversal_skew = SkewAnalysis._calculate_risk_reversal_skew(
            calls, puts, underlying_price
        )

        # put_call_skew is the canonical directional skew on Bybit (= risk reversal)
        put_call_skew = risk_reversal_skew
        
        # Calculate ATM IV
        atm_iv = (atm_call_iv + atm_put_iv) / 2 if atm_call_iv > 0 and atm_put_iv > 0 else 0
        
        # Calculate IV slope (how IV changes with moneyness)
        iv_slope = SkewAnalysis._calculate_iv_slope(expiry_options, underlying_price)
        
        # Determine skew direction (crypto-appropriate thresholds)
        # FIXED: Reduced threshold to better detect BTC's typical downside skew
        # BTC usually has 1-3% downside skew, so 5% threshold was too high
        if put_call_skew > 0.01:  # 1% threshold - BTC typically has downside skew
            skew_direction = "put_heavy"
        elif put_call_skew < -0.01:
            skew_direction = "call_heavy"
        else:
            skew_direction = "flat"
        
        # Calculate skew extremeness (0-100 percentile)
        skew_extremeness = SkewAnalysis._assess_skew_extremeness(put_call_skew, risk_reversal_skew)
        
        return VolatilitySkew(
            expiry_date=expiry_date,
            put_call_skew=put_call_skew,
            risk_reversal_skew=risk_reversal_skew,
            atm_iv=atm_iv,
            iv_slope=iv_slope,
            skew_direction=skew_direction,
            skew_extremeness=skew_extremeness
        )
    
    @staticmethod
    def _find_atm_iv_same_strike(calls: List[OptionsChainData], puts: List[OptionsChainData], 
                               underlying_price: float) -> Tuple[float, float, float]:
        """Find ATM implied volatility for SAME strike (proper skew calculation).
        
        Returns:
            (call_iv, put_iv, strike) - All from the same ATM strike
        """
        if not calls or not puts:
            return 0.0, 0.0, underlying_price
        
        # Filter for valid IVs
        valid_calls = [opt for opt in calls if opt.mark_iv > 0]
        valid_puts = [opt for opt in puts if opt.mark_iv > 0]
        
        if not valid_calls or not valid_puts:
            return 0.0, 0.0, underlying_price
        
        # Find strikes that have both call and put
        call_strikes = {opt.strike: opt for opt in valid_calls}
        put_strikes = {opt.strike: opt for opt in valid_puts}
        
        # Find common strikes
        common_strikes = set(call_strikes.keys()) & set(put_strikes.keys())
        
        if not common_strikes:
            return 0.0, 0.0, underlying_price
        
        # Find the strike closest to spot price
        atm_strike = min(common_strikes, key=lambda strike: abs(strike - underlying_price))
        
        call_option = call_strikes[atm_strike]
        put_option = put_strikes[atm_strike]
        
        return call_option.mark_iv, put_option.mark_iv, atm_strike
    
    @staticmethod
    def _find_atm_iv(options: List[OptionsChainData], underlying_price: float) -> float:
        """Find ATM (at-the-money) implied volatility."""
        if not options:
            return 0
        
        # Filter options with valid IV first
        valid_options = [opt for opt in options if opt.mark_iv > 0]
        if not valid_options:
            return 0
        
        # Find closest strike to current price among valid options
        closest_option = min(
            valid_options,
            key=lambda opt: abs(opt.strike - underlying_price)
        )
        
        atm_iv = closest_option.mark_iv
        
        # Extract asset from symbol for validation
        asset = "BTC"  # Default to BTC for crypto options
        if hasattr(closest_option, 'underlying_symbol') and closest_option.underlying_symbol:
            asset = closest_option.underlying_symbol
        elif hasattr(closest_option, 'symbol') and closest_option.symbol:
            # Extract from symbol like "BTC-30DEC24-70000-C"
            symbol_parts = closest_option.symbol.split('-')
            if symbol_parts:
                asset = symbol_parts[0]
        
        # Validate IV range - for crypto, minimum realistic IV is 15% for BTC
        if atm_iv < 0.15:  # Less than 15% is unrealistic for crypto
            iv_percent = atm_iv * 100
            logger.warning(
                f"Unrealistically low {asset} ATM IV: {iv_percent:.1f}% - "
                f"Minimum expected for crypto: 15%"
            )
            # Don't return 0, but flag as potentially bad data
        
        return atm_iv
    
    @staticmethod
    def _calculate_risk_reversal_skew(calls: List[OptionsChainData], 
                                    puts: List[OptionsChainData],
                                    underlying_price: float) -> float:
        """Calculate risk reversal skew using delta-equivalent strikes."""
        if not calls or not puts:
            return 0
        
        # Filter for options with valid IVs
        valid_calls = [opt for opt in calls if opt.mark_iv > 0]
        valid_puts = [opt for opt in puts if opt.mark_iv > 0]
        
        if not valid_calls or not valid_puts:
            return 0
        
        # For crypto options, use wider OTM ranges due to higher volatility
        # OTM puts (strikes below spot) and OTM calls (strikes above spot)
        otm_puts = [opt for opt in valid_puts if opt.strike < underlying_price * 0.90]  # 10% OTM puts
        otm_calls = [opt for opt in valid_calls if opt.strike > underlying_price * 1.10]  # 10% OTM calls
        
        if not otm_puts or not otm_calls:
            # Fallback to smaller OTM ranges if no options found
            otm_puts = [opt for opt in valid_puts if opt.strike < underlying_price * 0.95]  # 5% OTM puts
            otm_calls = [opt for opt in valid_calls if opt.strike > underlying_price * 1.05]  # 5% OTM calls
        
        if not otm_puts or not otm_calls:
            return 0
        
        # Select puts and calls with similar distance from ATM (crypto-appropriate ranges)
        target_moneyness_put = 0.90   # 90% of spot (10% OTM put)
        target_moneyness_call = 1.10  # 110% of spot (10% OTM call)
        
        best_put = min(
            otm_puts,
            key=lambda opt: abs(opt.strike / underlying_price - target_moneyness_put)
        )
        
        best_call = min(
            otm_calls,
            key=lambda opt: abs(opt.strike / underlying_price - target_moneyness_call)
        )
        
        # Ensure both IVs are reasonable before calculating skew
        if best_put.mark_iv > 0 and best_call.mark_iv > 0:
            return best_put.mark_iv - best_call.mark_iv
        else:
            return 0
    
    @staticmethod
    def _calculate_iv_slope(options: List[OptionsChainData], underlying_price: float) -> float:
        """Calculate how IV changes with moneyness (slope)."""
        if len(options) < 3:
            return 0
        
        # Calculate moneyness and IV pairs
        moneyness_iv_pairs = []
        for option in options:
            if option.mark_iv > 0:
                moneyness = option.strike / underlying_price
                moneyness_iv_pairs.append((moneyness, option.mark_iv))
        
        if len(moneyness_iv_pairs) < 3:
            return 0
        
        # Fit linear regression to get slope
        moneyness_values = [pair[0] for pair in moneyness_iv_pairs]
        iv_values = [pair[1] for pair in moneyness_iv_pairs]
        
        # Simple linear regression
        n = len(moneyness_values)
        sum_x = sum(moneyness_values)
        sum_y = sum(iv_values)
        sum_xy = sum(x * y for x, y in zip(moneyness_values, iv_values))
        sum_x2 = sum(x * x for x in moneyness_values)
        
        if n * sum_x2 - sum_x * sum_x == 0:
            return 0
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        return slope
    
    @staticmethod
    def _assess_skew_extremeness(put_call_skew: float, risk_reversal_skew: float) -> float:
        """Assess how extreme the current skew is (0-100 scale).
        
        Crypto-specific ranges (decimal format from Bybit):
        - Put-call skew: -0.30 to +0.50 (typical crypto range)
        - Risk reversal skew: -0.20 to +0.60 (crypto volatility premium)
        """
        # CRYPTO-SPECIFIC ranges (inputs are in decimal format)
        # Put-call skew: -30% to +50% in decimal (more extreme than equities)
        pc_normalized = abs(put_call_skew) / 0.50 * 50  # 50% = max typical for crypto
        
        # Risk reversal skew: -20% to +60% in decimal (crypto put premium)
        rr_normalized = abs(risk_reversal_skew) / 0.60 * 50  # 60% = max typical for crypto
        
        # Combine and cap at 100
        combined_extremeness = min(pc_normalized + rr_normalized, 100)
        
        return combined_extremeness
    
    @staticmethod
    def analyze_term_structure(options_data: List[OptionsChainData], 
                              underlying_price: float,
                              base_coin: str = "UNKNOWN") -> TermStructure:
        """Analyze volatility term structure across expiries."""
        # Group options by expiry
        expiry_groups = {}
        for option in options_data:
            expiry = option.expiry_date
            if expiry not in expiry_groups:
                expiry_groups[expiry] = []
            expiry_groups[expiry].append(option)
        
        # Analyze skew for each expiry
        expiry_analysis = []
        for expiry, expiry_options in expiry_groups.items():
            if len(expiry_options) >= 3:  # Minimum options needed
                skew = SkewAnalysis.calculate_volatility_skew(
                    options_data, expiry, underlying_price
                )
                expiry_analysis.append(skew)
        
        # Sort by expiry date
        expiry_analysis.sort(key=lambda x: x.expiry_date)
        
        # Calculate term structure metrics
        front_month_iv = 0
        back_month_iv = 0
        if expiry_analysis:
            front_month_iv = expiry_analysis[0].atm_iv
            if len(expiry_analysis) > 1:
                back_month_iv = expiry_analysis[-1].atm_iv
            else:
                back_month_iv = front_month_iv
        
        # Calculate term structure slope
        term_structure_slope = back_month_iv - front_month_iv
        
        # Identify calendar spread opportunities
        calendar_spread_opportunities = SkewAnalysis._find_calendar_opportunities(expiry_analysis)
        
        return TermStructure(
            base_coin=base_coin,
            underlying_price=underlying_price,
            expiry_analysis=expiry_analysis,
            front_month_iv=front_month_iv,
            back_month_iv=back_month_iv,
            term_structure_slope=term_structure_slope,
            calendar_spread_opportunities=calendar_spread_opportunities
        )
    
    @staticmethod
    def _find_calendar_opportunities(expiry_analysis: List[VolatilitySkew]) -> List[Dict[str, Any]]:
        """Identify calendar spread opportunities based on term structure anomalies."""
        opportunities = []
        
        if len(expiry_analysis) < 2:
            return opportunities
        
        # Compare adjacent expiries for IV inversions
        for i in range(len(expiry_analysis) - 1):
            front_expiry = expiry_analysis[i]
            back_expiry = expiry_analysis[i + 1]
            
            iv_diff = back_expiry.atm_iv - front_expiry.atm_iv
            
            # Normal term structure: longer expiry = higher IV
            # Opportunities arise when this is inverted or extremely steep
            
            if iv_diff < -0.02:  # Back month IV significantly lower (inverted)
                opportunities.append({
                    "type": "short_calendar",
                    "front_expiry": front_expiry.expiry_date,
                    "back_expiry": back_expiry.expiry_date,
                    "iv_differential": round(iv_diff, 4),
                    "opportunity_score": min(abs(iv_diff) * 100, 10),
                    "description": "Term structure inverted - consider short calendar"
                })
            
            elif iv_diff > 0.05:  # Extremely steep term structure
                opportunities.append({
                    "type": "long_calendar",
                    "front_expiry": front_expiry.expiry_date,
                    "back_expiry": back_expiry.expiry_date,
                    "iv_differential": round(iv_diff, 4),
                    "opportunity_score": min(iv_diff * 100, 10),
                    "description": "Steep term structure - consider long calendar"
                })
        
        # Sort by opportunity score
        opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)
        return opportunities[:3]  # Top 3 opportunities
    
    @staticmethod
    def calculate_vol_trigger_levels(options_data: List[OptionsChainData],
                                   underlying_price: float) -> List[float]:
        """Calculate price levels that could trigger volatility regime changes."""
        if not options_data:
            return []
        
        trigger_levels = []
        
        # Find strikes with high IV relative to neighbors
        # Group by expiry first
        expiry_groups = {}
        for option in options_data:
            expiry = option.expiry_date
            if expiry not in expiry_groups:
                expiry_groups[expiry] = []
            expiry_groups[expiry].append(option)
        
        for expiry, expiry_options in expiry_groups.items():
            if len(expiry_options) < 5:
                continue
            
            # Sort by strike
            sorted_options = sorted(expiry_options, key=lambda x: x.strike)
            
            # Find IV spikes that could indicate trigger levels
            for i in range(1, len(sorted_options) - 1):
                current_option = sorted_options[i]
                prev_option = sorted_options[i - 1]
                next_option = sorted_options[i + 1]
                
                # Check for IV spike
                current_iv = current_option.mark_iv
                avg_neighbor_iv = (prev_option.mark_iv + next_option.mark_iv) / 2
                
                if current_iv > avg_neighbor_iv * 1.2:  # 20% higher than neighbors
                    # This strike might be a vol trigger level
                    distance_from_spot = abs(current_option.strike - underlying_price) / underlying_price
                    
                    # Only consider levels within reasonable range
                    if distance_from_spot <= 0.15:  # Within 15%
                        trigger_levels.append(current_option.strike)
        
        # Add standard deviation levels based on ATM vol
        atm_iv = SkewAnalysis._find_atm_iv(options_data, underlying_price)
        if atm_iv > 0:
            # Convert to daily volatility
            daily_vol = atm_iv / np.sqrt(365)
            
            # 1-sigma and 2-sigma moves
            for sigma in [1, 2]:
                move = underlying_price * daily_vol * sigma
                trigger_levels.extend([
                    underlying_price + move,
                    underlying_price - move
                ])
        
        # Remove duplicates and sort
        trigger_levels = sorted(list(set(trigger_levels)))
        
        # Filter to reasonable range
        filtered_levels = [
            level for level in trigger_levels
            if 0.8 * underlying_price <= level <= 1.2 * underlying_price
        ]
        
        return filtered_levels
    
    @staticmethod
    def get_compact_skew_summary(term_structure: TermStructure) -> Dict[str, Any]:
        """Generate compact skew summary for LLM consumption.
        
        Note: Bybit returns IV in decimal format (0.135 = 13.5%), so we convert to percentage for display.
        """
        # Overall skew assessment
        avg_put_call_skew = np.mean([exp.put_call_skew for exp in term_structure.expiry_analysis]) if term_structure.expiry_analysis else 0
        avg_extremeness = np.mean([exp.skew_extremeness for exp in term_structure.expiry_analysis]) if term_structure.expiry_analysis else 0
        
        # Dominant skew direction
        skew_directions = [exp.skew_direction for exp in term_structure.expiry_analysis]
        dominant_direction = max(set(skew_directions), key=skew_directions.count) if skew_directions else "flat"
        
        # CRITICAL FIX: Bybit IV is in decimal format (0.135 = 13.5%)
        # Convert to percentage for proper display
        front_month_iv_pct = term_structure.front_month_iv * 100
        back_month_iv_pct = term_structure.back_month_iv * 100
        
        # Validate crypto IV ranges and skew realism for BTC
        data_quality = "validated"
        if front_month_iv_pct < 20 or back_month_iv_pct < 20:
            data_quality = "warning_low_iv"
            logger.warning(f"Potentially unrealistic BTC IV detected: Front={front_month_iv_pct:.1f}%, Back={back_month_iv_pct:.1f}%")
        
        # Check for unrealistic flat skew (BTC almost always has downside skew)
        if abs(avg_put_call_skew) < 0.01 and len(term_structure.expiry_analysis) > 0:
            if data_quality == "validated":
                data_quality = "warning_flat_skew"
            else:
                data_quality = "warning_multiple_issues"
            logger.warning(f"Unusually flat skew detected for BTC: {avg_put_call_skew:.4f} - Expected downside skew")
        
        return {
            "front_month_iv": round(front_month_iv_pct, 1),
            "back_month_iv": round(back_month_iv_pct, 1),
            "term_structure_slope": round(term_structure.term_structure_slope * 100, 2),
            "avg_put_call_skew": round(avg_put_call_skew * 100, 2),
            "dominant_skew_direction": dominant_direction,
            "skew_extremeness": round(avg_extremeness, 1),
            "calendar_opportunities": len(term_structure.calendar_spread_opportunities),
            "expiries_analyzed": len(term_structure.expiry_analysis),
            "term_structure_regime": "contango" if term_structure.term_structure_slope > 0 else "backwardation",
            "data_quality": data_quality
        }