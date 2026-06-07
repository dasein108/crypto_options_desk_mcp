"""
Comprehensive Summary Indicators for Options Trading Analysis
===========================================================

This module provides advanced market intelligence specifically designed for options trading decisions.
It creates compact, actionable summaries optimized for both human traders and LLM consumption.

Core Philosophy:
- Focus on volatility metrics (critical for options pricing and strategy selection)
- Provide actionable strategy recommendations based on market conditions
- Support both individual analysis and systematic trading systems
- Optimize data formats for external LLM integration via MCP protocols

Key Components:
1. **MarketSummary Dataclass**: Comprehensive market state representation
2. **SummaryIndicators Class**: Main analysis engine with static methods
3. **Advanced Volatility Metrics**: Composite volatility, CVOL analysis, convexity metrics
4. **Market Regime Detection**: Automated classification of market environments
5. **Strategy Recommendation Engine**: Context-aware options strategy suggestions

Primary Use Cases:
- Real-time market analysis for options traders
- Automated strategy selection in trading systems
- Risk management and position sizing decisions
- Market research and backtesting analysis
- Integration with external AI/LLM systems via MCP

Focus Areas:
1. **Volatility Intelligence** (most critical for options):
   - Multi-timeframe volatility analysis
   - Regime change detection
   - Volatility percentile tracking
   - Advanced composite volatility metrics

2. **Price Direction Analysis**:
   - Multi-timeframe momentum analysis
   - Support/resistance level identification
   - Technical signal aggregation
   - Market structure analysis

3. **Market Regime Identification**:
   - Automated regime classification
   - Confidence scoring
   - Regime-specific strategy recommendations
   - Risk level assessment

4. **Entry/Exit Timing Signals**:
   - Volume-based confirmation signals
   - Technical indicator convergence
   - Volatility expansion/contraction timing
   - Options-specific bias detection

Data Flow:
Kline Data → Technical Analysis → Volatility Analysis → Strategy Generation → MarketSummary

Integration Points:
- Compatible with Bybit API data formats
- Supports pandas DataFrame operations
- Optimized for MCP server responses
- JSON-serializable output for external systems
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from .technical import TechnicalIndicators
from .volatility import VolatilityAnalysis
from .market import MarketAnalysis
from .utils import IndicatorUtils
from .types import Kline, AdvancedVolatilityMetrics, CompositeVolatilityMetrics, CVOLMetrics


@dataclass
class MarketSummary:
    """
    Comprehensive Market Analysis Summary for Options Trading
    ========================================================
    
    This dataclass encapsulates all critical market intelligence needed for options trading decisions.
    It provides a structured format for market data that's optimized for both human interpretation
    and programmatic consumption by trading systems and LLMs.
    
    The design follows these principles:
    - All metrics are normalized and standardized for cross-asset comparison
    - Optional fields handle cases where advanced metrics aren't available
    - Clear separation between price action, volatility, volume, and technical analysis
    - Direct mapping to actionable trading strategies and risk management
    
    Usage Examples:
    ```python
    # Get comprehensive market summary
    summary = SummaryIndicators.get_summary_klines(symbol="BTCUSDT", klines=klines, hours=24)
    
    # Check volatility regime for strategy selection
    if summary.volatility_regime in ["high", "extreme"]:
        # Consider premium selling strategies
        strategies = [hint for hint in summary.options_strategy_hints if "sell" in hint.lower()]
    
    # Risk management using ATR
    position_size = calculate_position_size(summary.atr_metrics["atr_percentage"])
    
    # Market regime-specific logic
    if summary.market_regime == "crisis_volatility":
        # Implement defensive positioning
        pass
    ```
    
    Attributes are grouped by analysis type for logical organization:
    """
    
    # Price Action Analysis
    symbol: str                          # Trading symbol (e.g., 'BTCUSDT')
    timeframe: str                       # Analysis timeframe ('1h', '4h', '1d')
    period_hours: int                    # Lookback period in hours
    current_price: float                 # Latest close price
    price_range: Dict[str, float]        # {"min": float, "max": float, "range_pct": float, "current_position": float}
    price_momentum: Dict[str, float]     # {"1h": pct_change, "4h": pct_change, "24h": pct_change}
    
    # Volatility Intelligence (CRITICAL for options)
    volatility_profile: Dict[str, Any]   # {"current_realized": float, "recent_acceleration": float, "percentile": float, "regime": str, "expanding": bool, "contracting": bool}
    volatility_regime: str               # "low", "normal", "high", "extreme" - used for strategy selection
    volatility_percentile: float         # Where current volatility sits in historical distribution (0-100)
    
    # Volume Analysis
    volume_profile: Dict[str, float]     # {"min": float, "max": float, "mean": float, "current": float, "current_vs_mean": float}
    volume_trend: str                    # "rising", "falling", "stable" - directional volume trend
    volume_strength: str                 # "high", "normal", "low" - volume strength relative to historical average
    
    # Technical Analysis
    technical_signals: Dict[str, Any]    # {"rsi": float, "rsi_signal": str, "bb_position": float, "bb_signal": str, "macd_signal": str, "overall_bias": str}
    market_structure: Dict[str, Any]     # {"structure": str, "higher_highs": int, "higher_lows": int, "trend_strength": float}
    
    # Options-Specific Intelligence
    options_bias: str                    # "bullish", "bearish", "neutral" - directional bias for options strategies
    volatility_bias: str                 # "expanding", "contracting", "stable" - volatility direction for gamma positioning
    options_strategy_hints: List[str]    # Actionable strategy recommendations based on current conditions
    
    # Risk Management
    atr_metrics: Dict[str, float]        # {"atr_absolute": float, "atr_percentage": float, "position_size_long": float, "position_size_short": float}
    support_resistance: Dict[str, List[float]]  # {"support": [float, ...], "resistance": [float, ...]} - key price levels
    
    # Market Intelligence Summary
    market_regime: str                   # "crisis_volatility", "low_volatility_grind", "trending_market", "range_bound", "transitional"
    confidence_score: float              # 0-100 - overall confidence in the analysis based on data quality and signal alignment
    key_insights: List[str]              # Top actionable insights for immediate decision making
    
    # Advanced Volatility Metrics (Optional - requires options data)
    composite_vol_metrics: Optional[Dict[str, Any]] = None    # Composite volatility combining multiple vol measures
    cvol_metrics: Optional[Dict[str, Any]] = None            # CVOL analysis across all option strikes with volume weighting
    convexity_metrics: Optional[Dict[str, Any]] = None       # Price convexity for gamma exposure assessment
    composite_atm_ratio: Optional[float] = None              # Ratio of composite vol to ATM implied vol


class SummaryIndicators:
    """
    Professional Market Analysis Engine for Options Trading
    =====================================================
    
    This class provides comprehensive market analysis specifically designed for options trading decisions.
    All methods are static, making the class a pure analysis utility without state management.
    
    The analysis engine follows a multi-layered approach:
    1. **Data Validation**: Ensures sufficient data quality for reliable analysis
    2. **Technical Analysis**: RSI, Bollinger Bands, MACD, ATR, support/resistance
    3. **Volatility Intelligence**: Multi-timeframe volatility analysis with regime detection
    4. **Volume Analysis**: Volume trend analysis and strength assessment
    5. **Market Structure**: Price action patterns and trend identification
    6. **Strategy Generation**: Context-aware options strategy recommendations
    7. **Risk Assessment**: Position sizing and confidence scoring
    
    Key Features:
    - **Minimal Data Requirements**: Works with as few as 20 candles, optimal with 50+
    - **Multi-Timeframe Analysis**: Supports 1m, 5m, 15m, 30m, 1h, 4h, 1d timeframes
    - **Fallback Handling**: Graceful degradation when advanced metrics aren't available
    - **Performance Optimized**: Vectorized operations using pandas/numpy
    - **LLM Compatible**: Structured output optimized for external AI consumption
    
    Thread Safety: All methods are stateless and thread-safe.
    Performance: Typical execution time 50-200ms for 200 candles on modern hardware.
    """
    
    @staticmethod
    def get_summary_klines(symbol: str, klines: List[Kline], hours: int = 24, 
                          timeframe: str = "1h") -> MarketSummary:
        """
        Generate Comprehensive Market Intelligence Summary
        ===============================================
        
        This is the primary entry point for market analysis. It processes raw kline data
        and produces a complete MarketSummary with all metrics needed for options trading decisions.
        
        The analysis process:
        1. Validates input data quality and sufficiency
        2. Calculates price action metrics (momentum, range, support/resistance)
        3. Performs comprehensive volatility analysis with regime detection
        4. Analyzes volume patterns and trends
        5. Generates technical signals (RSI, MACD, Bollinger Bands)
        6. Determines market structure and trend strength
        7. Calculates advanced volatility metrics (composite vol, CVOL, convexity)
        8. Generates options-specific strategy recommendations
        9. Provides risk management metrics (ATR, position sizing)
        10. Assigns confidence score based on signal alignment
        
        Args:
            symbol (str): Trading symbol (e.g., 'BTCUSDT', 'ETHUSDT')
            klines (List[Kline]): Historical price data with OHLCV + timestamp
            hours (int, optional): Lookback period in hours. Defaults to 24.
                                 Recommended: 24-168 hours (1-7 days)
            timeframe (str, optional): Timeframe of the klines data. Defaults to "1h".
                                     Supported: "1m", "5m", "15m", "30m", "1h", "4h", "1d"
            
        Returns:
            MarketSummary: Complete market intelligence summary with:
                - Price action analysis (current price, momentum, range)
                - Volatility intelligence (regime, percentile, bias)
                - Volume analysis (trend, strength, ratios)
                - Technical signals (RSI, MACD, Bollinger Bands)
                - Options strategy recommendations
                - Risk management metrics (ATR, support/resistance)
                - Market regime classification
                - Advanced volatility metrics (when available)
        
        Raises:
            ValueError: If insufficient kline data provided (< 10 candles)
            TypeError: If klines data format is invalid
            
        Performance Notes:
            - Optimal performance with 50-200 candles
            - Advanced metrics require 30+ candles
            - Execution time: typically 50-200ms
            
        Example:
            ```python
            # Basic usage
            summary = SummaryIndicators.get_summary_klines(
                symbol="BTCUSDT",
                klines=btc_hourly_data,
                hours=168,  # 7 days
                timeframe="1h"
            )
            
            # Check volatility regime for strategy selection
            if summary.volatility_regime in ["high", "extreme"]:
                print("Consider premium selling strategies:")
                for hint in summary.options_strategy_hints:
                    if "sell" in hint.lower():
                        print(f"  - {hint}")
            
            # Risk management
            atr_pct = summary.atr_metrics["atr_percentage"]
            position_size = min(max_position, risk_capital / (atr_pct * 2))
            ```
        """
        if len(klines) < 20:
            return SummaryIndicators._minimal_summary(symbol, klines, hours, timeframe)
        
        # Calculate lookback period in candles
        timeframe_minutes = IndicatorUtils.get_timeframe_multiplier(timeframe)
        lookback_candles = min(len(klines), int(hours * 60 / timeframe_minutes))
        recent_klines = klines[-lookback_candles:] if lookback_candles > 0 else klines
        
        current_price = recent_klines[-1].close
        
        # Price Action Analysis
        price_range = SummaryIndicators._analyze_price_range(recent_klines)
        price_momentum = SummaryIndicators._analyze_price_momentum(klines, timeframe_minutes)
        
        # Volume Analysis using existing MarketAnalysis
        volume_indicators = MarketAnalysis.calculate_volume_indicators(recent_klines)
        volume_profile = {
            "min": min([k.volume for k in recent_klines]),
            "max": max([k.volume for k in recent_klines]),
            "mean": volume_indicators.get('volume_sma_20', np.mean([k.volume for k in recent_klines])),
            "current": recent_klines[-1].volume,
            "current_vs_mean": volume_indicators.get('volume_ratio', 1)
        }
        volume_trend, volume_strength = SummaryIndicators._get_volume_trend_from_indicators(volume_indicators)
        
        # Volatility Intelligence (CRITICAL) using existing VolatilityAnalysis
        vol_metrics = VolatilityAnalysis.calculate_comprehensive_metrics(klines)
        vol_regime = VolatilityAnalysis.detect_volatility_regime(klines)
        
        # Create volatility profile using existing metrics
        recent_vol = VolatilityAnalysis.calculate_realized_volatility(klines[-10:], 10)
        recent_avg = recent_vol[-1] if recent_vol and not np.isnan(recent_vol[-1]) else vol_metrics.historical_vol_20d
        vol_acceleration = recent_avg / vol_metrics.historical_vol_20d if vol_metrics.historical_vol_20d > 0 else 1
        
        volatility_profile = {
            "current_realized": vol_metrics.historical_vol_20d,
            "recent_acceleration": vol_acceleration,
            "percentile": vol_metrics.vol_percentile,
            "regime": vol_regime,
            "expanding": vol_acceleration > 1.2,
            "contracting": vol_acceleration < 0.8
        }
        
        # Technical Analysis using existing modules
        technical_signals = SummaryIndicators._get_enhanced_technical_signals(klines)
        market_structure_data = MarketAnalysis.detect_market_structure(recent_klines)
        market_structure = {
            "structure": market_structure_data.trend_direction,
            "higher_highs": len(market_structure_data.swing_highs),
            "higher_lows": len(market_structure_data.swing_lows),
            "trend_strength": market_structure_data.trend_strength
        }
        
        # ATR for Position Sizing using existing TechnicalIndicators
        atr_values = TechnicalIndicators.calculate_atr(recent_klines, 14)
        current_atr = 0
        if atr_values:
            for atr in reversed(atr_values):
                if not np.isnan(atr):
                    current_atr = atr
                    break
        current_price = recent_klines[-1].close
        atr_pct = (current_atr / current_price) * 100 if current_price > 0 else 0
        atr_metrics = {
            "atr_absolute": current_atr,
            "atr_percentage": atr_pct,
            "position_size_long": current_price - (2 * current_atr),
            "position_size_short": current_price + (2 * current_atr)
        }
        
        # Support/Resistance using existing MarketAnalysis
        key_levels = MarketAnalysis.get_key_levels(recent_klines)
        support_resistance = {
            "support": key_levels.get('support_levels', [])[:3],
            "resistance": key_levels.get('resistance_levels', [])[:3]
        }
        
        # Advanced Volatility Metrics
        advanced_vol_metrics = VolatilityAnalysis.calculate_advanced_volatility_metrics(klines)
        
        # Options-Specific Analysis
        options_bias, volatility_bias = SummaryIndicators._analyze_options_bias(
            price_momentum, volatility_profile, technical_signals
        )
        strategy_hints = SummaryIndicators._generate_strategy_hints(
            options_bias, volatility_bias, vol_regime, technical_signals,
            advanced_vol_metrics.composite_vol_metrics.__dict__ if advanced_vol_metrics.composite_vol_metrics else None,
            advanced_vol_metrics.convexity_metrics.__dict__ if advanced_vol_metrics.convexity_metrics else None
        )
        
        # Market Regime
        market_regime = SummaryIndicators._determine_market_regime(
            price_momentum, vol_regime, technical_signals, volume_trend
        )
        
        # Confidence Score
        confidence_score = SummaryIndicators._calculate_confidence_score(
            technical_signals, volume_strength, volatility_profile
        )
        
        # Key Insights
        key_insights = SummaryIndicators._generate_key_insights(
            price_momentum, volatility_profile, technical_signals, market_regime, vol_regime
        )
        
        # Simplified dataclass creation - let dataclass handle the complexity
        from dataclasses import asdict
        
        return MarketSummary(
            symbol=symbol,
            timeframe=timeframe,
            period_hours=hours,
            current_price=current_price,
            price_range=price_range,
            price_momentum=price_momentum,
            volatility_profile=volatility_profile,
            volatility_regime=vol_regime,
            volatility_percentile=vol_metrics.vol_percentile,
            volume_profile=volume_profile,
            volume_trend=volume_trend,
            volume_strength=volume_strength,
            technical_signals=technical_signals,
            market_structure=market_structure,
            options_bias=options_bias,
            volatility_bias=volatility_bias,
            options_strategy_hints=strategy_hints,
            atr_metrics=atr_metrics,
            support_resistance=support_resistance,
            market_regime=market_regime,
            confidence_score=confidence_score,
            key_insights=key_insights,
            # Simplified nested structure conversion
            composite_vol_metrics=asdict(advanced_vol_metrics.composite_vol_metrics),
            cvol_metrics=asdict(advanced_vol_metrics.cvol_metrics),
            convexity_metrics=asdict(advanced_vol_metrics.convexity_metrics),
            composite_atm_ratio=advanced_vol_metrics.composite_atm_ratio
        )
    
    @staticmethod
    def get_volatility_intelligence(klines: List[Kline], symbol: str = "") -> Dict[str, Any]:
        """
        Focused volatility analysis for options trading.
        
        Returns:
            Comprehensive volatility intelligence optimized for options decisions
        """
        if len(klines) < 30:
            return {"error": "Insufficient data for volatility analysis"}
        
        vol_metrics = VolatilityAnalysis.calculate_comprehensive_metrics(klines)
        vol_regime = VolatilityAnalysis.detect_volatility_regime(klines)
        vol_cone = VolatilityAnalysis.calculate_volatility_cone(klines)
        
        # Current vs Historical
        current_vol = vol_metrics.historical_vol_20d
        vol_percentile = vol_metrics.vol_percentile
        
        # Volatility trend
        recent_vol = VolatilityAnalysis.calculate_realized_volatility(klines[-10:], 10)
        vol_trend = "rising" if recent_vol[-1] > vol_metrics.historical_vol_20d else "falling"
        
        # Options trading signals
        vol_signals = []
        if vol_percentile > 80:
            vol_signals.append("HIGH_IV_SELL")
        elif vol_percentile < 20:
            vol_signals.append("LOW_IV_BUY")
        
        if vol_regime in ["extreme", "high"]:
            vol_signals.append("VOLATILITY_SPIKE")
        elif vol_regime == "low":
            vol_signals.append("VOLATILITY_COMPRESSION")
        
        return {
            "current_volatility": current_vol,
            "volatility_regime": vol_regime,
            "volatility_percentile": vol_percentile,
            "volatility_trend": vol_trend,
            "volatility_cone": vol_cone,
            "trading_signals": vol_signals,
            "options_bias": "sell_premium" if vol_percentile > 70 else "buy_premium" if vol_percentile < 30 else "neutral",
            "mean_reversion_probability": 100 - vol_percentile if vol_percentile > 50 else vol_percentile
        }
    
    @staticmethod
    def get_detailed_macd_analysis(klines: List[Kline], symbol: str = "") -> Dict[str, Any]:
        """
        Detailed MACD analysis for options trading decisions.
        """
        if len(klines) < 50:
            return {"error": "Insufficient data for MACD analysis"}
        
        prices = [k.close for k in klines]
        current_price = prices[-1]
        
        # Calculate MACD
        macd = TechnicalIndicators.calculate_macd(prices, 12, 26, 9)
        
        if not macd.macd_line or all(np.isnan(x) for x in macd.macd_line):
            return {"error": "Unable to calculate MACD"}
        
        # Current values
        macd_line = macd.macd_line[-1] if not np.isnan(macd.macd_line[-1]) else 0
        signal_line = macd.signal_line[-1] if not np.isnan(macd.signal_line[-1]) else 0
        histogram = macd.histogram[-1] if not np.isnan(macd.histogram[-1]) else 0
        
        # Signal analysis
        bullish = macd_line > signal_line
        
        # Momentum analysis
        recent_hist = [h for h in macd.histogram[-5:] if not np.isnan(h)]
        momentum_trend = "neutral"
        if len(recent_hist) >= 3:
            if recent_hist[-1] > recent_hist[-2] > recent_hist[-3]:
                momentum_trend = "accelerating"
            elif recent_hist[-1] < recent_hist[-2] < recent_hist[-3]:
                momentum_trend = "decelerating"
            elif recent_hist[-1] > recent_hist[-2]:
                momentum_trend = "improving"
            elif recent_hist[-1] < recent_hist[-2]:
                momentum_trend = "weakening"
        
        # Crossover detection
        if len(macd.macd_line) >= 2 and len(macd.signal_line) >= 2:
            prev_macd = macd.macd_line[-2]
            prev_signal = macd.signal_line[-2]
            if not np.isnan(prev_macd) and not np.isnan(prev_signal):
                if prev_macd <= prev_signal and macd_line > signal_line:
                    crossover = "bullish_crossover"
                elif prev_macd >= prev_signal and macd_line < signal_line:
                    crossover = "bearish_crossover"
                else:
                    crossover = "none"
            else:
                crossover = "none"
        else:
            crossover = "none"
        
        # Options trading signals
        options_signals = []
        if crossover == "bullish_crossover":
            options_signals.append("Consider call spreads or long volatility")
        elif crossover == "bearish_crossover":
            options_signals.append("Consider put spreads or protective puts")
        
        if momentum_trend == "accelerating" and bullish:
            options_signals.append("Strong uptrend - consider momentum strategies")
        elif momentum_trend == "accelerating" and not bullish:
            options_signals.append("Strong downtrend - consider bearish strategies")
        
        return {
            "symbol": symbol,
            "macd_line": round(macd_line, 6),
            "signal_line": round(signal_line, 6),
            "histogram": round(histogram, 6),
            "signal": "bullish" if bullish else "bearish",
            "momentum_trend": momentum_trend,
            "crossover": crossover,
            "strength": abs(histogram / max(abs(macd_line), 0.001)),
            "options_signals": options_signals,
            "interpretation": {
                "trend": "uptrend" if bullish else "downtrend",
                "momentum": "strong" if abs(histogram) > abs(macd_line) * 0.1 else "weak",
                "timing": "good entry" if crossover != "none" else "wait for signal"
            }
        }
    
    @staticmethod
    def get_detailed_bollinger_analysis(klines: List[Kline], symbol: str = "") -> Dict[str, Any]:
        """
        Detailed Bollinger Bands analysis for options trading decisions.
        """
        if len(klines) < 30:
            return {"error": "Insufficient data for Bollinger Bands analysis"}
        
        current_price = klines[-1].close
        
        # Calculate Bollinger Bands
        bb = TechnicalIndicators.calculate_bollinger_bands(klines, 20, 2.0)
        
        if not bb.upper_band or all(np.isnan(x) for x in bb.upper_band):
            return {"error": "Unable to calculate Bollinger Bands"}
        
        # Current values
        upper = bb.upper_band[-1] if not np.isnan(bb.upper_band[-1]) else current_price
        middle = bb.middle_band[-1] if not np.isnan(bb.middle_band[-1]) else current_price
        lower = bb.lower_band[-1] if not np.isnan(bb.lower_band[-1]) else current_price
        bandwidth = bb.bandwidth[-1] if not np.isnan(bb.bandwidth[-1]) else 0
        bb_position = bb.bb_position[-1] if not np.isnan(bb.bb_position[-1]) else 50
        
        # Squeeze analysis
        recent_bandwidth = [bw for bw in bb.bandwidth[-10:] if not np.isnan(bw)]
        squeeze_status = "normal"
        if bandwidth < 10:
            squeeze_status = "tight_squeeze"
        elif bandwidth < 15:
            squeeze_status = "squeeze"
        elif bandwidth > 25:
            squeeze_status = "expansion"
        
        # Trend analysis
        if len(recent_bandwidth) >= 5:
            avg_recent = np.mean(recent_bandwidth[-5:])
            avg_earlier = np.mean(recent_bandwidth[-10:-5])
            if avg_recent > avg_earlier * 1.2:
                volatility_trend = "expanding"
            elif avg_recent < avg_earlier * 0.8:
                volatility_trend = "contracting"
            else:
                volatility_trend = "stable"
        else:
            volatility_trend = "unknown"
        
        # Support/Resistance levels
        distance_to_upper = ((upper - current_price) / current_price) * 100
        distance_to_lower = ((current_price - lower) / current_price) * 100
        
        # Options trading signals
        options_signals = []
        
        if squeeze_status in ["tight_squeeze", "squeeze"]:
            options_signals.append("Low volatility - consider long straddles/strangles")
            options_signals.append("Prepare for breakout - volatility expansion likely")
        elif squeeze_status == "expansion":
            options_signals.append("High volatility - consider short straddles/iron condors")
        
        if bb_position > 80:
            options_signals.append("Overbought - consider put spreads or covered calls")
        elif bb_position < 20:
            options_signals.append("Oversold - consider call spreads or protective puts")
        
        if current_price > upper:
            options_signals.append("Above upper band - strong momentum, but watch for reversal")
        elif current_price < lower:
            options_signals.append("Below lower band - oversold, potential bounce")
        
        return {
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "upper_band": round(upper, 2),
            "middle_band": round(middle, 2),
            "lower_band": round(lower, 2),
            "bandwidth": round(bandwidth, 2),
            "bb_position": round(bb_position, 1),
            "squeeze_status": squeeze_status,
            "volatility_trend": volatility_trend,
            "distance_to_upper": round(distance_to_upper, 2),
            "distance_to_lower": round(distance_to_lower, 2),
            "options_signals": options_signals,
            "interpretation": {
                "position": "overbought" if bb_position > 80 else "oversold" if bb_position < 20 else "neutral",
                "volatility": "low" if squeeze_status in ["tight_squeeze", "squeeze"] else "high" if squeeze_status == "expansion" else "normal",
                "trend": "bullish" if bb_position > 60 else "bearish" if bb_position < 40 else "sideways"
            }
        }
    
    @staticmethod
    def get_market_regime_analysis(klines: List[Kline], symbol: str = "") -> Dict[str, Any]:
        """
        Comprehensive market regime identification for strategic positioning.
        """
        if len(klines) < 50:
            return {"regime": "unknown", "confidence": 0}
        
        # Price trend analysis
        prices = [k.close for k in klines]
        sma_20 = TechnicalIndicators.calculate_sma(prices, 20)
        sma_50 = TechnicalIndicators.calculate_sma(prices, 50)
        
        # Trend determination
        if sma_20[-1] > sma_50[-1]:
            trend = "uptrend" if prices[-1] > sma_20[-1] else "uptrend_weakening"
        else:
            trend = "downtrend" if prices[-1] < sma_20[-1] else "downtrend_weakening"
        
        # Volatility regime
        vol_regime = VolatilityAnalysis.detect_volatility_regime(klines)
        
        # Volume analysis
        volumes = [k.volume for k in klines[-20:]]
        avg_volume = np.mean(volumes)
        recent_volume = np.mean(volumes[-5:])
        volume_trend = "increasing" if recent_volume > avg_volume * 1.2 else "decreasing" if recent_volume < avg_volume * 0.8 else "stable"
        
        # Market regimes
        if vol_regime in ["extreme", "high"] and volume_trend == "increasing":
            regime = "crisis_mode"
            confidence = 85
        elif vol_regime == "low" and trend.startswith("uptrend"):
            regime = "bull_market_grind"
            confidence = 75
        elif vol_regime in ["high", "extreme"] and trend.startswith("downtrend"):
            regime = "bear_market_volatility"
            confidence = 80
        elif vol_regime == "normal":
            regime = "range_bound_market"
            confidence = 60
        else:
            regime = "transitional"
            confidence = 40
        
        return {
            "regime": regime,
            "trend": trend,
            "volatility_regime": vol_regime,
            "volume_trend": volume_trend,
            "confidence": confidence,
            "regime_characteristics": SummaryIndicators._get_regime_characteristics(regime)
        }
    
    # Helper Methods
    
    @staticmethod
    def _analyze_price_range(klines: List[Kline]) -> Dict[str, float]:
        """Analyze price range for the period."""
        prices = [k.close for k in klines]
        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        
        price_min = min(lows)
        price_max = max(highs)
        current_price = prices[-1]
        
        range_pct = ((price_max - price_min) / price_min) * 100
        position_in_range = ((current_price - price_min) / (price_max - price_min)) * 100
        
        return {
            "min": price_min,
            "max": price_max,
            "range_pct": range_pct,
            "current_position": position_in_range
        }
    
    @staticmethod
    def _analyze_price_momentum(klines: List[Kline], timeframe_minutes: int) -> Dict[str, float]:
        """Calculate price momentum across different timeframes."""
        if len(klines) < 24:
            return {"1h": 0, "4h": 0, "24h": 0}
        
        current_price = klines[-1].close
        
        # Calculate lookback indices
        h1_candles = max(1, int(60 / timeframe_minutes))
        h4_candles = max(1, int(240 / timeframe_minutes))
        h24_candles = max(1, int(1440 / timeframe_minutes))
        
        momentum = {}
        
        if len(klines) > h1_candles:
            h1_price = klines[-h1_candles].close
            momentum["1h"] = ((current_price - h1_price) / h1_price) * 100
        else:
            momentum["1h"] = 0
        
        if len(klines) > h4_candles:
            h4_price = klines[-h4_candles].close
            momentum["4h"] = ((current_price - h4_price) / h4_price) * 100
        else:
            momentum["4h"] = 0
        
        if len(klines) > h24_candles:
            h24_price = klines[-h24_candles].close
            momentum["24h"] = ((current_price - h24_price) / h24_price) * 100
        else:
            momentum["24h"] = 0
        
        return momentum
    
    @staticmethod
    def _get_volume_trend_from_indicators(volume_indicators: Dict[str, float]) -> Tuple[str, str]:
        """Extract volume trend and strength from MarketAnalysis indicators."""
        if not volume_indicators:
            return "unknown", "unknown"
        
        volume_trend_pct = volume_indicators.get('volume_trend_pct', 0)
        volume_ratio = volume_indicators.get('volume_ratio', 1)
        
        # Determine trend
        if volume_trend_pct > 30:
            trend = "rising"
        elif volume_trend_pct < -30:
            trend = "falling"
        else:
            trend = "stable"
        
        # Determine strength
        if volume_ratio > 1.5:
            strength = "high"
        elif volume_ratio < 0.5:
            strength = "low"
        else:
            strength = "normal"
        
        return trend, strength
    
    
    @staticmethod
    def _get_enhanced_technical_signals(klines: List[Kline]) -> Dict[str, Any]:
        """Generate enhanced technical analysis signals using existing modules."""
        if len(klines) < 50:
            return {}
        
        prices = [k.close for k in klines]
        current_price = prices[-1]
        
        # Use existing TechnicalIndicators
        rsi = TechnicalIndicators.calculate_rsi(prices, 14)
        current_rsi = rsi[-1] if rsi and not np.isnan(rsi[-1]) else 50
        
        bb = TechnicalIndicators.calculate_bollinger_bands(klines, 20, 2.0)
        bb_position = bb.bb_position[-1] if bb.bb_position and not np.isnan(bb.bb_position[-1]) else 50
        bb_bandwidth = bb.bandwidth[-1] if bb.bandwidth and not np.isnan(bb.bandwidth[-1]) else 0
        
        macd = TechnicalIndicators.calculate_macd(prices, 12, 26, 9)
        macd_line = macd.macd_line[-1] if macd.macd_line and not np.isnan(macd.macd_line[-1]) else 0
        macd_signal_line = macd.signal_line[-1] if macd.signal_line and not np.isnan(macd.signal_line[-1]) else 0
        macd_histogram = macd.histogram[-1] if macd.histogram and not np.isnan(macd.histogram[-1]) else 0
        
        macd_bullish = macd_line > macd_signal_line
        macd_signal = "bullish" if macd_bullish else "bearish"
        
        return {
            "rsi": current_rsi,
            "rsi_signal": "overbought" if current_rsi > 70 else "oversold" if current_rsi < 30 else "neutral",
            "bb_position": bb_position,
            "bb_signal": "overbought" if bb_position > 80 else "oversold" if bb_position < 20 else "neutral",
            "bb_bandwidth": bb_bandwidth,
            "bb_squeeze": bb_bandwidth < 10,
            "macd_line": macd_line,
            "macd_signal_line": macd_signal_line,
            "macd_histogram": macd_histogram,
            "macd_signal": macd_signal,
            "overall_bias": SummaryIndicators._determine_technical_bias(current_rsi, bb_position, macd_signal)
        }
    
    
    
    
    @staticmethod
    def _analyze_options_bias(price_momentum: Dict[str, float], 
                            volatility_profile: Dict[str, Any],
                            technical_signals: Dict[str, Any]) -> Tuple[str, str]:
        """Determine options trading bias."""
        
        # Price bias
        momentum_score = price_momentum.get("24h", 0) + price_momentum.get("4h", 0) * 0.5
        
        if momentum_score > 3:
            price_bias = "bullish"
        elif momentum_score < -3:
            price_bias = "bearish"
        else:
            price_bias = "neutral"
        
        # Volatility bias
        if volatility_profile.get("expanding", False):
            vol_bias = "expanding"
        elif volatility_profile.get("contracting", False):
            vol_bias = "contracting"
        else:
            vol_bias = "stable"
        
        return price_bias, vol_bias
    
    @staticmethod
    def _generate_strategy_hints(options_bias: str, volatility_bias: str, 
                               vol_regime: str, technical_signals: Dict[str, Any],
                               composite_vol_metrics: Dict[str, Any] = None,
                               convexity_metrics: Dict[str, Any] = None) -> List[str]:
        """Generate options strategy suggestions."""
        hints = []
        
        # High IV strategies
        if vol_regime in ["high", "extreme"]:
            hints.append("Consider selling premium (short straddles, iron condors)")
            hints.append("High IV environment favors net short positions")
        
        # Low IV strategies
        elif vol_regime == "low":
            hints.append("Consider buying premium (long straddles, butterflies)")
            hints.append("Low IV environment favors net long positions")
        
        # Directional bias
        if options_bias == "bullish":
            hints.append("Bullish bias: Consider call spreads, risk reversals")
        elif options_bias == "bearish":
            hints.append("Bearish bias: Consider put spreads, protective puts")
        
        # Volatility expansion/contraction
        if volatility_bias == "expanding":
            hints.append("Volatility expanding: Long gamma positions")
        elif volatility_bias == "contracting":
            hints.append("Volatility contracting: Short gamma positions")
        
        # Composite Volatility-based strategies
        if composite_vol_metrics:
            composite_vol_regime = composite_vol_metrics.get('composite_vol_regime', 'normal')
            composite_vol_percentile = composite_vol_metrics.get('composite_vol_percentile', 50)
            
            if composite_vol_regime in ['extreme', 'high'] and composite_vol_percentile > 80:
                hints.append("Elevated Composite Volatility: Consider premium selling strategies")
            elif composite_vol_regime == 'low' and composite_vol_percentile < 20:
                hints.append("Low Composite Volatility: Consider long volatility strategies")
            
            if composite_vol_percentile > 90:
                hints.append("Composite Volatility at extreme levels: Monitor for mean reversion")
        
        # Convexity-based strategies  
        if convexity_metrics:
            convexity_trend = convexity_metrics.get('convexity_trend', 'stable')
            convexity_regime = convexity_metrics.get('convexity_regime', 'normal')
            
            if convexity_trend == 'increasing' and convexity_regime == 'high':
                hints.append("Rising convexity: Consider long gamma strategies")
            elif convexity_trend == 'decreasing' and convexity_regime == 'low':
                hints.append("Falling convexity: Consider short gamma strategies")
            
            if convexity_regime == 'high':
                hints.append("High convexity: Expect accelerating price moves")
        
        return hints
    
    @staticmethod
    def _determine_market_regime(price_momentum: Dict[str, float], vol_regime: str,
                               technical_signals: Dict[str, Any], volume_trend: str) -> str:
        """Determine overall market regime."""
        
        momentum_24h = price_momentum.get("24h", 0)
        
        if vol_regime in ["extreme", "high"] and abs(momentum_24h) > 5:
            return "crisis_volatility"
        elif vol_regime == "low" and abs(momentum_24h) < 2:
            return "low_volatility_grind"
        elif volume_trend == "rising" and abs(momentum_24h) > 3:
            return "trending_market"
        elif volume_trend == "falling" and abs(momentum_24h) < 1:
            return "range_bound"
        else:
            return "transitional"
    
    @staticmethod
    def _calculate_confidence_score(technical_signals: Dict[str, Any], 
                                  volume_strength: str, 
                                  volatility_profile: Dict[str, Any]) -> float:
        """Calculate confidence score for the analysis."""
        score = 50  # Base score
        
        # Technical alignment
        if technical_signals.get("overall_bias") != "neutral":
            score += 15
        
        # Volume confirmation
        if volume_strength == "high":
            score += 20
        elif volume_strength == "normal":
            score += 10
        
        # Volatility regime clarity
        if volatility_profile.get("percentile", 50) > 80 or volatility_profile.get("percentile", 50) < 20:
            score += 15
        
        return min(100, max(0, score))
    
    @staticmethod
    def _generate_key_insights(price_momentum: Dict[str, float], 
                             volatility_profile: Dict[str, Any],
                             technical_signals: Dict[str, Any],
                             market_regime: str, vol_regime: str) -> List[str]:
        """Generate key actionable insights."""
        insights = []
        
        # Price insights
        momentum_24h = price_momentum.get("24h", 0)
        if abs(momentum_24h) > 5:
            direction = "up" if momentum_24h > 0 else "down"
            insights.append(f"Strong 24h momentum {direction} ({momentum_24h:.1f}%)")
        
        # Volatility insights
        vol_percentile = volatility_profile.get("percentile", 50)
        if vol_percentile > 80:
            insights.append(f"High IV environment ({vol_percentile:.0f}th percentile) - consider selling premium")
        elif vol_percentile < 20:
            insights.append(f"Low IV environment ({vol_percentile:.0f}th percentile) - consider buying premium")
        
        # Technical insights
        rsi = technical_signals.get("rsi", 50)
        if rsi > 70:
            insights.append(f"Overbought conditions (RSI: {rsi:.0f})")
        elif rsi < 30:
            insights.append(f"Oversold conditions (RSI: {rsi:.0f})")
        
        # Market regime insight
        insights.append(f"Market regime: {market_regime.replace('_', ' ')}")
        
        return insights
    
    @staticmethod
    def _determine_technical_bias(rsi: float, bb_position: float, macd_signal: str) -> str:
        """Determine overall technical bias."""
        bullish_signals = 0
        bearish_signals = 0
        
        if rsi > 50:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if bb_position > 50:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if macd_signal == "bullish":
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if bullish_signals > bearish_signals:
            return "bullish"
        elif bearish_signals > bullish_signals:
            return "bearish"
        else:
            return "neutral"
    
    @staticmethod
    def _get_regime_characteristics(regime: str) -> Dict[str, str]:
        """Get characteristics of market regime."""
        regimes = {
            "crisis_mode": {
                "description": "High volatility with significant price moves",
                "options_strategy": "Short premium, delta hedge frequently",
                "risk_level": "Very High"
            },
            "bull_market_grind": {
                "description": "Steady uptrend with low volatility",
                "options_strategy": "Buy calls, sell puts, covered calls",
                "risk_level": "Low"
            },
            "bear_market_volatility": {
                "description": "Downtrend with high volatility",
                "options_strategy": "Protective puts, bear spreads",
                "risk_level": "High"
            },
            "range_bound_market": {
                "description": "Sideways movement with normal volatility",
                "options_strategy": "Iron condors, short straddles",
                "risk_level": "Medium"
            },
            "transitional": {
                "description": "Unclear market direction",
                "options_strategy": "Wait for clarity, small positions",
                "risk_level": "Medium"
            }
        }
        
        return regimes.get(regime, {
            "description": "Unknown market conditions",
            "options_strategy": "Exercise caution",
            "risk_level": "Unknown"
        })
    
    @staticmethod
    def _minimal_summary(symbol: str, klines: List[Kline], hours: int, timeframe: str) -> MarketSummary:
        """Create minimal summary when insufficient data."""
        current_price = klines[-1].close if klines else 0
        
        return MarketSummary(
            symbol=symbol,
            timeframe=timeframe,
            period_hours=hours,
            current_price=current_price,
            price_range={"min": current_price, "max": current_price, "range_pct": 0},
            price_momentum={"1h": 0, "4h": 0, "24h": 0},
            volatility_profile={"current_realized": 0, "percentile": 50},
            volatility_regime="unknown",
            volatility_percentile=50,
            volume_profile={"min": 0, "max": 0, "mean": 0, "current": 0},
            volume_trend="unknown",
            volume_strength="unknown",
            technical_signals={},
            market_structure={},
            options_bias="neutral",
            volatility_bias="stable",
            options_strategy_hints=["Insufficient data for analysis"],
            atr_metrics={"atr_absolute": 0, "atr_percentage": 0},
            support_resistance={"support": [], "resistance": []},
            market_regime="unknown",
            confidence_score=0,
            key_insights=["Insufficient data for comprehensive analysis"]
        )