"""
trading_agent.py – LangGraph stateful trading agent.

Defines a five-node state machine:

  fetch_market_state
        │
        ▼
  technical_analysis
        │
        ▼
  llm_reasoning  ──(WAIT)──► END
        │ BUY / SELL
        ▼
  risk_validator ──(REJECTED)──► END
        │ APPROVED
        ▼
  execute_order
        │
        ▼
       END
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from loguru import logger

# ── LangGraph imports ─────────────────────────────────────────────────────────
try:
    from langgraph.graph import END, StateGraph  # type: ignore
    from typing_extensions import TypedDict
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "langgraph is required. Install it with: pip install langgraph"
    ) from exc

# ── Internal imports ──────────────────────────────────────────────────────────
from src.tools.data_pipeline import DataPipeline
from src.tools.kite_tools import KiteOrderManager, KitePortfolio
from src.utils.risk_manager import RiskManager
from src.utils.technical_analysis import compute_indicators, format_market_state_prompt


# ─────────────────────────────────────────────────────────────────────────────
# State definition
# ─────────────────────────────────────────────────────────────────────────────


class TradingState(TypedDict, total=False):
    """Shared state passed between every node in the graph."""

    # Inputs
    symbol: str
    instrument_token: int
    exchange: str

    # Market data
    ohlcv_df: Any                    # pd.DataFrame (stored as Any to avoid import cycle)
    latest_quote: dict[str, Any]

    # Technical indicators
    indicators: dict[str, Any]
    market_state_prompt: str

    # LLM output
    llm_action: str                  # "BUY" | "SELL" | "WAIT"
    llm_reason: str

    # Risk validation
    risk_result: dict[str, Any]      # output of RiskManager.validate_order

    # Execution
    order_id: str | None
    execution_status: str            # "PLACED" | "SKIPPED" | "REJECTED" | "ERROR"

    # Runtime context (injected before graph invocation)
    pipeline: Any                    # DataPipeline
    order_manager: Any               # KiteOrderManager
    portfolio: Any                   # KitePortfolio | None
    risk_manager: Any                # RiskManager
    llm_chain: Any                   # LangChain Runnable


# ─────────────────────────────────────────────────────────────────────────────
# Node implementations
# ─────────────────────────────────────────────────────────────────────────────


def fetch_market_state(state: TradingState) -> TradingState:
    """Node 1 – Pull live OHLCV candles and the latest quote."""
    pipeline: DataPipeline = state["pipeline"]
    symbol: str = state["symbol"]
    instrument_token: int = state["instrument_token"]

    logger.info("[Node] fetch_market_state  –  {}", symbol)

    df = pipeline.get_ohlcv_df(
        instrument_token=instrument_token,
        tradingsymbol=symbol,
        interval="minute",
        days_back=1,
    )

    exchange = state.get("exchange", "NSE")
    quote = pipeline.fetch_latest_quote([f"{exchange}:{symbol}"])

    return {**state, "ohlcv_df": df, "latest_quote": quote}


def technical_analysis(state: TradingState) -> TradingState:
    """Node 2 – Calculate RSI, EMA, Bollinger Bands."""
    logger.info("[Node] technical_analysis")

    indicators = compute_indicators(state["ohlcv_df"])
    prompt = format_market_state_prompt(state["symbol"], indicators)

    return {**state, "indicators": indicators, "market_state_prompt": prompt}


def llm_reasoning(state: TradingState) -> TradingState:
    """Node 3 – Let the fine-tuned LLM decide: BUY, SELL, or WAIT."""
    logger.info("[Node] llm_reasoning")

    llm_chain = state["llm_chain"]
    prompt: str = state["market_state_prompt"]

    try:
        raw_output: str = llm_chain.invoke({"input": prompt})
        parsed = _parse_llm_output(raw_output)
        action: str = parsed.get("action", "WAIT").upper()
        reason: str = parsed.get("reason", "")
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM reasoning failed: {}. Defaulting to WAIT.", exc)
        action = "WAIT"
        reason = f"LLM error: {exc}"

    logger.info("LLM decision: {} – {}", action, reason)
    return {**state, "llm_action": action, "llm_reason": reason}


def risk_validator(state: TradingState) -> TradingState:
    """Node 4 – Validate the LLM's intent against hard-coded risk rules."""
    logger.info("[Node] risk_validator  –  intent={}", state.get("llm_action"))

    risk_mgr: RiskManager = state["risk_manager"]
    indicators: dict[str, Any] = state.get("indicators", {})
    price: float = indicators.get("close", 0.0)

    # Determine current day P&L
    current_pnl: float = 0.0
    portfolio: Any = state.get("portfolio")
    if portfolio is not None:
        try:
            current_pnl = portfolio.get_pnl()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch P&L: {}", exc)

    # Use a sensible default quantity; real sizing is done inside validate_order
    proposed_qty = risk_mgr.calculate_quantity(price) if price > 0 else 0

    risk_result = risk_mgr.validate_order(
        price=price,
        quantity=proposed_qty,
        current_pnl=current_pnl,
    )

    logger.info(
        "Risk validation: approved={}, reason={}",
        risk_result["approved"],
        risk_result["reason"],
    )
    return {**state, "risk_result": risk_result}


