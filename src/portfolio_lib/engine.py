"""
Portfolio Engine - Core portfolio management engine

Contains PortfolioEngine class for portfolio CRUD operations, scenario analysis,
and portfolio management. Exchange-agnostic business logic only.
"""

import json
import logging
import os
import pandas as pd
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dataclasses import asdict

logger = logging.getLogger(__name__)

from .types import Portfolio, Position, Scenario, ScenarioResults, Greeks
from .transformer import StrategyTransformer
from .utils import validate_portfolio_data
from .risk_validator import (
    PortfolioRiskValidator,
    PortfolioRiskLimits,
    TradeRequest,
    PortfolioValidationResult,
    PortfolioRiskResult,
    AccountSnapshot,
    AccountPositionRisk
)
# API client is duck-typed (passed at construction)


class PortfolioEngine:
    """Core portfolio management engine - exchange agnostic"""
    
    def __init__(self, portfolio_dir: str = "portfolio_data", client = None, risk_limits: PortfolioRiskLimits = None):
        # Use absolute path to ensure we can write to the directory
        if not os.path.isabs(portfolio_dir):
            self.portfolio_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), portfolio_dir)
        else:
            self.portfolio_dir = portfolio_dir
        
        self.portfolios: List[Portfolio] = []
        self.client = client
        
        # Ensure directory exists and is writable
        try:
            os.makedirs(self.portfolio_dir, exist_ok=True)
        except OSError as e:
            # If we can't create the directory, use a temporary one in user's home
            import tempfile
            self.portfolio_dir = os.path.join(tempfile.gettempdir(), "bybit_portfolio_data")
            os.makedirs(self.portfolio_dir, exist_ok=True)
            logger.warning("Using temporary directory for portfolio data: %s", self.portfolio_dir)
        
        # Initialize portfolio-aware risk validator
        self.risk_validator = PortfolioRiskValidator(risk_limits)
        
    def load_all_portfolios(self) -> List[Portfolio]:
        """Load all portfolios from directory into memory
        
        Returns:
            List of loaded portfolios
        """
        self.portfolios = []
        
        for filename in os.listdir(self.portfolio_dir):
            if filename.endswith('.json'):
                portfolio_name = filename.replace('.json', '')
                try:
                    portfolio = self.load_portfolio(portfolio_name)
                    self.portfolios.append(portfolio)
                except Exception as e:
                    logger.warning("Failed to load portfolio %s: %s", portfolio_name, e)
        
        return self.portfolios
    
    def load_portfolio(self, name: str) -> Portfolio:
        """Load single portfolio from file
        
        Args:
            name: Portfolio name
            
        Returns:
            Loaded portfolio
            
        Raises:
            FileNotFoundError: If portfolio file doesn't exist
        """
        filepath = os.path.join(self.portfolio_dir, f"{name}.json")
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Portfolio '{name}' not found")
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Validate data structure
        if not validate_portfolio_data(data):
            raise ValueError(f"Invalid portfolio data format in {name}")
        
        # New format
        portfolio = Portfolio(**data)
        
        return portfolio
    
    def save_portfolio(self, portfolio: Portfolio) -> None:
        """Save portfolio to file
        
        Args:
            portfolio: Portfolio to save
        """
        filepath = os.path.join(self.portfolio_dir, f"{portfolio.name}.json")
        
        # Convert to serializable format
        data = {
            'name': portfolio.name,
            'positions': {
                symbol: asdict(pos) for symbol, pos in portfolio.positions.items()
            },
            'metadata': portfolio.metadata,
            'created_at': portfolio.created_at.isoformat() if portfolio.created_at else None,
            'last_synced': portfolio.last_synced.isoformat() if portfolio.last_synced else None
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def create_portfolio(self, name: str, positions: Dict[str, Position]) -> Portfolio:
        """Create new portfolio with validation
        
        Args:
            name: Portfolio name
            positions: Dictionary of positions
            
        Returns:
            Created portfolio
            
        Raises:
            ValueError: If portfolio already exists
        """
        if any(p for p in self.portfolios if p.name == name):
            raise ValueError(f"Portfolio '{name}' already exists")
        
        portfolio = Portfolio(
            name=name,
            positions=positions,
            created_at=datetime.now(timezone.utc)
        )
        
        self.portfolios.append(portfolio)
        self.save_portfolio(portfolio)
        return portfolio
    
    def update_portfolio(self, portfolio_name: str, updates: Dict[str, Any]) -> Portfolio:
        """Update existing portfolio
        
        Args:
            portfolio_name: Name of portfolio to update
            updates: Dictionary of updates to apply
            
        Returns:
            Updated portfolio
        """
        portfolio = self.get_portfolio(portfolio_name)
        
        if 'positions' in updates:
            for symbol, position_data in updates['positions'].items():
                if isinstance(position_data, dict):
                    if position_data.get('quantity', 0) == 0:
                        # Remove position
                        portfolio.positions.pop(symbol, None)
                    else:
                        # Update or add position
                        portfolio.positions[symbol] = Position(**position_data)
                elif isinstance(position_data, Position):
                    portfolio.positions[symbol] = position_data
        
        if 'metadata' in updates:
            portfolio.metadata.update(updates['metadata'])
        
        portfolio.last_synced = datetime.now(timezone.utc)
        self.save_portfolio(portfolio)
        return portfolio
    
    def delete_portfolio(self, portfolio_name: str) -> bool:
        """Remove portfolio from system
        
        Args:
            portfolio_name: Name of portfolio to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Remove from memory
            self.portfolios = [p for p in self.portfolios if p.name != portfolio_name]
            
            # Remove file
            filepath = os.path.join(self.portfolio_dir, f"{portfolio_name}.json")
            if os.path.exists(filepath):
                os.remove(filepath)
            
            return True
        except Exception as e:
            logger.error("Error deleting portfolio %s: %s", portfolio_name, e)
            return False
    
    def get_portfolio(self, name: str) -> Portfolio:
        """Get portfolio by name
        
        Args:
            name: Portfolio name
            
        Returns:
            Portfolio object
            
        Raises:
            FileNotFoundError: If portfolio not found
        """
        for portfolio in self.portfolios:
            if portfolio.name == name:
                return portfolio
        
        # Try loading from file if not in memory
        return self.load_portfolio(name)
    
    def clone_portfolio(self, source_name: str, target_name: str) -> Portfolio:
        """Create copy for what-if analysis
        
        Args:
            source_name: Name of source portfolio
            target_name: Name for cloned portfolio
            
        Returns:
            Cloned portfolio
        """
        source_portfolio = self.get_portfolio(source_name)
        
        # Deep copy positions
        new_positions = {}
        for symbol, pos in source_portfolio.positions.items():
            new_positions[symbol] = Position(
                symbol=pos.symbol,
                quantity=pos.quantity,
                entry_price=pos.entry_price,
                entry_iv=pos.entry_iv,
                current_price=pos.current_price,
                greeks=pos.greeks  # Greeks are immutable, safe to reference
            )
        
        cloned_portfolio = Portfolio(
            name=target_name,
            positions=new_positions,
            metadata={**source_portfolio.metadata, "cloned_from": source_name},
            created_at=datetime.now(timezone.utc)
        )
        
        # Add to portfolios list and save
        self.portfolios.append(cloned_portfolio)
        self.save_portfolio(cloned_portfolio)
        
        return cloned_portfolio
    
    def transform_strategy(self, portfolio: Portfolio, transformation: str, **kwargs) -> Portfolio:
        """Apply strategy transformations
        
        Args:
            portfolio: Source portfolio
            transformation: Type of transformation
            **kwargs: Transformation parameters
            
        Returns:
            Transformed portfolio
            
        Raises:
            ValueError: If unknown transformation or missing parameters
        """
        transformer = StrategyTransformer()
        
        if transformation == "risk_reversal_to_seagull":
            short_call_strike = kwargs.get("short_call_strike")
            if not short_call_strike:
                raise ValueError("short_call_strike required for seagull transformation")
            return transformer.risk_reversal_to_seagull(portfolio, short_call_strike)
        
        elif transformation == "straddle_to_strangle":
            strike_width = kwargs.get("strike_width", 1000)  # Default 1000 strike width
            return transformer.straddle_to_strangle(portfolio, strike_width)
        
        else:
            raise ValueError(f"Unknown transformation: {transformation}")
    
    def analyze_scenario(self, portfolio: Portfolio, scenarios: List[Scenario]) -> ScenarioResults:
        """Run what-if analysis on portfolio
        
        Args:
            portfolio: Portfolio to analyze
            scenarios: List of market scenarios
            
        Returns:
            Scenario analysis results
        """
        pnl_data = []
        greek_data = []
        
        for scenario in scenarios:
            scenario_pnl = 0.0
            scenario_greeks = {'delta': 0.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}
            
            for position in portfolio.positions.values():
                if not position.greeks or not position.current_price:
                    continue
                
                # Calculate position PnL using Greeks approximation
                spot_pnl = position.greeks.delta * position.quantity * scenario.spot_change_pct / 100
                iv_pnl = position.greeks.vega * position.quantity * scenario.iv_change_pct / 100
                time_pnl = position.greeks.theta * position.quantity * scenario.days_forward
                
                position_pnl = spot_pnl + iv_pnl + time_pnl
                scenario_pnl += position_pnl
                
                # Track Greek contributions
                scenario_greeks['delta'] += position.greeks.delta * position.quantity
                scenario_greeks['gamma'] += position.greeks.gamma * position.quantity
                scenario_greeks['theta'] += position.greeks.theta * position.quantity
                scenario_greeks['vega'] += position.greeks.vega * position.quantity
            
            pnl_data.append({
                'scenario': scenario.name,
                'pnl': scenario_pnl,
                'spot_change': scenario.spot_change_pct,
                'iv_change': scenario.iv_change_pct,
                'days_forward': scenario.days_forward
            })
            
            greek_data.append({
                'scenario': scenario.name,
                **scenario_greeks
            })
        
        pnl_df = pd.DataFrame(pnl_data)
        greek_df = pd.DataFrame(greek_data)
        
        summary_stats = {
            'max_profit': pnl_df['pnl'].max() if not pnl_df.empty else 0.0,
            'max_loss': pnl_df['pnl'].min() if not pnl_df.empty else 0.0,
            'profit_scenarios': (pnl_df['pnl'] > 0).sum() if not pnl_df.empty else 0,
            'total_scenarios': len(scenarios),
            'avg_pnl': pnl_df['pnl'].mean() if not pnl_df.empty else 0.0
        }
        
        return ScenarioResults(
            scenarios=scenarios,
            pnl_matrix=pnl_df,
            greek_sensitivity=greek_df,
            summary_stats=summary_stats
        )
    
    async def create_full_portfolio_from_asset(self, asset: str) -> Portfolio:
        """Create and save a full portfolio from all live positions for an asset
        
        Args:
            asset: Base asset (e.g., 'BTC', 'ETH')
            
        Returns:
            Created portfolio with live positions
        """
        portfolio_name = f"{asset}_full"
        
        # Create a minimal portfolio first
        portfolio = Portfolio(
            name=portfolio_name,
            positions={},
            metadata={'asset': asset, 'source': 'live_positions', 'category': 'full_portfolio', 'base_coin': asset},
            created_at=datetime.now(timezone.utc),
            last_synced=datetime.now(timezone.utc)
        )
        
        # Save to portfolio system first (sync_with_exchange expects it to exist)
        if any(p for p in self.portfolios if p.name == portfolio_name):
            # Update existing
            self.portfolios = [p if p.name != portfolio_name else portfolio for p in self.portfolios]
        else:
            # Add new
            self.portfolios.append(portfolio)
        
        self.save_portfolio(portfolio)
        
        # Now use sync_with_exchange to get all positions with proper Greeks enrichment
        enriched_portfolio = await self.sync_with_exchange(portfolio_name, only_existing=False)
        
        return enriched_portfolio
    
    async def validate_trade(self, trade_request: TradeRequest) -> "PortfolioValidationResult":
        """
        Validate a proposed trade against portfolio risk limits.
        
        Args:
            trade_request: TradeRequest with trade details
            
        Returns:
            PortfolioValidationResult with validation decision
        """
        try:
            current_portfolio = await self.sync_with_exchange(
                trade_request.portfolio_name, only_existing=False
            )
        except Exception as e:
            logger.error("Failed to sync portfolio: %s", e)
            return PortfolioValidationResult(
                result=PortfolioRiskResult.BLOCKED_PORTFOLIO_ERROR,
                current_portfolio=None,
                projected_portfolio=None,
                projected_greeks=None,
                risk_metrics=None,
                reason=f"Portfolio sync failed: {e}",
                warnings=[]
            )

        account_snapshot = await self._fetch_account_snapshot()
        trade_request.account_snapshot = account_snapshot
        return self.risk_validator.validate_trade(current_portfolio, trade_request)
    
    def update_risk_limits(self, new_limits: PortfolioRiskLimits):
        """Update portfolio risk limits."""
        self.risk_validator.limits = new_limits
    
    def get_portfolio_risk_status(self, portfolio_name: str) -> Dict[str, Any]:
        """Get current portfolio risk status for monitoring."""
        portfolio = self.get_portfolio(portfolio_name)
        return self.risk_validator.get_portfolio_status(portfolio)
    
    def list_portfolio_names(self) -> List[str]:
        """Get list of all portfolio names
        
        Returns:
            List of portfolio names
        """
        return [p.name for p in self.portfolios]

    async def sync_with_exchange(self, name: str, only_existing: bool = False) -> Portfolio:
        """
        Syncs the portfolio with the exchange, fetching all actual positions
        and updating metrics.
        
        Args:
            name: The name of the portfolio to sync.
            only_existing: If True, only syncs positions that already exist in the portfolio file.
                           If False, overwrites the portfolio with all positions from the exchange.
        """
        portfolio = self.get_portfolio(name)
        client = self.client

        # 1. Infer base coin
        first_symbol = next(iter(portfolio.positions.keys()), None)
        base_coin = portfolio.metadata.get('base_coin')
        if not base_coin:
            if not first_symbol:
                raise ValueError("Cannot determine base coin for an empty portfolio without 'base_coin' in metadata.")
            base_coin = first_symbol.split('-')[0]
            portfolio.metadata['base_coin'] = base_coin

        logger.info("Syncing portfolio '%s' for base coin '%s'", name, base_coin)

        # 2. Fetch all positions from Bybit
        all_exchange_positions = {}
        
        # --- Fetch Option Positions ---
        try:
            option_positions_raw = await client.get_positions(category='option', base_coin=base_coin)
            
            if option_positions_raw:
                option_tickers_raw = await client.get_tickers(category='option', base_coin=base_coin)
                tickers_map = {ticker['symbol']: ticker for ticker in option_tickers_raw.get('list', [])}

                for pos_data in option_positions_raw:
                    symbol = pos_data.symbol
                    quantity = float(pos_data.size)
                    if pos_data.side.lower() == 'sell':
                        quantity *= -1

                    # Initialize defaults
                    greeks = None
                    current_price = 0.0
                    
                    if symbol in tickers_map:
                        ticker = tickers_map[symbol]
                        greeks = Greeks(
                            delta=float(ticker.get('delta', 0)),
                            gamma=float(ticker.get('gamma', 0)),
                            theta=float(ticker.get('theta', 0)),
                            vega=float(ticker.get('vega', 0))
                        )
                        current_price = float(ticker.get('markPrice', 0))

                    all_exchange_positions[symbol] = Position(
                        symbol=symbol,
                        quantity=quantity,
                        entry_price=float(pos_data.avg_price) if pos_data.avg_price else 0,
                        current_price=current_price,
                        greeks=greeks
                    )
        except Exception as e:
            logger.warning("Failed to fetch option positions for %s: %s", base_coin, e)

        # --- Fetch Futures Positions ---
        perp_symbol = f"{base_coin}USDT"
        try:
            future_positions_raw = await client.get_positions(category='linear', symbol=perp_symbol)

            if future_positions_raw:
                for pos_data in future_positions_raw:
                    symbol = pos_data.symbol
                    quantity = float(pos_data.size)
                    if pos_data.side.lower() == 'sell':
                        quantity *= -1
                    greeks = Greeks(delta=1.0, gamma=0.0, theta=0.0, vega=0.0)
                    all_exchange_positions[symbol] = Position(
                        symbol=symbol,
                        quantity=quantity,
                        entry_price=float(pos_data.avg_price) if pos_data.avg_price else 0,
                        current_price=float(pos_data.mark_price) if pos_data.mark_price else 0,
                        greeks=greeks
                    )
        except Exception as e:
            logger.warning("Failed to fetch futures positions for %s: %s", perp_symbol, e)

        # --- Fetch Delivery Futures Positions (via inverse category) ---
        # Note: Delivery futures are handled under 'inverse' category in Bybit API v5
        try:
            # Fetch inverse positions which includes both inverse perpetual and delivery futures
            inverse_positions_raw = await client.get_positions(category='inverse', base_coin=base_coin)

            if inverse_positions_raw:
                for pos_data in inverse_positions_raw:
                    symbol = pos_data.symbol
                    
                    # Skip if this is a perpetual (already handled above)
                    if symbol == f"{base_coin}USD":
                        continue
                        
                    # Only process if it looks like a delivery futures contract
                    # Delivery futures typically have date-based naming (e.g., BTCUSD0329, BTCUSDM24)
                    if not any(char.isdigit() for char in symbol):
                        continue
                    
                    quantity = float(pos_data.size)
                    if pos_data.side.lower() == 'sell':
                        quantity *= -1
                    greeks = Greeks(delta=1.0, gamma=0.0, theta=0.0, vega=0.0)
                    all_exchange_positions[symbol] = Position(
                        symbol=symbol,
                        quantity=quantity,
                        entry_price=float(pos_data.avg_price) if pos_data.avg_price else 0,
                        current_price=float(pos_data.mark_price) if pos_data.mark_price else 0,
                        greeks=greeks
                    )
        except Exception as e:
            logger.warning("Failed to fetch inverse/delivery futures for %s: %s", base_coin, e)

        # 3. Update portfolio based on only_existing flag
        if only_existing:
            existing_symbols = set(portfolio.positions.keys())
            synced_positions = {
                symbol: pos for symbol, pos in all_exchange_positions.items() 
                if symbol in existing_symbols
            }
            portfolio.positions = synced_positions
        else:
            portfolio.positions = all_exchange_positions

        portfolio.last_synced = datetime.now(timezone.utc)
        self.save_portfolio(portfolio)
        
        logger.info("Portfolio '%s' synced with exchange. Found %d positions.", name, len(portfolio.positions))

        return portfolio

    async def _fetch_account_snapshot(self) -> Optional[AccountSnapshot]:
        """Fetch account wallet and position data for risk validation."""
        try:
            wallet_balance = await self.client.get_wallet_balance(account_type="UNIFIED")
        except Exception as e:
            logger.warning("Failed to fetch wallet balance: %s", e)
            return None

        positions = []
        try:
            positions_by_category = await self.client.get_all_positions()
            for category_positions in positions_by_category.values():
                positions.extend(category_positions)
        except Exception as e:
            logger.warning("Failed to fetch aggregated positions: %s", e)

        return self._build_account_snapshot(wallet_balance, positions)

    def _build_account_snapshot(self, wallet_balance: Dict[str, Any],
                                positions: List[Any]) -> Optional[AccountSnapshot]:
        """Build a normalized account snapshot from Bybit API responses."""
        def _to_optional_float(value: Any) -> Optional[float]:
            if value is None or value == '':
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _first_present(data: Dict[str, Any], keys: List[str]) -> Optional[float]:
            for key in keys:
                if key in data:
                    value = _to_optional_float(data.get(key))
                    if value is not None:
                        return value
            return None

        def _sum_coin_equity_usd(coins: List[Dict[str, Any]]) -> Optional[float]:
            total = 0.0
            found = False
            for coin_info in coins:
                usd_value = _to_optional_float(coin_info.get("usdValue"))
                if usd_value is not None:
                    total += usd_value
                    found = True
                    continue

                coin = coin_info.get("coin")
                equity = _to_optional_float(coin_info.get("equity"))
                if coin == "USDT" and equity is not None:
                    total += equity
                    found = True
            return total if found else None

        account_list = wallet_balance.get('list', [])
        if not account_list:
            return None

        totals = account_list[0]
        coin_balances = totals.get("coin", []) if isinstance(totals, dict) else []
        coin_equity_usd = _sum_coin_equity_usd(coin_balances)
        total_available_balance = _first_present(
            totals, ["totalAvailableBalance", "availableBalance", "availableToWithdraw"]
        )
        snapshot_positions = []
        for pos in positions:
            position_value = pos.position_value
            if position_value is None and pos.mark_price > 0:
                position_value = abs(pos.size * pos.mark_price)

            snapshot_positions.append(AccountPositionRisk(
                symbol=pos.symbol,
                size=pos.size,
                mark_price=pos.mark_price,
                liquidation_price=pos.liquidation_price,
                position_value=position_value,
                unrealized_pnl=pos.unrealised_pnl,
                category=pos.category
            ))

        return AccountSnapshot(
            total_equity=_first_present(totals, ["totalEquity"]),
            available_balance=coin_equity_usd if coin_equity_usd is not None else total_available_balance,
            total_margin_balance=_first_present(totals, ["totalMarginBalance"]),
            total_initial_margin=_first_present(totals, ["totalInitialMargin"]),
            total_maintenance_margin=_first_present(totals, ["totalMaintenanceMargin"]),
            total_unrealized_pnl=_first_present(totals, ["totalUnrealisedPnl", "totalUnrealizedPnl", "totalPerpUPL"]),
            total_wallet_balance=_first_present(totals, ["totalWalletBalance"]),
            positions=snapshot_positions
        )
