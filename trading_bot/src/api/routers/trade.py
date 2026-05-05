"""
trade.py – Trade execution endpoints.

Routes:
  POST /trade/run  – run one full LangGraph cycle for a symbol
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import (
    get_data_fetcher,
    get_llm_chain,
    get_order_manager,
    get_portfolio,
    get_risk_manager,
)
from src.agents.trading_agent import TradingState, build_trading_graph
from src.api.routers.market import _make_stub_df
from src.tools.data_pipeline import DataPipeline
from src.tools.kite_tools import KiteDataFetcher, KiteOrderManager, KitePortfolio
from src.utils.risk_manager import RiskManager

router = APIRouter(prefix="/trade")


class TradeRunRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"


class _StubPipeline:
    """Paper-trading stub – identical to the one in main.py."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def get_ohlcv_df(self, instrument_token: int = 0, tradingsymbol: str = "",
                     interval: str = "minute", days_back: int = 1,
                     use_cache: bool = False) -> Any:
        return _make_stub_df(tradingsymbol or self.symbol)

    def fetch_latest_quote(self, symbols: list[str]) -> dict[str, Any]:
        return {s: {"last_price": 1000.0} for s in symbols}


@router.post("/run", summary="Trigger one full LangGraph trading cycle for a symbol")
def trade_run(
    body: TradeRunRequest,
    fetcher: KiteDataFetcher | None = Depends(get_data_fetcher),
    order_manager: KiteOrderManager = Depends(get_order_manager),
    portfolio: KitePortfolio | None = Depends(get_portfolio),
    risk_mgr: RiskManager = Depends(get_risk_manager),
    llm_chain: Any = Depends(get_llm_chain),
) -> dict[str, Any]:
    """Run the 5-node LangGraph state machine for *symbol* and return the result.

    The graph runs synchronously and returns immediately with the final state.
    """
    symbol = body.symbol.upper()

    # ── Resolve instrument token ──────────────────────────────────────────────
    token: int = 0
    if fetcher is not None:
        try:
            token = fetcher.lookup_instrument_token(body.exchange, symbol)
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail=f"Instrument '{symbol}' not found on '{body.exchange}'.",
            )

    # ── Build pipeline ────────────────────────────────────────────────────────
    pipeline: Any
    if fetcher is not None:
        pipeline = DataPipeline(fetcher)
    else:
        pipeline = _StubPipeline(symbol)

    # ── Invoke graph ──────────────────────────────────────────────────────────
    trading_graph = build_trading_graph()
    initial_state: TradingState = {
        "symbol": symbol,
        "instrument_token": token,
        "exchange": body.exchange,
        "pipeline": pipeline,
        "order_manager": order_manager,
        "portfolio": portfolio,
        "risk_manager": risk_mgr,
        "llm_chain": llm_chain,
    }

    try:
        result = trading_graph.invoke(initial_state)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Graph execution error: {exc}")

    return {
        "symbol": symbol,
        "llm_action": result.get("llm_action", "N/A"),
        "llm_reason": result.get("llm_reason", ""),
        "execution_status": result.get("execution_status", "N/A"),
        "order_id": result.get("order_id"),
        "risk_result": result.get("risk_result", {}),
        "indicators": result.get("indicators", {}),
        "stub_data": fetcher is None,
    }
