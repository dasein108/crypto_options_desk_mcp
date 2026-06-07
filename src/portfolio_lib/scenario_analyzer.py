import logging
import pandas as pd
import asyncio
import re
from datetime import datetime, timedelta
from py_vollib.black_scholes import black_scholes
from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega
from options_lib.pricing import ProfessionalOptionsEngine, OptionSpec

logger = logging.getLogger(__name__)

# Use unified position loading and client
# API client is duck-typed (passed at construction)

# Set pandas display options for better readability
pd.set_option('display.width', 1000)
pd.set_option('display.max_columns', 15)


def _parse_expiry_from_symbol(symbol: str) -> datetime:
    """Helper to extract the expiry date from a Bybit option symbol like 'BTC-30DEC24-70000-C'."""
    match = re.search(r'-(\d{1,2}[A-Z]{3}\d{2})-', symbol)
    if not match:
        raise ValueError(f"Could not parse expiry date from symbol: {symbol}")
    return datetime.strptime(match.group(1), '%d%b%y')


class ScenarioAnalyzer:
    def __init__(self, use_mock: bool = False):
        """
        Initializes the ScenarioAnalyzer.

        :param use_mock: If True, uses MockBybitClient for testing. If False, uses the live BybitOptionsResearch client.
        """
        self.portfolio = []
        self.risk_free_rate = 0.05  # Default risk-free rate, can be adjusted.
        self.pricing_engine = ProfessionalOptionsEngine(self.risk_free_rate)

        # IMPORTANT: For live trading, ensure API keys are set in your .env file
        self.client = None  # API client set externally

    def set_manual_portfolio(self, portfolio_data: list, underlying_price: float):
        """
        Allows using a manually defined portfolio, preserving the original script's functionality.
        """
        logger.info("Setting manual portfolio")
        self.portfolio = []
        for pos in portfolio_data:
            pos_data = pos.copy()
            pos_data['S'] = underlying_price # Set the underlying price for all

            # For manual portfolios, add entry_price if not provided
            if 'entry_price' not in pos_data:
                # Use current theoretical price as entry price for manual portfolios
                if 't' in pos_data:
                    metrics = calculate_option_metrics(pos_data['flag'], underlying_price, pos_data['K'], pos_data['t'], pos_data['r'], pos_data['sigma'])
                    pos_data['entry_price'] = metrics['price']
                else:
                    pos_data['entry_price'] = 0.0  # Default fallback

            self.portfolio.append(pos_data)
        logger.info("Manual portfolio set with %d positions.", len(self.portfolio))

    async def load_full_portfolio(self, underlying: str, categories: list = None):
        """
        Fetches all open positions for a given underlying across all categories using unified loading.
        
        Args:
            underlying: Base asset (e.g., 'BTC', 'ETH')
            categories: List of categories to load ['option', 'linear', 'inverse', 'spot']. 
                       If None, loads all categories.
        """
        logger.info("Loading full Bybit portfolio for %s", underlying)
        
        if categories is None:
            categories = ['option', 'linear', 'inverse', 'spot']
        
        # Use unified position loading
        all_positions = await self.client.get_all_positions(underlying)
        
        # Filter by requested categories
        filtered_positions = []
        for category in categories:
            if category in all_positions:
                filtered_positions.extend(all_positions[category])
        
        if not filtered_positions:
            logger.info("No positions found for %s in categories %s.", underlying, categories)
            self.portfolio = []
            return

        logger.info("Found %d total positions across categories: %s", len(filtered_positions), categories)
        
        # Separate options from other instruments for different processing
        option_positions = [pos for pos in filtered_positions if 'option' in getattr(pos, 'category', '')]
        other_positions = [pos for pos in filtered_positions if 'option' not in getattr(pos, 'category', '')]
        
        self.portfolio = []
        
        # Process option positions (require detailed pricing data)
        if option_positions:
            await self._process_option_positions(option_positions, underlying)
        
        # Process other positions (futures, spot - simpler processing)
        if other_positions:
            await self._process_other_positions(other_positions, underlying)
        
        logger.info("Loaded %d positions from Bybit.", len(self.portfolio))

    async def _process_option_positions(self, positions, underlying):
        """Process option positions with detailed market data."""
        logger.info("Processing %d option positions.", len(positions))
        
        # Fetch market data for all options of the underlying at once
        all_option_prices = await self.client.get_option_prices(base_coin=underlying)
        prices_map = {price.symbol: price for price in all_option_prices}

        for pos in positions:
            if pos.symbol not in prices_map:
                logger.warning("Could not find market data for option %s. Skipping.", pos.symbol)
                continue

            price_info = prices_map[pos.symbol]
            expiry_date = _parse_expiry_from_symbol(pos.symbol)

            self.portfolio.append({
                'symbol': pos.symbol,
                'quantity': pos.size,
                'entry_price': pos.avg_price if hasattr(pos, 'avg_price') and pos.avg_price > 0 else price_info.mark_price,
                'flag': 'c' if 'C' in pos.symbol.split('-')[-1] else 'p',
                'S': price_info.underlying_price,
                'K': float(pos.symbol.split('-')[2]),
                'expiry_date': expiry_date,
                'r': self.risk_free_rate,
                'sigma': price_info.mark_iv,
                'category': 'option',
                'current_market_price': price_info.mark_price
            })

    async def _process_other_positions(self, positions, underlying):
        """Process non-option positions (futures, spot)."""
        logger.info("Processing %d non-option positions.", len(positions))
        
        # Get current underlying price
        try:
            current_price = await self.client.get_asset_price(f"{underlying}USDT")
        except:
            current_price = 50000.0  # Fallback price
            logger.warning("Could not fetch %s price, using fallback: %s", underlying, current_price)

        for pos in positions:
            # For non-option positions, we model them as having delta=1 (linear exposure)
            category = getattr(pos, 'category', 'unknown')
            
            # Use Greeks from position if available, otherwise default to linear exposure
            if hasattr(pos, 'greeks') and pos.greeks:
                delta_value = pos.greeks.delta
            else:
                # Default: linear instruments have delta = 1
                delta_value = 1.0 if pos.size > 0 else -1.0
            
            self.portfolio.append({
                'symbol': pos.symbol,
                'quantity': pos.size,
                'entry_price': pos.avg_price if hasattr(pos, 'avg_price') and pos.avg_price > 0 else pos.mark_price,
                'current_price': pos.mark_price if hasattr(pos, 'mark_price') else current_price,
                'S': current_price,
                'delta': delta_value,
                'category': category,
                'is_linear': True  # Flag to identify non-option instruments
            })


    async def load_specific_instruments(self, instruments: dict):
        """
        Fetches data for a specific list of instruments and quantities.
        Now supports mixed instrument types (options, futures, spot).

        :param instruments: A dictionary of {'symbol': quantity}, e.g., 
                           {'BTC-30DEC24-70000-C': 1.5, 'BTCUSDT': 0.1, 'BTC-30DEC24-75000-P': -1}
        """
        logger.info("Loading specific instruments from Bybit")
        if not instruments:
            self.portfolio = []
            return
            
        symbols = list(instruments.keys())
        
        # Categorize symbols by type
        option_symbols = []
        other_symbols = []
        
        for symbol in symbols:
            if self._is_option_symbol(symbol):
                option_symbols.append(symbol)
            else:
                other_symbols.append(symbol)
        
        logger.info("Detected %d option symbols and %d other symbols", len(option_symbols), len(other_symbols))
        
        # Detect base coins from the symbols
        base_coins = set()
        for symbol in symbols:
            base_coin = self._extract_base_coin(symbol)
            if base_coin:
                base_coins.add(base_coin)
        
        if not base_coins:
            logger.warning("No base coins detected, falling back to BTC")
            base_coins = {'BTC'}
        
        self.portfolio = []
        
        # Process option symbols
        if option_symbols:
            await self._load_specific_options(option_symbols, instruments, base_coins)
        
        # Process other symbols (futures, spot)
        if other_symbols:
            await self._load_specific_others(other_symbols, instruments, base_coins)
            
        logger.info("Loaded %d specific instruments from Bybit.", len(self.portfolio))

    def _is_option_symbol(self, symbol: str) -> bool:
        """Check if symbol is an option (contains expiry and strike pattern)."""
        return bool(re.search(r'-\d{1,2}[A-Z]{3}\d{2}-\d+-[CP]$', symbol))

    def _extract_base_coin(self, symbol: str) -> str:
        """Extract base coin from symbol."""
        if '-' in symbol:
            return symbol.split('-')[0]
        elif symbol.endswith('USDT'):
            return symbol.replace('USDT', '')
        else:
            return symbol  # Assume symbol is the base coin itself

    async def _load_specific_options(self, option_symbols, instruments, base_coins):
        """Load specific option instruments."""
        # Fetch market data for all detected base coins
        prices_map = {}
        for base_coin in base_coins:
            try:
                option_prices = await self.client.get_option_prices(base_coin=base_coin)
                for price in option_prices:
                    if price.symbol in option_symbols:
                        prices_map[price.symbol] = price
            except Exception as e:
                logger.warning("Could not fetch option data for %s: %s", base_coin, e)

        pass
        for symbol in option_symbols:
            if symbol not in prices_map:
                logger.warning("Could not find market data for option %s. Skipping.", symbol)
                continue

            price_info = prices_map[symbol]
            expiry_date = _parse_expiry_from_symbol(symbol)
            position_data = instruments[symbol]

            # Handle both old format (float) and new format (dict with size/entry_price)
            if isinstance(position_data, dict):
                quantity = position_data.get('size', 0)
                entry_price = position_data.get('entry_price', price_info.mark_price)
            else:
                quantity = float(position_data)
                entry_price = price_info.mark_price

            self.portfolio.append({
                'symbol': symbol,
                'quantity': quantity,
                'entry_price': entry_price,
                'flag': 'c' if 'C' in symbol.split('-')[-1] else 'p',
                'S': price_info.underlying_price,
                'K': float(symbol.split('-')[2]),
                'expiry_date': expiry_date,
                'r': self.risk_free_rate,
                'sigma': price_info.mark_iv,
                'current_market_price': price_info.mark_price,
                'category': 'option'
            })

    async def _load_specific_others(self, other_symbols, instruments, base_coins):
        """Load specific non-option instruments (futures, spot)."""
        # Get current prices for base coins
        prices_map = {}
        for base_coin in base_coins:
            try:
                price = await self.client.get_asset_price(f"{base_coin}USDT")
                prices_map[base_coin] = price
                prices_map[f"{base_coin}USDT"] = price  # Also map the full symbol
            except Exception as e:
                logger.warning("Could not fetch price for %s: %s", base_coin, e)

        for symbol in other_symbols:
            position_data = instruments[symbol]
            base_coin = self._extract_base_coin(symbol)
            
            # Get current price
            current_price = prices_map.get(symbol) or prices_map.get(base_coin, 50000.0)
            
            # Handle both old format (float) and new format (dict with size/entry_price)
            if isinstance(position_data, dict):
                quantity = position_data.get('size', 0)
                entry_price = position_data.get('entry_price', current_price)
            else:
                quantity = float(position_data)
                entry_price = current_price

            # Determine category based on symbol pattern
            if symbol.endswith('USDT'):
                category = 'linear'  # Linear perpetual
            elif symbol == base_coin:
                category = 'spot'    # Spot
            else:
                category = 'inverse' # Inverse or delivery futures

            self.portfolio.append({
                'symbol': symbol,
                'quantity': quantity,
                'entry_price': entry_price,
                'current_price': current_price,
                'S': current_price,
                'delta': 1.0 if quantity > 0 else -1.0,  # Linear exposure
                'category': category,
                'is_linear': True
            })


    def run_analysis(self, scenarios: dict):
        """
        Runs scenario analysis on the currently loaded portfolio using professional pricing.
        
        Args:
            scenarios: Dict with scenario_name: scenario_params format
                      Expected params: 'new_underlying_price', 'new_iv_level', 'days_passed'
        """
        if not self.portfolio:
            logger.error("Portfolio is not loaded. Cannot run analysis.")
            return None, None

        logger.info("Running professional scenario analysis.")
        
        # Classify positions by instrument type
        option_positions = []
        linear_positions = []
        
        for pos in self.portfolio:
            if self._is_option_position(pos):
                option_positions.append(pos)
            else:
                linear_positions.append(pos)
        
        logger.info("Portfolio breakdown: %d options, %d linear instruments", len(option_positions), len(linear_positions))
        
        results = []
        
        # Calculate current values for all positions
        self._calculate_current_values()
        
        # Process each scenario
        for scenario_name, params in scenarios.items():
            logger.debug("Processing scenario: %s", scenario_name)
            
            # Extract scenario parameters with fallbacks
            new_price = params.get('new_underlying_price', None)
            new_iv = params.get('new_iv_level', None) 
            days_forward = params.get('days_passed', 0)
            
            # Calculate price change percentage if new_price provided
            price_change_pct = params.get('price_change_pct', 0)
            if new_price is not None and len(self.portfolio) > 0:
                current_price = self.portfolio[0]['S']  # Use first position's underlying price as reference
                price_change_pct = (new_price - current_price) / current_price * 100
            
            # Debug output for first few scenarios
            if len(results) < 10:
                logger.debug("Scenario params: new_price=%s, new_iv=%s, days=%s", new_price, new_iv, days_forward)
                logger.debug("price_change_pct=%s", price_change_pct)
            
            for pos in self.portfolio:
                scenario_result = self._calculate_position_scenario_pnl(
                    pos, new_price, new_iv, days_forward, price_change_pct
                )
                
                # Debug output for first position
                if len(results) < 5 and pos == self.portfolio[0]:
                    logger.debug("Position %s: entry=%.2f, scenario=%.2f, pnl=%.2f", pos['symbol'], scenario_result['entry_value'], scenario_result['scenario_value'], scenario_result['pnl'])
                
                results.append({
                    'symbol': pos['symbol'],
                    'scenario': scenario_name,
                    'pnl': scenario_result['pnl'],
                    'entry_value': scenario_result['entry_value'],
                    'scenario_value': scenario_result['scenario_value'],
                    'category': pos.get('category', 'option'),
                    'position_type': 'Short' if pos['quantity'] < 0 else 'Long',
                    'underlying_price': new_price or pos['S'],
                    'iv_level': new_iv if new_iv is not None else pos.get('sigma', 0.5)
                })

        df = pd.DataFrame(results)
        summary = df.groupby('scenario')['pnl'].sum().reset_index().rename(columns={'pnl': 'total_pnl'})
        
        logger.info("Professional analysis complete.")
        return df, summary
    
    def _is_option_position(self, pos: dict) -> bool:
        """Determine if position is an option based on available fields."""
        # Check for option-specific fields
        has_option_fields = all(key in pos for key in ['K', 'flag', 'sigma'])
        has_expiry = 'expiry_date' in pos
        is_marked_linear = pos.get('is_linear', False)
        
        return (has_option_fields or has_expiry) and not is_marked_linear
    
    def _calculate_current_values(self):
        """Calculate current theoretical values for all positions."""
        logger.info("Calculating current values for portfolio.")
        for i, pos in enumerate(self.portfolio):
            pos['entry_value'] = pos['entry_price'] * abs(pos['quantity'])

            if self._is_option_position(pos):
                # Use professional pricing for options
                current_price = self._get_option_theoretical_price(pos)
            else:
                # Linear instruments use market price
                current_price = pos.get('current_price', pos['S'])

            pos['current_theoretical_value'] = current_price * abs(pos['quantity'])

            # Debug output for first few positions
            if i < 3:
                logger.debug("Position %d: %s", i, pos['symbol'])
                logger.debug("  Entry price: %s, Quantity: %s", pos['entry_price'], pos['quantity'])
                logger.debug("  Entry value: %.2f", pos['entry_value'])
                logger.debug("  Current theoretical value: %.2f", pos['current_theoretical_value'])
    
    def _get_option_theoretical_price(self, pos: dict, 
                                    underlying_price: float = None,
                                    iv: float = None,
                                    scenario_date: datetime = None) -> float:
        """Get theoretical option price using professional pricing engine."""
        try:
            # Use provided values or defaults from position
            S = underlying_price or pos['S']
            sigma = iv or pos.get('sigma', 0.5)
            
            # Create option specification
            if 'expiry_date' in pos:
                # Modern format with expiry date
                spec = OptionSpec(
                    symbol=pos['symbol'],
                    underlying_price=S,
                    strike=pos['K'],
                    expiration_date=pos['expiry_date'],
                    option_type='call' if pos['flag'] == 'c' else 'put',
                    risk_free_rate=pos.get('r', self.risk_free_rate),
                    implied_volatility=sigma
                )
                
                metrics = self.pricing_engine.calculate_option_metrics(spec, scenario_date)
                return metrics.theoretical_price
            else:
                # Legacy format with time to expiration
                t = pos.get('t', 0)
                if scenario_date:
                    # Adjust time for scenario date
                    days_passed = (scenario_date - datetime.now()).days
                    t = max(0, t - days_passed / 365.0)
                
                if t <= 0:
                    # Expired option - intrinsic value only
                    if pos['flag'] == 'c':
                        return max(0.0, S - pos['K'])
                    else:
                        return max(0.0, pos['K'] - S)
                
                # Use legacy calculation
                metrics = calculate_option_metrics(
                    pos['flag'], S, pos['K'], t, pos.get('r', self.risk_free_rate), sigma
                )
                return metrics['price']
                
        except Exception as e:
            logger.error("Error calculating option price for %s: %s", pos['symbol'], e)
            # Return intrinsic value as fallback
            if pos['flag'] == 'c':
                return max(0.0, (underlying_price or pos['S']) - pos['K'])
            else:
                return max(0.0, pos['K'] - (underlying_price or pos['S']))
    
    def _calculate_position_scenario_pnl(self, pos: dict, 
                                       new_price: float = None,
                                       new_iv: float = None, 
                                       days_forward: float = 0,
                                       price_change_pct: float = 0) -> dict:
        """Calculate P&L for a position under scenario conditions."""
        entry_value = pos['entry_value']
        
        if self._is_option_position(pos):
            # Option position - use professional pricing
            scenario_date = datetime.now() + timedelta(days=days_forward)
            
            # Determine new underlying price
            if new_price is not None:
                underlying_price = new_price
            else:
                underlying_price = pos['S'] * (1 + price_change_pct / 100)
            
            # Determine new IV - handle percentage vs decimal formats
            if new_iv is not None:
                # Check if IV is in percentage format (>1) or decimal format (<1)
                if new_iv > 1:
                    iv = new_iv / 100  # Convert percentage to decimal
                else:
                    iv = new_iv  # Already in decimal format
            else:
                iv = pos.get('sigma', 0.5)
            
            scenario_price = self._get_option_theoretical_price(
                pos, underlying_price, iv, scenario_date
            )
            scenario_value = scenario_price * abs(pos['quantity'])
            
        else:
            # Linear instrument - direct price relationship
            if new_price is not None:
                price_per_unit = new_price
            else:
                price_per_unit = pos['S'] * (1 + price_change_pct / 100)
                
            scenario_value = price_per_unit * abs(pos['quantity'])
        
        # Calculate P&L considering position direction
        pnl = (scenario_value - entry_value) * (1 if pos['quantity'] > 0 else -1)
        
        return {
            'pnl': pnl,
            'entry_value': entry_value,
            'scenario_value': scenario_value
        }


