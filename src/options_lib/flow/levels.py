"""Support and resistance level detection from options data."""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from .types import (
    OptionsChainData, GEXAnalysis, VannaAnalysis, OptionsFlowConfig
)


class SupportResistanceLevels:
    """Detect support and resistance levels using options flow data."""
    
    @staticmethod
    def extract_gex_levels(gex_analysis: GEXAnalysis, 
                          significance_threshold: float = 0.1) -> Dict[str, List[Tuple[float, float, str]]]:
        """Extract support/resistance levels from GEX analysis."""
        levels = {
            "resistance": [],
            "support": [],
            "pivot": []
        }
        
        if not gex_analysis.gex_levels:
            return levels
        
        total_abs_gex = sum(abs(level.net_gex) for level in gex_analysis.gex_levels)
        threshold = total_abs_gex * significance_threshold
        
        for gex_level in gex_analysis.gex_levels:
            if abs(gex_level.net_gex) >= threshold:
                # Positive GEX = resistance (dealers short gamma, need to sell)
                if gex_level.net_gex > 0:
                    levels["resistance"].append((
                        gex_level.strike,
                        gex_level.net_gex,
                        "gamma_resistance"
                    ))
                # Negative GEX = support (dealers long gamma, need to buy)
                elif gex_level.net_gex < 0:
                    levels["support"].append((
                        gex_level.strike,
                        abs(gex_level.net_gex),
                        "gamma_support"
                    ))
        
        # Add GEX flip level as pivot
        if gex_analysis.gex_flip_level:
            levels["pivot"].append((
                gex_analysis.gex_flip_level,
                0,
                "gex_flip"
            ))
        
        # Sort by strength (GEX magnitude)
        levels["resistance"].sort(key=lambda x: x[1], reverse=True)
        levels["support"].sort(key=lambda x: x[1], reverse=True)
        
        return levels
    
    @staticmethod
    def extract_vanna_levels(vanna_analysis: VannaAnalysis,
                           underlying_price: float,
                           significance_threshold: float = 0.15) -> Dict[str, List[Tuple[float, float, str]]]:
        """Extract key levels from Vanna analysis."""
        levels = {
            "resistance": [],
            "support": [],
            "pivot": []
        }
        
        if not vanna_analysis.vanna_exposures:
            return levels
        
        total_abs_vanna = sum(abs(exp.net_vanna) for exp in vanna_analysis.vanna_exposures)
        threshold = total_abs_vanna * significance_threshold
        
        for vanna_exp in vanna_analysis.vanna_exposures:
            if abs(vanna_exp.net_vanna) >= threshold:
                # Vanna effects create dynamic support/resistance
                if vanna_exp.strike > underlying_price and vanna_exp.net_vanna > 0:
                    # Positive vanna above spot = potential resistance
                    levels["resistance"].append((
                        vanna_exp.strike,
                        vanna_exp.net_vanna,
                        "vanna_resistance"
                    ))
                elif vanna_exp.strike < underlying_price and vanna_exp.net_vanna < 0:
                    # Negative vanna below spot = potential support
                    levels["support"].append((
                        vanna_exp.strike,
                        abs(vanna_exp.net_vanna),
                        "vanna_support"
                    ))
        
        # Add vanna trigger levels
        if vanna_analysis.vanna_trigger_up != underlying_price:
            levels["resistance"].append((
                vanna_analysis.vanna_trigger_up,
                0,
                "vanna_trigger_up"
            ))
        
        if vanna_analysis.vanna_trigger_down != underlying_price:
            levels["support"].append((
                vanna_analysis.vanna_trigger_down,
                0,
                "vanna_trigger_down"
            ))
        
        return levels
    
    @staticmethod
    def extract_oi_levels(options_data: List[OptionsChainData],
                         underlying_price: float,
                         oi_percentile_threshold: float = 0.8) -> Dict[str, List[Tuple[float, float, str]]]:
        """Extract levels based on open interest concentration."""
        levels = {
            "resistance": [],
            "support": [],
            "pivot": []
        }
        
        if not options_data:
            return levels
        
        # Group by strike and calculate total OI
        oi_by_strike = {}
        for option in options_data:
            strike = option.strike
            if strike not in oi_by_strike:
                oi_by_strike[strike] = 0
            oi_by_strike[strike] += option.open_interest
        
        # Find high OI strikes
        all_oi_values = list(oi_by_strike.values())
        oi_threshold = np.percentile(all_oi_values, oi_percentile_threshold * 100)
        
        for strike, total_oi in oi_by_strike.items():
            if total_oi >= oi_threshold:
                # Classify based on position relative to current price
                if strike > underlying_price:
                    levels["resistance"].append((
                        strike,
                        total_oi,
                        "high_oi_resistance"
                    ))
                elif strike < underlying_price:
                    levels["support"].append((
                        strike,
                        total_oi,
                        "high_oi_support"
                    ))
                else:
                    levels["pivot"].append((
                        strike,
                        total_oi,
                        "high_oi_pivot"
                    ))
        
        return levels
    
    @staticmethod
    def extract_volume_levels(options_data: List[OptionsChainData],
                            underlying_price: float,
                            volume_percentile_threshold: float = 0.85) -> Dict[str, List[Tuple[float, float, str]]]:
        """Extract levels based on volume concentration."""
        levels = {
            "resistance": [],
            "support": [],
            "pivot": []
        }
        
        if not options_data:
            return levels
        
        # Group by strike and calculate total volume
        volume_by_strike = {}
        for option in options_data:
            if option.volume > 0:  # Only consider strikes with actual volume
                strike = option.strike
                if strike not in volume_by_strike:
                    volume_by_strike[strike] = 0
                volume_by_strike[strike] += option.volume
        
        if not volume_by_strike:
            return levels
        
        # Find high volume strikes
        all_volume_values = list(volume_by_strike.values())
        volume_threshold = np.percentile(all_volume_values, volume_percentile_threshold * 100)
        
        for strike, total_volume in volume_by_strike.items():
            if total_volume >= volume_threshold:
                if strike > underlying_price:
                    levels["resistance"].append((
                        strike,
                        total_volume,
                        "high_volume_resistance"
                    ))
                elif strike < underlying_price:
                    levels["support"].append((
                        strike,
                        total_volume,
                        "high_volume_support"
                    ))
                else:
                    levels["pivot"].append((
                        strike,
                        total_volume,
                        "high_volume_pivot"
                    ))
        
        return levels
    
    @staticmethod
    def consolidate_levels(gex_levels: Dict[str, List[Tuple[float, float, str]]],
                          vanna_levels: Dict[str, List[Tuple[float, float, str]]],
                          oi_levels: Dict[str, List[Tuple[float, float, str]]],
                          volume_levels: Dict[str, List[Tuple[float, float, str]]],
                          underlying_price: float,
                          consolidation_threshold: float = 0.02) -> Dict[str, Any]:
        """Consolidate all levels into unified support/resistance map."""
        consolidated = {
            "key_resistance": [],
            "key_support": [],
            "pivot_levels": [],
            "level_confluence": []
        }
        
        # Combine all levels
        all_resistance = []
        all_support = []
        all_pivots = []
        
        for level_type in [gex_levels, vanna_levels, oi_levels, volume_levels]:
            all_resistance.extend(level_type.get("resistance", []))
            all_support.extend(level_type.get("support", []))
            all_pivots.extend(level_type.get("pivot", []))
        
        # Consolidate nearby levels
        consolidated_resistance = SupportResistanceLevels._consolidate_nearby_levels(
            all_resistance, underlying_price, consolidation_threshold
        )
        
        consolidated_support = SupportResistanceLevels._consolidate_nearby_levels(
            all_support, underlying_price, consolidation_threshold
        )
        
        consolidated_pivots = SupportResistanceLevels._consolidate_nearby_levels(
            all_pivots, underlying_price, consolidation_threshold
        )
        
        # Score levels by confluence (multiple indicators at same level)
        confluence_levels = SupportResistanceLevels._find_confluence_levels(
            all_resistance + all_support + all_pivots, underlying_price, consolidation_threshold
        )
        
        consolidated.update({
            "key_resistance": consolidated_resistance[:5],  # Top 5
            "key_support": consolidated_support[:5],       # Top 5
            "pivot_levels": consolidated_pivots,
            "level_confluence": confluence_levels[:3]       # Top 3 confluence areas
        })
        
        return consolidated
    
    @staticmethod
    def _consolidate_nearby_levels(levels: List[Tuple[float, float, str]],
                                 underlying_price: float,
                                 threshold: float) -> List[Dict[str, Any]]:
        """Consolidate levels that are close to each other."""
        if not levels:
            return []
        
        # Sort by price
        sorted_levels = sorted(levels, key=lambda x: x[0])
        consolidated = []
        
        i = 0
        while i < len(sorted_levels):
            current_price = sorted_levels[i][0]
            current_strength = sorted_levels[i][1]
            current_types = [sorted_levels[i][2]]
            
            # Find nearby levels
            j = i + 1
            while j < len(sorted_levels):
                next_price = sorted_levels[j][0]
                price_diff = abs(next_price - current_price) / underlying_price
                
                if price_diff <= threshold:
                    # Combine levels
                    current_strength += sorted_levels[j][1]
                    current_types.append(sorted_levels[j][2])
                    j += 1
                else:
                    break
            
            # Create consolidated level
            avg_price = np.mean([sorted_levels[k][0] for k in range(i, j)])
            
            consolidated.append({
                "price": round(avg_price, 2),
                "strength": round(current_strength, 2),
                "types": current_types,
                "confluence_count": len(current_types),
                "distance_pct": round(abs(avg_price - underlying_price) / underlying_price * 100, 2)
            })
            
            i = j
        
        # Sort by strength
        consolidated.sort(key=lambda x: x["strength"], reverse=True)
        return consolidated
    
    @staticmethod
    def _find_confluence_levels(all_levels: List[Tuple[float, float, str]],
                              underlying_price: float,
                              threshold: float) -> List[Dict[str, Any]]:
        """Find price levels where multiple indicators converge."""
        if len(all_levels) < 2:
            return []
        
        confluence_areas = []
        
        # Group levels by proximity
        grouped_levels = {}
        for price, strength, level_type in all_levels:
            # Find existing group or create new one
            found_group = None
            for group_price in grouped_levels:
                if abs(price - group_price) / underlying_price <= threshold:
                    found_group = group_price
                    break
            
            if found_group:
                grouped_levels[found_group].append((price, strength, level_type))
            else:
                grouped_levels[price] = [(price, strength, level_type)]
        
        # Identify confluence areas (2+ different indicator types)
        for group_price, group_levels in grouped_levels.items():
            if len(group_levels) >= 2:
                unique_types = list(set(level[2] for level in group_levels))
                if len(unique_types) >= 2:  # Multiple indicator types
                    avg_price = np.mean([level[0] for level in group_levels])
                    total_strength = sum(level[1] for level in group_levels)
                    
                    confluence_areas.append({
                        "price": round(avg_price, 2),
                        "confluence_count": len(unique_types),
                        "total_strength": round(total_strength, 2),
                        "indicator_types": unique_types,
                        "distance_pct": round(abs(avg_price - underlying_price) / underlying_price * 100, 2)
                    })
        
        # Sort by confluence count and strength
        confluence_areas.sort(key=lambda x: (x["confluence_count"], x["total_strength"]), reverse=True)
        return confluence_areas
    
    @staticmethod
    def get_compact_levels_summary(consolidated_levels: Dict[str, Any],
                                 underlying_price: float) -> Dict[str, Any]:
        """Generate compact levels summary for LLM consumption."""
        return {
            "current_price": round(underlying_price, 2),
            "nearest_resistance": consolidated_levels["key_resistance"][0]["price"] if consolidated_levels["key_resistance"] else None,
            "nearest_support": consolidated_levels["key_support"][0]["price"] if consolidated_levels["key_support"] else None,
            "key_resistance_count": len(consolidated_levels["key_resistance"]),
            "key_support_count": len(consolidated_levels["key_support"]),
            "high_confluence_areas": len(consolidated_levels["level_confluence"]),
            "strongest_resistance_strength": consolidated_levels["key_resistance"][0]["strength"] if consolidated_levels["key_resistance"] else 0,
            "strongest_support_strength": consolidated_levels["key_support"][0]["strength"] if consolidated_levels["key_support"] else 0,
            "pivot_levels_count": len(consolidated_levels["pivot_levels"])
        }