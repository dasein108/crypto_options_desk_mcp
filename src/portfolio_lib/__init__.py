"""
Portfolio Module - Exchange-agnostic portfolio management

This module provides core portfolio management functionality including:
- Portfolio CRUD operations  
- Strategy transformations
- Scenario analysis
- Portfolio Greeks calculations

All classes follow YAGNI, KISS principles with dataclasses and pandas DataFrames.
"""

from .types import (
    Greeks,
    Position, 
    Portfolio,
    Scenario,
    ScenarioResults,
    OptionInfo
)

from .engine import PortfolioEngine
from .transformer import StrategyTransformer
from .analysis import PortfolioAnalyzer
from .risk_validator import (
    PortfolioRiskValidator,
    PortfolioRiskLimits,
    TradeRequest,
    PortfolioRiskResult,
    PortfolioValidationResult,
    AccountRiskLimits,
    AccountSnapshot,
    AccountRiskMetrics,
    AccountPositionRisk
)
from .utils import (
    parse_option_symbol,
    create_option_symbol,
    is_option_symbol,
    calculate_time_to_expiry,
    validate_portfolio_data
)

__all__ = [
    # Types
    'Greeks',
    'Position',
    'Portfolio', 
    'Scenario',
    'ScenarioResults',
    'OptionInfo',
    
    # Core classes
    'PortfolioEngine',
    'StrategyTransformer',
    'PortfolioAnalyzer',
    
    # Risk management
    'PortfolioRiskValidator',
    'PortfolioRiskLimits',
    'TradeRequest',
    'PortfolioRiskResult', 
    'PortfolioValidationResult',
    'AccountRiskLimits',
    'AccountSnapshot',
    'AccountRiskMetrics',
    'AccountPositionRisk',
    
    # Utilities
    'parse_option_symbol',
    'create_option_symbol', 
    'is_option_symbol',
    'calculate_time_to_expiry',
    'validate_portfolio_data',
]
