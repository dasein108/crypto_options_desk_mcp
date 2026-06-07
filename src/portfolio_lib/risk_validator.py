"""Portfolio-aware risk validation system for trading strategies."""

import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import copy

from .types import Portfolio, Position, Greeks


logger = logging.getLogger('strategy_logger')


class PortfolioRiskResult(Enum):
    """Result of portfolio risk validation."""
    APPROVED = "approved"
    BLOCKED_DELTA_LIMIT = "blocked_delta_limit"
    BLOCKED_GAMMA_LIMIT = "blocked_gamma_limit"  
    BLOCKED_THETA_LIMIT = "blocked_theta_limit"
    BLOCKED_POSITION_RATIO = "blocked_position_ratio"
    BLOCKED_HEDGING_EFFICIENCY = "blocked_hedging_efficiency"
    BLOCKED_STRATEGY_LIMIT = "blocked_strategy_limit"
    BLOCKED_MARGIN_RATIO = "blocked_margin_ratio"
    BLOCKED_ACCOUNT_LEVERAGE = "blocked_account_leverage"
    BLOCKED_GROSS_LEVERAGE = "blocked_gross_leverage"
    BLOCKED_NET_DIRECTIONAL_LIMIT = "blocked_net_directional_limit"
    BLOCKED_CONCENTRATION_LIMIT = "blocked_concentration_limit"
    BLOCKED_VAR_LIMIT = "blocked_var_limit"
    BLOCKED_TRADE_RISK = "blocked_trade_risk"
    BLOCKED_LIQUIDATION_DISTANCE = "blocked_liquidation_distance"
    BLOCKED_UNREALIZED_LOSS = "blocked_unrealized_loss"
    BLOCKED_FREE_BALANCE = "blocked_free_balance"
    BLOCKED_ACCOUNT_DATA = "blocked_account_data"
    BLOCKED_PORTFOLIO_ERROR = "blocked_portfolio_error"


@dataclass
class AccountPositionRisk:
    """Account position details used for liquidation and leverage checks."""
    symbol: str
    size: float
    mark_price: float
    liquidation_price: Optional[float]
    position_value: Optional[float]
    unrealized_pnl: float
    category: str


@dataclass
class AccountSnapshot:
    """Account-level snapshot for margin and liquidation checks."""
    total_equity: Optional[float]
    available_balance: Optional[float]
    total_margin_balance: Optional[float]
    total_initial_margin: Optional[float]
    total_maintenance_margin: Optional[float]
    total_unrealized_pnl: Optional[float]
    total_wallet_balance: Optional[float]
    positions: List[AccountPositionRisk] = field(default_factory=list)


@dataclass
class AccountRiskLimits:
    """Account-level risk limits configuration."""
    min_margin_ratio: float = 0.3
    max_account_leverage: float = 2.5
    min_liquidation_distance: float = 0.2
    soft_unrealized_loss_pct: float = 0.01
    max_unrealized_loss_pct: float = 0.018
    min_free_balance: float = 1000.0
    require_account_data: bool = True


@dataclass
class AccountRiskMetrics:
    """Computed account-level risk metrics."""
    margin_ratio: Optional[float] = None
    account_leverage: Optional[float] = None
    liquidation_distance: Optional[float] = None
    unrealized_loss_pct: Optional[float] = None
    free_balance: Optional[float] = None
    calculation_method: Optional[str] = None


@dataclass
class TradeRequest:
    """Represents a proposed trade for validation."""
    symbol: str
    side: str  # 'Buy' or 'Sell'
    quantity: float
    strategy_name: str
    portfolio_name: str
    trade_purpose: str = "hedge"  # 'hedge', 'scalp', 'rebalance', etc.
    mark_price: Optional[float] = None
    position_greeks: Optional[Greeks] = None
    account_snapshot: Optional[AccountSnapshot] = None
    nav_usd: Optional[float] = None
    var_95_pct: Optional[float] = None


@dataclass
class PortfolioRiskMetrics:
    """Computed portfolio risk metrics."""
    futures_exposure: float = 0.0
    options_notional: float = 0.0
    futures_options_ratio: float = 0.0
    has_options_notional: bool = False
    hedging_efficiency: float = 1.0
    max_concentration: float = 0.0
    portfolio_value: float = 0.0


