"""
Portfolio Utilities - Helper functions for portfolio operations

Contains utility functions for option symbol parsing, date handling,
and other portfolio-related operations.
"""

from datetime import datetime
from typing import Dict, Any
from .types import OptionInfo


def parse_option_symbol(symbol: str) -> OptionInfo:
    """Parse Bybit option symbol format: BTC-30DEC24-70000-C
    
    Args:
        symbol: Option symbol in Bybit format
        
    Returns:
        OptionInfo dataclass with parsed components
        
    Raises:
        ValueError: If symbol format is invalid
    """
    try:
        parts = symbol.split('-')
        if len(parts) != 4:
            raise ValueError(f"Invalid option symbol format: {symbol}")
        
        base_coin = parts[0]
        expiry_str = parts[1]
        strike = float(parts[2])
        option_type = parts[3]  # 'C' or 'P'
        
        # Parse expiry date
        expiry_date = datetime.strptime(expiry_str, '%d%b%y')
        
        return OptionInfo(
            base_coin=base_coin,
            expiry_date=expiry_date,
            strike=strike,
            option_type=option_type,
            is_call=option_type == 'C',
            symbol=symbol
        )
    except Exception as e:
        raise ValueError(f"Failed to parse option symbol {symbol}: {e}")


def create_option_symbol(base_coin: str, expiry_date: datetime, strike: float, option_type: str) -> str:
    """Create option symbol from components
    
    Args:
        base_coin: Base cryptocurrency (e.g., 'BTC')
        expiry_date: Option expiry date
        strike: Strike price
        option_type: 'C' for call, 'P' for put
        
    Returns:
        Formatted option symbol
    """
    expiry_str = expiry_date.strftime('%d%b%y').upper()
    return f"{base_coin}-{expiry_str}-{int(strike)}-{option_type}"


def is_option_symbol(symbol: str) -> bool:
    """Check if symbol is a valid option symbol format
    
    Args:
        symbol: Symbol to validate
        
    Returns:
        True if valid option symbol, False otherwise
    """
    try:
        parse_option_symbol(symbol)
        return True
    except ValueError:
        return False


def calculate_time_to_expiry(expiry_date: datetime, current_date: datetime = None) -> float:
    """Calculate time to expiry in years
    
    Args:
        expiry_date: Option expiry date
        current_date: Current date (defaults to now)
        
    Returns:
        Time to expiry in years
    """
    if current_date is None:
        current_date = datetime.now()
    
    time_delta = expiry_date - current_date
    return max(0, time_delta.total_seconds() / (365 * 24 * 60 * 60))


def validate_portfolio_data(data: Dict[str, Any]) -> bool:
    """Validate portfolio data structure
    
    Args:
        data: Portfolio data dictionary
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ['name', 'positions']
    
    # Check required fields
    for field in required_fields:
        if field not in data:
            return False
    
    # Validate positions structure
    if not isinstance(data['positions'], dict):
        return False
    
    # Basic validation of position data
    for symbol, position_data in data['positions'].items():
        if not isinstance(symbol, str) or not symbol:
            return False
        
        if isinstance(position_data, dict):
            if 'quantity' not in position_data:
                return False
            try:
                float(position_data['quantity'])
            except (ValueError, TypeError):
                return False
    
    return True