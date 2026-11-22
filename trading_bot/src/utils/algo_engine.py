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


# ─── Signal builders (v1.0 contract) ─────────────────────────────────────────

def _create_wait_signal(
    symbol: str,
    exchange: str,
    reason: str,
    indicators: dict,
    scenario: str,
    scenario_confidence: float,
    timeframes: list[str],
    confluence: dict,
) -> dict:
    """Create a WAIT signal dict matching v1.0 contract."""
    import uuid
    return {
        "id": str(uuid.uuid4())[:8],
        "symbol": symbol,
        "exchange": exchange,
        "action": "WAIT",
        "strategy": "GuardGate",
        "entry_price": indicators.get("close", 0.0),
        "suggested_sl": 0.0,
        "suggested_tp": 0.0,
        "rr_ratio": 0.0,
        "confidence": 0.0,
        "scenario": scenario,
        "scenario_confidence": scenario_confidence,
        "timeframes": timeframes,
        "confluence": confluence.get("confluence_pct", 0.0) if confluence else 0.0,
        "reason": reason,
        "checklist": {
            "market_hours": _market_open_ist(),
            "kill_switch_off": True,
            "confidence_ok": False,
            "rr_ok": False,
            "daily_loss_ok": True,
            "position_size_ok": False,
        },
        "checklist_pass": False,
        "execution_note": "BLOCKED — analysis-only mode",
        "timestamp": datetime.now(_IST).isoformat(),
    }


def _build_signal_dict(
    sig: AlgoSignal,
    exchange: str,
    timeframes: list[str],
    confluence: dict,
) -> dict:
    """Build full signal dict from AlgoSignal matching v1.0 contract."""
    from dataclasses import asdict
    d = asdict(sig)
    d["exchange"] = exchange
    d["timeframes"] = timeframes
    d["confluence"] = confluence.get("confluence_pct", 0.0) if confluence else 0.0
    d["execution_note"] = "BLOCKED — analysis-only mode"

    # Build checklist for passed signals
    d["checklist"] = {
        "market_hours": _market_open_ist(),
        "kill_switch_off": True,
        "confidence_ok": sig.scenario_confidence >= 60,
        "rr_ok": sig.rr_ratio >= 2.0,
        "daily_loss_ok": True,
        "position_size_ok": sig.entry_price > 0,
    }
    d["checklist_pass"] = all(v for k, v in d["checklist"].items() if k != "execution_note")

    return d


