"""Utility functions for indicators module."""

import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .types import Kline, TechnicalSummary, IndicatorConfig


class IndicatorUtils:
    """Utility functions for indicator calculations and data processing."""
    
    @staticmethod
    def klines_from_bybit_data(bybit_data: List[List]) -> List[Kline]:
        """Convert Bybit kline data format to Kline objects."""
        klines = []
        
        for data_point in bybit_data:
            if len(data_point) >= 6:
                try:
                    # Bybit format: [timestamp, open, high, low, close, volume, turnover]
                    timestamp = datetime.fromtimestamp(int(data_point[0]) / 1000)
                    symbol = "UNKNOWN"  # Will be set by caller
                    
                    kline = Kline(
                        symbol=symbol,
                        timestamp=timestamp,
                        open=float(data_point[1]),
                        high=float(data_point[2]),
                        low=float(data_point[3]),
                        close=float(data_point[4]),
                        volume=float(data_point[5])
                    )
                    klines.append(kline)
                except (ValueError, IndexError) as e:
                    continue  # Skip malformed data points
        
        return klines
    
    @staticmethod
    def filter_klines_by_timeframe(klines: List[Kline], timeframe: str, limit: Optional[int] = None) -> List[Kline]:
        """Filter klines based on timeframe requirements."""
        if not klines:
            return []
        
        # Sort by timestamp
        sorted_klines = sorted(klines, key=lambda k: k.timestamp)
        
        # Apply limit if specified
        if limit:
            sorted_klines = sorted_klines[-limit:]
        
        return sorted_klines
    
    @staticmethod
    def validate_kline_data(klines: List[Kline]) -> bool:
        """Validate kline data integrity."""
        if not klines:
            return False
        
        for kline in klines:
            # Check for valid OHLC relationship
            if not (kline.low <= kline.open <= kline.high and 
                   kline.low <= kline.close <= kline.high):
                return False
            
            # Check for positive values
            if any(val <= 0 for val in [kline.open, kline.high, kline.low, kline.close]):
                return False
            
            # Check for valid volume
            if kline.volume < 0:
                return False
        
        return True
    
    @staticmethod
    def calculate_price_change(klines: List[Kline], periods: int = 1) -> float:
        """Calculate price change percentage over specified periods."""
        if len(klines) < periods + 1:
            return 0.0
        
        current_price = klines[-1].close
        previous_price = klines[-(periods + 1)].close
        
        if previous_price == 0:
            return 0.0
        
        return ((current_price - previous_price) / previous_price) * 100
    
    @staticmethod
    def normalize_values(values: List[float], min_val: float = 0, max_val: float = 100) -> List[float]:
        """Normalize values to specified range."""
        if not values or all(np.isnan(v) for v in values):
            return values
        
        clean_values = [v for v in values if not np.isnan(v)]
        if not clean_values:
            return values
        
        min_input = min(clean_values)
        max_input = max(clean_values)
        
        if max_input == min_input:
            return [min_val + (max_val - min_val) / 2] * len(values)
        
        normalized = []
        for value in values:
            if np.isnan(value):
                normalized.append(np.nan)
            else:
                norm_val = min_val + (value - min_input) * (max_val - min_val) / (max_input - min_input)
                normalized.append(norm_val)
        
        return normalized
    
    @staticmethod
    def calculate_correlation(series1: List[float], series2: List[float]) -> float:
        """Calculate correlation between two series."""
        if len(series1) != len(series2) or len(series1) < 2:
            return 0.0
        
        # Remove pairs with NaN values
        clean_pairs = [(x, y) for x, y in zip(series1, series2) 
                      if not (np.isnan(x) or np.isnan(y))]
        
        if len(clean_pairs) < 2:
            return 0.0
        
        x_values = [pair[0] for pair in clean_pairs]
        y_values = [pair[1] for pair in clean_pairs]
        
        return np.corrcoef(x_values, y_values)[0, 1]
    
    @staticmethod
    def generate_comprehensive_summary(klines: List[Kline], symbol: str, 
                                     timeframe: str, config: Optional[IndicatorConfig] = None) -> TechnicalSummary:
        """Generate comprehensive technical analysis summary."""
        from .technical import TechnicalIndicators
        from .market import MarketAnalysis
        from .volatility import VolatilityAnalysis
        
        if not config:
            config = IndicatorConfig()
        
        if len(klines) < 20:
            # Return minimal summary for insufficient data
            return TechnicalSummary(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=datetime.now(),
                current_price=klines[-1].close if klines else 0,
                price_change_pct=0,
                sma_20=0,
                sma_50=0,
                ema_20=0,
                rsi=50,
                atr=0,
                bollinger_position=50,
                volume_sma_ratio=1,
                signals=[],
                trend_score=0,
                momentum_score=0,
                volatility_percentile=50
            )
        
        prices = [k.close for k in klines]
        current_price = prices[-1]
        
        # Price action metrics
        price_change_pct = IndicatorUtils.calculate_price_change(klines, 1)
        
        # Moving averages
        sma_20 = TechnicalIndicators.calculate_sma(prices, 20)[-1]
        sma_50 = TechnicalIndicators.calculate_sma(prices, 50)[-1] if len(prices) >= 50 else sma_20
        ema_20 = TechnicalIndicators.calculate_ema(prices, 20)[-1]
        
        # RSI
        rsi_values = TechnicalIndicators.calculate_rsi(prices, config.rsi_period)
        rsi = rsi_values[-1] if rsi_values and not np.isnan(rsi_values[-1]) else 50
        
        # ATR
        atr_values = TechnicalIndicators.calculate_atr(klines, config.atr_period)
        atr = atr_values[-1] if atr_values and not np.isnan(atr_values[-1]) else 0
        
        # Bollinger Bands position
        bb = TechnicalIndicators.calculate_bollinger_bands(klines, config.bb_period, config.bb_std_dev)
        bollinger_position = bb.bb_position[-1] if bb.bb_position and not np.isnan(bb.bb_position[-1]) else 50
        
        # Volume analysis
        volume_indicators = MarketAnalysis.calculate_volume_indicators(klines)
        volume_sma_ratio = volume_indicators.get('volume_ratio', 1)
        
        # Volatility analysis
        vol_metrics = VolatilityAnalysis.calculate_comprehensive_metrics(klines)
        volatility_percentile = vol_metrics.vol_percentile
        
        # Generate signals
        signals = TechnicalIndicators.get_signals(klines, config)
        
        # Calculate scores
        trend_score = IndicatorUtils._calculate_trend_score(current_price, sma_20, sma_50, ema_20)
        momentum_score = IndicatorUtils._calculate_momentum_score(rsi, price_change_pct)
        
        return TechnicalSummary(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.now(),
            current_price=current_price,
            price_change_pct=price_change_pct,
            sma_20=sma_20 if not np.isnan(sma_20) else current_price,
            sma_50=sma_50 if not np.isnan(sma_50) else current_price,
            ema_20=ema_20 if not np.isnan(ema_20) else current_price,
            rsi=rsi,
            atr=atr,
            bollinger_position=bollinger_position,
            volume_sma_ratio=volume_sma_ratio,
            signals=signals,
            trend_score=trend_score,
            momentum_score=momentum_score,
            volatility_percentile=volatility_percentile
        )
    
    @staticmethod
    def _calculate_trend_score(current_price: float, sma_20: float, sma_50: float, ema_20: float) -> float:
        """Calculate trend score (-100 to +100)."""
        if any(np.isnan(val) for val in [current_price, sma_20, sma_50, ema_20]):
            return 0
        
        score = 0
        
        # Price vs moving averages (40 points max)
        if current_price > sma_20:
            score += 20
        if current_price > sma_50:
            score += 20
        
        # Moving average relationships (40 points max)
        if sma_20 > sma_50:
            score += 20
        if current_price > ema_20:
            score += 20
        
        # Distance from moving averages (20 points max)
        sma_20_distance = (current_price - sma_20) / sma_20 if sma_20 != 0 else 0
        score += min(max(sma_20_distance * 100, -20), 20)
        
        return max(min(score, 100), -100)
    
    @staticmethod
    def _calculate_momentum_score(rsi: float, price_change_pct: float) -> float:
        """Calculate momentum score (-100 to +100)."""
        score = 0
        
        # RSI contribution (60 points max)
        if rsi > 70:
            score += 30 - (rsi - 70)  # Overbought penalty
        elif rsi > 50:
            score += (rsi - 50) * 1.5  # Bullish momentum
        elif rsi > 30:
            score -= (50 - rsi) * 1.5  # Bearish momentum
        else:
            score -= 30 + (30 - rsi)  # Oversold penalty
        
        # Price change contribution (40 points max)
        score += min(max(price_change_pct * 2, -40), 40)
        
        return max(min(score, 100), -100)
    
    @staticmethod
    def format_for_llm(data: Dict[str, Any], max_items: int = 5) -> Dict[str, Any]:
        """Format technical analysis data for LLM consumption."""
        formatted = {}
        
        for key, value in data.items():
            if isinstance(value, list):
                # Truncate lists and round numbers
                truncated = value[-max_items:] if len(value) > max_items else value
                formatted[key] = [round(x, 4) if isinstance(x, float) else x for x in truncated]
            elif isinstance(value, float):
                # Round floats to 4 decimal places
                formatted[key] = round(value, 4)
            elif isinstance(value, dict):
                # Recursively format nested dictionaries
                formatted[key] = IndicatorUtils.format_for_llm(value, max_items)
            else:
                formatted[key] = value
        
        return formatted
    
    @staticmethod
    def get_timeframe_multiplier(timeframe: str) -> int:
        """Get multiplier for timeframe conversion."""
        from bybit_api import TIMEFRAME_INTERVALS
        return TIMEFRAME_INTERVALS.get(timeframe, 60)
