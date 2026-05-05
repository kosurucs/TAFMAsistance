"""
app.py – Streamlit dashboard for the TAFM Trading Bot.

Run with::

    streamlit run src/dashboard/app.py --server.port 8501

The dashboard calls the FastAPI backend (src/api/app.py) for all data.
Set API_BASE_URL in your environment (default: http://localhost:8000).
"""

from __future__ import annotations

import os
import time
from typing import Any

import pandas as pd
import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="TAFM Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Helpers ───────────────────────────────────────────────────────────────────


@st.cache_data(ttl=10)
def _get(path: str) -> Any:
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _post(path: str, payload: dict) -> Any:
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _badge(ok: bool, true_label: str = "✅ Yes", false_label: str = "❌ No") -> str:
    return true_label if ok else false_label


# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("📈 TAFM Trading Bot")
st.sidebar.markdown(f"**API:** `{API_BASE}`")

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Market Analysis", "LLM Chat", "Trade", "Portfolio", "Settings"],
)

if st.sidebar.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

# ── Page: Dashboard ───────────────────────────────────────────────────────────

if page == "Dashboard":
    st.title("🤖 Bot Dashboard")

    status = _get("/status")

    if "error" in status:
        st.error(f"Cannot reach API: {status['error']}")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Paper Trading", _badge(status.get("paper_trading", True)))
        col2.metric(
            "Kill Switch",
            _badge(status.get("kill_switch_active", False), "🔴 Active", "🟢 Inactive"),
        )
        col3.metric("Opening Capital", f"₹{status.get('opening_capital', 0):,.0f}")
        col4.metric("Redis", _badge(status.get("redis_connected", False)))

        st.subheader("Risk Limits")
        r1, r2 = st.columns(2)
        r1.metric(
            "Max Daily Loss",
            f"{status.get('max_daily_loss_pct', 0) * 100:.1f}%",
        )
        r2.metric(
            "Max Position Size",
            f"{status.get('max_position_size_pct', 0) * 100:.1f}%",
        )

        st.subheader("Watchlist")
        watchlist = status.get("watchlist", [])
        if watchlist:
            st.write(", ".join(f"`{s}`" for s in watchlist))
        else:
            st.write("(empty)")

        # Kill-switch controls
        st.subheader("Kill Switch Control")
        k1, k2 = st.columns(2)
        if k1.button("🔴 Activate Kill Switch"):
            res = _post("/bot/kill", {})
            st.toast(res.get("message", str(res)))
            st.cache_data.clear()
            st.rerun()
        if k2.button("🟢 Deactivate Kill Switch"):
            res = _post("/bot/unkill", {})
            st.toast(res.get("message", str(res)))
            st.cache_data.clear()
            st.rerun()

# ── Page: Market Analysis ─────────────────────────────────────────────────────

elif page == "Market Analysis":
    st.title("📊 Market Analysis")

    status = _get("/status")
    default_symbols = status.get("watchlist", ["RELIANCE"])

    symbol_input = st.text_input(
        "Symbol", value=default_symbols[0] if default_symbols else "RELIANCE"
    ).upper()
    exchange_input = st.selectbox("Exchange", ["NSE", "BSE"], index=0)

    if st.button("Fetch Data") or symbol_input:
        data = _get(f"/market/{symbol_input}?exchange={exchange_input}")

        if "error" in data:
            st.error(data["error"])
        else:
            ind = data.get("indicators", {})

            st.subheader(f"{symbol_input} – Technical Indicators")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Close", f"₹{ind.get('close', 0):.2f}")
            c2.metric("RSI (14)", f"{ind.get('rsi', 0):.1f}")
            c3.metric("Trend", ind.get("trend", "N/A"))
            c4.metric("BB Signal", ind.get("bb_signal", "N/A"))

            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("EMA Fast (9)", f"₹{ind.get('ema_fast', 0):.2f}")
                st.metric("EMA Slow (21)", f"₹{ind.get('ema_slow', 0):.2f}")
            with col_b:
                st.metric("BB Upper", f"₹{ind.get('bb_upper', 0):.2f}")
                st.metric("BB Lower", f"₹{ind.get('bb_lower', 0):.2f}")

            if data.get("stub_data"):
                st.info("⚠️ Showing **synthetic stub data** (paper-trading mode).")

            if data.get("quote"):
                st.subheader("Live Quote")
                st.json(data["quote"])

# ── Page: LLM Chat ────────────────────────────────────────────────────────────

