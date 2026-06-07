"""Shared rolling-window risk metrics.

This module intentionally stays dependency-light so runtime services can
reuse the same drawdown logic for canonical risk-control signals.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Deque, Iterable, Mapping, Sequence


WINDOW_24H = timedelta(hours=24)
WINDOW_7D = timedelta(days=7)


@dataclass(frozen=True)
class EquitySample:
    """Timestamped equity sample used for rolling drawdown calculations."""

    ts: datetime
    equity_usd: float


def _to_utc_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _normalize_sample(item: EquitySample | Mapping[str, object]) -> EquitySample | None:
    if isinstance(item, EquitySample):
        return item

    ts_raw = item.get("ts") or item.get("timestamp")
    equity_raw = item.get("equity_usd")
    if ts_raw is None or equity_raw is None:
        return None

    try:
        ts = _to_utc_datetime(str(ts_raw))
        equity = float(equity_raw)
    except (TypeError, ValueError):
        return None
    return EquitySample(ts=ts, equity_usd=equity)


def rolling_drawdown_pct(
    samples: Sequence[EquitySample],
    *,
    window: timedelta,
    now: datetime | None = None,
) -> float:
    """Return current drawdown from the rolling-window peak.

    Drawdown is `(rolling_peak - current_equity) / rolling_peak`.
    Returns `0.0` when no valid samples exist or peak equity is non-positive.
    """

    if not samples:
        return 0.0

    current_ts = _to_utc_datetime(now) if now else samples[-1].ts
    cutoff = current_ts - window

    current_equity: float | None = None
    in_window_equities: list[float] = []
    for sample in samples:
        if sample.ts > current_ts:
            continue
        current_equity = sample.equity_usd
        if sample.ts >= cutoff:
            in_window_equities.append(sample.equity_usd)

    if current_equity is None:
        return 0.0
    if not in_window_equities:
        in_window_equities = [current_equity]

    peak_equity = max(in_window_equities)
    if peak_equity <= 0:
        return 0.0

    return max(0.0, (peak_equity - current_equity) / peak_equity)


def compute_window_drawdowns(
    points: Iterable[EquitySample | Mapping[str, object]],
    *,
    now: datetime | None = None,
) -> dict[str, float]:
    """Compute canonical 24h and 7d rolling drawdown percentages."""

    normalized = [sample for sample in (_normalize_sample(p) for p in points) if sample]
    if not normalized:
        return {
            "rolling_drawdown_pct_24h": 0.0,
            "rolling_drawdown_pct_7d": 0.0,
        }

    normalized.sort(key=lambda sample: sample.ts)
    return {
        "rolling_drawdown_pct_24h": rolling_drawdown_pct(
            normalized, window=WINDOW_24H, now=now
        ),
        "rolling_drawdown_pct_7d": rolling_drawdown_pct(
            normalized, window=WINDOW_7D, now=now
        ),
    }


class RollingDrawdownTracker:
    """In-memory tracker for runtime services emitting risk-control signals."""

    def __init__(self, max_window: timedelta = WINDOW_7D):
        self._max_window = max_window
        self._samples: Deque[EquitySample] = deque()

    def update(self, ts: datetime | str, equity_usd: float) -> dict[str, float]:
        sample = EquitySample(ts=_to_utc_datetime(ts), equity_usd=float(equity_usd))
        self._samples.append(sample)
        self._prune(sample.ts)
        return compute_window_drawdowns(tuple(self._samples), now=sample.ts)

    def _prune(self, current_ts: datetime) -> None:
        cutoff = current_ts - self._max_window
        while self._samples and self._samples[0].ts < cutoff:
            self._samples.popleft()
