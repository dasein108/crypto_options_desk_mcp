"""Covered call bot — automated weekly OTM call selling with safety rails.

Modes:
    --paper  : Log decisions, simulate fills, no real orders (default)
    --execute: Place real orders on Bybit

Usage:
    # Paper mode (default)
    python -m options_lib.strategy.covered_call_bot --asset BTC

    # Live mode
    python -m options_lib.strategy.covered_call_bot --asset BTC --execute

    # Custom parameters
    python -m options_lib.strategy.covered_call_bot --asset ETH --target-delta 0.08 --iv-rv-threshold 8
"""

import asyncio
import json
import logging
import os
import signal
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class CoveredCallConfig:
    """Bot configuration — env vars override defaults."""

    asset: str = "BTC"
    paper_mode: bool = True

    # Signal thresholds
    iv_rv_threshold: float = 10.0  # min IV-RV spread in vol points
    target_delta: float = 0.10
    min_delta: float = 0.05
    max_delta: float = 0.20
    min_dte: int = 3
    max_dte: int = 14

    # Position sizing
    qty: float = 0.0  # 0 = auto from holdings
    max_positions: int = 1  # max short calls per asset

    # Safety
    circuit_breaker_pct: float = 0.08  # skip roll if spot gaps > 8%
    max_drawdown_pct: float = 0.05  # close if cumulative loss > 5% of premium collected

    # Timing
    poll_interval_seconds: int = 3600  # check every hour
    roll_dte: int = 1  # roll when DTE <= this

    # Paths
    log_dir: str = "logs/covered-call"
    state_file: str = "current_state.json"

    @classmethod
    def from_env(cls, **overrides) -> "CoveredCallConfig":
        """Load from env vars with explicit overrides."""
        config = cls(
            asset=os.getenv("CC_ASSET", cls.asset),
            paper_mode=os.getenv("CC_PAPER_MODE", "true").lower() == "true",
            iv_rv_threshold=float(os.getenv("CC_IV_RV_THRESHOLD", cls.iv_rv_threshold)),
            target_delta=float(os.getenv("CC_TARGET_DELTA", cls.target_delta)),
            qty=float(os.getenv("CC_QTY", cls.qty)),
            poll_interval_seconds=int(
                os.getenv("CC_POLL_INTERVAL", cls.poll_interval_seconds)
            ),
            log_dir=os.getenv("CC_LOG_DIR", cls.log_dir),
        )
        for k, v in overrides.items():
            if hasattr(config, k):
                setattr(config, k, v)
        return config


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


@dataclass
class CoveredCallState:
    """Persisted bot state — survives restarts."""

    # Active position
    symbol: Optional[str] = None
    strike: Optional[float] = None
    expiry_date: Optional[str] = None
    qty: float = 0.0
    entry_price: float = 0.0  # premium collected per contract
    entry_time: Optional[str] = None
    entry_spot: float = 0.0

    # Cumulative tracking
    total_premium_collected: float = 0.0
    total_rolls: int = 0
    total_skips: int = 0
    total_called_away: int = 0

    # Circuit breaker
    last_spot_price: float = 0.0
    last_check_time: Optional[str] = None

    def has_position(self) -> bool:
        return self.symbol is not None and self.qty > 0


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------


