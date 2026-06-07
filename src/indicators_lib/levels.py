"""Unified support/resistance levels — combines volume profile, swing detection, and MAs.

Orchestrates existing tools (MarketAnalysis, TechnicalIndicators) into a single
KeyLevels dataclass consumed by market-brief, strategies, and CLI.

Usage:
    from indicators_lib.levels import compute_levels
    levels = compute_levels(klines, "BTCUSDT")
    print(levels.poc, levels.nearest_support, levels.resistance_distance_pct)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from .market import MarketAnalysis
from .technical import TechnicalIndicators
from .types import Kline


@dataclass
class KeyLevels:
    """Unified S/R levels from volume, swing, and technical analysis."""

    symbol: str
    price: float

    # Volume-based (strongest — real money committed at these prices)
    poc: float = 0.0             # Point of Control (highest volume node)
    vah: float = 0.0             # Value Area High (70% volume top)
    val: float = 0.0             # Value Area Low (70% volume bottom)

    # Swing-based (pattern recognition from price pivots)
    support: list[float] = field(default_factory=list)     # nearest swing lows (up to 3)
    resistance: list[float] = field(default_factory=list)  # nearest swing highs (up to 3)

    # Technical (dynamic, moves with price)
    sma_20: float = 0.0
    sma_50: float = 0.0
    ema_20: float = 0.0

    # Derived — distances from nearest levels
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    support_distance_pct: float = 0.0    # positive = price above support
    resistance_distance_pct: float = 0.0  # negative = price below resistance

    def to_dict(self) -> dict:
        return {
            "poc": _r(self.poc),
            "vah": _r(self.vah),
            "val": _r(self.val),
            "support": [_r(s) for s in self.support[:3]],
            "resistance": [_r(r) for r in self.resistance[:3]],
            "nearest_support": _r(self.nearest_support),
            "nearest_resistance": _r(self.nearest_resistance),
            "support_distance_pct": _r(self.support_distance_pct, 2),
            "resistance_distance_pct": _r(self.resistance_distance_pct, 2),
            "sma_20": _r(self.sma_20),
            "sma_50": _r(self.sma_50),
            "ema_20": _r(self.ema_20),
        }

    def to_compact_dict(self) -> dict:
        """Minimal version for market-brief per-symbol output."""
        return {
            "poc": _r(self.poc),
            "vah": _r(self.vah),
            "val": _r(self.val),
            "nearest_support": _r(self.nearest_support),
            "nearest_resistance": _r(self.nearest_resistance),
            "support_distance_pct": _r(self.support_distance_pct, 2),
            "resistance_distance_pct": _r(self.resistance_distance_pct, 2),
        }


def _r(v: float, n: int = 6) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(v, n)


def compute_levels(klines: List[Kline], symbol: str = "") -> KeyLevels:
    """Compute unified S/R levels from klines.

    Combines:
    1. Volume Profile → POC, VAH, VAL (strongest levels — real money)
    2. Market Structure → swing highs/lows as S/R
    3. Technical → SMA20/50, EMA20 as dynamic levels
    """
    if not klines or len(klines) < 20:
        price = float(klines[-1].close) if klines else 0.0
        return KeyLevels(symbol=symbol, price=price)

    klines_sorted = sorted(klines, key=lambda k: k.timestamp)
    price = float(klines_sorted[-1].close)
    levels = KeyLevels(symbol=symbol, price=price)

    # 1. Volume Profile
    try:
        vp = MarketAnalysis.get_volume_profile(klines, bins=25)
        levels.poc = vp.poc
        levels.vah = vp.value_area_high
        levels.val = vp.value_area_low
    except Exception:
        pass

    # 2. Swing-based S/R
    try:
        ms = MarketAnalysis.detect_market_structure(klines, swing_strength=3)
        # Filter to levels near current price (within 20%)
        nearby_support = sorted(
            [s for s in ms.support_levels if 0.80 * price <= s <= price],
            reverse=True,
        )[:3]
        nearby_resistance = sorted(
            [r for r in ms.resistance_levels if price <= r <= 1.20 * price],
        )[:3]
        levels.support = nearby_support
        levels.resistance = nearby_resistance
    except Exception:
        pass

    # 3. Technical MAs
    try:
        ta = TechnicalIndicators.get_comprehensive_analysis(klines, symbol)
        levels.sma_20 = ta.sma_20 if not math.isnan(ta.sma_20) else 0.0
        levels.sma_50 = ta.sma_50 if not math.isnan(ta.sma_50) else 0.0
        levels.ema_20 = ta.ema_20 if not math.isnan(ta.ema_20) else 0.0
    except Exception:
        pass

    # 4. Compute nearest support/resistance
    all_support = []
    if levels.poc > 0 and levels.poc < price:
        all_support.append(levels.poc)
    if levels.vah > 0 and levels.vah < price:
        all_support.append(levels.vah)
    if levels.val > 0 and levels.val < price:
        all_support.append(levels.val)
    all_support.extend(levels.support)
    # MAs as support if below price
    for ma in [levels.sma_20, levels.sma_50, levels.ema_20]:
        if ma > 0 and ma < price:
            all_support.append(ma)

    all_resistance = []
    if levels.poc > 0 and levels.poc > price:
        all_resistance.append(levels.poc)
    if levels.vah > 0 and levels.vah > price:
        all_resistance.append(levels.vah)
    all_resistance.extend(levels.resistance)
    for ma in [levels.sma_20, levels.sma_50, levels.ema_20]:
        if ma > 0 and ma > price:
            all_resistance.append(ma)

    if all_support:
        levels.nearest_support = max(all_support)  # closest below
        levels.support_distance_pct = (
            (price - levels.nearest_support) / levels.nearest_support * 100
            if levels.nearest_support > 0
            else 0.0
        )
    if all_resistance:
        levels.nearest_resistance = min(all_resistance)  # closest above
        levels.resistance_distance_pct = (
            (price - levels.nearest_resistance) / levels.nearest_resistance * 100
            if levels.nearest_resistance > 0
            else 0.0
        )

    return levels