elif page == "LLM Chat":
    st.title("🧠 LLM Chat Interface")

    tab1, tab2 = st.tabs(["📈 Symbol Analysis", "💬 Free-form Chat"])

    with tab1:
        st.markdown("Ask the LLM for a **BUY / SELL / WAIT** decision on a symbol.")
        symbol = st.text_input("Symbol", value="RELIANCE", key="llm_symbol").upper()
        exchange = st.selectbox("Exchange", ["NSE", "BSE"], key="llm_exchange")
        question = st.text_area(
            "Additional context (optional)",
            placeholder="e.g. Should I buy based on the current RSI crossover?",
        )

        if st.button("Analyze with LLM"):
            with st.spinner("Querying LLM..."):
                res = _post(
                    "/llm/analyze",
                    {"symbol": symbol, "exchange": exchange, "question": question or None},
                )

            if "error" in res:
                st.error(res["error"])
            else:
                action = res.get("action", "WAIT")
                color = {"BUY": "green", "SELL": "red", "WAIT": "orange"}.get(action, "gray")
                st.markdown(
                    f"### Decision: <span style='color:{color}; font-size:1.5em'>"
                    f"**{action}**</span>",
                    unsafe_allow_html=True,
                )
                st.write(f"**Reason:** {res.get('reason', 'N/A')}")

                if res.get("indicators"):
                    with st.expander("📊 Technical Indicators"):
                        st.json(res["indicators"])

                if res.get("stub_data"):
                    st.info("⚠️ Showing **synthetic stub data** (paper-trading mode).")

    with tab2:
        st.markdown("Send any free-form prompt directly to the LLM.")

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for role, msg in st.session_state.chat_history:
            with st.chat_message(role):
                st.markdown(msg)

        user_prompt = st.chat_input("Ask the LLM anything…")
        if user_prompt:
            st.session_state.chat_history.append(("user", user_prompt))
            with st.chat_message("user"):
                st.markdown(user_prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    res = _post("/llm/chat", {"prompt": user_prompt})
                reply = res.get("response", res.get("error", "No response."))
                st.markdown(reply)
            st.session_state.chat_history.append(("assistant", reply))

# ── Page: Trade ───────────────────────────────────────────────────────────────

elif page == "Trade":
    st.title("⚡ Run Trade Cycle")
    st.markdown(
        "Trigger one full **LangGraph** cycle "
        "(fetch → indicators → LLM → risk → execute) for a symbol."
    )

    symbol = st.text_input("Symbol", value="RELIANCE").upper()
    exchange = st.selectbox("Exchange", ["NSE", "BSE"])

    if st.button("▶️ Run Cycle"):
        with st.spinner(f"Running LangGraph cycle for {symbol}…"):
            res = _post("/trade/run", {"symbol": symbol, "exchange": exchange})

        if "error" in res:
            st.error(res["error"])
        else:
            action = res.get("llm_action", "N/A")
            status = res.get("execution_status", "N/A")
            color = {"BUY": "green", "SELL": "red", "WAIT": "orange"}.get(action, "gray")

            col1, col2, col3 = st.columns(3)
            col1.markdown(
                f"**LLM Action**<br><span style='color:{color};font-size:1.5em'>"
                f"{action}</span>",
                unsafe_allow_html=True,
            )
            col2.metric("Execution Status", status)
            col3.metric("Order ID", res.get("order_id") or "—")

            if res.get("llm_reason"):
                st.write(f"**Reason:** {res['llm_reason']}")

            risk = res.get("risk_result", {})
            if risk:
                with st.expander("🛡️ Risk Validation Details"):
                    st.json(risk)

            if res.get("indicators"):
                with st.expander("📊 Technical Indicators"):
                    st.json(res["indicators"])

            if res.get("stub_data"):
                st.info("⚠️ Showing **synthetic stub data** (paper-trading mode).")

# ── Page: Portfolio ───────────────────────────────────────────────────────────

elif page == "Portfolio":
    st.title("💼 Portfolio")

    portfolio = _get("/portfolio")

    if "error" in portfolio:
        st.warning(
            f"Portfolio unavailable: {portfolio['error']}\n\n"
            "Enable live trading (PAPER_TRADING=false) to see real portfolio data."
        )
    else:
        st.metric("Day P&L", f"₹{portfolio.get('day_pnl', 0):,.2f}")

        st.subheader("Margins")
        st.json(portfolio.get("margins", {}))

        st.subheader("Positions")
        positions = portfolio.get("positions", {})
        day_pos = positions.get("day", [])
        if day_pos:
            st.dataframe(pd.DataFrame(day_pos))
        else:
            st.info("No open positions.")

        st.subheader("Holdings")
        holdings = portfolio.get("holdings", [])
        if holdings:
            st.dataframe(pd.DataFrame(holdings))
        else:
            st.info("No holdings.")

# ── Page: Settings ────────────────────────────────────────────────────────────

elif page == "Settings":
    st.title("⚙️ Settings")

    st.subheader("Watchlist")
    status = _get("/status")
    current_watchlist = status.get("watchlist", [])
    new_symbols = st.text_area(
        "Symbols (one per line)",
        value="\n".join(current_watchlist),
    )

    if st.button("Update Watchlist"):
        symbols = [s.strip().upper() for s in new_symbols.splitlines() if s.strip()]
        res = _post("/watchlist", {"symbols": symbols})
        if "error" in res:
            st.error(res["error"])
        else:
            st.success(f"Watchlist updated: {', '.join(res.get('watchlist', []))}")
            st.cache_data.clear()

    st.subheader("API Connection")
    st.info(f"Connected to: `{API_BASE}`")
    if st.button("Test Connection"):
        health = _get("/")
        if "error" in health:
            st.error(f"Cannot reach API: {health['error']}")
        else:
            st.success(f"API is healthy: {health}")

    st.subheader("Auto-Refresh")
    auto_refresh = st.checkbox("Enable auto-refresh (every 60 seconds)", value=False)
    if auto_refresh:
        refresh_placeholder = st.empty()
        for remaining in range(60, 0, -1):
            refresh_placeholder.info(f"⏳ Auto-refresh in {remaining}s…")
            time.sleep(1)
        st.cache_data.clear()
        st.rerun()