@dataclass 
class PortfolioRiskLimits:
    """Portfolio-level risk limits configuration."""
    # Asset-weighted delta limits (new approach)
    max_portfolio_delta_usd: float = 120_000.0
    max_asset_delta_usd: Dict[str, float] = field(default_factory=lambda: {
        'BTC': 200_000.0,  # $200k max BTC delta exposure
        'ETH': 100_000.0,  # $100k max ETH delta exposure
        'SOL': 50_000.0,   # $50k max SOL delta exposure
        'DEFAULT': 25_000.0  # Default limit for other assets
    })
    
    # Use asset-weighted USD-based delta limits
    use_asset_weighted_delta: bool = True  # Enable asset-weighted approach
    
    # Other Greek limits
    max_portfolio_gamma: float = 1
    max_daily_theta: float = 500.0        # Max daily theta decay (positive = loss)
    max_portfolio_vega: float = 1000.0    # Max vega exposure
    
    # Position ratio limits
    max_futures_options_ratio: float = 3.0
    min_hedging_efficiency: float = 0.7     # Min hedge coverage (futures/options delta)
    
    # Strategy-specific limits
    max_gamma_scalp_frequency: float = 10.0  # Max trades per hour for gamma scalp
    max_delta_hedge_size: float = 5.0       # Max single hedge size
    
    # Portfolio health checks
    max_concentrated_position: float = 0.20
    min_portfolio_value: float = 1000.0

    # Quant-approved hard runtime limits
    max_gross_leverage: float = 2.5
    max_net_directional_leverage: float = 1.2
    max_trade_risk_bps: float = 35.0
    max_var_95_pct: float = 0.015


@dataclass
class PortfolioValidationResult:
    """Result of portfolio-level trade validation."""
    result: PortfolioRiskResult
    current_portfolio: Optional[Portfolio]
    projected_portfolio: Optional[Portfolio]
    projected_greeks: Optional[Greeks]
    risk_metrics: Optional[PortfolioRiskMetrics]
    reason: str
    warnings: List[str]
    account_risk: Optional[AccountRiskMetrics] = None


