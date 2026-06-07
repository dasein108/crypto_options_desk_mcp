"""Data types for technical indicators module."""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime


@dataclass
class Kline:
    """OHLCV data structure for price analysis."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class BollingerBands:
    """Bollinger Bands indicator result."""
    upper_band: List[float]
    middle_band: List[float]  # SMA
    lower_band: List[float]
    bandwidth: List[float]
    bb_position: List[float]  # % position between bands


@dataclass
class MACD:
    """MACD indicator result."""
    macd_line: List[float]
    signal_line: List[float]
    histogram: List[float]


@dataclass
class Stochastic:
    """Stochastic oscillator result."""
    k_percent: List[float]
    d_percent: List[float]


@dataclass
class VolumeProfile:
    """Volume profile analysis result."""
    price_levels: List[float]
    volume_distribution: List[float]
    poc: float  # Point of Control
    value_area_high: float
    value_area_low: float
    value_area_volume_pct: float


@dataclass
class MarketStructure:
    """Market structure analysis result."""
    trend_direction: str  # "bullish", "bearish", "sideways"
    support_levels: List[float]
    resistance_levels: List[float]
    swing_highs: List[Tuple[datetime, float]]
    swing_lows: List[Tuple[datetime, float]]
    trend_strength: float  # 0-1 scale


@dataclass
class VolatilityMetrics:
    """Comprehensive volatility analysis."""
    realized_vol: List[float]
    historical_vol_20d: float
    historical_vol_30d: float
    volatility_cone: Dict[str, float]  # {10d: vol, 20d: vol, etc.}
    regime: str  # "low", "normal", "high", "extreme"
    garman_klass_vol: List[float]
    vol_percentile: float  # Where current vol sits in historical context


@dataclass
class CompositeVolatilityMetrics:
    """Composite Volatility analysis metrics - weighted combination of volatility measures."""
    composite_vol_value: float
    composite_vol_percentile: float
    composite_vol_regime: str  # "low", "normal", "high", "extreme"
    components: Dict[str, float]  # Individual volatility components


@dataclass
class CVOLMetrics:
    """CVOL (Composite Implied Volatility) analysis metrics across all strikes."""
    cvol_by_expiry: Dict[str, float]  # Average IV per expiry date
    cvol_overall: float  # Weighted average IV across all options
    cvol_by_moneyness: Dict[str, float]  # IV by moneyness buckets
    cvol_skew: Dict[str, float]  # Put/call skew metrics
    total_open_interest: float  # Total OI across all options
    volume_weighted_iv: float  # Volume-weighted implied volatility
    
    
@dataclass
class ConvexityMetrics:
    """Price convexity analysis metrics."""
    convexity_value: float
    convexity_trend: str  # "increasing", "decreasing", "stable"
    convexity_regime: str  # "low", "normal", "high"
    price_acceleration: float  # Second derivative of price
    

@dataclass
class AdvancedVolatilityMetrics:
    """Advanced volatility metrics for sophisticated options analysis."""
    composite_vol_metrics: CompositeVolatilityMetrics
    cvol_metrics: CVOLMetrics  # New CVOL as IV across all strikes
    convexity_metrics: ConvexityMetrics
    composite_atm_ratio: float  # Composite Vol divided by ATM strike volatility
    volatility_skew: Dict[str, float]  # Put/call skew metrics
    term_structure: Dict[str, float]  # Volatility across different terms


@dataclass
class TechnicalSummary:
    """Summary of all technical indicators for a symbol."""
    symbol: str
    timeframe: str
    timestamp: datetime
    
    # Price action
    current_price: float
    price_change_pct: float
    
    # Trend indicators
    sma_20: float
    sma_50: float
    ema_20: float
    rsi: float
    
    # Volatility
    atr: float
    bollinger_position: float  # Current price position in BB
    
    # Volume
    volume_sma_ratio: float  # Current volume vs 20-day average
    
    # Signals
    signals: List[str]  # List of active signals
    trend_score: float  # -100 to +100
    momentum_score: float  # -100 to +100
    volatility_percentile: float  # 0-100

    # Additional context for more precise analysis
    sma_200: float = float("nan")
    ema_50: float = float("nan")
    ema_200: float = float("nan")
    macd_line: float = float("nan")
    macd_signal: float = float("nan")
    macd_histogram: float = float("nan")
    bb_bandwidth_pct: float = float("nan")
    stoch_k: float = float("nan")
    stoch_d: float = float("nan")
    atr_pct: float = float("nan")
    atr_pct_percentile: float = float("nan")
    return_5_pct: float = float("nan")
    return_20_pct: float = float("nan")
    realized_vol_20_pct: float = float("nan")
    price_vs_sma20_pct: float = float("nan")
    price_vs_sma50_pct: float = float("nan")
    sma20_vs_sma50_pct: float = float("nan")
    ema_stack_alignment: float = float("nan")
    zscore_rolling: float = float("nan")
    trend_persistence_prob: float = float("nan")
    adx: float = float("nan")
    hurst_exponent: float = float("nan")


@dataclass
class IndicatorConfig:
    """Configuration for technical indicators."""
    rsi_period: int = 14
    atr_period: int = 14
    bb_period: int = 20
    bb_std_dev: float = 2.0
    sma_periods: List[int] = None
    ema_periods: List[int] = None
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    stoch_k_period: int = 14
    stoch_d_period: int = 3
    volume_sma_period: int = 20
    
    def __post_init__(self):
        if self.sma_periods is None:
            self.sma_periods = [20, 50, 200]
        if self.ema_periods is None:
            self.ema_periods = [12, 26, 50]
