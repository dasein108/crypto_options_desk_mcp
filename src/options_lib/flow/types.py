"""Data types for options flow analysis module."""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum


class OptionType(str, Enum):
    """Option type enumeration."""
    CALL = "C"
    PUT = "P"


class FlowDirection(str, Enum):
    """Options flow direction."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class VolatilityRegime(str, Enum):
    """Volatility regime classification."""
    LOW = "low"
    NORMAL = "normal" 
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class OptionsChainData:
    """Options chain data structure."""
    symbol: str
    underlying_symbol: str
    strike: float
    expiry_date: str
    option_type: OptionType
    underlying_price: float
    mark_price: float
    mark_iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    volume: float
    open_interest: float
    bid_price: float
    ask_price: float
    bid_iv: float
    ask_iv: float
    timestamp: Optional[datetime] = None


@dataclass
class GEXLevels:
    """Gamma Exposure levels analysis."""
    strike: float
    call_gex: float
    put_gex: float
    net_gex: float
    call_oi: float
    put_oi: float
    total_oi: float


@dataclass
class GEXAnalysis:
    """Comprehensive Gamma Exposure analysis."""
    base_coin: str
    underlying_price: float
    analysis_timestamp: datetime
    
    # GEX by strike
    gex_levels: List[GEXLevels]
    
    # Key levels
    total_net_gex: float
    gex_flip_level: float  # Where net GEX changes sign
    
    # Resistance/Support levels based on GEX
    resistance_levels: List[Tuple[float, float]]  # (strike, gex_value)
    support_levels: List[Tuple[float, float]]     # (strike, gex_value)
    
    # Market impact assessment
    suppression_zones: List[Tuple[float, float]]  # Price ranges with high negative GEX
    acceleration_zones: List[Tuple[float, float]] # Price ranges with high positive GEX
    
    # Trading implications
    expected_max_move: float
    vol_suppression_active: bool
    breakout_probability: float


@dataclass
class VannaExposure:
    """Vanna exposure by strike."""
    strike: float
    call_vanna: float  # delta per vol point
    put_vanna: float   # delta per vol point
    net_vanna: float   # delta per vol point
    call_oi: float
    put_oi: float


@dataclass
class VannaAnalysis:
    """Comprehensive Vanna analysis."""
    base_coin: str
    underlying_price: float
    analysis_timestamp: datetime
    
    # Vanna by strike
    vanna_exposures: List[VannaExposure]
    
    # Aggregated metrics
    total_vanna: float  # delta per vol point
    vanna_trigger_up: float    # Price level where positive vanna kicks in
    vanna_trigger_down: float  # Price level where negative vanna kicks in
    
    # Flow predictions
    predicted_flow: FlowDirection
    flow_strength: float  # 0-100 scale
    
    # Volatility impact
    vol_impact_up: float    # Expected IV change if price moves up
    vol_impact_down: float  # Expected IV change if price moves down


@dataclass
class DeltaImbalance:
    """Delta imbalance analysis."""
    total_call_delta: float
    total_put_delta: float
    net_delta: float
    delta_imbalance_ratio: float  # Calls / (Calls + Puts)
    
    # Dealer positioning
    estimated_dealer_delta: float
    dealer_hedging_pressure: FlowDirection


@dataclass
class FlowMetrics:
    """Options flow metrics."""
    call_volume: float
    put_volume: float
    call_put_ratio: float
    
    # Unusual activity
    unusual_call_volume: float
    unusual_put_volume: float
    
    # Open interest changes
    call_oi_change: float
    put_oi_change: float
    
    # Premium flows
    total_premium: float
    call_premium: float
    put_premium: float


@dataclass
class UnusualActivity:
    """Unusual options activity detection."""
    symbol: str
    strike: float
    expiry_date: str
    option_type: OptionType
    
    # Volume metrics
    volume: float
    avg_volume_10d: float
    volume_ratio: float
    
    # Open interest
    open_interest: float
    oi_change: float
    
    # Premium metrics
    premium: float
    iv_percentile: float
    
    # Classification
    activity_type: str  # "sweep", "block", "unusual_volume", "dark_pool"
    confidence: float  # 0-100
    bullish_probability: float  # 0-100


@dataclass
class VolatilitySkew:
    """Volatility skew analysis."""
    expiry_date: str
    
    # Skew metrics
    put_call_skew: float        # Put IV - Call IV at ATM
    risk_reversal_skew: float   # 25-delta put IV - 25-delta call IV
    
    # Term structure
    atm_iv: float
    iv_slope: float  # How IV changes with moneyness
    
    # Skew indicators
    skew_direction: str  # "put_heavy", "call_heavy", "flat"
    skew_extremeness: float  # How extreme the skew is (0-100 percentile)


@dataclass
class TermStructure:
    """Options term structure analysis."""
    base_coin: str
    underlying_price: float
    
    # Term structure by expiry
    expiry_analysis: List[VolatilitySkew]
    
    # Overall structure
    front_month_iv: float
    back_month_iv: float
    term_structure_slope: float  # Positive = contango, Negative = backwardation
    
    # Trading opportunities
    calendar_spread_opportunities: List[Dict[str, Any]]
    
    
@dataclass
class RegimeAnalysis:
    """Volatility regime analysis."""
    current_regime: VolatilityRegime
    regime_probability: float
    time_in_regime: int  # days
    
    # Regime change signals
    regime_change_probability: float
    next_likely_regime: VolatilityRegime
    
    # Key indicators
    vix_level: float
    realized_vs_implied: float
    vol_of_vol: float
    
    # Options market indicators
    put_call_ratio: float
    skew_level: float
    term_structure_slope: float


@dataclass
class OptionsFlowSummary:
    """Comprehensive options flow summary for LLM optimization."""
    base_coin: str
    underlying_price: float
    analysis_timestamp: datetime
    
    # Key metrics (most important for LLM)
    overall_sentiment: FlowDirection
    conviction_score: float  # 0-100
    
    # GEX summary
    net_gex: float
    gex_flip_level: float
    key_resistance: Optional[float]
    key_support: Optional[float]
    
    # Vanna summary  
    net_vanna: float
    vanna_trigger_up: float
    vanna_trigger_down: float
    
    # Flow summary
    call_put_ratio: float
    unusual_activity_count: int
    net_premium_flow: float
    
    # Regime summary
    vol_regime: VolatilityRegime
    skew_direction: str
    
    # Trading signals
    primary_signal: str
    signal_strength: float  # 0-100
    key_levels: List[float]
    
    # Recommendations (LLM-friendly)
    recommendations: List[str]


@dataclass
class OptionsFlowConfig:
    """Configuration for options flow analysis."""
    # GEX calculation settings
    spot_gamma_cutoff: float = 0.01  # Ignore strikes with < 1% of spot gamma
    
    # Vanna settings
    vanna_threshold: float = 0.001
    
    # Unusual activity thresholds
    volume_threshold: float = 3.0  # Volume must be 3x average
    oi_change_threshold: float = 0.5  # 50% OI change threshold
    
    # Skew analysis
    min_options_for_skew: int = 5
    
    # Time to expiry filters
    min_dte: int = 1    # Minimum days to expiry
    max_dte: int = 60   # Maximum days to expiry
    
    # Moneyness filters
    min_moneyness: float = 0.7   # 70% of spot
    max_moneyness: float = 1.3   # 130% of spot