def calculate_option_metrics(flag, S, K, t, r, sigma):
    """
    Calculate comprehensive option metrics including price and all Greeks using professional engine.
    
    Args:
        flag: 'c' for call, 'p' for put
        S: Underlying price
        K: Strike price  
        t: Time to expiration in years
        r: Risk-free rate
        sigma: Implied volatility
        
    Returns:
        Dict with price and all Greeks
    """
    try:
        # If time to expiry is zero or negative, value is only intrinsic
        if t <= 0:
            if flag == 'c':
                price = max(0.0, S - K)
                delta_val = 1.0 if S > K else 0.0
            else:  # 'p'
                price = max(0.0, K - S)
                delta_val = -1.0 if S < K else 0.0
            
            return {
                'price': price,
                'delta': delta_val,
                'gamma': 0.0,
                'theta': 0.0,
                'vega': 0.0,
                'rho': 0.0,
                'intrinsic_value': price,
                'time_value': 0.0
            }
        else:
            # Calculate Black-Scholes price and Greeks
            price = black_scholes(flag, S, K, t, r, sigma)
            
            # Check for NaN
            if price != price:
                price = 0.0
            
            # Calculate Greeks using py-vollib. analytical.theta/vega already
            # return per-day / per-1pp values; do NOT double-divide (see
            # options_lib/pricing/black_scholes.py for the same fix).
            try:
                delta_val = delta(flag, S, K, t, r, sigma)
                gamma_val = gamma(flag, S, K, t, r, sigma)
                theta_val = theta(flag, S, K, t, r, sigma)  # per-day
                vega_val = vega(flag, S, K, t, r, sigma)    # per 1 pct pt IV
                
                # Calculate intrinsic and time value
                if flag == 'c':
                    intrinsic = max(0.0, S - K)
                else:
                    intrinsic = max(0.0, K - S)
                
                time_value = max(0.0, price - intrinsic)
                
                return {
                    'price': max(0.0, price),
                    'delta': delta_val,
                    'gamma': max(0.0, gamma_val),
                    'theta': theta_val,
                    'vega': max(0.0, vega_val),
                    'rho': 0.0,  # Can calculate if needed
                    'intrinsic_value': intrinsic,
                    'time_value': time_value
                }
                
            except Exception as e:
                logger.error("Error calculating Greeks: %s", e)
                # Return price with zero Greeks if Greeks calculation fails
                return {
                    'price': max(0.0, price),
                    'delta': 0.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0, 'rho': 0.0,
                    'intrinsic_value': 0.0, 'time_value': max(0.0, price)
                }
                
    except Exception as e:
        logger.error("Error in calculate_option_metrics: %s", e)
        # If any other unexpected error occurs, return safe defaults
        return {
            'price': 0.0,
            'delta': 0.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0, 'rho': 0.0,
            'intrinsic_value': 0.0, 'time_value': 0.0
        }

