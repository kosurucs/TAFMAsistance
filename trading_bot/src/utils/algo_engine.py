"""
algo_engine.py – Algo Engine orchestrator.

Pipeline per cycle (every N minutes or on demand):
  1.  Fetch live OHLCV + indicators for each symbol in watchlist
  2.  Run scenario engine
  3.  Evaluate all algo strategies → signals
  4.  For each signal: run pre-execution checklist
  5.  Store signals in ring buffer (last 200)
  6.  Return cycle report

Execution note: This engine LOGS signals only. Actual order placement is
disabled system-wide (HTTP 403). The checklist gate shows what WOULD happen.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dtime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from loguru import logger

from src.utils.algo_strategies import STRATEGY_REGISTRY, AlgoSignal, evaluate_all

_IST = ZoneInfo("Asia/Kolkata")
_MAX_SIGNALS = 200       # ring-buffer size
_DEFAULT_INTERVAL_SEC = int(os.environ.get("ALGO_INTERVAL_SEC", "120"))  # 2 min


# ─── Pre-execution checklist ──────────────────────────────────────────────────

def _market_open_ist() -> bool:
    now = datetime.now(_IST)
    if now.weekday() >= 5:          # Sat/Sun
        return False
    t = now.time()
    return dtime(9, 15) <= t <= dtime(15, 30)


def run_checklist(signal: AlgoSignal, risk_mgr: Any | None) -> dict[str, bool]:
    """
    Return a dict of {check_name: passed}.
    All checks must pass for the signal to be executable.
    """
    checks: dict[str, bool] = {}

    # 1. Market hours
    checks["market_hours"] = _market_open_ist()

    # 2. Kill switch
    if risk_mgr is not None:
        checks["kill_switch_off"] = not risk_mgr.is_kill_switch_active()
    else:
        checks["kill_switch_off"] = True   # can't verify without risk_mgr

    # 3. R:R ≥ 2.0
    checks["rr_ratio_ok"] = signal.rr_ratio >= 2.0

    # 4. Scenario confidence gate
    checks["scenario_confidence"] = signal.scenario_confidence >= 60

    # 5. Daily loss within limit
    if risk_mgr is not None:
        checks["daily_loss_ok"] = risk_mgr.check_daily_loss(0.0)
    else:
        checks["daily_loss_ok"] = True

    # 6. Entry price > 0 (sanity)
    checks["valid_price"] = signal.entry_price > 0

    # 7. Order placement disabled (always shows correctly)
    checks["execution_note"] = False   # analysis-only — never True

    return checks


def _checklist_pass(checklist: dict[str, bool]) -> bool:
    """All items except execution_note must be True."""
    return all(v for k, v in checklist.items() if k != "execution_note")


# ─── Engine state (module-level singleton) ────────────────────────────────────

@dataclass
class EngineState:
    running: bool = False
    cycle_count: int = 0
    last_run_ist: str = ""
    last_error: str = ""
    interval_sec: int = _DEFAULT_INTERVAL_SEC
    watchlist: list[str] = field(default_factory=list)
    signals: list[dict] = field(default_factory=list)   # ring buffer (newest first)
    _task: Any = field(default=None, repr=False)

_state = EngineState()


def get_state() -> EngineState:
    return _state


# ─── Single cycle ─────────────────────────────────────────────────────────────

async def run_cycle(
    symbols: list[str],
    fetcher: Any,               # KiteDataFetcher / InstrumentsCache
    pipeline: Any,              # DataPipeline
    risk_mgr: Any | None,
    exchange: str = "NSE",
) -> list[dict]:
    """Run one full pipeline cycle. Returns list of signal dicts."""
    from src.utils.technical_analysis import compute_indicators
    from src.utils.scenario_engine import ScenarioEngine

    _scenario_engine = ScenarioEngine()
    cycle_signals: list[dict] = []

    for symbol in symbols:
        try:
            # 1. Resolve instrument token + fetch OHLCV
            token = await asyncio.to_thread(
                fetcher.lookup_instrument_token, exchange, symbol
            )
            df = await asyncio.to_thread(
                pipeline.get_ohlcv_df,
                token, symbol, "day", 60
            )
            if df is None or len(df) < 20:
                logger.warning(f"AlgoEngine: not enough data for {symbol}")
                continue

            # 2. Indicators
            indicators = compute_indicators(df)

            # 3. Scenario
            scenario_result = _scenario_engine.score_scenarios(indicators)
            dominant = scenario_result.dominant.name
            sc_conf  = scenario_result.confidence

            # 4. Evaluate strategies
            signals = evaluate_all(symbol, indicators, dominant, sc_conf)

            # 5. Checklist per signal
            for sig in signals:
                checklist = run_checklist(sig, risk_mgr)
                sig.checklist = checklist
                sig.checklist_pass = _checklist_pass(checklist)

                d = asdict(sig)
                cycle_signals.append(d)
                logger.info(
                    f"AlgoEngine | {symbol} | {sig.strategy} | {sig.action} "
                    f"| conf={sig.confidence:.0f}% | checklist={'PASS' if sig.checklist_pass else 'FAIL'}"
                )

        except Exception as exc:
            logger.error(f"AlgoEngine cycle error for {symbol}: {exc}")

    return cycle_signals


# ─── Background scheduler ─────────────────────────────────────────────────────

async def _scheduler_loop(fetcher: Any, pipeline: Any, risk_mgr: Any | None, exchange: str = "NSE") -> None:
    logger.info(f"AlgoEngine scheduler started (interval={_state.interval_sec}s)")
    while _state.running:
        try:
            signals = await run_cycle(_state.watchlist, fetcher, pipeline, risk_mgr, exchange)
            _state.cycle_count += 1
            _state.last_run_ist = datetime.now(_IST).isoformat()
            # Prepend + keep ring buffer
            _state.signals = (signals + _state.signals)[:_MAX_SIGNALS]
        except Exception as exc:
            _state.last_error = str(exc)
            logger.error(f"AlgoEngine scheduler error: {exc}")

        await asyncio.sleep(_state.interval_sec)

    logger.info("AlgoEngine scheduler stopped.")


def start_engine(
    watchlist: list[str],
    fetcher: Any,
    pipeline: Any,
    risk_mgr: Any | None,
    interval_sec: int | None = None,
    exchange: str = "NSE",
) -> None:
    if _state.running:
        logger.warning("AlgoEngine already running.")
        return
    _state.running = True
    _state.watchlist = watchlist
    if interval_sec:
        _state.interval_sec = interval_sec

    loop = asyncio.get_event_loop()
    task = loop.create_task(_scheduler_loop(fetcher, pipeline, risk_mgr, exchange))
    _state._task = task


def stop_engine() -> None:
    _state.running = False
    if _state._task and not _state._task.done():
        _state._task.cancel()
    _state._task = None
    logger.info("AlgoEngine stopped.")


def clear_signals() -> None:
    _state.signals.clear()
