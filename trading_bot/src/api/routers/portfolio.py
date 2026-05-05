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
