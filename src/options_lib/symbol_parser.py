"""Shared Bybit option symbol parser."""

import re
from datetime import datetime
from typing import Optional, Dict

MONTH_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

_BYBIT_PATTERN = re.compile(r'^(\w+)-(\d{1,2})([A-Z]{3})(\d{2})-(\d+)-([CP])(?:-USDT)?$')


def parse_bybit_option_symbol(symbol: str) -> Optional[Dict]:
    """Parse Bybit option symbol format: BTC-30DEC24-70000-C

    Returns dict with keys: asset, expiry (str), expiry_date (datetime),
    strike (float), option_type ('C'/'P'), option_type_long ('call'/'put').
    Returns None if parsing fails.
    """
    try:
        match = _BYBIT_PATTERN.match(symbol)
        if not match:
            return None

        asset, day, month_str, year, strike, option_type = match.groups()

        month = MONTH_MAP.get(month_str)
        if not month:
            return None

        full_year = 2000 + int(year)
        expiry_date = datetime(full_year, month, int(day))

        return {
            'asset': asset,
            'underlying': asset,
            'expiry': f"{full_year}-{month:02d}-{int(day):02d}",
            'expiry_date': expiry_date,
            'strike': float(strike),
            'option_type': option_type,
            'option_type_long': 'call' if option_type == 'C' else 'put',
        }

    except Exception:
        return None
