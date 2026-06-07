"""
Portfolio Types - All dataclasses and types for portfolio module

Contains all portfolio-related dataclasses following YAGNI, KISS principles.
All types use dataclasses over enums with automatic type conversion.
"""

import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class Greeks:
    """Options Greeks container with automatic type conversion"""
    delta: float
    gamma: float
    theta: float
    vega: float
    net_exposure: Optional[float] = None  # Optional field for exposure metrics
    
    def __post_init__(self):
        """Ensure all Greeks are float values"""
        self.delta = float(self.delta)
        self.gamma = float(self.gamma)
        self.theta = float(self.theta)
        self.vega = float(self.vega)

    def __str__(self):
        """String representation of Greeks"""
        return f"Greeks: Δ={self.delta:.4f}, Γ={self.gamma:.6f}, Θ={self.theta:.2f}, ν={self.vega:.2f}"


@dataclass  
class Position:
    """Individual position in portfolio with pricing and Greeks data"""
    symbol: str
    quantity: float
    entry_price: Optional[float] = None
    entry_iv: Optional[float] = None
    current_price: Optional[float] = None
    greeks: Optional[Greeks] = None
    
    def __post_init__(self):
        """Ensure quantity is float and convert Greeks if dict"""
        self.quantity = float(self.quantity)
        if self.entry_price is not None:
            self.entry_price = float(self.entry_price)
        if self.current_price is not None:
            self.current_price = float(self.current_price)
        if self.entry_iv is not None:
            self.entry_iv = float(self.entry_iv)
        
        # Convert dict to Greeks object if needed
        if isinstance(self.greeks, dict):
            self.greeks = Greeks(**self.greeks)

    def __str__(self):
        """String representation of Position"""
        return f"{self.symbol}: {self.quantity}, entry: {self.entry_price}, curr: {self.current_price}: {self.greeks})"


@dataclass
class Portfolio:
    """Portfolio container with positions and metadata"""
    name: str
    positions: Dict[str, Position]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    last_synced: Optional[datetime] = None
    
    def __post_init__(self):
        """Initialize datetime fields and convert positions if needed"""
        if self.created_at is None:
            self.created_at = datetime.now()
        elif isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at.replace('Z', '+00:00'))
            
        if isinstance(self.last_synced, str):
            self.last_synced = datetime.fromisoformat(self.last_synced.replace('Z', '+00:00'))
        
        # Convert position dicts to Position objects if needed
        converted_positions = {}
        for symbol, pos in self.positions.items():
            if isinstance(pos, dict):
                converted_positions[symbol] = Position(**pos)
            else:
                converted_positions[symbol] = pos
        self.positions = converted_positions

    @property
    def greeks(self) -> "Greeks":
        """Aggregate Greeks across all positions"""
        total_delta = 0.0
        total_gamma = 0.0
        total_theta = 0.0
        total_vega = 0.0
        net_exposure = 0.0
        
        for position in self.positions.values():
            if position.greeks:
                weighted_delta = position.greeks.delta * position.quantity
                weighted_gamma = position.greeks.gamma * position.quantity
                weighted_theta = position.greeks.theta * position.quantity
                weighted_vega = position.greeks.vega * position.quantity
                
                total_delta += weighted_delta
                total_gamma += weighted_gamma
                total_theta += weighted_theta
                total_vega += weighted_vega
            
            if position.current_price:
                net_exposure += abs(position.current_price * position.quantity)
        
        return Greeks(
            delta=total_delta,
            gamma=total_gamma,
            theta=total_theta,
            vega=total_vega,
            net_exposure=net_exposure
        )


@dataclass
class Scenario:
    """Market scenario definition for what-if analysis"""
    name: str
    spot_change_pct: float = 0.0
    iv_change_pct: float = 0.0
    days_forward: int = 0
    custom_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioResults:
    """Results from scenario analysis with PnL matrix and statistics"""
    scenarios: List[Scenario]
    pnl_matrix: pd.DataFrame
    greek_sensitivity: pd.DataFrame
    summary_stats: Dict[str, float]





@dataclass
class OptionInfo:
    """Parsed option symbol information"""
    base_coin: str
    expiry_date: datetime
    strike: float
    option_type: str  # 'C' or 'P'
    is_call: bool
    symbol: str