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
import time
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
from src.tools.historical_data import HistoricalDataManager
from src.tools.kite_tools import KiteOrderManager, KitePortfolio
from src.utils.risk_manager import RiskManager
from src.utils.rr_calculator import calculate_sl_tp, RRResult
from src.utils.scenario_engine import ScenarioEngine, SCENARIO_CONFIDENCE_THRESHOLD
from src.utils.technical_analysis import (
    compute_indicators,
    compute_indicators_multi_timeframe,
    format_market_state_prompt,
)


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

    # Multi-timeframe analysis fields (Phase 2)
    mtf_indicators: dict[str, dict]   # timeframe → indicators dict
    mtf_confluence_score: int          # positive = bullish, negative = bearish
    mtf_bias: str                      # "BULLISH" | "BEARISH" | "NEUTRAL"

    # Phase 4: Scenario engine fields
    scenarios: list[dict]              # scored scenario list [{name, probability, signals}]
    dominant_scenario: str             # name of the dominant scenario
    scenario_confidence: float         # probability of dominant scenario (0-100)
    scenario_bias: str                 # "BUY" | "SELL" | "WAIT"

    # LLM output
    llm_action: str                  # "BUY" | "SELL" | "WAIT"
    llm_reason: str

    # Phase 3: R:R engine fields
    sl: float           # calculated stop-loss price
    tp: float           # calculated take-profit price
    rr_ratio: float     # calculated R:R ratio
    rr_reason: str      # reason if R:R rejected

    # Risk validation
    risk_result: dict[str, Any]      # output of RiskManager.validate_order

    # Execution
    order_id: str | None
    execution_status: str            # "PLACED" | "SKIPPED" | "REJECTED" | "ERROR"
    quantity: int                    # Order quantity (for DB logging)
    current_price: float             # Current price at time of order (for DB logging)

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

    # Fetch multi-timeframe data for confluence analysis
    try:
        hist_mgr = HistoricalDataManager()
        timeframe_dfs = {}
        # Daily (1 year = ~250 trading days)
        df_daily = hist_mgr.get_symbol_data(symbol, period="1y", interval="1d")
        if df_daily is not None:
            timeframe_dfs["1d"] = df_daily
        # Hourly (past 60 days — yfinance limit for 1h is 730 days)
        df_hourly = hist_mgr.get_symbol_data(symbol, period="60d", interval="1h")
        if df_hourly is not None:
            timeframe_dfs["1h"] = df_hourly
        mtf = compute_indicators_multi_timeframe(symbol, timeframe_dfs)
        state["mtf_indicators"] = mtf
        state["mtf_confluence_score"] = mtf.get("confluence", {}).get("score", 0)
        state["mtf_bias"] = mtf.get("confluence", {}).get("bias", "NEUTRAL")
        logger.info(f"MTF confluence for {symbol}: {state['mtf_bias']} (score {state['mtf_confluence_score']})")
    except Exception as e:
        logger.warning(f"MTF analysis failed (non-critical): {e}")
        state["mtf_indicators"] = {}
        state["mtf_confluence_score"] = 0
        state["mtf_bias"] = "NEUTRAL"

    return {**state, "ohlcv_df": df, "latest_quote": quote}


def technical_analysis(state: TradingState) -> TradingState:
    """Node 2 – Calculate RSI, EMA, Bollinger Bands."""
    logger.info("[Node] technical_analysis")

    indicators = compute_indicators(state["ohlcv_df"])
    prompt = format_market_state_prompt(
        state["symbol"],
        indicators,
        mtf_indicators=state.get("mtf_indicators")
    )

    # Log snapshot to DB (non-blocking)
    try:
        from src.utils.db_logger import get_db_logger
        get_db_logger().log_market_snapshot(
            symbol=state.get("symbol", ""),
            timeframe="1min",
            indicators={k: v for k, v in (indicators or {}).items() if isinstance(v, (int, float, str))},
            scenarios=state.get("scenarios"),
        )
    except Exception:
        pass  # Non-critical

    return {**state, "indicators": indicators, "market_state_prompt": prompt}


