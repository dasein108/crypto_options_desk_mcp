"""Portfolio-level Greeks for option positions."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class OptionPositionGreeks:
    """Greeks for a single option position (weighted by size and side)."""
    symbol: str
    asset: str
    side: str
    size: float
    strike: float
    option_type: str
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float
    mark_price: float
    underlying_price: float


@dataclass
class OptionsPortfolioGreeks:
    """Aggregated Greeks across option positions."""
    positions: List[OptionPositionGreeks]
    net_delta: Dict[str, float] = field(default_factory=dict)
    net_gamma: Dict[str, float] = field(default_factory=dict)
    net_theta: Dict[str, float] = field(default_factory=dict)
    net_vega: Dict[str, float] = field(default_factory=dict)


def _parse_asset(symbol: str) -> str:
    """Extract base asset from option symbol like 'ETH-24APR26-2200-C-USDT'."""
    return symbol.split("-")[0] if "-" in symbol else symbol


def _parse_option_type(symbol: str) -> str:
    """Extract C or P from symbol."""
    parts = symbol.split("-")
    for part in reversed(parts):
        if part in ("C", "P"):
            return part
    return "C"


def compute_option_greeks(
    position: Dict,
    side: str = None,
    size: float = None,
) -> OptionPositionGreeks:
    """Compute weighted Greeks for a single option position.

    Args:
        position: Dict with keys: symbol, delta, gamma, theta, vega,
                  mark_iv (or iv), mark_price, underlying_price, strike
                  Optionally: side, size (overridden by params if provided)
        side: "Buy" or "Sell" (overrides position dict)
        size: Position size (overrides position dict)
    """
    side = side or position.get("side", "Buy")
    size = size if size is not None else position.get("size", 1.0)
    mult = 1.0 if side == "Buy" else -1.0

    symbol = position.get("symbol", "")
    delta = float(position.get("delta", 0)) * size * mult
    gamma = float(position.get("gamma", 0)) * size * mult
    theta = float(position.get("theta", 0)) * size * mult
    vega = float(position.get("vega", 0)) * size * mult
    iv = float(position.get("mark_iv", position.get("iv", 0)))

    return OptionPositionGreeks(
        symbol=symbol,
        asset=_parse_asset(symbol),
        side=side,
        size=size,
        strike=float(position.get("strike", 0)),
        option_type=position.get("option_type", _parse_option_type(symbol)),
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        iv=iv,
        mark_price=float(position.get("mark_price", 0)),
        underlying_price=float(position.get("underlying_price", 0)),
    )


def compute_options_portfolio_greeks(
    positions: List[Dict],
) -> OptionsPortfolioGreeks:
    """Aggregate Greeks across multiple option positions.

    Args:
        positions: List of dicts. Each must have: symbol, side, size,
                   delta, gamma, theta, vega, mark_iv/iv,
                   mark_price, underlying_price, strike
    """
    greeks_list: List[OptionPositionGreeks] = []
    net_delta: Dict[str, float] = {}
    net_gamma: Dict[str, float] = {}
    net_theta: Dict[str, float] = {}
    net_vega: Dict[str, float] = {}

    for pos in positions:
        g = compute_option_greeks(pos)
        greeks_list.append(g)

        asset = g.asset
        net_delta[asset] = net_delta.get(asset, 0.0) + g.delta
        net_gamma[asset] = net_gamma.get(asset, 0.0) + g.gamma
        net_theta[asset] = net_theta.get(asset, 0.0) + g.theta
        net_vega[asset] = net_vega.get(asset, 0.0) + g.vega

    return OptionsPortfolioGreeks(
        positions=greeks_list,
        net_delta=net_delta,
        net_gamma=net_gamma,
        net_theta=net_theta,
        net_vega=net_vega,
    )
