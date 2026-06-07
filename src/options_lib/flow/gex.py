"""Gamma Exposure (GEX) analysis for options flow."""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from .types import (
    OptionsChainData, GEXLevels, GEXAnalysis, FlowDirection,
    OptionsFlowConfig
)
from .helpers import group_by_strike


class GammaExposure:
    """Professional Gamma Exposure analysis for market makers and flow."""
    
    @staticmethod
    def calculate_gex_by_strike(options_data: List[OptionsChainData], 
                               config: Optional[OptionsFlowConfig] = None) -> List[GEXLevels]:
        """Calculate Gamma Exposure by strike level."""
        if config is None:
            config = OptionsFlowConfig()
        
        if not options_data:
            return []

        strikes_data = group_by_strike(options_data)
        gex_levels = []

        for strike, data in strikes_data.items():
            # Calculate call GEX
            call_gex = 0
            call_oi = 0
            for call in data['calls']:
                # GEX = Gamma * Open Interest * Contract Size * Spot^2
                # For crypto options: 1 contract = 1 BTC/ETH/SOL (not 100 shares like equities)
                # Positive for calls (market makers are short gamma)
                contract_size = 1.0  # 1 BTC per contract for crypto options
                gex_contribution = call.gamma * call.open_interest * contract_size * (call.underlying_price ** 2)
                call_gex += gex_contribution
                call_oi += call.open_interest
            
            # Calculate put GEX
            put_gex = 0
            put_oi = 0
            for put in data['puts']:
                # GEX = Gamma * Open Interest * Contract Size * Spot^2
                # Negative for puts (market makers are short gamma)
                contract_size = 1.0  # 1 BTC per contract for crypto options
                gex_contribution = -put.gamma * put.open_interest * contract_size * (put.underlying_price ** 2)
                put_gex += gex_contribution
                put_oi += put.open_interest
            
            net_gex = call_gex + put_gex
            total_oi = call_oi + put_oi
            
            gex_levels.append(GEXLevels(
                strike=strike,
                call_gex=call_gex,
                put_gex=put_gex,
                net_gex=net_gex,
                call_oi=call_oi,
                put_oi=put_oi,
                total_oi=total_oi
            ))
        
        # Filter by spot_gamma_cutoff — remove strikes with negligible GEX
        if gex_levels:
            max_abs_gex = max(abs(g.net_gex) for g in gex_levels) or 1.0
            cutoff = config.spot_gamma_cutoff * max_abs_gex
            gex_levels = [g for g in gex_levels if abs(g.net_gex) >= cutoff]

        # Sort by strike
        gex_levels.sort(key=lambda x: x.strike)
        return gex_levels
    
    @staticmethod
    def find_gex_walls(gex_levels: List[GEXLevels], 
                       underlying_price: float,
                       threshold_percentile: float = 0.8) -> Dict[str, List[Tuple[float, float]]]:
        """Identify significant GEX walls that could act as support/resistance."""
        if not gex_levels:
            return {"resistance": [], "support": []}
        
        # Calculate threshold based on GEX magnitude
        all_gex_values = [abs(level.net_gex) for level in gex_levels]
        threshold = np.percentile(all_gex_values, threshold_percentile * 100) if all_gex_values else 0
        
        resistance_levels = []
        support_levels = []
        
        for level in gex_levels:
            # Significant positive GEX (call walls) = resistance
            if level.net_gex > threshold:
                resistance_levels.append((level.strike, level.net_gex))
            
            # Significant negative GEX (put walls) = support  
            elif level.net_gex < -threshold:
                support_levels.append((level.strike, abs(level.net_gex)))
        
        # Filter by proximity to current price (within 20%)
        price_range = underlying_price * 0.2
        
        resistance_levels = [
            (strike, gex) for strike, gex in resistance_levels
            if underlying_price <= strike <= underlying_price + price_range
        ]
        
        support_levels = [
            (strike, gex) for strike, gex in support_levels
            if underlying_price - price_range <= strike <= underlying_price
        ]
        
        # Sort by proximity to current price
        resistance_levels.sort(key=lambda x: x[0])
        support_levels.sort(key=lambda x: x[0], reverse=True)
        
        return {
            "resistance": resistance_levels,
            "support": support_levels
        }
    
    @staticmethod
    def calculate_gex_flip_level(gex_levels: List[GEXLevels], 
                                underlying_price: float) -> Optional[float]:
        """Find the price level where net GEX changes from negative to positive (or vice versa)."""
        if len(gex_levels) < 2:
            return None
        
        # Sort by strike
        sorted_levels = sorted(gex_levels, key=lambda x: x.strike)
        
        # Find zero-crossing of net GEX
        for i in range(len(sorted_levels) - 1):
            current_gex = sorted_levels[i].net_gex
            next_gex = sorted_levels[i + 1].net_gex
            
            # Check for sign change
            if (current_gex <= 0 <= next_gex) or (current_gex >= 0 >= next_gex):
                # Linear interpolation to find exact zero crossing
                current_strike = sorted_levels[i].strike
                next_strike = sorted_levels[i + 1].strike
                
                if next_gex != current_gex:
                    # Interpolate
                    flip_strike = current_strike + (next_strike - current_strike) * (0 - current_gex) / (next_gex - current_gex)
                    return flip_strike
                else:
                    return current_strike
        
        return None
    
    @staticmethod
    def analyze_gex_impact(gex_levels: List[GEXLevels],
                          underlying_price: float,
                          config: Optional[OptionsFlowConfig] = None,
                          base_coin: str = "") -> GEXAnalysis:
        """Comprehensive GEX analysis with market impact assessment."""
        if config is None:
            config = OptionsFlowConfig()
        
        if not gex_levels:
            return GEXAnalysis(
                base_coin=base_coin,
                underlying_price=underlying_price,
                analysis_timestamp=datetime.now(),
                gex_levels=[],
                total_net_gex=0,
                gex_flip_level=underlying_price,
                resistance_levels=[],
                support_levels=[],
                suppression_zones=[],
                acceleration_zones=[],
                expected_max_move=0,
                vol_suppression_active=False,
                breakout_probability=0
            )
        
        # Calculate aggregate metrics
        total_net_gex = sum(level.net_gex for level in gex_levels)
        
        # Find GEX flip level
        gex_flip_level = GammaExposure.calculate_gex_flip_level(gex_levels, underlying_price)
        if gex_flip_level is None:
            gex_flip_level = underlying_price
        
        # Find walls
        walls = GammaExposure.find_gex_walls(gex_levels, underlying_price)
        resistance_levels = walls["resistance"]
        support_levels = walls["support"]
        
        # Identify suppression and acceleration zones
        suppression_zones = []
        acceleration_zones = []
        
        for i in range(len(gex_levels) - 1):
            current_level = gex_levels[i]
            next_level = gex_levels[i + 1]
            
            strike_range = (current_level.strike, next_level.strike)
            avg_gex = (current_level.net_gex + next_level.net_gex) / 2
            
            # CORRECTED GEX INTERPRETATION:
            # High positive GEX = suppression (dealers short gamma, sell rallies, buy dips = mean reversion)
            if avg_gex > abs(total_net_gex) * 0.1:
                suppression_zones.append(strike_range)
            
            # High negative GEX = acceleration (dealers long gamma, buy rallies, sell dips = trend following)  
            elif avg_gex < -abs(total_net_gex) * 0.1:
                acceleration_zones.append(strike_range)
        
        # Calculate expected maximum move based on GEX distribution
        expected_max_move = GammaExposure._calculate_expected_max_move(
            gex_levels, underlying_price
        )
        
        # Assess volatility suppression
        vol_suppression_active = GammaExposure._assess_vol_suppression(
            gex_levels, underlying_price, total_net_gex
        )
        
        # Calculate breakout probability
        breakout_probability = GammaExposure._calculate_breakout_probability(
            gex_levels, underlying_price, resistance_levels, support_levels
        )
        
        return GEXAnalysis(
            base_coin=base_coin,
            underlying_price=underlying_price,
            analysis_timestamp=datetime.now(),
            gex_levels=gex_levels,
            total_net_gex=total_net_gex,
            gex_flip_level=gex_flip_level,
            resistance_levels=resistance_levels,
            support_levels=support_levels,
            suppression_zones=suppression_zones,
            acceleration_zones=acceleration_zones,
            expected_max_move=expected_max_move,
            vol_suppression_active=vol_suppression_active,
            breakout_probability=breakout_probability
        )
    
    @staticmethod
    def _calculate_expected_max_move(gex_levels: List[GEXLevels], 
                                   underlying_price: float) -> float:
        """Calculate GEX-based resistance/support range, NOT implied volatility expected move.
        
        NOTE: This method calculates distance to key GEX levels, which represents 
        gamma walls/resistance zones. For true expected moves from implied volatility,
        use: Expected Daily Move = ATM_IV / sqrt(365)
        
        This is intentionally kept as GEX-based analysis since it serves a different purpose.
        """
        if not gex_levels:
            return 2.0  # Reduced default - was 5.0% which is unrealistic for daily moves
        
        # Find the strikes with highest absolute GEX
        max_positive_gex = max((level.net_gex for level in gex_levels), default=0)
        max_negative_gex = min((level.net_gex for level in gex_levels), default=0)
        
        upside_resistance = None
        downside_support = None
        
        # Find strikes corresponding to max GEX levels
        for level in gex_levels:
            if level.net_gex == max_positive_gex and level.strike > underlying_price:
                upside_resistance = level.strike
            if level.net_gex == max_negative_gex and level.strike < underlying_price:
                downside_support = level.strike
        
        # Calculate move as average distance to key GEX levels (not IV-based expected move)
        moves = []
        if upside_resistance:
            moves.append(abs(upside_resistance - underlying_price) / underlying_price)
        if downside_support:
            moves.append(abs(underlying_price - downside_support) / underlying_price)
        
        # Cap at reasonable levels for GEX-based ranges
        gex_range = np.mean(moves) * 100 if moves else 2.0
        return min(gex_range, 10.0)  # Cap at 10% to prevent unrealistic values
    
    @staticmethod
    def _assess_vol_suppression(gex_levels: List[GEXLevels], 
                              underlying_price: float,
                              total_net_gex: float) -> bool:
        """Assess if volatility suppression is likely active."""
        # CORRECTED: Volatility suppression occurs when:
        # 1. Price is between significant call and put walls
        # 2. Net GEX is highly POSITIVE (dealers are SHORT gamma, sell rallies/buy dips)
        
        # Find nearby walls
        nearby_call_wall = any(
            level.strike > underlying_price and level.net_gex > 0
            for level in gex_levels
            if abs(level.strike - underlying_price) / underlying_price < 0.1
        )
        
        nearby_put_wall = any(
            level.strike < underlying_price and level.net_gex < 0  
            for level in gex_levels
            if abs(level.strike - underlying_price) / underlying_price < 0.1
        )
        
        # High POSITIVE net GEX suggests dealers are SHORT gamma (suppression)
        high_positive_gex = total_net_gex > 0 and abs(total_net_gex) > 1000000  # $1M threshold
        
        return nearby_call_wall and nearby_put_wall and high_positive_gex
    
    @staticmethod
    def _calculate_breakout_probability(gex_levels: List[GEXLevels],
                                      underlying_price: float,
                                      resistance_levels: List[Tuple[float, float]],
                                      support_levels: List[Tuple[float, float]]) -> float:
        """Calculate qualitative breakout likelihood based on proximity to GEX levels.
        
        NOTE: This returns a heuristic score, NOT a statistical probability.
        True breakout probabilities require:
        - Historical regime statistics
        - Backtested compression → expansion transitions  
        - Statistical significance testing
        """
        if not resistance_levels and not support_levels:
            return 50.0  # Neutral if no clear levels
        
        # Distance to nearest resistance/support
        nearest_resistance = min(
            (strike for strike, _ in resistance_levels if strike > underlying_price),
            default=underlying_price * 1.1
        )
        nearest_support = max(
            (strike for strike, _ in support_levels if strike < underlying_price),
            default=underlying_price * 0.9
        )
        
        # Distance ratios
        upside_distance = (nearest_resistance - underlying_price) / underlying_price
        downside_distance = (underlying_price - nearest_support) / underlying_price
        
        # Heuristic scores based on proximity (NOT statistical probabilities)
        min_distance = min(upside_distance, downside_distance)
        if min_distance < 0.02:  # Within 2%
            return 70.0  # "High likelihood" - close to key level
        elif min_distance < 0.05:  # Within 5%  
            return 55.0  # "Moderate likelihood" 
        else:
            return 35.0  # "Low likelihood" - far from levels
    
    @staticmethod
    def get_compact_gex_summary(gex_analysis: GEXAnalysis) -> Dict[str, Any]:
        """Generate compact GEX summary for LLM consumption."""
        net_gex_millions = gex_analysis.total_net_gex / 1000000
        
        # Validate GEX magnitude for BTC (should be $50M-$2B range for realistic markets)
        data_quality = "good"
        if abs(net_gex_millions) < 10:  # Less than $10M is suspiciously low for BTC
            data_quality = "warning_low_magnitude"
        elif abs(net_gex_millions) > 5000:  # Over $5B is suspiciously high
            data_quality = "warning_high_magnitude"
        
        return {
            "net_gex_millions": round(net_gex_millions, 2),
            "gex_regime": "suppression" if gex_analysis.vol_suppression_active else "neutral",
            "flip_level": round(gex_analysis.gex_flip_level, 2),
            "key_resistance": gex_analysis.resistance_levels[0][0] if gex_analysis.resistance_levels else None,
            "key_support": gex_analysis.support_levels[0][0] if gex_analysis.support_levels else None,
            "gex_range_pct": round(gex_analysis.expected_max_move, 2),  # Renamed: this is GEX wall range, not IV-based expected move
            "breakout_probability": round(gex_analysis.breakout_probability, 1),
            "total_strikes_analyzed": len(gex_analysis.gex_levels),
            "data_quality": data_quality
        }