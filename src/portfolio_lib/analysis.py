"""Portfolio Analysis - Comprehensive portfolio analysis and reporting.

This module provides high-level portfolio analysis capabilities for MCP integration,
building on top of the core PortfolioEngine functionality.
"""

from typing import Dict, Any, List
from datetime import datetime
import pandas as pd

from .engine import PortfolioEngine
from .types import Portfolio, Position, Scenario, Greeks


class PortfolioAnalyzer:
    """High-level portfolio analysis for MCP integration."""
    
    def __init__(self, portfolio_engine: PortfolioEngine = None):
        """Initialize with optional portfolio engine."""
        self.engine = portfolio_engine or PortfolioEngine()
    
    def analyze_portfolio_greeks(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive portfolio Greeks analysis with risk metrics.
        
        Args:
            portfolio_data: Portfolio dictionary with positions and metadata
            
        Returns:
            Dict with portfolio Greeks, risk metrics, and position analysis
        """
        # Convert to Portfolio object for business logic
        portfolio = self._dict_to_portfolio(portfolio_data)
        
        # Calculate portfolio-level Greeks
        portfolio_greeks = portfolio.greeks
        
        # Calculate position-level analysis
        position_analysis = []
        for symbol, position in portfolio.positions.items():
            if not position.greeks:
                continue
                
            # Position Greeks contribution
            weighted_delta = position.greeks.delta * position.quantity
            weighted_gamma = position.greeks.gamma * position.quantity  
            weighted_theta = position.greeks.theta * position.quantity
            weighted_vega = position.greeks.vega * position.quantity
            
            # Position PnL and risk metrics
            position_value = (position.current_price or 0) * position.quantity
            unrealized_pnl = 0
            if position.entry_price and position.current_price:
                unrealized_pnl = (position.current_price - position.entry_price) * position.quantity
            
            position_analysis.append({
                "symbol": symbol,
                "quantity": position.quantity,
                "current_price": position.current_price,
                "entry_price": position.entry_price,
                "position_value": position_value,
                "unrealized_pnl": unrealized_pnl,
                "delta_contribution": weighted_delta,
                "gamma_contribution": weighted_gamma,
                "theta_contribution": weighted_theta,
                "vega_contribution": weighted_vega,
                "delta_exposure": abs(weighted_delta),
                "risk_percentage": abs(position_value / portfolio_greeks.net_exposure * 100) if portfolio_greeks.net_exposure > 0 else 0
            })
        
        # Portfolio-level risk metrics
        total_unrealized_pnl = sum(pos["unrealized_pnl"] for pos in position_analysis)
        
        # Risk concentration analysis
        position_analysis.sort(key=lambda x: x["risk_percentage"], reverse=True)
        top_3_concentration = sum(pos["risk_percentage"] for pos in position_analysis[:3])
        
        # Hedging recommendations
        hedging_recs = self._generate_hedging_recommendations(portfolio_greeks, portfolio_data.get("underlying_price", 0))
        
        return {
            # Portfolio Greeks
            "total_delta": round(portfolio_greeks.delta, 4),
            "total_gamma": round(portfolio_greeks.gamma, 4), 
            "total_theta": round(portfolio_greeks.theta, 4),
            "total_vega": round(portfolio_greeks.vega, 4),
            "net_exposure": round(portfolio_greeks.net_exposure, 2),
            
            # Portfolio metrics
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "positions_count": len(position_analysis),
            "risk_concentration_top3": round(top_3_concentration, 1),
            
            # Risk assessment
            "delta_risk_level": self._assess_delta_risk(portfolio_greeks.delta),
            "gamma_risk_level": self._assess_gamma_risk(portfolio_greeks.gamma),
            "theta_decay_daily": round(portfolio_greeks.theta, 2),
            "vega_sensitivity": self._assess_vega_risk(portfolio_greeks.vega),
            
            # Position breakdown
            "position_analysis": position_analysis,
            
            # Hedging recommendations
            "hedging_recommendations": hedging_recs,
            
            # Metadata
            "analysis_timestamp": datetime.now().isoformat(),
            "base_coin": portfolio_data.get("base_coin", "UNKNOWN"),
            "underlying_price": portfolio_data.get("underlying_price", 0)
        }
    
    def analyze_scenarios(self, portfolio_data: Dict[str, Any], scenarios_config: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive scenario analysis for portfolio PnL and risk.
        
        Args:
            portfolio_data: Portfolio dictionary with positions
            scenarios_config: Configuration for scenario analysis
            
        Returns:
            Dict with scenario analysis results and insights
        """
        # Convert to Portfolio object
        portfolio = self._dict_to_portfolio(portfolio_data)
        
        # Create scenarios from config
        scenarios = self._create_scenarios_from_config(scenarios_config)
        
        # Run scenario analysis using business logic
        scenario_results = self.engine.analyze_scenario(portfolio, scenarios)
        
        # Enhanced analysis
        pnl_analysis = self._analyze_pnl_scenarios(scenario_results.pnl_matrix)
        risk_analysis = self._analyze_risk_scenarios(scenario_results.greek_sensitivity)
        
        # Summary insights
        insights = self._generate_scenario_insights(pnl_analysis, risk_analysis)
        
        return {
            # Scenario results summary
            "scenario_count": len(scenarios),
            "max_gain": pnl_analysis["max_pnl"],
            "max_loss": pnl_analysis["min_pnl"], 
            "break_even_scenarios": pnl_analysis["break_even_count"],
            "profitable_scenarios": pnl_analysis["profitable_count"],
            
            # Risk metrics
            "var_95": pnl_analysis.get("var_95", 0),
            "expected_pnl": pnl_analysis["mean_pnl"],
            "pnl_std_dev": pnl_analysis["std_pnl"],
            "sharpe_estimate": pnl_analysis.get("sharpe_estimate", 0),
            
            # Scenario breakdown
            "scenarios_summary": self._create_scenarios_summary(scenario_results.pnl_matrix),
            "risk_breakdown": risk_analysis,
            
            # Strategic insights
            "insights": insights,
            
            # Metadata
            "analysis_timestamp": datetime.now().isoformat(),
            "base_coin": portfolio_data.get("base_coin", "UNKNOWN"),
            "underlying_price": portfolio_data.get("underlying_price", 0)
        }
    
    def _dict_to_portfolio(self, portfolio_data: Dict[str, Any]) -> Portfolio:
        """Convert portfolio dictionary to Portfolio object."""
        positions = {}
        
        for symbol, pos_data in portfolio_data.get("positions", {}).items():
            greeks = None
            if pos_data.get("greeks"):
                greeks_data = pos_data["greeks"]
                greeks = Greeks(
                    delta=greeks_data.get("delta", 0),
                    gamma=greeks_data.get("gamma", 0),
                    theta=greeks_data.get("theta", 0),
                    vega=greeks_data.get("vega", 0)
                )
            
            positions[symbol] = Position(
                symbol=symbol,
                quantity=pos_data.get("quantity", 0),
                entry_price=pos_data.get("entry_price"),
                current_price=pos_data.get("current_price"),
                greeks=greeks
            )
        
        metadata = {
            "base_coin": portfolio_data.get("base_coin", "BTC"),
            "underlying_price": portfolio_data.get("underlying_price", 0),
            "source": "mcp_analysis"
        }
        
        return Portfolio(
            name=portfolio_data.get("name", "mcp_analysis"),
            positions=positions,
            metadata=metadata,
            created_at=datetime.now(),
            last_synced=datetime.now()
        )
    
    def _create_scenarios_from_config(self, config: Dict[str, Any]) -> List[Scenario]:
        """Create scenario objects from configuration."""
        scenarios = []
        
        price_scenarios = config.get("price_scenarios", [-10, -5, 0, 5, 10])
        vol_scenarios = config.get("vol_scenarios", [-20, -10, 0, 10, 20])
        days_forward = config.get("days_forward", 1)
        
        for price_change in price_scenarios:
            for vol_change in vol_scenarios:
                scenarios.append(Scenario(
                    name=f"Price{price_change:+.0f}%_Vol{vol_change:+.0f}%",
                    spot_change_pct=price_change,
                    iv_change_pct=vol_change,
                    days_forward=days_forward
                ))
        
        return scenarios
    
    def _analyze_pnl_scenarios(self, pnl_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze PnL distribution across scenarios."""
        pnl_values = pnl_df['pnl'].values
        
        return {
            "max_pnl": float(pnl_values.max()),
            "min_pnl": float(pnl_values.min()),
            "mean_pnl": float(pnl_values.mean()),
            "std_pnl": float(pnl_values.std()),
            "profitable_count": int((pnl_values > 0).sum()),
            "break_even_count": int((abs(pnl_values) < 1).sum()),
            "var_95": float(pd.Series(pnl_values).quantile(0.05)),
            "median_pnl": float(pd.Series(pnl_values).median())
        }
    
    def _analyze_risk_scenarios(self, greek_df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze Greeks distribution across scenarios.""" 
        return {
            "delta_range": [float(greek_df['delta'].min()), float(greek_df['delta'].max())],
            "gamma_range": [float(greek_df['gamma'].min()), float(greek_df['gamma'].max())],
            "theta_range": [float(greek_df['theta'].min()), float(greek_df['theta'].max())],
            "vega_range": [float(greek_df['vega'].min()), float(greek_df['vega'].max())]
        }
    
    def _create_scenarios_summary(self, pnl_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Create summary of individual scenarios."""
        summary = []
        
        for _, row in pnl_df.head(10).iterrows():  # Top 10 for LLM efficiency
            summary.append({
                "scenario": row['scenario'],
                "pnl": round(row['pnl'], 2),
                "spot_change": row['spot_change'],
                "iv_change": row['iv_change']
            })
        
        return summary
    
    def _generate_hedging_recommendations(self, greeks: Greeks, underlying_price: float) -> List[str]:
        """Generate hedging recommendations based on portfolio Greeks."""
        recs = []
        
        # Delta hedging
        if abs(greeks.delta) > 0.1:
            direction = "sell" if greeks.delta > 0 else "buy"
            shares_needed = abs(greeks.delta)
            recs.append(f"Delta hedge: {direction} {shares_needed:.2f} shares of underlying")
        
        # Gamma exposure
        if abs(greeks.gamma) > 0.01:
            recs.append("High gamma exposure - monitor for delta changes on price moves")
        
        # Theta decay
        if greeks.theta < -10:
            recs.append("High theta decay - time working against position")
        elif greeks.theta > 10:
            recs.append("Positive theta - time working in favor")
        
        # Vega risk
        if abs(greeks.vega) > 100:
            recs.append("High vega exposure - sensitive to volatility changes")
        
        if not recs:
            recs.append("Portfolio Greeks are within acceptable ranges")
        
        return recs
    
    def _generate_scenario_insights(self, pnl_analysis: Dict, risk_analysis: Dict) -> List[str]:
        """Generate strategic insights from scenario analysis."""
        insights = []
        
        # PnL insights
        if pnl_analysis["profitable_count"] / 25 > 0.6:  # Assuming 25 scenarios
            insights.append("Portfolio shows positive bias across most scenarios")
        elif pnl_analysis["profitable_count"] / 25 < 0.4:
            insights.append("Portfolio shows negative bias - consider hedging")
        
        # Risk insights
        if abs(pnl_analysis["min_pnl"]) > pnl_analysis["max_pnl"] * 2:
            insights.append("Downside risk significantly exceeds upside potential")
        
        # Volatility insights
        if pnl_analysis["std_pnl"] > abs(pnl_analysis["mean_pnl"]) * 3:
            insights.append("High volatility in outcomes - consider risk reduction")
        
        return insights
    
    def _assess_delta_risk(self, delta: float) -> str:
        """Assess delta risk level."""
        abs_delta = abs(delta)
        if abs_delta > 0.5:
            return "high"
        elif abs_delta > 0.2:
            return "medium"
        else:
            return "low"
    
    def _assess_gamma_risk(self, gamma: float) -> str:
        """Assess gamma risk level."""
        abs_gamma = abs(gamma)
        if abs_gamma > 0.02:
            return "high"
        elif abs_gamma > 0.01:
            return "medium"
        else:
            return "low"
    
    def _assess_vega_risk(self, vega: float) -> str:
        """Assess vega risk level."""
        abs_vega = abs(vega)
        if abs_vega > 200:
            return "high"
        elif abs_vega > 100:
            return "medium"
        else:
            return "low"