def execute_order(state: TradingState) -> TradingState:
    """Node 5 – Place the validated order via Kite (or simulate it)."""
    logger.info("[Node] execute_order")

    risk_result: dict[str, Any] = state.get("risk_result", {})
    if not risk_result.get("approved", False):
        return {**state, "execution_status": "REJECTED", "order_id": None}

    action: str = state.get("llm_action", "WAIT")
    if action == "WAIT":
        return {**state, "execution_status": "SKIPPED", "order_id": None}

    order_manager: KiteOrderManager = state["order_manager"]
    symbol: str = state["symbol"]
    exchange: str = state.get("exchange", "NSE")
    qty: int = risk_result.get("safe_quantity", 0)

    if qty == 0:
        return {**state, "execution_status": "SKIPPED", "order_id": None}

    try:
        order_id = order_manager.place_order(
            tradingsymbol=symbol,
            exchange=exchange,
            transaction_type=action,   # "BUY" | "SELL"
            quantity=qty,
        )
        status = "PLACED"
    except Exception as exc:  # noqa: BLE001
        logger.error("Order placement failed: {}", exc)
        order_id = None
        status = "ERROR"

    return {**state, "order_id": order_id, "execution_status": status}


# ─────────────────────────────────────────────────────────────────────────────
# Conditional edge router
# ─────────────────────────────────────────────────────────────────────────────


def _route_after_llm(
    state: TradingState,
) -> Literal["risk_validator", "__end__"]:
    """Skip risk validation and execution if LLM chose WAIT."""
    if state.get("llm_action", "WAIT") in ("BUY", "SELL"):
        return "risk_validator"
    return "__end__"


def _route_after_risk(
    state: TradingState,
) -> Literal["execute_order", "__end__"]:
    """Skip execution if the risk validator rejected the order."""
    risk_result = state.get("risk_result", {})
    if risk_result.get("approved", False):
        return "execute_order"
    return "__end__"


# ─────────────────────────────────────────────────────────────────────────────
# Graph factory
# ─────────────────────────────────────────────────────────────────────────────


def build_trading_graph() -> Any:
    """Construct and compile the LangGraph StateGraph.

    Returns:
        A compiled LangGraph ``CompiledGraph`` that can be invoked with an
        initial ``TradingState`` dict.
    """
    graph = StateGraph(TradingState)

    graph.add_node("fetch_market_state", fetch_market_state)
    graph.add_node("technical_analysis", technical_analysis)
    graph.add_node("llm_reasoning", llm_reasoning)
    graph.add_node("risk_validator", risk_validator)
    graph.add_node("execute_order", execute_order)

    graph.set_entry_point("fetch_market_state")
    graph.add_edge("fetch_market_state", "technical_analysis")
    graph.add_edge("technical_analysis", "llm_reasoning")

    graph.add_conditional_edges(
        "llm_reasoning",
        _route_after_llm,
        {"risk_validator": "risk_validator", "__end__": END},
    )
    graph.add_conditional_edges(
        "risk_validator",
        _route_after_risk,
        {"execute_order": "execute_order", "__end__": END},
    )
    graph.add_edge("execute_order", END)

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_llm_output(raw: str) -> dict[str, Any]:
    """Extract the JSON payload from the LLM response.

    The model is instructed to output *only* JSON, but we tolerate surrounding
    text by searching for the first ``{...}`` block.
    """
    raw = raw.strip()
    # Attempt direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Search for embedded JSON object
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse LLM output as JSON: {!r}", raw[:200])
    return {"action": "WAIT", "reason": "Could not parse LLM response."}