def scenario_analysis_node(state: TradingState) -> TradingState:
    """
    Phase 4: Score all 5 market scenarios and determine trade bias.
    Inserts between technical_analysis and llm_reasoning.
    
    CRITICAL: If dominant scenario < 60% confidence → bias is WAIT.
    LLM receives this as READ-ONLY context. risk_validator enforces the gate.
    """
    indicators = state.get("indicators", {})
    mtf_indicators = state.get("mtf_indicators", {})
    
    try:
        engine = ScenarioEngine()
        result = engine.score_scenarios(indicators, mtf_indicators)
        
        state["scenarios"] = [
            {"name": s.name, "probability": s.probability, "signals": s.signals}
            for s in result.scores
        ]
        state["dominant_scenario"] = result.dominant.name
        state["scenario_confidence"] = result.confidence
        state["scenario_bias"] = result.trade_bias
        
        logger.info(
            f"Scenario analysis for {state.get('symbol')}: "
            f"{result.dominant.name} ({result.confidence:.1f}%) → {result.trade_bias}"
        )
    except Exception as e:
        logger.error(f"Scenario analysis failed: {e}")
        state["scenarios"] = []
        state["dominant_scenario"] = "UNKNOWN"
        state["scenario_confidence"] = 0.0
        state["scenario_bias"] = "WAIT"
    
    return state


def llm_reasoning(state: TradingState) -> TradingState:
    """Node 3 – Let the fine-tuned LLM decide: BUY, SELL, or WAIT."""
    logger.info("[Node] llm_reasoning")

    llm_chain = state["llm_chain"]
    prompt: str = state["market_state_prompt"]
    
    # Prepend scenario context to market state prompt
    scenarios = state.get("scenarios", [])
    if scenarios:
        top2 = scenarios[:2]
        scenario_lines = "\n".join([
            f"  - {s['name']}: {s['probability']:.1f}% ({', '.join(s['signals'][:2]) if s['signals'] else 'no signals'})"
            for s in top2
        ])
        scenario_section = f"\nScenario Analysis:\n{scenario_lines}\nDominant Bias: {state.get('scenario_bias','WAIT')} ({state.get('scenario_confidence',0):.1f}% confidence)\n"
        prompt = scenario_section + prompt

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


def rr_calculator_node(state: TradingState) -> TradingState:
    """
    Phase 3: Calculate dynamic SL/TP based on ATR and validate R:R ≥ 1:2.
    If R:R is below minimum, forces action to WAIT.
    
    Placement: runs after llm_reasoning, before risk_validator.
    TODO Phase 4: reorder to run after scenario_analysis when that node is added.
    """
    action = state.get("llm_action", "WAIT")
    
    # Skip R:R check if already WAIT
    if action == "WAIT":
        logger.debug("R:R node: action is WAIT, skipping calculation")
        state["sl"] = 0.0
        state["tp"] = 0.0
        state["rr_ratio"] = 0.0
        state["rr_reason"] = "No trade — action is WAIT"
        return state

    indicators = state.get("indicators", {})
    entry_price = indicators.get("close", 0.0)
    atr = indicators.get("atr", 0.0)

    if entry_price <= 0:
        logger.error(f"R:R node: invalid entry_price={entry_price}, forcing WAIT")
        state["llm_action"] = "WAIT"
        state["sl"] = 0.0
        state["tp"] = 0.0
        state["rr_ratio"] = 0.0
        state["rr_reason"] = "Invalid entry price"
        return state

    try:
        rr: RRResult = calculate_sl_tp(action, entry_price, atr)
        state["sl"] = rr.sl
        state["tp"] = rr.tp
        state["rr_ratio"] = rr.rr_ratio

        if not rr.acceptable:
            state["llm_action"] = "WAIT"
            state["rr_reason"] = f"R:R {rr.rr_ratio:.2f}:1 below minimum 2:1 (risk={rr.risk:.2f}, reward={rr.reward:.2f})"
            logger.warning(f"R:R gate rejected trade: {state['rr_reason']}")
        else:
            state["rr_reason"] = f"R:R acceptable: {rr.rr_ratio:.2f}:1 (SL={rr.sl}, TP={rr.tp})"
            logger.info(f"R:R gate passed for {state.get('symbol')}: {state['rr_reason']}")

    except Exception as e:
        logger.error(f"R:R calculation failed: {e}")
        state["llm_action"] = "WAIT"
        state["sl"] = 0.0
        state["tp"] = 0.0
        state["rr_ratio"] = 0.0
        state["rr_reason"] = f"R:R calculation error: {e}"

    return state


