"""
bot.py – Bot-level control endpoints.

Routes:
  GET  /status         – bot health, kill-switch state, paper-trading flag
  GET  /watchlist      – current watchlist symbols
  POST /watchlist      – replace the watchlist
  POST /bot/kill       – activate kill switch
  POST /bot/unkill     – deactivate kill switch
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from fastapi import HTTPException
from pydantic import BaseModel

from src.api.dependencies import (
    get_redis,
    get_risk_manager,
    get_watchlist,
    set_watchlist,
)
from src.utils.risk_manager import RiskManager
from src.tools.kite_tools import KiteAuthManager

router = APIRouter()


# ── /status ───────────────────────────────────────────────────────────────────


@router.get("/status", summary="Bot health & configuration")
def get_status(
    risk_mgr: RiskManager = Depends(get_risk_manager),
    redis: Any = Depends(get_redis),
) -> dict[str, Any]:
    """Return current bot status including kill-switch state."""
    return {
        "paper_trading": os.environ.get("PAPER_TRADING", "true").lower() == "true",
        "kill_switch_active": risk_mgr.is_kill_switch_active(),
        "opening_capital": risk_mgr.opening_capital,
        "max_daily_loss_pct": risk_mgr.max_daily_loss_pct,
        "max_position_size_pct": risk_mgr.max_position_size_pct,
        "redis_connected": redis is not None,
        "watchlist": get_watchlist(),
    }


# ── /watchlist ────────────────────────────────────────────────────────────────


@router.get("/watchlist", summary="Get current watchlist")
def read_watchlist() -> dict[str, list[str]]:
    return {"watchlist": get_watchlist()}


class WatchlistRequest(BaseModel):
    symbols: list[str]


@router.post("/watchlist", summary="Replace the watchlist")
def update_watchlist(body: WatchlistRequest) -> dict[str, Any]:
    set_watchlist(body.symbols)
    return {"watchlist": get_watchlist(), "message": "Watchlist updated."}


# ── /bot/kill & /bot/unkill ───────────────────────────────────────────────────


@router.post("/bot/kill", summary="Activate the kill switch")
def kill_bot(risk_mgr: RiskManager = Depends(get_risk_manager)) -> dict[str, str]:
    risk_mgr.activate_kill_switch()
    return {"message": "Kill switch activated. All trading halted."}


@router.post("/bot/unkill", summary="Deactivate the kill switch")
def unkill_bot(risk_mgr: RiskManager = Depends(get_risk_manager)) -> dict[str, str]:
    risk_mgr.deactivate_kill_switch()
    return {"message": "Kill switch deactivated. Trading resumed."}


@router.post("/bot/authenticate", summary="Trigger Kite authentication")
def authenticate_kite() -> dict[str, str]:
    """Authenticate with Kite and cache the access token in process env.

    This explicitly triggers the login flow backed by ``KiteAuthManager``.
    If ``KITE_ACCESS_TOKEN`` is already set, the existing session is reused.
    """
    try:
        auth = KiteAuthManager()
        auth.get_kite_session()
        return {"status": "ok", "message": "Kite authentication successful."}
    except KeyError as exc:
        missing_key = str(exc).strip("\"'")
        raise HTTPException(
            status_code=400,
            detail=(
                f"Missing environment variable: {missing_key}. "
                "Set required Kite credentials and retry."
            ),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Kite authentication failed: {exc}") from exc