class PortfolioRiskValidator:
    """Portfolio-aware risk validator that understands options+futures relationships."""

    def __init__(self, limits: Optional[PortfolioRiskLimits] = None,
                 account_limits: Optional[AccountRiskLimits] = None):
        self.limits = limits or PortfolioRiskLimits()
        self.account_limits = account_limits or AccountRiskLimits()

        # Strategy-specific validation history for frequency limits
        self.strategy_history: Dict[str, List[float]] = {}  # strategy -> [timestamps]

    def validate_trade(self, current_portfolio: Portfolio, trade_request: TradeRequest) -> PortfolioValidationResult:
        """
        Validate trade against portfolio-level risk limits.

        Args:
            current_portfolio: The portfolio to validate against.
            trade_request: Proposed trade to validate

        Returns:
            PortfolioValidationResult with validation decision and metrics
        """
        logger.info(f"🛡️ PORTFOLIO RISK VALIDATION: {trade_request.side} {trade_request.quantity} {trade_request.symbol}")
        logger.info(f"  Strategy: {trade_request.strategy_name}")
        logger.info(f"  Purpose: {trade_request.trade_purpose}")

        # Calculate current portfolio Greeks and metrics
        current_greeks = current_portfolio.greeks
        current_metrics = self._calculate_risk_metrics(current_portfolio, current_greeks)

        # Simulate trade impact
        projected_portfolio = self._simulate_trade(current_portfolio, trade_request)
        projected_greeks = projected_portfolio.greeks
        projected_metrics = self._calculate_risk_metrics(projected_portfolio, projected_greeks)

        # Log current vs projected state
        logger.info(f"  📊 CURRENT STATE:")
        logger.info(f"    Delta: {current_greeks.delta:.4f} → {projected_greeks.delta:.4f}")
        logger.info(f"    Gamma: {current_greeks.gamma:.6f} → {projected_greeks.gamma:.6f}")
        logger.info(f"    Theta: {current_greeks.theta:.2f} → {projected_greeks.theta:.2f}")
        logger.info(f"    Futures/Options Ratio: {current_metrics.futures_options_ratio:.2f} → {projected_metrics.futures_options_ratio:.2f}")

        warnings = []

        # Validation checks
        validation_result = self._validate_portfolio_limits(
            projected_greeks, projected_metrics, current_metrics, trade_request, warnings
        )

        if validation_result != PortfolioRiskResult.APPROVED:
            logger.warning(f"  🚫 PORTFOLIO VALIDATION FAILED: {validation_result.value}")
            return PortfolioValidationResult(
                result=validation_result,
                current_portfolio=current_portfolio,
                projected_portfolio=projected_portfolio,
                projected_greeks=projected_greeks,
                risk_metrics=projected_metrics,
                reason=self._get_failure_reason(validation_result, projected_greeks, projected_metrics),
                warnings=warnings,
                account_risk=None
            )

        account_risk_metrics = None
        account_result = PortfolioRiskResult.APPROVED
        if trade_request.account_snapshot is None and self.account_limits.require_account_data:
            account_result = PortfolioRiskResult.BLOCKED_ACCOUNT_DATA
        elif trade_request.account_snapshot is not None:
            account_result, account_risk_metrics = self._validate_account_limits(
                trade_request.account_snapshot, warnings
            )

        if account_result != PortfolioRiskResult.APPROVED:
            logger.warning(f"  🚫 ACCOUNT VALIDATION FAILED: {account_result.value}")
            return PortfolioValidationResult(
                result=account_result,
                current_portfolio=current_portfolio,
                projected_portfolio=projected_portfolio,
                projected_greeks=projected_greeks,
                risk_metrics=projected_metrics,
                reason=self._get_failure_reason(account_result, projected_greeks, projected_metrics, account_risk_metrics),
                warnings=warnings,
                account_risk=account_risk_metrics
            )

        # Validation passed
        logger.info(f"  ✅ PORTFOLIO VALIDATION PASSED")
        if warnings:
            for warning in warnings:
                logger.warning(f"  ⚠️ {warning}")

        return PortfolioValidationResult(
            result=PortfolioRiskResult.APPROVED,
            current_portfolio=current_portfolio,
            projected_portfolio=projected_portfolio,
            projected_greeks=projected_greeks,
            risk_metrics=projected_metrics,
            reason="Trade approved by portfolio risk validator",
            warnings=warnings,
            account_risk=account_risk_metrics
        )

    
    def _simulate_trade(self, portfolio: Portfolio, trade_request: TradeRequest) -> Portfolio:
        """Simulate the impact of a trade on the portfolio."""
        # Deep copy portfolio to avoid modifying original
        projected_portfolio = copy.deepcopy(portfolio)
        
        symbol = trade_request.symbol
        trade_qty = trade_request.quantity if trade_request.side == 'Buy' else -trade_request.quantity
        
        # Update or add position
        if symbol in projected_portfolio.positions:
            # Update existing position
            existing_pos = projected_portfolio.positions[symbol]
            new_qty = existing_pos.quantity + trade_qty
            
            if abs(new_qty) < 0.0001:  # Position essentially closed
                del projected_portfolio.positions[symbol]
            else:
                existing_pos.quantity = new_qty
        else:
            # Create new position (simplified - would need market data for realistic Greeks)
            # For futures, assume delta = 1, no other Greeks
            if 'USDT' in symbol:  # Futures position
                greeks = Greeks(delta=1.0, gamma=0.0, theta=0.0, vega=0.0)
            else:  # Options position - use placeholder Greeks
                if trade_request.position_greeks is None:
                    raise ValueError("Option position simulation requires real Greeks data.")
                greeks = trade_request.position_greeks

            price = trade_request.mark_price

            projected_portfolio.positions[symbol] = Position(
                symbol=symbol,
                quantity=trade_qty,
                entry_price=price,
                current_price=price,
                greeks=greeks
            )
        
        return projected_portfolio
    
    # def _calculate_portfolio_greeks(self, portfolio: Portfolio) -> Greeks:
    #     """Calculate aggregated portfolio Greeks."""
    #     total_delta = 0.0
    #     total_gamma = 0.0
    #     total_theta = 0.0
    #     total_vega = 0.0
    #
    #     for position in portfolio.positions.values():
    #         if position.greeks and position.quantity != 0:
    #             total_delta += position.greeks.delta * position.quantity
    #             total_gamma += position.greeks.gamma * position.quantity
    #             total_theta += position.greeks.theta * position.quantity
    #             total_vega += position.greeks.vega * position.quantity
    #
    #     return Greeks(
    #         delta=total_delta,
    #         gamma=total_gamma,
    #         theta=total_theta,
    #         vega=total_vega
    #     )
    
    def _calculate_risk_metrics(self, portfolio: Portfolio, greeks: Greeks) -> PortfolioRiskMetrics:
        """Calculate portfolio risk metrics."""
        metrics = PortfolioRiskMetrics()
        
        # Separate futures and options exposure
        futures_exposure = 0.0
        options_notional = 0.0
        options_delta = 0.0
        futures_delta = 0.0
        
        for position in portfolio.positions.values():
            if position.quantity == 0:
                continue

            price = position.current_price if position.current_price is not None else position.entry_price

            if 'USDT' in position.symbol:  # Futures
                if price is not None and price > 0:
                    futures_exposure += abs(position.quantity * price)
                    futures_delta += abs(position.quantity)
            else:  # Options
                if price is not None and price > 0:
                    options_notional += abs(position.quantity * price)
                if position.greeks:
                    options_delta += position.greeks.delta * position.quantity
        
        # Calculate ratios
        metrics.futures_exposure = futures_exposure
        metrics.options_notional = options_notional
        if options_notional > 0:
            metrics.futures_options_ratio = futures_exposure / options_notional
            metrics.has_options_notional = True
        else:
            metrics.futures_options_ratio = 0.0
            metrics.has_options_notional = False
        
        # Hedging efficiency (how well futures hedge options delta)
        if abs(options_delta) > 0:
            hedge_coverage = abs(futures_delta) / abs(options_delta)
            metrics.hedging_efficiency = min(hedge_coverage, 2.0)  # Cap at 200%
        else:
            metrics.hedging_efficiency = 1.0  # No options delta to hedge
        
        # Portfolio concentration
        total_notional = futures_exposure + options_notional
        if total_notional > 0:
            position_values = []
            for pos in portfolio.positions.values():
                price = pos.current_price if pos.current_price is not None else pos.entry_price
                if price is not None and price > 0:
                    position_values.append(abs(pos.quantity * price))
            max_position_value = max(position_values, default=0.0)
            metrics.max_concentration = max_position_value / total_notional
        else:
            metrics.max_concentration = 0.0
        
        metrics.portfolio_value = total_notional
        
        return metrics
    
    @staticmethod
    def _resolve_nav_usd(projected_metrics: PortfolioRiskMetrics, trade_request: TradeRequest) -> float:
        if trade_request.nav_usd is not None and trade_request.nav_usd > 0:
            return trade_request.nav_usd
        if projected_metrics.portfolio_value > 0:
            return projected_metrics.portfolio_value
        return 1.0

    def _validate_portfolio_limits(self, projected_greeks: Greeks, projected_metrics: PortfolioRiskMetrics,
                                 current_metrics: PortfolioRiskMetrics, trade_request: TradeRequest,
                                 warnings: List[str]) -> PortfolioRiskResult:
        """Validate projected portfolio against all risk limits."""

        # Check if this trade would reduce overall position risk
        is_position_reducing = self._is_position_reducing_trade(trade_request)
        if is_position_reducing:
            logger.info(f"  ✅ POSITION REDUCING: Trade reduces overall position risk, allowing with relaxed limits")
            # Allow position-reducing trades to bypass some risk limits
            return PortfolioRiskResult.APPROVED

        nav_usd = self._resolve_nav_usd(projected_metrics, trade_request)

        # Gross and directional leverage hard checks
        gross_leverage = projected_metrics.portfolio_value / nav_usd if nav_usd > 0 else float("inf")
        if gross_leverage > self.limits.max_gross_leverage:
            return PortfolioRiskResult.BLOCKED_GROSS_LEVERAGE

        # Greek and directional checks
        delta_usd = abs(projected_greeks.delta * self._estimate_asset_price(trade_request.symbol))
        if delta_usd > self.limits.max_portfolio_delta_usd:
            return PortfolioRiskResult.BLOCKED_DELTA_LIMIT
        directional_leverage = delta_usd / nav_usd if nav_usd > 0 else float("inf")
        if directional_leverage > self.limits.max_net_directional_leverage:
            return PortfolioRiskResult.BLOCKED_NET_DIRECTIONAL_LIMIT

        if abs(projected_greeks.gamma) > self.limits.max_portfolio_gamma:
            return PortfolioRiskResult.BLOCKED_GAMMA_LIMIT

        if projected_greeks.theta < -self.limits.max_daily_theta:
            return PortfolioRiskResult.BLOCKED_THETA_LIMIT

        # Per-trade risk bps cap
        mark_price = trade_request.mark_price or self._estimate_asset_price(trade_request.symbol)
        trade_notional = abs(trade_request.quantity * mark_price)
        trade_risk_bps = (trade_notional / nav_usd) * 10_000 if nav_usd > 0 else float("inf")
        if trade_risk_bps > self.limits.max_trade_risk_bps:
            return PortfolioRiskResult.BLOCKED_TRADE_RISK

        # Daily VaR(95) cap
        if trade_request.var_95_pct is not None and trade_request.var_95_pct > self.limits.max_var_95_pct:
            return PortfolioRiskResult.BLOCKED_VAR_LIMIT

        # Check position ratios
        if projected_metrics.has_options_notional:
            ratio = projected_metrics.futures_options_ratio
            if ratio > self.limits.max_futures_options_ratio:
                return PortfolioRiskResult.BLOCKED_POSITION_RATIO

        # Check hedging efficiency for gamma scalp strategies
        if 'gamma_scalp' in trade_request.strategy_name.lower():
            hedge_efficiency = projected_metrics.hedging_efficiency
            if hedge_efficiency < self.limits.min_hedging_efficiency:
                return PortfolioRiskResult.BLOCKED_HEDGING_EFFICIENCY

        # Hard concentration cap
        if projected_metrics.max_concentration > self.limits.max_concentrated_position:
            return PortfolioRiskResult.BLOCKED_CONCENTRATION_LIMIT

        # Check minimum portfolio value
        if projected_metrics.portfolio_value < self.limits.min_portfolio_value:
            warnings.append(f"Portfolio value below minimum: ${projected_metrics.portfolio_value:.0f}")

        # Strategy-specific limits
        strategy_result = self._validate_strategy_limits(trade_request)
        if strategy_result != PortfolioRiskResult.APPROVED:
            return strategy_result

        return PortfolioRiskResult.APPROVED

    def _validate_account_limits(self, account_snapshot: AccountSnapshot,
                                 warnings: List[str]) -> Tuple[PortfolioRiskResult, AccountRiskMetrics]:
        total_equity = account_snapshot.total_equity
        available_balance = account_snapshot.available_balance
        total_margin_balance = account_snapshot.total_margin_balance or total_equity
        used_margin_balance = (
            account_snapshot.total_initial_margin
            if account_snapshot.total_initial_margin is not None
            else account_snapshot.total_maintenance_margin
        )
        total_unrealized_pnl = account_snapshot.total_unrealized_pnl

        # Calculate risk-adjusted position value (only positions with leverage/margin risk)
        leveraged_position_value = 0.0
        total_notional_value = 0.0
        liquidation_distances = []
        
        for position in account_snapshot.positions:
            position_value = position.position_value
            if position_value is None and position.mark_price > 0:
                position_value = abs(position.size * position.mark_price)
            if position_value is not None:
                total_notional_value += position_value
                
                # Only count positions with leverage risk toward leverage calculation
                has_leverage_risk = False
                
                if position.category == 'linear':  # Perpetual futures - always leveraged
                    has_leverage_risk = True
                elif position.category == 'option':
                    # Short options have leverage risk, long options don't
                    if position.size < 0:  # Short option position
                        has_leverage_risk = True
                    # Long options (position.size > 0) don't contribute to leverage
                elif position.category == 'spot':
                    # Spot positions have no leverage (unless margin trading)
                    has_leverage_risk = False
                
                if has_leverage_risk:
                    leveraged_position_value += position_value

            # Check liquidation distances for all positions that can be liquidated
            if position.liquidation_price and position.liquidation_price > 0 and position.mark_price > 0:
                liquidation_distances.append(
                    abs(position.mark_price - position.liquidation_price) / position.mark_price
                )

        margin_ratio = None
        if available_balance is not None and used_margin_balance is not None and used_margin_balance > 0:
            margin_ratio = available_balance / (available_balance + used_margin_balance)
        elif available_balance is not None and total_margin_balance and total_margin_balance > 0:
            margin_ratio = available_balance / total_margin_balance

        # Calculate leverage using only leveraged positions, or fall back to margin-based calculation
        account_leverage = None
        leverage_calculation_method = "none"
        
        if used_margin_balance is not None and used_margin_balance > 0 and total_equity and total_equity > 0:
            # Preferred: Use actual margin used vs equity (more accurate)
            account_leverage = used_margin_balance / total_equity
            leverage_calculation_method = "margin_based"
            logger.debug(f"Leverage calculation: margin_based = {used_margin_balance:.2f} / {total_equity:.2f} = {account_leverage:.2f}")
        elif leveraged_position_value > 0 and total_equity and total_equity > 0:
            # Fallback: Use leveraged position value vs equity
            account_leverage = leveraged_position_value / total_equity
            leverage_calculation_method = "position_based"
            logger.debug(f"Leverage calculation: position_based = {leveraged_position_value:.2f} / {total_equity:.2f} = {account_leverage:.2f}")
        else:
            # If no leveraged positions and no margin used, leverage is effectively 0 (no risk)
            account_leverage = 0.0
            leverage_calculation_method = "no_leverage"
            logger.debug(f"Leverage calculation: no_leverage (long options only or no positions)")

        liquidation_distance = min(liquidation_distances) if liquidation_distances else None

        unrealized_loss_pct = None
        if total_unrealized_pnl is not None and total_equity and total_equity > 0:
            if total_unrealized_pnl < 0:
                unrealized_loss_pct = abs(total_unrealized_pnl) / total_equity
        gross_leverage = (
            total_notional_value / total_equity
            if total_equity is not None and total_equity > 0
            else None
        )
        concentration = (
            (max(abs(pos.position_value or 0.0) for pos in account_snapshot.positions) / total_notional_value)
            if total_notional_value > 0 and account_snapshot.positions
            else None
        )

        account_metrics = AccountRiskMetrics(
            margin_ratio=margin_ratio,
            account_leverage=account_leverage,
            liquidation_distance=liquidation_distance,
            unrealized_loss_pct=unrealized_loss_pct,
            free_balance=available_balance,
            calculation_method=leverage_calculation_method
        )

        if margin_ratio is not None and margin_ratio < self.account_limits.min_margin_ratio:
            return PortfolioRiskResult.BLOCKED_MARGIN_RATIO, account_metrics

        if account_leverage is not None and account_leverage > self.account_limits.max_account_leverage:
            return PortfolioRiskResult.BLOCKED_ACCOUNT_LEVERAGE, account_metrics
        if gross_leverage is not None and gross_leverage > self.limits.max_gross_leverage:
            return PortfolioRiskResult.BLOCKED_GROSS_LEVERAGE, account_metrics

        if liquidation_distance is not None and liquidation_distance < self.account_limits.min_liquidation_distance:
            return PortfolioRiskResult.BLOCKED_LIQUIDATION_DISTANCE, account_metrics

        if unrealized_loss_pct is not None and unrealized_loss_pct > self.account_limits.max_unrealized_loss_pct:
            return PortfolioRiskResult.BLOCKED_UNREALIZED_LOSS, account_metrics
        if unrealized_loss_pct is not None and unrealized_loss_pct >= self.account_limits.soft_unrealized_loss_pct:
            warnings.append(
                f"Unrealized loss reached {unrealized_loss_pct:.2%} (soft stop {self.account_limits.soft_unrealized_loss_pct:.2%})"
            )
        if concentration is not None and concentration > self.limits.max_concentrated_position:
            return PortfolioRiskResult.BLOCKED_CONCENTRATION_LIMIT, account_metrics

        if available_balance is not None and available_balance < self.account_limits.min_free_balance:
            return PortfolioRiskResult.BLOCKED_FREE_BALANCE, account_metrics

        if margin_ratio is None:
            warnings.append("Account margin ratio unavailable from wallet snapshot.")
        if account_leverage is None:
            warnings.append("Account leverage unavailable from wallet snapshot.")
        if liquidation_distance is None:
            warnings.append("Liquidation distance unavailable from open positions.")

        return PortfolioRiskResult.APPROVED, account_metrics
    
    def _validate_strategy_limits(self, trade_request: TradeRequest) -> PortfolioRiskResult:
        """Validate strategy-specific limits like trading frequency."""
        import time
        
        current_time = time.time()
        strategy_key = f"{trade_request.strategy_name}_{trade_request.portfolio_name}"
        
        # Initialize history if needed
        if strategy_key not in self.strategy_history:
            self.strategy_history[strategy_key] = []
        
        # Clean old history (older than 1 hour)
        hour_ago = current_time - 3600
        self.strategy_history[strategy_key] = [
            t for t in self.strategy_history[strategy_key] if t > hour_ago
        ]
        
        # Check frequency limits
        if 'gamma_scalp' in trade_request.strategy_name.lower():
            recent_trades = len(self.strategy_history[strategy_key])
            if recent_trades >= self.limits.max_gamma_scalp_frequency:
                return PortfolioRiskResult.BLOCKED_STRATEGY_LIMIT
        
        # Check trade size limits
        if 'delta_hedge' in trade_request.strategy_name.lower():
            if abs(trade_request.quantity) > self.limits.max_delta_hedge_size:
                return PortfolioRiskResult.BLOCKED_STRATEGY_LIMIT
        
        # Only record ACTUAL executed trades, not just signals
        # We'll update this in a separate method when the trade is actually executed
        # self.strategy_history[strategy_key].append(current_time)
        
        return PortfolioRiskResult.APPROVED
    
    def _is_position_reducing_trade(self, trade_request: TradeRequest) -> bool:
        """Check if this trade reduces overall position risk (e.g., buying back short positions)."""
        # Position reducing trades should be allowed with relaxed limits:
        # - Buying back short options (closing short positions)
        # - Selling long options (reducing long exposure)
        # - Any trade that moves delta closer to zero
        
        # For now, implement basic logic - can be enhanced based on actual portfolio state
        # This is a simplified check - in practice would need current portfolio state
        return trade_request.trade_purpose in ['close', 'reduce', 'hedge_close']
    
    def _estimate_asset_price(self, symbol: str) -> float:
        """Estimate asset price for USD conversion. Rough estimates for validation."""
        # Extract base asset from symbol
        if symbol.startswith('BTC'):
            return 100000.0  # Rough BTC price estimate
        elif symbol.startswith('ETH'):
            return 4000.0    # Rough ETH price estimate  
        elif symbol.startswith('SOL'):
            return 200.0     # Rough SOL price estimate
        else:
            return 50000.0   # Default estimate
    
    def record_executed_trade(self, trade_request: TradeRequest):
        """Record an actually executed trade for frequency limit tracking."""
        import time
        
        current_time = time.time()
        strategy_key = f"{trade_request.strategy_name}_{trade_request.portfolio_name}"
        
        # Initialize history if needed
        if strategy_key not in self.strategy_history:
            self.strategy_history[strategy_key] = []
        
        # Clean old history (older than 1 hour)
        hour_ago = current_time - 3600
        self.strategy_history[strategy_key] = [
            t for t in self.strategy_history[strategy_key] if t > hour_ago
        ]
        
        # Record this actual execution
        self.strategy_history[strategy_key].append(current_time)
        logger.info(f"📝 RECORDED EXECUTED TRADE: {trade_request.strategy_name} - {len(self.strategy_history[strategy_key])} trades in last hour")

    def _get_failure_reason(self, result: PortfolioRiskResult, greeks: Greeks,
                            metrics: Optional[PortfolioRiskMetrics],
                            account_metrics: Optional[AccountRiskMetrics] = None) -> str:
        """Generate human-readable failure reason."""
        def _format_optional(value: Optional[float], fmt: str) -> str:
            if value is None:
                return "n/a"
            return format(value, fmt)

        if result == PortfolioRiskResult.BLOCKED_DELTA_LIMIT:
            delta_usd = abs(greeks.delta * 50000)  # Rough estimate for error message
            return f"Portfolio delta ${delta_usd:.0f} would exceed USD limit ${self.limits.max_portfolio_delta_usd:.0f}"
        elif result == PortfolioRiskResult.BLOCKED_GAMMA_LIMIT:
            return f"Portfolio gamma {abs(greeks.gamma):.6f} would exceed limit {self.limits.max_portfolio_gamma:.6f}"
        elif result == PortfolioRiskResult.BLOCKED_THETA_LIMIT:
            return f"Portfolio theta {greeks.theta:.2f} would exceed daily limit {-self.limits.max_daily_theta:.2f}"
        elif result == PortfolioRiskResult.BLOCKED_POSITION_RATIO:
            ratio = metrics.futures_options_ratio if metrics else 0.0
            return f"Futures/options ratio {ratio:.2f} would exceed limit {self.limits.max_futures_options_ratio:.2f}"
        elif result == PortfolioRiskResult.BLOCKED_HEDGING_EFFICIENCY:
            efficiency = metrics.hedging_efficiency if metrics else 0.0
            return f"Hedge efficiency {efficiency:.2f} would be below minimum {self.limits.min_hedging_efficiency:.2f}"
        elif result == PortfolioRiskResult.BLOCKED_STRATEGY_LIMIT:
            return "Strategy-specific limit exceeded (frequency or trade size)"
        elif result == PortfolioRiskResult.BLOCKED_MARGIN_RATIO:
            ratio = account_metrics.margin_ratio if account_metrics else None
            return f"Margin ratio {_format_optional(ratio, '.2f')} would fall below minimum {self.account_limits.min_margin_ratio:.2f}"
        elif result == PortfolioRiskResult.BLOCKED_ACCOUNT_LEVERAGE:
            leverage = account_metrics.account_leverage if account_metrics else None
            method = getattr(account_metrics, 'calculation_method', 'unknown')
            return f"Account leverage {_format_optional(leverage, '.2f')} would exceed limit {self.account_limits.max_account_leverage:.2f} (method: {method})"
        elif result == PortfolioRiskResult.BLOCKED_GROSS_LEVERAGE:
            return f"Gross exposure leverage would exceed limit {self.limits.max_gross_leverage:.2f}x"
        elif result == PortfolioRiskResult.BLOCKED_NET_DIRECTIONAL_LIMIT:
            return f"Net directional leverage would exceed limit {self.limits.max_net_directional_leverage:.2f}x NAV"
        elif result == PortfolioRiskResult.BLOCKED_CONCENTRATION_LIMIT:
            return f"Concentration would exceed limit {self.limits.max_concentrated_position:.1%}"
        elif result == PortfolioRiskResult.BLOCKED_VAR_LIMIT:
            return f"Daily VaR(95) would exceed limit {self.limits.max_var_95_pct:.2%}"
        elif result == PortfolioRiskResult.BLOCKED_TRADE_RISK:
            return f"Per-trade risk would exceed limit {self.limits.max_trade_risk_bps:.1f} bps NAV"
        elif result == PortfolioRiskResult.BLOCKED_LIQUIDATION_DISTANCE:
            distance = account_metrics.liquidation_distance if account_metrics else None
            return f"Liquidation distance {_format_optional(distance, '.2%')} would be below minimum {self.account_limits.min_liquidation_distance:.2%}"
        elif result == PortfolioRiskResult.BLOCKED_UNREALIZED_LOSS:
            loss_pct = account_metrics.unrealized_loss_pct if account_metrics else None
            return f"Unrealized loss {_format_optional(loss_pct, '.2%')} would exceed limit {self.account_limits.max_unrealized_loss_pct:.2%}"
        elif result == PortfolioRiskResult.BLOCKED_FREE_BALANCE:
            free_balance = account_metrics.free_balance if account_metrics else None
            return f"Free balance {_format_optional(free_balance, '.2f')} would be below minimum {self.account_limits.min_free_balance:.2f}"
        elif result == PortfolioRiskResult.BLOCKED_ACCOUNT_DATA:
            return "Account snapshot unavailable for margin/liquidation checks"
        else:
            return f"Portfolio validation failed: {result.value}"
    
    def get_portfolio_status(self, portfolio: Portfolio) -> Dict[str, Any]:
        """Get current portfolio risk status for monitoring."""
        try:
            greeks = portfolio.greeks
            metrics = self._calculate_risk_metrics(portfolio, greeks)

            return {
                'portfolio_name': portfolio.name,
                'current_greeks': {
                    'delta': greeks.delta,
                    'gamma': greeks.gamma,
                    'theta': greeks.theta,
                    'vega': greeks.vega
                },
                'risk_utilization': {
                    'delta_usage': (
                        abs(greeks.delta * 50000) / self.limits.max_portfolio_delta_usd 
                        if self.limits.max_portfolio_delta_usd > 0 else 0
                    ),
                    'gamma_usage': abs(greeks.gamma) / self.limits.max_portfolio_gamma if self.limits.max_portfolio_gamma > 0 else 0,
                    'theta_usage': abs(greeks.theta) / self.limits.max_daily_theta if self.limits.max_daily_theta > 0 else 0,
                },
                'risk_metrics': asdict(metrics),
                'limits_active': True
            }
        except Exception as e:
            logger.error(f"Error getting portfolio status for {portfolio.name}: {e}")
            return {'error': str(e)}