def risk_validator(state: TradingState) -> TradingState:
    """Node 4 – Validate the LLM's intent against hard-coded risk rules."""
    logger.info("[Node] risk_validator  –  intent={}", state.get("llm_action"))

    # GATE 1: Scenario confidence gate (Risk Guardian mandatory — Phase 4)
    scenario_confidence = state.get("scenario_confidence", 0.0)
    if scenario_confidence < SCENARIO_CONFIDENCE_THRESHOLD:
        logger.warning(
            f"Risk validator: REJECTED — scenario confidence {scenario_confidence:.1f}% "
            f"< {SCENARIO_CONFIDENCE_THRESHOLD}% required threshold"
        )
        state["risk_result"] = {
            "approved": False,
            "reason": f"Scenario confidence {scenario_confidence:.1f}% below required {SCENARIO_CONFIDENCE_THRESHOLD}%",
            "safe_quantity": 0,
        }
        return state

    risk_mgr: RiskManager = state["risk_manager"]
    indicators: dict[str, Any] = state.get("indicators", {})
    price: float = indicators.get("close", 0.0)

    # Determine current day P&L
    current_pnl: float = 0.0
    portfolio: Any = state.get("portfolio")
    if portfolio is not None:
        try:
            current_pnl = portfolio.get_day_pnl()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch P&L: {}", exc)

    # Use a sensible default quantity; real sizing is done inside validate_order
    proposed_qty = risk_mgr.calculate_quantity(price) if price > 0 else 0

    risk_result = risk_mgr.validate_order(
        price=price,
        quantity=proposed_qty,
        current_pnl=current_pnl,
        sl=state.get("sl", 0.0),  # Phase 3: pass SL to risk manager
        tp=state.get("tp", 0.0),  # Phase 3: pass TP (for future use)
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

    # Phase 3: Paper trading guard (Risk Guardian mandatory requirement)
    is_paper = os.getenv("PAPER_TRADING", "false").lower() == "true"
    current_price = state.get("indicators", {}).get("close", 0.0)
    
    if is_paper:
        logger.info(
            f"PAPER TRADE: {state['llm_action']} {state.get('symbol')} @ "
            f"{current_price} SL={state.get('sl', 0.0)} "
            f"TP={state.get('tp', 0.0)} R:R={state.get('rr_ratio', 0.0):.2f}"
        )
        order_id = f"PAPER_{int(time.time())}"
        state["order_id"] = order_id
        state["execution_status"] = "PLACED"
        state["current_price"] = current_price
        
        # Log to DB (non-blocking — degraded OK if DB unavailable)
        from src.utils.db_logger import get_db_logger
        db = get_db_logger()
        risk_result = state.get("risk_result", {})
        db.log_trade_entry(
            order_id=order_id,
            symbol=state.get("symbol", ""),
            action=state.get("llm_action", ""),
            entry_price=current_price,
            quantity=risk_result.get("safe_quantity", 0),
            sl=state.get("sl", 0.0),
            tp=state.get("tp", 0.0),
            rr_ratio=state.get("rr_ratio", 0.0),
            scenario=state.get("dominant_scenario", "UNKNOWN"),
            confidence=state.get("scenario_confidence", 0.0),
            paper_trade=True,
        )
        return state

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

    # ANALYSIS-ONLY MODE: Log the trade signal but do NOT place orders
    logger.info(
        "[ANALYSIS] Would place {} order for {} qty {} @ market (order placement disabled)",
        action, symbol, qty
    )
    order_id = f"ANALYSIS-{symbol}-{int(time.time() * 1000)}"
    status = "ANALYSIS_ONLY"
    
    # Log to DB for analysis tracking
    from src.utils.db_logger import get_db_logger
    db = get_db_logger()
    current_price = state.get("indicators", {}).get("close", 0.0)
    db.log_trade_entry(
        order_id=order_id,
        symbol=symbol,
        action=action,
        entry_price=current_price,
        quantity=qty,
        sl=state.get("sl", 0.0),
        tp=state.get("tp", 0.0),
        rr_ratio=state.get("rr_ratio", 0.0),
        scenario=state.get("dominant_scenario", "UNKNOWN"),
        confidence=state.get("scenario_confidence", 0.0),
        paper_trade=True,  # Mark as paper trade since we're not actually executing
    )

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
    graph.add_node("scenario_analysis", scenario_analysis_node)  # Phase 4
    graph.add_node("llm_reasoning", llm_reasoning)
    graph.add_node("rr_calculator", rr_calculator_node)  # Phase 3
    graph.add_node("risk_validator", risk_validator)
    graph.add_node("execute_order", execute_order)

    graph.set_entry_point("fetch_market_state")
    graph.add_edge("fetch_market_state", "technical_analysis")
    graph.add_edge("technical_analysis", "scenario_analysis")  # Phase 4
    graph.add_edge("scenario_analysis", "llm_reasoning")  # Phase 4
    graph.add_edge("llm_reasoning", "rr_calculator")  # Phase 3: always go to R:R calculator

    graph.add_conditional_edges(
        "rr_calculator",  # Phase 3: route from rr_calculator instead of llm_reasoning
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

    logger.error("Could not parse LLM output as JSON: {!r}", raw[:200])
    return {"action": "WAIT", "reason": "Could not parse LLM response."}
