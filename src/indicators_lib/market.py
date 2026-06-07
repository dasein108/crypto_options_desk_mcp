"""Market structure and volume analysis."""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from .types import Kline, VolumeProfile, MarketStructure
from .sentiment import SentimentAnalyzer


class MarketAnalysis:
    """Market structure and volume analysis tools."""
    
    @staticmethod
    def get_price_extremes(klines: List[Kline], days: int) -> Dict[str, float]:
        """Get price extremes over specified period."""
        if not klines or days <= 0:
            return {}
        
        # Get recent data based on days
        cutoff_time = datetime.now() - timedelta(days=days)
        recent_klines = [k for k in klines if k.timestamp >= cutoff_time]
        
        if not recent_klines:
            recent_klines = klines[-min(days * 24, len(klines)):]  # Fallback to last N candles
        
        if not recent_klines:
            return {}
        
        highs = [k.high for k in recent_klines]
        lows = [k.low for k in recent_klines]
        closes = [k.close for k in recent_klines]
        volumes = [k.volume for k in recent_klines]
        
        return {
            "period_high": max(highs),
            "period_low": min(lows),
            "period_range": max(highs) - min(lows),
            "period_range_pct": ((max(highs) - min(lows)) / min(lows)) * 100,
            "current_price": closes[-1],
            "price_position_in_range": ((closes[-1] - min(lows)) / (max(highs) - min(lows))) * 100,
            "avg_volume": np.mean(volumes),
            "max_volume": max(volumes),
            "current_volume": volumes[-1],
            "volume_percentile": len([v for v in volumes if v < volumes[-1]]) / len(volumes) * 100
        }
    
    @staticmethod
    def get_volume_profile(klines: List[Kline], bins: int = 20) -> VolumeProfile:
        """Calculate volume profile for price discovery."""
        if len(klines) < 2:
            return VolumeProfile(
                price_levels=[],
                volume_distribution=[],
                poc=0,
                value_area_high=0,
                value_area_low=0,
                value_area_volume_pct=0
            )
        
        # Get price and volume data
        all_prices = []
        all_volumes = []
        
        for kline in klines:
            # Create price levels within each candle's range
            price_range = kline.high - kline.low
            if price_range > 0:
                # Distribute volume across the price range
                volume_per_level = kline.volume / 4  # Simple approximation
                price_levels = [
                    kline.open,
                    kline.high,
                    kline.low,
                    kline.close
                ]
                for price in price_levels:
                    all_prices.append(price)
                    all_volumes.append(volume_per_level)
            else:
                all_prices.append(kline.close)
                all_volumes.append(kline.volume)
        
        if not all_prices:
            return VolumeProfile(
                price_levels=[],
                volume_distribution=[],
                poc=0,
                value_area_high=0,
                value_area_low=0,
                value_area_volume_pct=0
            )
        
        # Create price bins
        min_price = min(all_prices)
        max_price = max(all_prices)
        price_step = (max_price - min_price) / bins
        
        price_levels = []
        volume_distribution = []
        
        for i in range(bins):
            bin_low = min_price + (i * price_step)
            bin_high = bin_low + price_step
            bin_center = (bin_low + bin_high) / 2
            
            # Sum volumes for prices in this bin
            bin_volume = sum(
                vol for price, vol in zip(all_prices, all_volumes)
                if bin_low <= price < bin_high
            )
            
            price_levels.append(bin_center)
            volume_distribution.append(bin_volume)
        
        # Find Point of Control (highest volume)
        max_vol_idx = volume_distribution.index(max(volume_distribution))
        poc = price_levels[max_vol_idx]
        
        # Calculate Value Area (70% of total volume)
        total_volume = sum(volume_distribution)
        target_volume = total_volume * 0.7
        
        # Start from POC and expand outward
        value_area_indices = [max_vol_idx]
        value_area_volume = volume_distribution[max_vol_idx]
        
        while value_area_volume < target_volume and len(value_area_indices) < len(price_levels):
            # Find best expansion (higher volume adjacent bin)
            candidates = []
            
            min_idx = min(value_area_indices)
            max_idx = max(value_area_indices)
            
            if min_idx > 0:
                candidates.append((min_idx - 1, volume_distribution[min_idx - 1]))
            if max_idx < len(price_levels) - 1:
                candidates.append((max_idx + 1, volume_distribution[max_idx + 1]))
            
            if not candidates:
                break
                
            # Add the index with higher volume
            best_idx = max(candidates, key=lambda x: x[1])[0]
            value_area_indices.append(best_idx)
            value_area_volume += volume_distribution[best_idx]
        
        value_area_low = price_levels[min(value_area_indices)]
        value_area_high = price_levels[max(value_area_indices)]
        value_area_volume_pct = (value_area_volume / total_volume) * 100
        
        return VolumeProfile(
            price_levels=price_levels,
            volume_distribution=volume_distribution,
            poc=poc,
            value_area_high=value_area_high,
            value_area_low=value_area_low,
            value_area_volume_pct=value_area_volume_pct
        )
    
    @staticmethod
    def calculate_volume_indicators(klines: List[Kline]) -> Dict[str, float]:
        """Calculate volume-based indicators."""
        if len(klines) < 20:
            return {}
        
        volumes = [k.volume for k in klines]
        prices = [k.close for k in klines]
        
        # Volume moving averages
        vol_sma_20 = np.mean(volumes[-20:])
        vol_sma_5 = np.mean(volumes[-5:])
        current_volume = volumes[-1]
        
        # Volume ratio
        volume_ratio = current_volume / vol_sma_20 if vol_sma_20 > 0 else 0
        
        # Volume trend
        volume_trend = (vol_sma_5 / vol_sma_20 - 1) * 100 if vol_sma_20 > 0 else 0
        
        # On-Balance Volume (OBV)
        obv = 0
        obv_values = [0]
        
        for i in range(1, len(klines)):
            if prices[i] > prices[i-1]:
                obv += volumes[i]
            elif prices[i] < prices[i-1]:
                obv -= volumes[i]
            obv_values.append(obv)
        
        # Volume Price Trend (VPT)
        vpt = 0
        vpt_values = [0]
        
        for i in range(1, len(klines)):
            price_change_pct = (prices[i] - prices[i-1]) / prices[i-1] if prices[i-1] != 0 else 0
            vpt += volumes[i] * price_change_pct
            vpt_values.append(vpt)
        
        return {
            "current_volume": current_volume,
            "volume_sma_20": vol_sma_20,
            "volume_sma_5": vol_sma_5,
            "volume_ratio": volume_ratio,
            "volume_trend_pct": volume_trend,
            "obv": obv_values[-1],
            "vpt": vpt_values[-1],
            "volume_percentile": len([v for v in volumes if v < current_volume]) / len(volumes) * 100
        }
    
    @staticmethod
    def detect_market_structure(klines: List[Kline], swing_strength: int = 5) -> MarketStructure:
        """Detect market structure including trends and key levels."""
        if len(klines) < swing_strength * 2 + 1:
            return MarketStructure(
                trend_direction="unknown",
                support_levels=[],
                resistance_levels=[],
                swing_highs=[],
                swing_lows=[],
                trend_strength=0
            )
        
        # Find swing highs and lows
        swing_highs = []
        swing_lows = []
        
        for i in range(swing_strength, len(klines) - swing_strength):
            # Check for swing high
            is_swing_high = True
            for j in range(i - swing_strength, i + swing_strength + 1):
                if j != i and klines[j].high >= klines[i].high:
                    is_swing_high = False
                    break
            
            if is_swing_high:
                swing_highs.append((klines[i].timestamp, klines[i].high))
            
            # Check for swing low
            is_swing_low = True
            for j in range(i - swing_strength, i + swing_strength + 1):
                if j != i and klines[j].low <= klines[i].low:
                    is_swing_low = False
                    break
            
            if is_swing_low:
                swing_lows.append((klines[i].timestamp, klines[i].low))
        
        # Determine trend direction
        trend_direction = MarketAnalysis._analyze_trend(klines, swing_highs, swing_lows)
        
        # Calculate trend strength
        trend_strength = MarketAnalysis._calculate_trend_strength(klines)
        
        # Extract support and resistance levels
        support_levels = [low[1] for low in swing_lows[-5:]]  # Last 5 swing lows
        resistance_levels = [high[1] for high in swing_highs[-5:]]  # Last 5 swing highs
        
        return MarketStructure(
            trend_direction=trend_direction,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            trend_strength=trend_strength
        )
    
    @staticmethod
    def _analyze_trend(klines: List[Kline], swing_highs: List[Tuple[datetime, float]], 
                      swing_lows: List[Tuple[datetime, float]]) -> str:
        """Analyze overall trend direction."""
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "sideways"
        
        # Check for higher highs and higher lows (bullish)
        recent_highs = swing_highs[-3:] if len(swing_highs) >= 3 else swing_highs
        recent_lows = swing_lows[-3:] if len(swing_lows) >= 3 else swing_lows
        
        higher_highs = all(recent_highs[i][1] >= recent_highs[i-1][1] 
                          for i in range(1, len(recent_highs)))
        higher_lows = all(recent_lows[i][1] >= recent_lows[i-1][1] 
                         for i in range(1, len(recent_lows)))
        
        # Check for lower highs and lower lows (bearish)
        lower_highs = all(recent_highs[i][1] <= recent_highs[i-1][1] 
                         for i in range(1, len(recent_highs)))
        lower_lows = all(recent_lows[i][1] <= recent_lows[i-1][1] 
                        for i in range(1, len(recent_lows)))
        
        if higher_highs and higher_lows:
            return "bullish"
        elif lower_highs and lower_lows:
            return "bearish"
        else:
            return "sideways"
    
    @staticmethod
    def _calculate_trend_strength(klines: List[Kline], period: int = 20) -> float:
        """Calculate trend strength (0-1 scale)."""
        if len(klines) < period:
            return 0
        
        recent_klines = klines[-period:]
        prices = [k.close for k in recent_klines]
        
        # Calculate linear regression slope
        x = np.arange(len(prices))
        slope = np.polyfit(x, prices, 1)[0]
        
        # Normalize slope relative to price range
        price_range = max(prices) - min(prices)
        if price_range == 0:
            return 0
        
        # Convert to 0-1 scale
        trend_strength = abs(slope) / price_range * period
        return min(trend_strength, 1.0)
    
    @staticmethod
    def get_key_levels(klines: List[Kline], lookback_days: int = 30) -> Dict[str, List[float]]:
        """Extract key support and resistance levels."""
        cutoff_time = datetime.now() - timedelta(days=lookback_days)
        recent_klines = [k for k in klines if k.timestamp >= cutoff_time]
        
        if not recent_klines:
            recent_klines = klines[-min(lookback_days * 24, len(klines)):]
        
        market_structure = MarketAnalysis.detect_market_structure(recent_klines)
        
        # Get psychological levels (round numbers)
        current_price = recent_klines[-1].close
        price_magnitude = 10 ** (len(str(int(current_price))) - 1)
        
        psychological_levels = []
        for multiplier in [0.5, 1, 1.5, 2, 2.5]:
            level = price_magnitude * multiplier
            if abs(level - current_price) / current_price < 0.2:  # Within 20%
                psychological_levels.append(level)
        
        return {
            "support_levels": market_structure.support_levels,
            "resistance_levels": market_structure.resistance_levels,
            "psychological_levels": psychological_levels,
            "current_price": current_price
        }

    # ============================================================================
    # SENTIMENT ANALYSIS METHODS
    # ============================================================================

    def __init__(self, sentiment_analyzer: Optional[SentimentAnalyzer] = None):
        """Initialize market analysis with sentiment analyzer"""
        self.sentiment_analyzer = sentiment_analyzer or SentimentAnalyzer()

    async def get_market_sentiment(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """Get comprehensive market sentiment analysis"""
        return await self.sentiment_analyzer.get_market_sentiment_analysis(symbol)

    async def get_funding_analysis(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """Get detailed funding rate analysis"""
        return await self.sentiment_analyzer.get_funding_rate_analysis(symbol)