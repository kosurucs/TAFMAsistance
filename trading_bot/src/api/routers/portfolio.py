"""
portfolio.py – Portfolio query endpoints.

Routes:
  GET /portfolio             – positions, holdings, margins, P&L
  GET /portfolio/positions   – open positions
  GET /portfolio/holdings    – long-term holdings
  GET /portfolio/margins     – available margin/cash
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_portfolio
from src.tools.kite_tools import KitePortfolio

router = APIRouter(prefix="/portfolio")


def _require_portfolio(
    portfolio: KitePortfolio | None = Depends(get_portfolio),
) -> KitePortfolio:
    if portfolio is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Portfolio data unavailable in paper-trading mode. "
                "Set PAPER_TRADING=false and configure Kite credentials."
            ),
        )
    return portfolio


@router.get("", summary="Full portfolio snapshot (positions + holdings + margins + P&L)")
def get_portfolio_snapshot(
    portfolio: KitePortfolio = Depends(_require_portfolio),
) -> dict[str, Any]:
    return {
        "positions": portfolio.get_positions(),
        "holdings": portfolio.get_holdings(),
        "margins": portfolio.get_margins(),
        "day_pnl": portfolio.get_pnl(),
    }


@router.get("/positions", summary="Open intraday and net positions")
def get_positions(
    portfolio: KitePortfolio = Depends(_require_portfolio),
) -> dict[str, Any]:
    return portfolio.get_positions()


@router.get("/holdings", summary="Long-term CNC holdings")
def get_holdings(
    portfolio: KitePortfolio = Depends(_require_portfolio),
) -> list[dict[str, Any]]:
    return portfolio.get_holdings()


@router.get("/margins", summary="Available margin and cash balances")
def get_margins(
    portfolio: KitePortfolio = Depends(_require_portfolio),
) -> dict[str, Any]:
    return portfolio.get_margins()


@router.get("/monitor", summary="Position monitoring status with exit signals")
def get_monitor_status(
    portfolio: KitePortfolio = Depends(_require_portfolio),
) -> dict[str, Any]:
    """
    Returns current open positions with their monitoring status.
    Runs ExitMonitor against all open positions and returns the signals.
    """
    from src.utils.exit_monitor import ExitMonitor
    from src.utils.technical_analysis import compute_indicators
    from src.tools.data_pipeline import DataPipeline
    from src.tools.kite_tools import KiteDataFetcher
    import os
    
    # Get open positions
    positions_data = portfolio.get_positions()
    day_positions = positions_data.get("day", [])
    net_positions = positions_data.get("net", [])
    all_positions = day_positions + net_positions
    
    if not all_positions:
        return {"positions": [], "message": "No open positions", "count": 0}
    
    # Normalize positions for monitoring
    normalized_positions = []
    for pos in all_positions:
        tradingsymbol = pos.get("tradingsymbol", "")
        quantity = pos.get("quantity", 0)
        if quantity == 0:
            continue
        
        action = "BUY" if quantity > 0 else "SELL"
        
        normalized_positions.append({
            "symbol": tradingsymbol,
            "action": action,
            "entry_price": float(pos.get("average_price", 0)),
            "current_price": float(pos.get("last_price", 0)),
            "sl": float(pos.get("sl", 0)) if pos.get("sl") else 0,
            "tp": float(pos.get("tp", 0)) if pos.get("tp") else 0,
            "quantity": abs(quantity),
            "pnl": float(pos.get("pnl", 0)),
            "beta": 1.0,
        })
    
    # Get indicators for each position (simplified — no live data fetch in API)
    indicators_by_symbol = {}
    # In a full implementation, fetch live indicators here
    # For now, return positions without detailed indicator-based signals
    
    monitor = ExitMonitor()
    
    # Return simplified monitoring data
    monitored = []
    for pos in normalized_positions:
        # Basic check without full indicators
        signal = monitor.should_exit(
            action=pos["action"],
            entry_price=pos["entry_price"],
            current_price=pos["current_price"],
            sl=pos["sl"],
            tp=pos["tp"],
            atr=0,  # Would need to fetch from indicators
            volume=0,
            avg_volume=0,
            nifty_change_pct=0,
            beta=pos["beta"],
            rsi=50,
        )
        
        monitored.append({
            "symbol": pos["symbol"],
            "action": pos["action"],
            "entry_price": pos["entry_price"],
            "current_price": pos["current_price"],
            "sl": pos["sl"],
            "tp": pos["tp"],
            "pnl": pos["pnl"],
            "exit_signal": {
                "should_exit": signal.should_exit,
                "reason": signal.reason,
                "urgency": signal.urgency,
                "adjusted_sl": signal.adjusted_sl,
            },
        })
    
    return {
        "positions": monitored,
        "count": len(monitored),
        "message": f"Monitoring {len(monitored)} open positions"
    }
