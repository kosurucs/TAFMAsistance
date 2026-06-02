"""
algo.py – Algo Engine REST endpoints.

Prefix: /algo

Routes:
  GET  /algo/status              – engine state (running, cycles, last_run)
  POST /algo/run                 – trigger one manual cycle
  GET  /algo/signals             – recent signals (ring buffer)
  GET  /algo/strategies          – list strategies with enabled state
  POST /algo/strategies/{name}/toggle – enable/disable a strategy

Analysis-only: no orders placed. All signals are logged recommendations only.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import (
    get_data_fetcher,
    get_risk_manager,
    get_watchlist,
)
from src.tools.data_pipeline import DataPipeline
from src.utils import algo_engine as engine
from src.utils.algo_strategies import STRATEGY_REGISTRY
from src.utils.risk_manager import RiskManager

router = APIRouter(prefix="/algo", tags=["Algo"])


# ─── Pydantic models ──────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    symbols: list[str] | None = None   # override watchlist if provided
    exchange: str = "NSE"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _strategy_list() -> list[dict]:
    return [
        {
            "name": s.name,
            "description": s.description,
            "enabled": s.enabled,
        }
        for s in STRATEGY_REGISTRY
    ]


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/status")
def algo_status() -> dict[str, Any]:
    """Return current engine state."""
    s = engine.get_state()
    return {
        "running": s.running,
        "cycle_count": s.cycle_count,
        "last_run_ist": s.last_run_ist,
        "last_error": s.last_error,
        "interval_sec": s.interval_sec,
        "watchlist": s.watchlist,
        "signal_count": len(s.signals),
        "strategies": _strategy_list(),
    }


@router.post("/run")
async def algo_run(
    body: RunRequest = RunRequest(),
    fetcher: Any = Depends(get_data_fetcher),
    risk_mgr: RiskManager = Depends(get_risk_manager),
    watchlist: list[str] = Depends(get_watchlist),
) -> dict[str, Any]:
    """
    Trigger one algo cycle synchronously and return the signals produced.
    Does NOT require the scheduler to be running.
    """
    symbols = [s.upper() for s in body.symbols] if body.symbols else watchlist
    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols in watchlist.")

    if fetcher is None:
        raise HTTPException(status_code=503, detail="Data fetcher not available.")

    try:
        pipeline = DataPipeline(fetcher)
        signals = await engine.run_cycle(
            symbols=symbols,
            fetcher=fetcher,
            pipeline=pipeline,
            risk_mgr=risk_mgr,
            exchange=body.exchange,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Update global state
    state = engine.get_state()
    state.cycle_count += 1
    from datetime import datetime
    from zoneinfo import ZoneInfo
    state.last_run_ist = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
    state.signals = (signals + state.signals)[:200]

    return {
        "symbols_processed": len(symbols),
        "signals_generated": len(signals),
        "signals": signals,
        "cycle_count": state.cycle_count,
    }


@router.get("/signals")
def get_signals(limit: int = 50) -> dict[str, Any]:
    """Return the most recent algo signals (newest first)."""
    state = engine.get_state()
    capped = min(limit, 200)
    return {
        "signals": state.signals[:capped],
        "total": len(state.signals),
    }


@router.get("/strategies")
def list_strategies() -> dict[str, Any]:
    """List all strategies with their current enabled/disabled state."""
    return {"strategies": _strategy_list()}


@router.post("/strategies/{name}/toggle")
def toggle_strategy(name: str) -> dict[str, Any]:
    """Toggle a strategy on or off by name."""
    from src.utils.algo_strategies import get_strategy
    strategy = get_strategy(name)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found.")
    strategy.enabled = not strategy.enabled
    return {
        "name": strategy.name,
        "enabled": strategy.enabled,
        "message": f"Strategy '{name}' {'enabled' if strategy.enabled else 'disabled'}.",
    }


@router.delete("/signals")
def clear_signals() -> dict[str, str]:
    """Clear the signal ring buffer."""
    engine.clear_signals()
    return {"message": "Signal buffer cleared."}
