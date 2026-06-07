"""Options flow analysis including delta imbalance, charm, and volume flows."""

import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
from .types import (
    OptionsChainData, DeltaImbalance, FlowMetrics, UnusualActivity,
    FlowDirection, OptionType, OptionsFlowConfig
)


class OptionsFlow:
    """Comprehensive options flow analysis."""
    
    @staticmethod
    def calculate_delta_imbalance(options_data: List[OptionsChainData],
                                config: Optional[OptionsFlowConfig] = None) -> DeltaImbalance:
        """Calculate delta imbalance across the options chain."""
        if config is None:
            config = OptionsFlowConfig()
        
        if not options_data:
            return DeltaImbalance(
                total_call_delta=0,
                total_put_delta=0,
                net_delta=0,
                delta_imbalance_ratio=0.5,
                estimated_dealer_delta=0,
                dealer_hedging_pressure=FlowDirection.NEUTRAL
            )
        
        # Separate calls and puts
        calls = [opt for opt in options_data if opt.option_type == OptionType.CALL]
        puts = [opt for opt in options_data if opt.option_type == OptionType.PUT]
        
        # Calculate total deltas weighted by open interest
        total_call_delta = sum(opt.delta * opt.open_interest for opt in calls)
        total_put_delta = sum(opt.delta * opt.open_interest for opt in puts)
        
        net_delta = total_call_delta + total_put_delta  # Put delta is negative
        
        # Calculate delta imbalance ratio
        total_abs_delta = abs(total_call_delta) + abs(total_put_delta)
        if total_abs_delta > 0:
            delta_imbalance_ratio = abs(total_call_delta) / total_abs_delta
        else:
            delta_imbalance_ratio = 0.5
        
        # Estimate dealer delta (opposite of customer delta)
        estimated_dealer_delta = -net_delta
        
        # Determine dealer hedging pressure
        if estimated_dealer_delta > total_abs_delta * 0.1:
            dealer_hedging_pressure = FlowDirection.BEARISH  # Dealers need to sell futures
        elif estimated_dealer_delta < -total_abs_delta * 0.1:
            dealer_hedging_pressure = FlowDirection.BULLISH  # Dealers need to buy futures
        else:
            dealer_hedging_pressure = FlowDirection.NEUTRAL
        
        return DeltaImbalance(
            total_call_delta=total_call_delta,
            total_put_delta=total_put_delta,
            net_delta=net_delta,
            delta_imbalance_ratio=delta_imbalance_ratio,
            estimated_dealer_delta=estimated_dealer_delta,
            dealer_hedging_pressure=dealer_hedging_pressure
        )
    
    @staticmethod
    def calculate_charm(options_data: List[OptionsChainData]) -> Dict[float, float]:
        """Calculate charm (delta decay) by strike."""
        if not options_data:
            return {}
        
        charm_by_strike = {}
        
        # Group by strike
        strikes_data = {}
        for option in options_data:
            strike = option.strike
            if strike not in strikes_data:
                strikes_data[strike] = []
            strikes_data[strike].append(option)
        
        for strike, options in strikes_data.items():
            total_charm = 0
            
            for option in options:
                # Charm approximation: -theta / (365 * underlying_price)
                # This represents how delta changes with time
                if option.underlying_price > 0:
                    charm_estimate = -option.theta / (365 * option.underlying_price)
                    charm_contribution = charm_estimate * option.open_interest
                    total_charm += charm_contribution
            
            charm_by_strike[strike] = total_charm
        
        return charm_by_strike
    
    @staticmethod
    def analyze_volume_imbalance(options_data: List[OptionsChainData]) -> FlowMetrics:
        """Analyze volume and open interest flows."""
        if not options_data:
            return FlowMetrics(
                call_volume=0,
                put_volume=0,
                call_put_ratio=1.0,
                unusual_call_volume=0,
                unusual_put_volume=0,
                call_oi_change=0,
                put_oi_change=0,
                total_premium=0,
                call_premium=0,
                put_premium=0
            )
        
        # Separate calls and puts
        calls = [opt for opt in options_data if opt.option_type == OptionType.CALL]
        puts = [opt for opt in options_data if opt.option_type == OptionType.PUT]
        
        # Calculate volume metrics
        call_volume = sum(opt.volume for opt in calls)
        put_volume = sum(opt.volume for opt in puts)
        
        call_put_ratio = call_volume / put_volume if put_volume > 0 else float('inf')
        
        # Calculate premium flows (volume * mark_price)
        call_premium = sum(opt.volume * opt.mark_price for opt in calls)
        put_premium = sum(opt.volume * opt.mark_price for opt in puts)
        total_premium = call_premium + put_premium
        
        # Estimate unusual volume (simplified - would need historical averages)
        # For now, use volume above median as "unusual"
        all_volumes = [opt.volume for opt in options_data if opt.volume > 0]
        if all_volumes:
            volume_median = np.median(all_volumes)
            unusual_call_volume = sum(
                opt.volume for opt in calls 
                if opt.volume > volume_median * 2
            )
            unusual_put_volume = sum(
                opt.volume for opt in puts 
                if opt.volume > volume_median * 2
            )
        else:
            unusual_call_volume = 0
            unusual_put_volume = 0
        
        # OI change would require historical data - setting to 0 for now
        call_oi_change = 0
        put_oi_change = 0
        
        return FlowMetrics(
            call_volume=call_volume,
            put_volume=put_volume,
            call_put_ratio=call_put_ratio,
            unusual_call_volume=unusual_call_volume,
            unusual_put_volume=unusual_put_volume,
            call_oi_change=call_oi_change,
            put_oi_change=put_oi_change,
            total_premium=total_premium,
            call_premium=call_premium,
            put_premium=put_premium
        )
    
    @staticmethod
    def detect_unusual_activity(options_data: List[OptionsChainData],
                              config: Optional[OptionsFlowConfig] = None) -> List[UnusualActivity]:
        """Detect unusual options activity patterns."""
        if config is None:
            config = OptionsFlowConfig()
        
        if not options_data:
            return []
        
        unusual_activities = []
        
        # Calculate baseline metrics
        all_volumes = [opt.volume for opt in options_data if opt.volume > 0]
        if not all_volumes:
            return []
        
        median_volume = np.median(all_volumes)
        volume_std = np.std(all_volumes)
        
        for option in options_data:
            if option.volume == 0:
                continue
            
            # Calculate volume ratio vs baseline
            volume_ratio = option.volume / median_volume if median_volume > 0 else 0
            
            # Check for unusual volume
            if volume_ratio >= config.volume_threshold:
                # Calculate IV percentile (simplified)
                all_ivs = [opt.mark_iv for opt in options_data if opt.mark_iv > 0]
                if all_ivs:
                    iv_percentile = len([iv for iv in all_ivs if iv < option.mark_iv]) / len(all_ivs) * 100
                else:
                    iv_percentile = 50
                
                # Determine activity type
                activity_type = "unusual_volume"
                confidence = min(volume_ratio * 20, 95)  # Scale confidence
                
                # Estimate bullish probability based on option type and moneyness
                moneyness = option.strike / option.underlying_price if option.underlying_price > 0 else 1
                
                if option.option_type == OptionType.CALL:
                    if moneyness < 1.0:  # ITM calls
                        bullish_probability = 80
                    elif moneyness < 1.1:  # Near ATM calls
                        bullish_probability = 70
                    else:  # OTM calls
                        bullish_probability = 60
                else:  # PUT
                    if moneyness > 1.0:  # ITM puts
                        bullish_probability = 20
                    elif moneyness > 0.9:  # Near ATM puts
                        bullish_probability = 30
                    else:  # OTM puts
                        bullish_probability = 40
                
                # Adjust for high IV (might be protective buying)
                if iv_percentile > 75:
                    if option.option_type == OptionType.PUT:
                        bullish_probability = max(bullish_probability - 20, 10)
                
                unusual_activities.append(UnusualActivity(
                    symbol=option.symbol,
                    strike=option.strike,
                    expiry_date=option.expiry_date,
                    option_type=option.option_type,
                    volume=option.volume,
                    avg_volume_10d=median_volume,  # Simplified
                    volume_ratio=volume_ratio,
                    open_interest=option.open_interest,
                    oi_change=0,  # Would need historical data
                    premium=option.volume * option.mark_price,
                    iv_percentile=iv_percentile,
                    activity_type=activity_type,
                    confidence=confidence,
                    bullish_probability=bullish_probability
                ))
        
        # Sort by volume ratio descending
        unusual_activities.sort(key=lambda x: x.volume_ratio, reverse=True)
        
        return unusual_activities
    
    @staticmethod
    def calculate_net_flow_pressure(delta_imbalance: DeltaImbalance,
                                  flow_metrics: FlowMetrics,
                                  unusual_activities: List[UnusualActivity]) -> Dict[str, Any]:
        """Calculate overall flow pressure and direction."""
        flow_pressure = {
            "overall_direction": FlowDirection.NEUTRAL,
            "pressure_strength": 0,  # 0-100 scale
            "key_drivers": [],
            "confidence": 0
        }
        
        signals = []
        
        # Delta imbalance signal
        if delta_imbalance.delta_imbalance_ratio > 0.6:
            signals.append(("call_delta_heavy", 30))
        elif delta_imbalance.delta_imbalance_ratio < 0.4:
            signals.append(("put_delta_heavy", -30))
        
        # Volume flow signal
        if flow_metrics.call_put_ratio > 1.5:
            signals.append(("call_volume_heavy", 25))
        elif flow_metrics.call_put_ratio < 0.67:
            signals.append(("put_volume_heavy", -25))
        
        # Premium flow signal
        total_premium = flow_metrics.total_premium
        if total_premium > 0:
            call_premium_ratio = flow_metrics.call_premium / total_premium
            if call_premium_ratio > 0.65:
                signals.append(("call_premium_heavy", 20))
            elif call_premium_ratio < 0.35:
                signals.append(("put_premium_heavy", -20))
        
        # Unusual activity signal
        unusual_bullish = sum(
            activity.bullish_probability * activity.confidence / 100
            for activity in unusual_activities
        )
        unusual_bearish = sum(
            (100 - activity.bullish_probability) * activity.confidence / 100
            for activity in unusual_activities
        )
        
        if unusual_bullish > unusual_bearish * 1.5:
            signals.append(("unusual_bullish_activity", 15))
        elif unusual_bearish > unusual_bullish * 1.5:
            signals.append(("unusual_bearish_activity", -15))
        
        # Dealer hedging pressure
        if delta_imbalance.dealer_hedging_pressure == FlowDirection.BULLISH:
            signals.append(("dealer_hedging_bullish", 10))
        elif delta_imbalance.dealer_hedging_pressure == FlowDirection.BEARISH:
            signals.append(("dealer_hedging_bearish", -10))
        
        # Calculate overall score
        total_score = sum(score for _, score in signals)
        
        # Determine direction and strength
        if total_score > 20:
            flow_pressure["overall_direction"] = FlowDirection.BULLISH
        elif total_score < -20:
            flow_pressure["overall_direction"] = FlowDirection.BEARISH
        else:
            flow_pressure["overall_direction"] = FlowDirection.NEUTRAL
        
        flow_pressure["pressure_strength"] = min(abs(total_score), 100)
        flow_pressure["key_drivers"] = [driver for driver, score in signals if abs(score) >= 15]
        flow_pressure["confidence"] = min(len([s for s in signals if abs(s[1]) >= 10]) * 20, 90)
        
        return flow_pressure
    
    @staticmethod
    def get_compact_flow_summary(delta_imbalance: DeltaImbalance,
                               flow_metrics: FlowMetrics,
                               unusual_activities: List[UnusualActivity]) -> Dict[str, Any]:
        """Generate compact flow summary for LLM consumption."""
        net_flow = OptionsFlow.calculate_net_flow_pressure(
            delta_imbalance, flow_metrics, unusual_activities
        )
        
        return {
            "net_delta": round(delta_imbalance.net_delta, 2),
            "delta_imbalance_pct": round(delta_imbalance.delta_imbalance_ratio * 100, 1),
            "call_put_ratio": round(flow_metrics.call_put_ratio, 2),
            "total_premium_millions": round(flow_metrics.total_premium / 1000000, 2),
            "unusual_activity_count": len(unusual_activities),
            "flow_direction": net_flow["overall_direction"].value,
            "flow_strength": round(net_flow["pressure_strength"], 1),
            "key_drivers": net_flow["key_drivers"],
            "dealer_hedging": delta_imbalance.dealer_hedging_pressure.value,
            "confidence": net_flow["confidence"]
        }