class CoveredCallBot:
    """Automated covered call writer with weekly roll cycle.

    Lifecycle:
        1. Load state from disk (or start fresh)
        2. Each cycle:
           a. Check circuit breaker (gap detection)
           b. If no position: evaluate signal → sell call
           c. If position: check expiry → roll if needed
        3. On SIGINT/SIGTERM: persist state and exit
    """

    STRATEGY_NAME = "covered-call"

    def __init__(self, config: CoveredCallConfig):
        self.config = config
        self.state = CoveredCallState()
        self._running = False
        self._state_loaded = False
        self._state_path = Path(config.log_dir) / config.asset / config.state_file
        self._log_path = Path(config.log_dir) / config.asset
        self._setup_logging()
        self._install_signal_handlers()

    # --- Logging -----------------------------------------------------------

    def _setup_logging(self):
        self._log_path.mkdir(parents=True, exist_ok=True)
        # File handler for structured events
        self._jsonl_path = self._log_path / "events.jsonl"
        # Human-readable log
        fh = logging.FileHandler(self._log_path / "bot.log")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
        logger.setLevel(logging.INFO)

    def _log_event(self, event: str, data: dict = None):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "asset": self.config.asset,
            "paper": self.config.paper_mode,
            **(data or {}),
        }
        logger.info(f"[{event}] {json.dumps(data or {}, default=str)}")
        with open(self._jsonl_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    # --- State persistence -------------------------------------------------

    def _load_state(self):
        if self._state_path.exists():
            try:
                raw = json.loads(self._state_path.read_text())
                self.state = CoveredCallState(**raw)
                self._log_event("state_loaded", {"symbol": self.state.symbol})
            except Exception as e:
                logger.warning(f"Failed to load state: {e} — starting fresh")
                self.state = CoveredCallState()
        self._state_loaded = True

    def _persist_state(self):
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(asdict(self.state), indent=2, default=str)
        )

    # --- Signal handling ---------------------------------------------------

    def _install_signal_handlers(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} received — shutting down gracefully")
        self._running = False

    # --- Core logic --------------------------------------------------------

    async def _get_client(self):
        from bybit_api import BybitClient

        return BybitClient.from_env()

    async def _fetch_data(self):
        """Fetch chain + klines + spot for signal evaluation."""
        from bybit_api import BybitPublicClient
        from ..cli import _safe_float
        from ..flow.types import OptionsChainData, OptionType

        client = BybitPublicClient()
        raw = await client.get_options_chain_data(self.config.asset)
        spot = await client.get_spot_price(f"{self.config.asset}USDT")

        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=30 * 24)
        klines = await client.get_klines(
            f"{self.config.asset}USDT",
            "4h",
            limit=200,
            start_time=start,
            end_time=end,
        )

        # Convert raw chain to OptionsChainData (same as cli._fetch_chain)
        chain = []
        for opt in raw:
            symbol = opt.get("symbol", "")
            if not symbol:
                continue
            opt_type_str = str(opt.get("option_type", ""))
            if (
                opt_type_str in ("Call", "C", "CALL")
                or symbol.endswith("-C")
                or "-C-" in symbol
            ):
                option_type = OptionType.CALL
            elif (
                opt_type_str in ("Put", "P", "PUT")
                or symbol.endswith("-P")
                or "-P-" in symbol
            ):
                option_type = OptionType.PUT
            else:
                continue
            parts = symbol.split("-")
            expiry_date = parts[1] if len(parts) >= 2 else ""
            chain.append(
                OptionsChainData(
                    symbol=symbol,
                    underlying_symbol=self.config.asset,
                    strike=_safe_float(opt.get("strike")),
                    expiry_date=expiry_date,
                    option_type=option_type,
                    underlying_price=spot,
                    mark_price=_safe_float(
                        opt.get("mark_price") or opt.get("markPrice", 0)
                    ),
                    mark_iv=_safe_float(opt.get("mark_iv") or opt.get("markIv", 0)),
                    delta=_safe_float(opt.get("delta", 0)),
                    gamma=_safe_float(opt.get("gamma", 0)),
                    theta=_safe_float(opt.get("theta", 0)),
                    vega=_safe_float(opt.get("vega", 0)),
                    volume=_safe_float(
                        opt.get("volume_24h") or opt.get("volume24h", 0)
                    ),
                    open_interest=_safe_float(
                        opt.get("open_interest") or opt.get("openInterest", 0)
                    ),
                    bid_price=_safe_float(
                        opt.get("bid_price") or opt.get("bid1Price", 0)
                    ),
                    ask_price=_safe_float(
                        opt.get("ask_price") or opt.get("ask1Price", 0)
                    ),
                    bid_iv=_safe_float(opt.get("bid_iv") or opt.get("bidIv", 0)),
                    ask_iv=_safe_float(opt.get("ask_iv") or opt.get("askIv", 0)),
                )
            )

        return chain, spot, klines

    async def _check_circuit_breaker(self, current_spot: float) -> bool:
        """Return True if circuit breaker triggered (should skip)."""
        if self.state.last_spot_price <= 0:
            return False
        gap = (
            abs(current_spot - self.state.last_spot_price) / self.state.last_spot_price
        )
        if gap > self.config.circuit_breaker_pct:
            self._log_event(
                "circuit_breaker",
                {
                    "gap_pct": round(gap * 100, 2),
                    "threshold_pct": self.config.circuit_breaker_pct * 100,
                    "last_spot": self.state.last_spot_price,
                    "current_spot": current_spot,
                },
            )
            return True
        return False

    async def _should_roll(self) -> bool:
        """Check if current position needs rolling (near expiry)."""
        if not self.state.has_position():
            return False
        from .covered_call import CoveredCallAnalyzer

        dte = CoveredCallAnalyzer._estimate_dte(self.state.expiry_date)
        if dte is not None and dte <= self.config.roll_dte:
            self._log_event("roll_triggered", {"dte": dte, "symbol": self.state.symbol})
            return True
        return False

    async def _close_position(self, client, spot: float):
        """Close existing short call position."""
        if not self.state.has_position():
            return

        # Check if expired ITM (called away)
        if self.state.strike and spot >= self.state.strike:
            self.state.total_called_away += 1
            self._log_event(
                "called_away",
                {
                    "symbol": self.state.symbol,
                    "strike": self.state.strike,
                    "spot": spot,
                    "premium_collected": self.state.entry_price,
                },
            )
        else:
            self._log_event(
                "position_closed",
                {
                    "symbol": self.state.symbol,
                    "reason": "roll" if self.state.has_position() else "exit",
                },
            )

        if not self.config.paper_mode:
            try:
                result = await client.place_order(
                    category="option",
                    symbol=self.state.symbol,
                    side="Buy",  # buy back the short call
                    order_type="Market",
                    qty=self.state.qty,
                )
                self._log_event("close_order_placed", {"result": result})
            except Exception as e:
                self._log_event("close_order_failed", {"error": str(e)})
                return  # don't clear state if close failed

        # Clear position state
        self.state.symbol = None
        self.state.strike = None
        self.state.expiry_date = None
        self.state.qty = 0.0
        self.state.entry_price = 0.0
        self.state.entry_time = None
        self._persist_state()

    async def _open_position(self, client, signal_result, spot: float):
        """Open a new short call position based on signal."""
        strike = signal_result.strike
        if not strike:
            return

        # Determine qty
        qty = self.config.qty
        if qty <= 0:
            # Auto-size: 1 contract minimum
            qty = 0.01 if self.config.asset == "BTC" else 0.1

        self._log_event(
            "opening_position",
            {
                "symbol": strike.symbol,
                "strike": strike.strike,
                "delta": round(strike.delta, 4),
                "premium_pct": round(strike.premium_pct * 100, 3),
                "qty": qty,
                "paper": self.config.paper_mode,
            },
        )

        if not self.config.paper_mode:
            try:
                # Limit order at mid price
                result = await client.place_order(
                    category="option",
                    symbol=strike.symbol,
                    side="Sell",
                    order_type="Limit",
                    qty=qty,
                    price=strike.mid_price,
                    time_in_force="GTC",
                )
                self._log_event("sell_order_placed", {"result": result})
            except Exception as e:
                self._log_event("sell_order_failed", {"error": str(e)})
                return

        # Update state
        self.state.symbol = strike.symbol
        self.state.strike = strike.strike
        self.state.expiry_date = strike.expiry_date
        self.state.qty = qty
        self.state.entry_price = strike.mid_price
        self.state.entry_time = datetime.now(timezone.utc).isoformat()
        self.state.entry_spot = spot
        self.state.total_premium_collected += strike.mid_price * qty
        self.state.total_rolls += 1
        self._persist_state()

    async def run_cycle(self):
        """Single bot cycle: check state, evaluate, act."""
        from .covered_call import CoveredCallAnalyzer

        # Ensure state is loaded (idempotent — checks if already loaded)
        if not self._state_loaded:
            self._load_state()

        try:
            chain, spot, klines = await self._fetch_data()
        except Exception as e:
            self._log_event("fetch_error", {"error": str(e)})
            return

        if not chain or not klines:
            self._log_event("no_data", {"chain_len": len(chain) if chain else 0})
            return

        # Circuit breaker
        if await self._check_circuit_breaker(spot):
            self.state.total_skips += 1
            self.state.last_spot_price = spot
            self._persist_state()
            return

        client = await self._get_client()

        # Roll existing position if near expiry
        if await self._should_roll():
            await self._close_position(client, spot)

        # If no position, evaluate signal and open
        if not self.state.has_position():
            signal_result = CoveredCallAnalyzer.evaluate_signal(
                chain,
                spot,
                klines,
                asset=self.config.asset,
                iv_rv_threshold=self.config.iv_rv_threshold,
                target_delta=self.config.target_delta,
                delta_range=(self.config.min_delta, self.config.max_delta),
                max_dte=self.config.max_dte,
            )

            self._log_event(
                "signal_evaluated",
                {
                    "go": signal_result.go,
                    "reasons": signal_result.reasons,
                    "iv_rv_spread": round(signal_result.iv_rv_spread.spread, 2)
                    if signal_result.iv_rv_spread
                    else None,
                    "vol_regime": signal_result.vol_regime,
                    "term_structure": signal_result.term_structure,
                },
            )

            if signal_result.go and signal_result.strike:
                await self._open_position(client, signal_result, spot)
            else:
                self.state.total_skips += 1
        else:
            # Log monitoring status
            from .covered_call import CoveredCallAnalyzer

            dte = CoveredCallAnalyzer._estimate_dte(self.state.expiry_date)
            self._log_event(
                "monitoring",
                {
                    "symbol": self.state.symbol,
                    "strike": self.state.strike,
                    "dte": dte,
                    "entry_spot": self.state.entry_spot,
                    "current_spot": spot,
                    "spot_change_pct": round(
                        (spot - self.state.entry_spot) / self.state.entry_spot * 100, 2
                    )
                    if self.state.entry_spot
                    else 0,
                },
            )

        # Update tracking
        self.state.last_spot_price = spot
        self.state.last_check_time = datetime.now(timezone.utc).isoformat()
        self._persist_state()

    async def run(self):
        """Main loop — runs until signal or error."""
        self._load_state()
        self._running = True

        mode = "PAPER" if self.config.paper_mode else "LIVE"
        self._log_event(
            "bot_started",
            {
                "mode": mode,
                "asset": self.config.asset,
                "target_delta": self.config.target_delta,
                "iv_rv_threshold": self.config.iv_rv_threshold,
                "poll_interval": self.config.poll_interval_seconds,
                "has_position": self.state.has_position(),
            },
        )
        logger.info(
            f"Covered Call Bot [{mode}] — {self.config.asset} "
            f"delta={self.config.target_delta} iv_rv>{self.config.iv_rv_threshold}"
        )

        while self._running:
            await self.run_cycle()
            if self._running:
                await asyncio.sleep(self.config.poll_interval_seconds)

        self._persist_state()
        self._log_event(
            "bot_stopped",
            {
                "total_rolls": self.state.total_rolls,
                "total_skips": self.state.total_skips,
                "total_premium": self.state.total_premium_collected,
                "total_called_away": self.state.total_called_away,
            },
        )

    def status(self) -> dict:
        """Return current bot status as dict."""
        self._load_state()
        return {
            "strategy": self.STRATEGY_NAME,
            "asset": self.config.asset,
            "paper_mode": self.config.paper_mode,
            "has_position": self.state.has_position(),
            "position": {
                "symbol": self.state.symbol,
                "strike": self.state.strike,
                "expiry": self.state.expiry_date,
                "qty": self.state.qty,
                "entry_price": self.state.entry_price,
                "entry_time": self.state.entry_time,
            }
            if self.state.has_position()
            else None,
            "stats": {
                "total_premium_collected": round(self.state.total_premium_collected, 6),
                "total_rolls": self.state.total_rolls,
                "total_skips": self.state.total_skips,
                "total_called_away": self.state.total_called_away,
            },
            "last_check": self.state.last_check_time,
            "last_spot": self.state.last_spot_price,
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Covered Call Bot — automated weekly OTM call selling",
        prog="python -m options_lib.strategy.covered_call_bot",
    )
    parser.add_argument("--asset", default="BTC", help="Asset (default: BTC)")
    parser.add_argument(
        "--execute", action="store_true", help="Live mode (default: paper)"
    )
    parser.add_argument("--target-delta", type=float, default=0.10)
    parser.add_argument("--iv-rv-threshold", type=float, default=10.0)
    parser.add_argument("--max-dte", type=int, default=14)
    parser.add_argument("--qty", type=float, default=0.0, help="Position size (0=auto)")
    parser.add_argument(
        "--poll-interval", type=int, default=3600, help="Check interval in seconds"
    )
    parser.add_argument("--status", action="store_true", help="Show status and exit")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = CoveredCallConfig.from_env(
        asset=args.asset,
        paper_mode=not args.execute,
        target_delta=args.target_delta,
        iv_rv_threshold=args.iv_rv_threshold,
        max_dte=args.max_dte,
        qty=args.qty,
        poll_interval_seconds=args.poll_interval,
    )

    bot = CoveredCallBot(config)

    if args.status:
        print(json.dumps(bot.status(), indent=2, default=str))
        return

    from dotenv import load_dotenv

    load_dotenv()

    if args.once:
        asyncio.run(bot.run_cycle())
        print(json.dumps(bot.status(), indent=2, default=str))
    else:
        asyncio.run(bot.run())


if __name__ == "__main__":
    main()
