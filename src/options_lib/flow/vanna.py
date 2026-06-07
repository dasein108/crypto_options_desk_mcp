"""Vanna analysis for options flow and volatility impact."""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from .types import (
    OptionsChainData, VannaExposure, VannaAnalysis as VannaResult, FlowDirection,
    OptionsFlowConfig
)
from .helpers import group_by_strike


class VannaAnalyzer:
    """Professional Vanna exposure analysis for flow prediction."""
    
    VANNA_UNIT = "delta_per_vol_point"
    VOL_IMPACT_UNIT = "vol_points_per_5pct_move"
    
    @staticmethod
    def calculate_vanna_by_strike(options_data: List[OptionsChainData],
                                 config: Optional[OptionsFlowConfig] = None) -> List[VannaExposure]:
        """Calculate Vanna exposure by strike level."""
        if config is None:
            config = OptionsFlowConfig()
        
        if not options_data:
            return []

        strikes_data = group_by_strike(options_data)
        vanna_exposures = []

        for strike, data in strikes_data.items():
            # Calculate call Vanna
            call_vanna = 0
            call_oi = 0
            for call in data['calls']:
                # Vanna ≈ dDelta/dIV (delta per 1 vol point)
                vanna_per_contract = (
                    call.vega * call.delta / call.underlying_price
                    if call.underlying_price > 0 else 0
                )
                call_vanna += vanna_per_contract * call.open_interest
                call_oi += call.open_interest
            
            # Calculate put Vanna  
            put_vanna = 0
            put_oi = 0
            for put in data['puts']:
                # For puts: negative vanna when ITM, positive when OTM
                vanna_per_contract = (
                    put.vega * put.delta / put.underlying_price
                    if put.underlying_price > 0 else 0
                )
                put_vanna += vanna_per_contract * put.open_interest
                put_oi += put.open_interest
            
            net_vanna = call_vanna + put_vanna
            
            # Filter out negligible vanna
            if abs(net_vanna) >= config.vanna_threshold:
                vanna_exposures.append(VannaExposure(
                    strike=strike,
                    call_vanna=call_vanna,
                    put_vanna=put_vanna,
                    net_vanna=net_vanna,
                    call_oi=call_oi,
                    put_oi=put_oi
                ))
        
        # Sort by strike
        vanna_exposures.sort(key=lambda x: x.strike)
        return vanna_exposures
    
    @staticmethod
    def analyze_vanna_impact(vanna_exposures: List[VannaExposure], 
                           underlying_price: float,
                           base_coin: str = "UNKNOWN") -> VannaResult:
        """Comprehensive Vanna analysis with flow predictions."""
        if not vanna_exposures:
            return VannaResult(
                base_coin=base_coin,
                underlying_price=underlying_price,
                analysis_timestamp=datetime.now(),
                vanna_exposures=[],
                total_vanna=0,
                vanna_trigger_up=underlying_price * 1.05,
                vanna_trigger_down=underlying_price * 0.95,
                predicted_flow=FlowDirection.NEUTRAL,
                flow_strength=0,
                vol_impact_up=0,
                vol_impact_down=0
            )
        
        # Calculate total vanna
        total_vanna = sum(exposure.net_vanna for exposure in vanna_exposures)
        
        # Find vanna trigger levels
        vanna_trigger_up, vanna_trigger_down = VannaAnalyzer._find_vanna_triggers(
            vanna_exposures, underlying_price
        )
        
        # Predict flow direction based on vanna positioning
        predicted_flow, flow_strength = VannaAnalyzer._predict_flow_from_vanna(
            vanna_exposures, underlying_price, total_vanna
        )
        
        # Calculate volatility impact expectations
        vol_impact_up, vol_impact_down = VannaAnalyzer._calculate_vol_impact(
            vanna_exposures, underlying_price
        )
        
        return VannaResult(
            base_coin=base_coin,
            underlying_price=underlying_price,
            analysis_timestamp=datetime.now(),
            vanna_exposures=vanna_exposures,
            total_vanna=total_vanna,
            vanna_trigger_up=vanna_trigger_up,
            vanna_trigger_down=vanna_trigger_down,
            predicted_flow=predicted_flow,
            flow_strength=flow_strength,
            vol_impact_up=vol_impact_up,
            vol_impact_down=vol_impact_down
        )
    
    @staticmethod
    def _find_vanna_triggers(vanna_exposures: List[VannaExposure], 
                           underlying_price: float) -> Tuple[float, float]:
        """Find price levels where vanna effects become significant."""
        if not vanna_exposures:
            return underlying_price * 1.05, underlying_price * 0.95
        
        # Sort exposures by strike
        sorted_exposures = sorted(vanna_exposures, key=lambda x: x.strike)
        
        # Find levels with significant positive/negative vanna
        upside_triggers = []
        downside_triggers = []
        
        total_abs_vanna = sum(abs(exp.net_vanna) for exp in vanna_exposures)
        vanna_threshold = total_abs_vanna * 0.1  # 10% of total vanna
        
        for exposure in sorted_exposures:
            if abs(exposure.net_vanna) >= vanna_threshold:
                if exposure.strike > underlying_price:
                    upside_triggers.append((exposure.strike, exposure.net_vanna))
                elif exposure.strike < underlying_price:
                    downside_triggers.append((exposure.strike, exposure.net_vanna))
        
        # Find closest significant levels
        vanna_trigger_up = underlying_price * 1.05  # Default
        if upside_triggers:
            vanna_trigger_up = min(strike for strike, vanna in upside_triggers)
        
        vanna_trigger_down = underlying_price * 0.95  # Default
        if downside_triggers:
            vanna_trigger_down = max(strike for strike, vanna in downside_triggers)
        
        return vanna_trigger_up, vanna_trigger_down
    
    @staticmethod
    def _predict_flow_from_vanna(vanna_exposures: List[VannaExposure],
                               underlying_price: float,
                               total_vanna: float) -> Tuple[FlowDirection, float]:
        """Predict options flow direction based on vanna positioning."""
        if not vanna_exposures:
            return FlowDirection.NEUTRAL, 0
        
        # Analyze vanna distribution around current price
        nearby_range = underlying_price * 0.1  # 10% range
        
        nearby_vanna = sum(
            exp.net_vanna for exp in vanna_exposures
            if abs(exp.strike - underlying_price) <= nearby_range
        )
        
        # Analyze asymmetry in vanna distribution
        upside_vanna = sum(
            exp.net_vanna for exp in vanna_exposures
            if exp.strike > underlying_price
        )
        
        downside_vanna = sum(
            exp.net_vanna for exp in vanna_exposures
            if exp.strike < underlying_price
        )
        
        vanna_asymmetry = upside_vanna - downside_vanna
        
        # Flow prediction logic:
        # Positive vanna above spot + negative vanna below = bullish flow expected
        # (Vol will rise if we move up, fall if we move down)
        
        flow_strength = 0
        predicted_flow = FlowDirection.NEUTRAL
        
        if total_vanna != 0:
            # Calculate flow strength (0-100 scale)
            flow_strength = min(abs(vanna_asymmetry) / abs(total_vanna) * 100, 100)
            
            # Strong positive asymmetry suggests bullish flow potential
            if vanna_asymmetry > abs(total_vanna) * 0.2:
                predicted_flow = FlowDirection.BULLISH
            elif vanna_asymmetry < -abs(total_vanna) * 0.2:
                predicted_flow = FlowDirection.BEARISH
            else:
                predicted_flow = FlowDirection.NEUTRAL
        
        return predicted_flow, flow_strength
    
    @staticmethod
    def _calculate_vol_impact(vanna_exposures: List[VannaExposure],
                            underlying_price: float) -> Tuple[float, float]:
        """Calculate expected volatility impact of price moves."""
        if not vanna_exposures:
            return 0, 0
        
        # Calculate vanna-weighted vol impact proxy for ±5% moves
        move_size = 0.05  # 5% move
        total_abs_vanna = sum(abs(exp.net_vanna) for exp in vanna_exposures)
        if total_abs_vanna == 0:
            return 0, 0
        
        # Upside vol impact
        vol_impact_up = 0.0
        for exposure in vanna_exposures:
            # Distance from strike affects vanna impact
            distance = (exposure.strike - underlying_price) / underlying_price
            
            # Vanna impact decays with distance
            distance_factor = max(0, 1 - abs(distance) / move_size)
            
            # Positive vanna = vol rises with up move
            vol_impact_up += exposure.net_vanna * distance_factor
        
        # Downside vol impact  
        vol_impact_down = 0.0
        for exposure in vanna_exposures:
            distance = (exposure.strike - underlying_price) / underlying_price
            distance_factor = max(0, 1 - abs(distance) / move_size)
            
            # Positive vanna = vol falls with down move
            vol_impact_down -= exposure.net_vanna * distance_factor
        
        # Normalize into a unitless proxy, reported as vol points per 5% move
        vol_impact_up = vol_impact_up / total_abs_vanna
        vol_impact_down = vol_impact_down / total_abs_vanna
        
        return vol_impact_up, vol_impact_down
    
    @staticmethod
    def detect_vanna_squeeze(vanna_analysis: VannaResult,
                           price_move_threshold: float = 0.02) -> Dict[str, Any]:
        """Detect potential vanna squeeze scenarios."""
        squeeze_analysis = {
            "squeeze_detected": False,
            "squeeze_type": "none",  # "bullish", "bearish", "none"
            "trigger_level": None,
            "expected_vol_impact": 0,
            "confidence": 0
        }
        
        if not vanna_analysis.vanna_exposures:
            return squeeze_analysis
        
        current_price = vanna_analysis.underlying_price
        
        # Check for concentration of vanna at specific levels
        for exposure in vanna_analysis.vanna_exposures:
            distance_pct = abs(exposure.strike - current_price) / current_price
            
            # If we're very close to a high vanna level
            if distance_pct <= price_move_threshold:
                total_abs_vanna = sum(abs(exp.net_vanna) for exp in vanna_analysis.vanna_exposures)
                
                if abs(exposure.net_vanna) > total_abs_vanna * 0.3:  # 30% of total vanna
                    squeeze_analysis.update({
                        "squeeze_detected": True,
                        "squeeze_type": "bullish" if exposure.net_vanna > 0 else "bearish",
                        "trigger_level": exposure.strike,
                        "expected_vol_impact": abs(exposure.net_vanna) / 1000,  # Normalized
                        "confidence": min(abs(exposure.net_vanna) / total_abs_vanna * 100, 95)
                    })
                    break
        
        return squeeze_analysis
    
    @staticmethod
    def get_compact_vanna_summary(vanna_analysis: VannaResult) -> Dict[str, Any]:
        """Generate compact vanna summary for LLM consumption."""
        squeeze_info = VannaAnalyzer.detect_vanna_squeeze(vanna_analysis)
        
        return {
            "total_vanna": round(vanna_analysis.total_vanna, 6),
            "total_vanna_units": VannaAnalyzer.VANNA_UNIT,
            "total_vanna_delta_per_1pct_move": round(vanna_analysis.total_vanna, 6),
            "vanna_per_1pct_move_assumption": "1 vol point per 1% move",
            "flow_prediction": vanna_analysis.predicted_flow.value,
            "flow_strength": round(vanna_analysis.flow_strength, 1),
            "upside_trigger": round(vanna_analysis.vanna_trigger_up, 2),
            "downside_trigger": round(vanna_analysis.vanna_trigger_down, 2),
            "vol_impact_up": round(vanna_analysis.vol_impact_up, 4),
            "vol_impact_down": round(vanna_analysis.vol_impact_down, 4),
            "vol_impact_units": VannaAnalyzer.VOL_IMPACT_UNIT,
            "squeeze_detected": squeeze_info["squeeze_detected"],
            "squeeze_type": squeeze_info["squeeze_type"],
            "strikes_analyzed": len(vanna_analysis.vanna_exposures)
        }