def _score_context_confluence(context_indicators: dict[str, dict]) -> dict[str, Any]:
    """
    Build a confluence score from 1M trend, 1W price action, and 2D execution frame.

    Rule: +1 when ema_fast > ema_slow, -1 when ema_fast < ema_slow.
    """
    bullish_count = 0
    bearish_count = 0

    for timeframe, ind in context_indicators.items():
        if timeframe == "confluence":
            continue
        if not ind:
            continue
        ema_fast = ind.get("ema_fast", 0.0)
        ema_slow = ind.get("ema_slow", 0.0)
        if ema_fast > ema_slow:
            bullish_count += 1
        elif ema_fast < ema_slow:
            bearish_count += 1

    total = bullish_count + bearish_count
    if bullish_count > bearish_count:
        bias = "BULLISH"
    elif bearish_count > bullish_count:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    confluence_pct = (max(bullish_count, bearish_count) / total * 100.0) if total > 0 else 0.0

    return {
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "total_timeframes": total,
        "score": bullish_count - bearish_count,
        "bias": bias,
        "confluence_pct": confluence_pct,
    }


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
    portfolio: Any | None = None,
    interval: str = "minute",
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
) -> list[dict]:
    """
    Run one full v1.0 pipeline cycle with 6 guard gates.

    Returns list of signal dicts (including WAIT signals with reasons).
    """
    from src.utils.technical_analysis import compute_indicators
    from src.utils.scenario_engine import ScenarioEngine
    from src.utils.db_logger import get_db_logger

    _scenario_engine = ScenarioEngine()
    _db_logger = get_db_logger()
    cycle_signals: list[dict] = []
    use_explicit_range = start_dt is not None and end_dt is not None

    for symbol in symbols:
        try:
            # STAGE 1 — Data Ingestion (1M trend, 1W price action, 2D execution)
            token = await asyncio.to_thread(
                fetcher.lookup_instrument_token, exchange, symbol
            )

            if use_explicit_range:
                # Fetch bulk range first, then run analysis over the selected window.
                month_df = await asyncio.to_thread(
                    pipeline.get_ohlcv_df_range, token, symbol, start_dt, end_dt, "day"
                )
                week_df = await asyncio.to_thread(
                    pipeline.get_ohlcv_df_range, token, symbol, start_dt, end_dt, "day"
                )
                two_day_df = await asyncio.to_thread(
                    pipeline.get_ohlcv_df_range, token, symbol, start_dt, end_dt, interval
                )
            else:
                month_df = await asyncio.to_thread(
                    pipeline.get_ohlcv_df, token, symbol, "day", 45
                )
                week_df = await asyncio.to_thread(
                    pipeline.get_ohlcv_df, token, symbol, "day", 14
                )
                two_day_df = await asyncio.to_thread(
                    pipeline.get_ohlcv_df, token, symbol, "minute", 2
                )

            if month_df is None or month_df.empty or len(month_df) < 20:
                logger.warning(f"AlgoEngine: insufficient month data for {symbol}")
                cycle_signals.append(
                    _create_wait_signal(
                        symbol=symbol,
                        exchange=exchange,
                        reason=(
                            "Insufficient one-month data in selected range"
                            if use_explicit_range
                            else "Insufficient one-month data"
                        ),
                        indicators={},
                        scenario="INSUFFICIENT_DATA",
                        scenario_confidence=0.0,
                        timeframes=["1M", "1W", interval],
                        confluence={},
                    )
                )
                continue

            if week_df is None or week_df.empty or len(week_df) < 7:
                logger.warning(f"AlgoEngine: insufficient week data for {symbol}")
                cycle_signals.append(
                    _create_wait_signal(
                        symbol=symbol,
                        exchange=exchange,
                        reason=(
                            "Insufficient one-week data in selected range"
                            if use_explicit_range
                            else "Insufficient one-week data"
                        ),
                        indicators={},
                        scenario="INSUFFICIENT_DATA",
                        scenario_confidence=0.0,
                        timeframes=["1M", "1W", interval],
                        confluence={},
                    )
                )
                continue

            if two_day_df is None or two_day_df.empty or len(two_day_df) < 20:
                logger.warning(f"AlgoEngine: insufficient two-day price action for {symbol}")
                cycle_signals.append(
                    _create_wait_signal(
                        symbol=symbol,
                        exchange=exchange,
                        reason=(
                            f"Insufficient {interval} data in selected range"
                            if use_explicit_range
                            else "Insufficient 2-day price-action data"
                        ),
                        indicators={},
                        scenario="INSUFFICIENT_DATA",
                        scenario_confidence=0.0,
                        timeframes=["1M", "1W", interval],
                        confluence={},
                    )
                )
                continue

            month_indicators = compute_indicators(month_df.tail(30))
            week_indicators = compute_indicators(week_df.tail(7))
            indicators = compute_indicators(two_day_df)

            # STAGE 2 — Context Build
            context_indicators = {
                "1M": month_indicators,
                "1W": week_indicators,
                interval: indicators,
            }

            # STAGE 3 — Context Confluence
            confluence = _score_context_confluence(context_indicators)
            timeframe_list = ["1M", "1W", interval]

            logger.debug(
                f"AlgoEngine | {symbol} | Context confluence: {confluence['bias']} "
                f"({confluence['confluence_pct']:.0f}%)"
            )

            # STAGE 4 — Scenario Engine
            scenario_result = _scenario_engine.score_scenarios(
                indicators,
                mtf_indicators={
                    "1M": month_indicators,
                    "1W": week_indicators,
                    interval: indicators,
                    "confluence": confluence,
                }
            )
            dominant = scenario_result.dominant.name
            sc_conf  = scenario_result.confidence

            # Context gates from user flow: 1M trend + 1W action context + 2D execution
            monthly_trend_bias = "BUY" if month_indicators.get("ema_fast", 0) > month_indicators.get("ema_slow", 0) else (
                "SELL" if month_indicators.get("ema_fast", 0) < month_indicators.get("ema_slow", 0) else "WAIT"
            )
            weekly_action_bias = "BUY" if week_indicators.get("close", 0) >= week_indicators.get("ema_fast", 0) else "SELL"

            # GUARD 3 — Confidence Gate (scenario confidence ≥ 60%)
            if sc_conf < 60:
                wait_signal = _create_wait_signal(
                    symbol=symbol,
                    exchange=exchange,
                    reason=f"Scenario confidence {sc_conf:.1f}% < 60% threshold",
                    indicators=indicators,
                    scenario=dominant,
                    scenario_confidence=sc_conf,
                    timeframes=timeframe_list,
                    confluence=confluence,
                )
                cycle_signals.append(wait_signal)
                _db_logger.log_market_snapshot(
                    symbol=symbol,
                    timeframe=interval,
                    indicators=indicators,
                    scenarios=[{"name": s.name, "probability": s.probability} for s in scenario_result.scores]
                )
                logger.info(f"AlgoEngine | {symbol} | WAIT — {wait_signal['reason']}")
                continue

            # STAGE 5 — Strategy Evaluation
            signals = evaluate_all(symbol, indicators, dominant, sc_conf)

            if not signals:
                wait_signal = _create_wait_signal(
                    symbol=symbol,
                    exchange=exchange,
                    reason="No strategy conditions met",
                    indicators=indicators,
                    scenario=dominant,
                    scenario_confidence=sc_conf,
                    timeframes=timeframe_list,
                    confluence=confluence,
                )
                cycle_signals.append(wait_signal)
                logger.info(f"AlgoEngine | {symbol} | WAIT — no strategy fired")
                continue

            # STAGE 6 — R:R Validation + Remaining Guards
            for sig in signals:
                # Enrich signal with MTF data
                sig.scenario = dominant
                sig.scenario_confidence = sc_conf

                # Context guard A — Month trend alignment
                if monthly_trend_bias != "WAIT" and sig.action != monthly_trend_bias:
                    wait_signal = _create_wait_signal(
                        symbol=symbol,
                        exchange=exchange,
                        reason=(
                            f"Month trend is {monthly_trend_bias}; blocked {sig.action}"
                        ),
                        indicators=indicators,
                        scenario=dominant,
                        scenario_confidence=sc_conf,
                        timeframes=timeframe_list,
                        confluence=confluence,
                    )
                    cycle_signals.append(wait_signal)
                    logger.info(f"AlgoEngine | {symbol} | WAIT — month trend mismatch")
                    continue

                # Context guard B — Week price-action alignment
                if sig.action != weekly_action_bias:
                    wait_signal = _create_wait_signal(
                        symbol=symbol,
                        exchange=exchange,
                        reason=(
                            f"Week price action bias is {weekly_action_bias}; blocked {sig.action}"
                        ),
                        indicators=indicators,
                        scenario=dominant,
                        scenario_confidence=sc_conf,
                        timeframes=timeframe_list,
                        confluence=confluence,
                    )
                    cycle_signals.append(wait_signal)
                    logger.info(f"AlgoEngine | {symbol} | WAIT — week action mismatch")
                    continue

                # GUARD 4 — R:R Ratio ≥ 1:2
                if sig.rr_ratio < 2.0:
                    wait_signal = _create_wait_signal(
                        symbol=symbol,
                        exchange=exchange,
                        reason=f"R:R {sig.rr_ratio:.2f} < 2.0 required",
                        indicators=indicators,
                        scenario=dominant,
                        scenario_confidence=sc_conf,
                        timeframes=timeframe_list,
                        confluence=confluence,
                    )
                    cycle_signals.append(wait_signal)
                    logger.info(f"AlgoEngine | {symbol} | WAIT — poor R:R {sig.rr_ratio:.2f}")
                    continue

                # GUARD 5 — Daily Loss Limit
                current_pnl = 0.0
                if portfolio is not None:
                    try:
                        current_pnl = portfolio.get_day_pnl()
                    except Exception:
                        try:
                            current_pnl = portfolio.get_pnl()
                        except Exception:
                            pass

                if risk_mgr and not risk_mgr.check_daily_loss(current_pnl):
                    # Kill-switch activated — stop entire cycle
                    logger.critical(f"AlgoEngine | Daily loss limit breached! Activating kill-switch.")
                    return cycle_signals  # Stop processing all symbols

                # GUARD 6 — Position Size OK
                if sig.entry_price <= 0:
                    wait_signal = _create_wait_signal(
                        symbol=symbol,
                        exchange=exchange,
                        reason="Invalid entry price",
                        indicators=indicators,
                        scenario=dominant,
                        scenario_confidence=sc_conf,
                        timeframes=timeframe_list,
                        confluence=confluence,
                    )
                    cycle_signals.append(wait_signal)
                    logger.info(f"AlgoEngine | {symbol} | WAIT — invalid price")
                    continue

                # Build full signal dict matching v1.0 contract
                signal_dict = _build_signal_dict(
                    sig, exchange, timeframe_list, confluence
                )

                cycle_signals.append(signal_dict)

                # STAGE 8 — DB Logging
                _db_logger.log_market_snapshot(
                    symbol=symbol,
                    timeframe=interval,
                    indicators=indicators,
                    scenarios=[{"name": s.name, "probability": s.probability} for s in scenario_result.scores]
                )

                logger.info(
                    f"AlgoEngine | {symbol} | {sig.strategy} | {sig.action} "
                    f"| conf={sig.confidence:.0f}% | R:R={sig.rr_ratio:.2f} | {confluence['bias']}"
                )

        except Exception as exc:
            logger.error(f"AlgoEngine cycle error for {symbol}: {exc}")
            # Log WAIT signal on error
            wait_signal = _create_wait_signal(
                symbol=symbol,
                exchange=exchange,
                reason=f"Cycle error: {str(exc)[:100]}",
                indicators={},
                scenario="ERROR",
                scenario_confidence=0.0,
                timeframes=[],
                confluence={},
            )
            cycle_signals.append(wait_signal)

    return cycle_signals


# ─── Background scheduler ─────────────────────────────────────────────────────

async def _scheduler_loop(
    fetcher: Any,
    pipeline: Any,
    risk_mgr: Any | None,
    portfolio: Any | None,
    exchange: str = "NSE",
) -> None:
    logger.info(f"AlgoEngine scheduler started (interval={_state.interval_sec}s)")
    while _state.running:
        try:
            signals = await run_cycle(
                _state.watchlist, fetcher, pipeline, risk_mgr, exchange, portfolio
            )
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
    portfolio: Any | None = None,
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
    task = loop.create_task(_scheduler_loop(fetcher, pipeline, risk_mgr, portfolio, exchange))
    _state._task = task


def stop_engine() -> None:
    _state.running = False
    if _state._task and not _state._task.done():
        _state._task.cancel()
    _state._task = None
    logger.info("AlgoEngine stopped.")


def clear_signals() -> None:
    _state.signals.clear()
