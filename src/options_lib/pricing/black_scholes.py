"""Professional options pricing and Greeks calculation using py-vollib."""

import logging
import py_vollib.black_scholes as bs
import py_vollib.black_scholes.greeks.analytical as greeks
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass

from ..symbol_parser import parse_bybit_option_symbol

logger = logging.getLogger(__name__)


@dataclass
class OptionSpec:
    """Specification for an option contract."""
    symbol: str
    underlying_price: float
    strike: float
    expiration_date: datetime
    option_type: str  # 'call' or 'put'
    risk_free_rate: float = 0.05
    implied_volatility: Optional[float] = None


@dataclass
class OptionMetrics:
    """Comprehensive option pricing metrics."""
    theoretical_price: float
    delta: float
    gamma: float
    theta: float  # Per day
    vega: float  # Per 1% vol change
    rho: float
    time_to_expiration: float  # In years
    intrinsic_value: float
    time_value: float


class ProfessionalOptionsEngine:
    """Professional options pricing engine using py-vollib Black-Scholes implementation."""
    
    def __init__(self, risk_free_rate: float = 0.05):
        """
        Initialize the pricing engine.
        
        Args:
            risk_free_rate: Risk-free interest rate (default 5%)
        """
        self.risk_free_rate = risk_free_rate
    
    def parse_option_symbol(self, symbol: str) -> Optional[Dict]:
        """Parse Bybit option symbol format: BTC-30DEC24-70000-C"""
        parsed = parse_bybit_option_symbol(symbol)
        if parsed is None:
            return None
        return {
            'asset': parsed['asset'],
            'expiration_date': parsed['expiry_date'],
            'strike': parsed['strike'],
            'option_type': parsed['option_type_long'],
        }
    
    def calculate_time_to_expiration(self, expiration_date: datetime, 
                                   current_date: Optional[datetime] = None) -> float:
        """
        Calculate time to expiration in years with proper handling.
        
        Args:
            expiration_date: Option expiration date
            current_date: Current date (defaults to now)
            
        Returns:
            Time to expiration in years
        """
        if current_date is None:
            current_date = datetime.now()
            
        if expiration_date <= current_date:
            return 0.0
            
        # Calculate time difference in years
        time_diff = expiration_date - current_date
        years = time_diff.total_seconds() / (365.25 * 24 * 3600)
        return max(0.0, years)
    
    def calculate_option_metrics(self, spec: OptionSpec, 
                               current_date: Optional[datetime] = None) -> OptionMetrics:
        """
        Calculate comprehensive option metrics using py-vollib.
        
        Args:
            spec: Option specification
            current_date: Current date for time calculation
            
        Returns:
            OptionMetrics with all Greeks and pricing data
        """
        # Convert option type to py-vollib format
        flag = 'c' if spec.option_type.lower() in ['call', 'c'] else 'p'
        
        # Calculate time to expiration
        time_to_exp = self.calculate_time_to_expiration(spec.expiration_date, current_date)
        
        # Handle expired options
        if time_to_exp <= 0:
            intrinsic = self._calculate_intrinsic_value(
                spec.underlying_price, spec.strike, flag
            )
            
            # For expired options, delta is 1 if ITM call or 0 otherwise
            if flag == 'c':
                delta_val = 1.0 if spec.underlying_price > spec.strike else 0.0
            else:
                delta_val = -1.0 if spec.underlying_price < spec.strike else 0.0
            
            return OptionMetrics(
                theoretical_price=intrinsic,
                delta=delta_val,
                gamma=0.0, theta=0.0, vega=0.0, rho=0.0,
                time_to_expiration=0.0,
                intrinsic_value=intrinsic,
                time_value=0.0
            )
        
        # Use provided IV or default
        iv = spec.implied_volatility or 0.5  # Default 50% if not provided
        
        # Ensure IV is positive
        iv = max(0.001, iv)  # Minimum 0.1% volatility
        
        try:
            # Calculate price using py-vollib Black-Scholes
            price = bs.black_scholes(
                flag, spec.underlying_price, spec.strike, 
                time_to_exp, spec.risk_free_rate, iv
            )
            
            # Calculate Greeks using py-vollib
            delta_val = greeks.delta(
                flag, spec.underlying_price, spec.strike,
                time_to_exp, spec.risk_free_rate, iv
            )
            
            gamma_val = greeks.gamma(
                flag, spec.underlying_price, spec.strike,
                time_to_exp, spec.risk_free_rate, iv
            )
            
            # Theta per day — py-vollib's analytical.theta already returns
            # per-day values (it divides by 365 internally). The earlier
            # code double-divided by 365.25, making theta 365x too small
            # and collapsing theta P&L to near-zero in PnL attribution.
            theta_val = greeks.theta(
                flag, spec.underlying_price, spec.strike,
                time_to_exp, spec.risk_free_rate, iv
            )

            # Vega per 1 percentage point of IV — py-vollib's analytical.vega
            # already returns dPrice per 0.01 change in sigma (i.e. per 1 pp).
            # The earlier /100 made vega 100x too small.
            vega_val = greeks.vega(
                flag, spec.underlying_price, spec.strike,
                time_to_exp, spec.risk_free_rate, iv
            )

            # Rho per 1 percentage point of rate — py-vollib's analytical.rho
            # already returns dPrice per 0.01 change in r. The earlier /100
            # made rho 100x too small.
            rho_val = greeks.rho(
                flag, spec.underlying_price, spec.strike,
                time_to_exp, spec.risk_free_rate, iv
            )
            
            # Calculate intrinsic and time value
            intrinsic = self._calculate_intrinsic_value(
                spec.underlying_price, spec.strike, flag
            )
            time_value = max(0.0, price - intrinsic)
            
            # Validate results
            if price != price:  # Check for NaN
                raise ValueError("Price calculation returned NaN")
            
            return OptionMetrics(
                theoretical_price=max(0.0, price),
                delta=delta_val,
                gamma=max(0.0, gamma_val),
                theta=theta_val,  # Can be negative
                vega=max(0.0, vega_val),
                rho=rho_val,  # Can be negative
                time_to_expiration=time_to_exp,
                intrinsic_value=max(0.0, intrinsic),
                time_value=max(0.0, time_value)
            )
            
        except Exception as e:
            logger.error(f"Error calculating metrics for {spec.symbol}: {e}")
            # Return safe defaults with proper intrinsic value
            intrinsic = self._calculate_intrinsic_value(
                spec.underlying_price, spec.strike, flag
            )
            
            return OptionMetrics(
                theoretical_price=max(0.0, intrinsic),
                delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0,
                time_to_expiration=time_to_exp,
                intrinsic_value=max(0.0, intrinsic),
                time_value=0.0
            )
    
    def _calculate_intrinsic_value(self, S: float, K: float, flag: str) -> float:
        """Calculate intrinsic value for call or put."""
        if flag == 'c':
            return max(0.0, S - K)
        else:
            return max(0.0, K - S)
    