async def main():
    # --- Define Scenarios ---
    scenarios = {
        'Price +10%, IV same, 7 days pass': {'price_change_pct': 10, 'days_passed': 7},
        'Price -10%, IV same, 7 days pass': {'price_change_pct': -10, 'days_passed': 7},
        'Market Crash: Price -25%, IV +50%': {'price_change_pct': -25, 'iv_change_pct': 50, 'days_passed': 1},
    }

    # Initialize the analyzer (using the mock client for this demo)
    analyzer = ScenarioAnalyzer(use_mock=True)

    # --- USAGE 1: Load full portfolio from Bybit (all categories) ---
    await analyzer.load_full_portfolio(underlying='BTC', categories=['option', 'linear', 'inverse', 'spot'])
    individual_pnl_df, summary_pnl_df = analyzer.run_analysis(scenarios)
    if summary_pnl_df is not None:
        print("\n--- Total P&L Summary (Full Bybit Portfolio - All Categories) ---")
        print(summary_pnl_df.to_string())

    # --- USAGE 2: Load specific instruments (mixed types) ---
    mixed_instruments = {
        'BTC-30DEC26-70000-C': {'size': 1.0, 'entry_price': 3500},   # Long call with entry price
        'BTC-30DEC26-80000-C': {'size': -2.0, 'entry_price': 2100}, # Short call with entry price
        'BTCUSDT': {'size': 0.1, 'entry_price': 68000},             # Long linear futures
        'BTC': {'size': -0.05},                                     # Short spot (uses current price as entry)
    }
    await analyzer.load_specific_instruments(mixed_instruments)
    individual_pnl_df, summary_pnl_df = analyzer.run_analysis(scenarios)
    if summary_pnl_df is not None:
        print("\n--- Total P&L Summary (Mixed Instrument Types) ---")
        print(summary_pnl_df.to_string())
        
        # Show detailed breakdown by category
        if individual_pnl_df is not None and not individual_pnl_df.empty:
            category_summary = individual_pnl_df.groupby(['scenario', 'category'])['pnl'].sum().reset_index()
            print("\n--- P&L Breakdown by Category ---")
            print(category_summary.pivot(index='scenario', columns='category', values='pnl').fillna(0).to_string())
        
    # --- USAGE 3: Use a manual portfolio (original functionality) ---
    manual_portfolio = [
        {'symbol': 'MANUAL-C', 'quantity': 1, 'flag': 'c', 'K': 70000, 't': 30/365.0, 'r': 0.05, 'sigma': 0.65},
        {'symbol': 'MANUAL-P', 'quantity': -2, 'flag': 'p', 'K': 65000, 't': 30/365.0, 'r': 0.05, 'sigma': 0.60},
    ]
    analyzer.set_manual_portfolio(manual_portfolio, underlying_price=68000)
    individual_pnl_df, summary_pnl_df = analyzer.run_analysis(scenarios)
    if summary_pnl_df is not None:
        print("\n--- Total P&L Summary (Manual Portfolio) ---")
        print(summary_pnl_df.to_string())


if __name__ == '__main__':
    asyncio.run(main())