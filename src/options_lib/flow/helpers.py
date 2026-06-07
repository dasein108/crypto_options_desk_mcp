"""Shared helpers for flow analysis modules."""

from typing import List, Dict
from .types import OptionsChainData, OptionType


def group_by_strike(options_data: List[OptionsChainData]) -> Dict[float, Dict[str, List[OptionsChainData]]]:
    """Group options by strike into calls and puts.

    Returns:
        {strike: {'calls': [...], 'puts': [...]}}
    """
    strikes: Dict[float, Dict[str, List[OptionsChainData]]] = {}
    for option in options_data:
        strike = option.strike
        if strike not in strikes:
            strikes[strike] = {'calls': [], 'puts': []}
        if option.option_type == OptionType.CALL or (hasattr(option.option_type, 'value') and option.option_type.value == "C"):
            strikes[strike]['calls'].append(option)
        else:
            strikes[strike]['puts'].append(option)
    return strikes
