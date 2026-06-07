"""
Option Strategy Classifier
=========================

Identifies and classifies option strategies from portfolios or option chains.
Supports straddles, strangles, spreads, condors, butterflies, and ratio spreads.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, NamedTuple
from enum import Enum
from collections import defaultdict

from ..symbol_parser import parse_bybit_option_symbol


class StrategyType(Enum):
    """Option strategy types"""
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    CALL_SPREAD = "call_spread"
    PUT_SPREAD = "put_spread"
    IRON_CONDOR = "iron_condor"
    IRON_BUTTERFLY = "iron_butterfly"
    CALL_RATIO_SPREAD = "call_ratio_spread"
    PUT_RATIO_SPREAD = "put_ratio_spread"
    CALENDAR_SPREAD = "calendar_spread"
    SYNTHETIC = "synthetic"
    COVERED_CALL = "covered_call"
    PROTECTIVE_PUT = "protective_put"
    UNKNOWN = "unknown"


@dataclass
class OptionLeg:
    """Represents a single option leg in a strategy"""
    symbol: str
    strike: float
    expiry: str
    option_type: str  # 'C' or 'P'
    quantity: float
    side: str  # 'long' or 'short'
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    underlying_symbol: Optional[str] = None


@dataclass
class IdentifiedStrategy:
    """Represents an identified option strategy"""
    strategy_type: StrategyType
    legs: List[OptionLeg]
    underlying_symbol: str
    expiry: str
    confidence: float  # 0-1 confidence in identification
    net_cost: Optional[float] = None
    max_profit: Optional[float] = None
    max_loss: Optional[float] = None
    breakeven_points: List[float] = field(default_factory=list)
    description: str = ""


class OptionSymbolParser:
    """Parse option symbols from various formats."""

    @staticmethod
    def parse_bybit_symbol(symbol: str) -> Optional[Dict]:
        """Parse Bybit option symbol format: BTC-30DEC24-70000-C"""
        return parse_bybit_option_symbol(symbol)


class StrategyClassifier:
    """Identifies option strategies from positions or option chains"""
    
    def __init__(self):
        self.parser = OptionSymbolParser()
    
    def classify_portfolio(self, positions: Dict[str, Dict]) -> List[IdentifiedStrategy]:
        """
        Classify strategies from a portfolio of positions
        
        Args:
            positions: Dict of {symbol: {quantity, entry_price, ...}}
            
        Returns:
            List of identified strategies
        """
        # Convert positions to OptionLeg format
        legs = self._positions_to_legs(positions)
        
        # Group by underlying and expiry
        grouped_legs = self._group_legs(legs)
        
        # Identify strategies in each group
        strategies = []
        for (underlying, expiry), group_legs in grouped_legs.items():
            group_strategies = self._identify_strategies_in_group(group_legs, underlying, expiry)
            strategies.extend(group_strategies)
        
        return strategies
    
    def find_potential_strategies(self, options_chain: List[Dict], 
                                underlying_price: float,
                                strategy_types: Optional[List[StrategyType]] = None) -> List[Dict]:
        """
        Find potential strategies from an options chain
        
        Args:
            options_chain: List of option data dictionaries
            underlying_price: Current underlying price
            strategy_types: Optional list to filter strategy types
            
        Returns:
            List of potential strategy configurations
        """
        if strategy_types is None:
            strategy_types = [StrategyType.STRADDLE, StrategyType.STRANGLE, 
                            StrategyType.CALL_SPREAD, StrategyType.PUT_SPREAD]
        
        # Group options by expiry
        by_expiry = defaultdict(list)
        for option in options_chain:
            parsed = self.parser.parse_bybit_symbol(option.get('symbol', ''))
            if parsed:
                by_expiry[parsed['expiry']].append({**option, **parsed})
        
        potential_strategies = []
        
        for expiry, options in by_expiry.items():
            if StrategyType.STRADDLE in strategy_types:
                potential_strategies.extend(
                    self._find_straddles(options, underlying_price, expiry)
                )
            
            if StrategyType.STRANGLE in strategy_types:
                potential_strategies.extend(
                    self._find_strangles(options, underlying_price, expiry)
                )
            
            if StrategyType.CALL_SPREAD in strategy_types:
                potential_strategies.extend(
                    self._find_call_spreads(options, underlying_price, expiry)
                )
            
            if StrategyType.PUT_SPREAD in strategy_types:
                potential_strategies.extend(
                    self._find_put_spreads(options, underlying_price, expiry)
                )
        
        return potential_strategies
    
    def _positions_to_legs(self, positions: Dict[str, Dict]) -> List[OptionLeg]:
        """Convert portfolio positions to OptionLeg objects"""
        legs = []
        
        for symbol, pos_data in positions.items():
            parsed = self.parser.parse_bybit_symbol(symbol)
            if not parsed:
                continue  # Skip non-option positions
            
            quantity = float(pos_data.get('quantity', pos_data.get('size', 0)))
            if quantity == 0:
                continue
            
            side = 'long' if quantity > 0 else 'short'
            
            leg = OptionLeg(
                symbol=symbol,
                strike=parsed['strike'],
                expiry=parsed['expiry'],
                option_type=parsed['option_type'],
                quantity=abs(quantity),
                side=side,
                entry_price=pos_data.get('entry_price'),
                current_price=pos_data.get('current_price', pos_data.get('mark_price')),
                delta=pos_data.get('delta'),
                gamma=pos_data.get('gamma'),
                theta=pos_data.get('theta'),
                vega=pos_data.get('vega'),
                iv=pos_data.get('mark_iv'),
                underlying_symbol=parsed['underlying']
            )
            
            legs.append(leg)
        
        return legs
    
    def _group_legs(self, legs: List[OptionLeg]) -> Dict[Tuple[str, str], List[OptionLeg]]:
        """Group legs by underlying symbol and expiry"""
        grouped = defaultdict(list)
        
        for leg in legs:
            key = (leg.underlying_symbol or 'UNKNOWN', leg.expiry)
            grouped[key].append(leg)
        
        return grouped
    
    def _identify_strategies_in_group(self, legs: List[OptionLeg], 
                                   underlying: str, expiry: str) -> List[IdentifiedStrategy]:
        """Identify strategies within a group of same underlying/expiry"""
        strategies = []
        used_legs = set()
        
        # Sort legs by strike for easier analysis
        sorted_legs = sorted(legs, key=lambda x: x.strike)
        
        # Try to identify each strategy type
        strategies.extend(self._find_straddles_in_group(sorted_legs, underlying, expiry, used_legs))
        strategies.extend(self._find_strangles_in_group(sorted_legs, underlying, expiry, used_legs))
        strategies.extend(self._find_spreads_in_group(sorted_legs, underlying, expiry, used_legs))
        
        # Any remaining legs as individual positions
        for leg in sorted_legs:
            if id(leg) not in used_legs:
                strategies.append(IdentifiedStrategy(
                    strategy_type=StrategyType.UNKNOWN,
                    legs=[leg],
                    underlying_symbol=underlying,
                    expiry=expiry,
                    confidence=1.0,
                    description=f"Individual {leg.side} {leg.option_type.lower()} @ {leg.strike}"
                ))
        
        return strategies
    
    def _find_straddles_in_group(self, legs: List[OptionLeg], underlying: str, 
                               expiry: str, used_legs: set) -> List[IdentifiedStrategy]:
        """Find straddle strategies in a group"""
        strategies = []
        
        # Group by strike
        by_strike = defaultdict(list)
        for leg in legs:
            if id(leg) not in used_legs:
                by_strike[leg.strike].append(leg)
        
        for strike, strike_legs in by_strike.items():
            calls = [l for l in strike_legs if l.option_type == 'C']
            puts = [l for l in strike_legs if l.option_type == 'P']
            
            # Look for call-put pairs with same side and quantity
            for call in calls:
                for put in puts:
                    if (call.side == put.side and 
                        abs(call.quantity - put.quantity) < 0.01):  # Same quantity
                        
                        strategy_legs = [call, put]
                        net_cost = self._calculate_net_cost(strategy_legs)
                        
                        strategies.append(IdentifiedStrategy(
                            strategy_type=StrategyType.STRADDLE,
                            legs=strategy_legs,
                            underlying_symbol=underlying,
                            expiry=expiry,
                            confidence=0.95,
                            net_cost=net_cost,
                            description=f"{call.side.title()} straddle @ {strike}"
                        ))
                        
                        # Mark legs as used
                        used_legs.add(id(call))
                        used_legs.add(id(put))
                        break
        
        return strategies
    
    def _find_strangles_in_group(self, legs: List[OptionLeg], underlying: str,
                               expiry: str, used_legs: set) -> List[IdentifiedStrategy]:
        """Find strangle strategies in a group"""
        strategies = []
        
        available_legs = [l for l in legs if id(l) not in used_legs]
        calls = [l for l in available_legs if l.option_type == 'C']
        puts = [l for l in available_legs if l.option_type == 'P']
        
        # Look for call-put pairs with different strikes, same side
        for call in calls:
            for put in puts:
                if (call.strike != put.strike and 
                    call.side == put.side and 
                    abs(call.quantity - put.quantity) < 0.01):
                    
                    strategy_legs = [call, put]
                    net_cost = self._calculate_net_cost(strategy_legs)
                    
                    strategies.append(IdentifiedStrategy(
                        strategy_type=StrategyType.STRANGLE,
                        legs=strategy_legs,
                        underlying_symbol=underlying,
                        expiry=expiry,
                        confidence=0.9,
                        net_cost=net_cost,
                        description=f"{call.side.title()} strangle {put.strike}/{call.strike}"
                    ))
                    
                    used_legs.add(id(call))
                    used_legs.add(id(put))
                    break
        
        return strategies
    
    def _find_spreads_in_group(self, legs: List[OptionLeg], underlying: str,
                             expiry: str, used_legs: set) -> List[IdentifiedStrategy]:
        """Find vertical spread strategies in a group"""
        strategies = []
        
        available_legs = [l for l in legs if id(l) not in used_legs]
        calls = [l for l in available_legs if l.option_type == 'C']
        puts = [l for l in available_legs if l.option_type == 'P']
        
        # Call spreads
        strategies.extend(self._find_vertical_spreads(
            calls, StrategyType.CALL_SPREAD, underlying, expiry, used_legs))
        
        # Put spreads  
        strategies.extend(self._find_vertical_spreads(
            puts, StrategyType.PUT_SPREAD, underlying, expiry, used_legs))
        
        return strategies
    
    def _find_vertical_spreads(self, options: List[OptionLeg], strategy_type: StrategyType,
                             underlying: str, expiry: str, used_legs: set) -> List[IdentifiedStrategy]:
        """Find vertical spreads among options of same type"""
        strategies = []
        
        # Look for pairs with opposite sides
        for i, leg1 in enumerate(options):
            for leg2 in options[i+1:]:
                if (leg1.side != leg2.side and 
                    abs(leg1.quantity - leg2.quantity) < 0.01):
                    
                    # Determine spread direction
                    long_leg = leg1 if leg1.side == 'long' else leg2
                    short_leg = leg2 if leg2.side == 'short' else leg1
                    
                    if strategy_type == StrategyType.CALL_SPREAD:
                        if long_leg.strike < short_leg.strike:
                            spread_name = "Bull Call Spread"
                        else:
                            spread_name = "Bear Call Spread"
                    else:  # PUT_SPREAD
                        if long_leg.strike > short_leg.strike:
                            spread_name = "Bull Put Spread"
                        else:
                            spread_name = "Bear Put Spread"
                    
                    strategy_legs = [long_leg, short_leg]
                    net_cost = self._calculate_net_cost(strategy_legs)
                    
                    strategies.append(IdentifiedStrategy(
                        strategy_type=strategy_type,
                        legs=strategy_legs,
                        underlying_symbol=underlying,
                        expiry=expiry,
                        confidence=0.85,
                        net_cost=net_cost,
                        description=f"{spread_name} {long_leg.strike}/{short_leg.strike}"
                    ))
                    
                    used_legs.add(id(leg1))
                    used_legs.add(id(leg2))
                    break
        
        return strategies
    
    def _calculate_net_cost(self, legs: List[OptionLeg]) -> Optional[float]:
        """Calculate net cost/credit of a strategy"""
        total_cost = 0
        valid_prices = 0
        
        for leg in legs:
            price = leg.entry_price or leg.current_price
            if price is not None:
                if leg.side == 'long':
                    total_cost += price * leg.quantity
                else:  # short
                    total_cost -= price * leg.quantity
                valid_prices += 1
        
        return total_cost if valid_prices == len(legs) else None
    
    # Potential strategy finders for option chains
    def _find_straddles(self, options: List[Dict], underlying_price: float, 
                       expiry: str) -> List[Dict]:
        """Find potential straddle configurations"""
        straddles = []
        
        # Group by strike
        by_strike = defaultdict(list)
        for option in options:
            by_strike[option['strike']].append(option)
        
        for strike, strike_options in by_strike.items():
            calls = [o for o in strike_options if o['option_type'] == 'C']
            puts = [o for o in strike_options if o['option_type'] == 'P']
            
            if calls and puts:
                call = calls[0]
                put = puts[0]
                
                cost = call['mark_price'] + put['mark_price']
                atm_distance = abs(strike - underlying_price)
                
                straddles.append({
                    'strategy_type': 'straddle',
                    'strike': strike,
                    'expiry': expiry,
                    'cost': cost,
                    'atm_distance': atm_distance,
                    'atm_distance_pct': atm_distance / underlying_price * 100,
                    'call_symbol': call['symbol'],
                    'put_symbol': put['symbol'],
                    'breakevens': [strike - cost, strike + cost],
                    'implied_move_pct': cost / underlying_price * 100
                })
        
        return straddles
    
    def _find_strangles(self, options: List[Dict], underlying_price: float,
                       expiry: str) -> List[Dict]:
        """Find potential strangle configurations"""
        strangles = []
        
        calls = [o for o in options if o['option_type'] == 'C']
        puts = [o for o in options if o['option_type'] == 'P']
        
        for call in calls:
            for put in puts:
                if call['strike'] != put['strike']:
                    cost = call['mark_price'] + put['mark_price']
                    
                    # Determine OTM vs ITM configuration
                    call_otm = call['strike'] > underlying_price
                    put_otm = put['strike'] < underlying_price
                    
                    config_type = "Standard" if (call_otm and put_otm) else "Inverted"
                    
                    strangles.append({
                        'strategy_type': 'strangle',
                        'put_strike': put['strike'],
                        'call_strike': call['strike'],
                        'expiry': expiry,
                        'cost': cost,
                        'width': abs(call['strike'] - put['strike']),
                        'configuration': config_type,
                        'call_symbol': call['symbol'],
                        'put_symbol': put['symbol'],
                        'breakevens': [
                            min(put['strike'], call['strike']) - cost,
                            max(put['strike'], call['strike']) + cost
                        ]
                    })
        
        return strangles
    
    def _find_call_spreads(self, options: List[Dict], underlying_price: float,
                          expiry: str) -> List[Dict]:
        """Find potential call spread configurations"""
        spreads = []
        calls = [o for o in options if o['option_type'] == 'C']
        
        for i, long_call in enumerate(calls):
            for short_call in calls[i+1:]:
                if long_call['strike'] != short_call['strike']:
                    # Bull call spread: long lower strike, short higher strike
                    if long_call['strike'] < short_call['strike']:
                        net_cost = long_call['mark_price'] - short_call['mark_price']
                        max_profit = (short_call['strike'] - long_call['strike']) - net_cost
                        
                        spreads.append({
                            'strategy_type': 'bull_call_spread',
                            'long_strike': long_call['strike'],
                            'short_strike': short_call['strike'],
                            'expiry': expiry,
                            'net_cost': net_cost,
                            'max_profit': max_profit,
                            'max_loss': net_cost,
                            'breakeven': long_call['strike'] + net_cost,
                            'width': short_call['strike'] - long_call['strike']
                        })
        
        return spreads
    
    def _find_put_spreads(self, options: List[Dict], underlying_price: float,
                         expiry: str) -> List[Dict]:
        """Find potential put spread configurations"""
        spreads = []
        puts = [o for o in options if o['option_type'] == 'P']
        
        for i, long_put in enumerate(puts):
            for short_put in puts[i+1:]:
                if long_put['strike'] != short_put['strike']:
                    # Bull put spread: short higher strike, long lower strike
                    if long_put['strike'] < short_put['strike']:
                        net_credit = short_put['mark_price'] - long_put['mark_price']
                        max_profit = net_credit
                        max_loss = (short_put['strike'] - long_put['strike']) - net_credit
                        
                        spreads.append({
                            'strategy_type': 'bull_put_spread',
                            'long_strike': long_put['strike'],
                            'short_strike': short_put['strike'],
                            'expiry': expiry,
                            'net_credit': net_credit,
                            'max_profit': max_profit,
                            'max_loss': max_loss,
                            'breakeven': short_put['strike'] - net_credit,
                            'width': short_put['strike'] - long_put['strike']
                        })
        
        return spreads