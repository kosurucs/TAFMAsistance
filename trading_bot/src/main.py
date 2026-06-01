"""
main.py – Entry point for the autonomous AI trading agent.

Usage::

    # Paper-trading mode (default)
    python src/main.py

    # Activate the manual kill switch
    python src/main.py --kill

    # Deactivate the kill switch
    python src/main.py --unkill

Environment variables are loaded from a `.env` file in the current working
directory (or from the shell environment).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

# Load .env before any other imports that read os.environ
load_dotenv()

# ── Optional Redis ────────────────────────────────────────────────────────────
try:
    import redis as redis_lib
    import socket

    _redis_client = redis_lib.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        db=int(os.environ.get("REDIS_DB", 0)),
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    # Test connection with a shorter timeout using socket check first
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((os.environ.get("REDIS_HOST", "localhost"), int(os.environ.get("REDIS_PORT", 6379))))
        sock.close()
        _redis_client.ping()
        logger.info("Redis connected at {}:{}", os.environ.get("REDIS_HOST", "localhost"), os.environ.get("REDIS_PORT", 6379))
    except (socket.timeout, socket.error, ConnectionRefusedError):
        raise RuntimeError("Redis not reachable")
except Exception:  # noqa: BLE001
    logger.warning("Redis not available – using in-process state only.")
    _redis_client = None  # type: ignore

# ── Internal imports ──────────────────────────────────────────────────────────
from src.agents.trading_agent import TradingState, build_trading_graph
from src.tools.kite_tools import KiteAuthManager, KiteDataFetcher, KiteOrderManager, KitePortfolio
from src.tools.data_pipeline import DataPipeline
from src.utils.risk_manager import RiskManager

# ── LLM chain setup ───────────────────────────────────────────────────────────
PAPER_TRADING: bool = os.environ.get("PAPER_TRADING", "true").lower() == "true"


def _build_llm_chain():
    """Return a LangChain Runnable backed by Ollama (trading-assistant model).

    Priority:
      1. Ollama 'trading-assistant' if Ollama is running
      2. Ollama 'mistral' fallback
      3. Fine-tuned local HuggingFace model (GPU required)
      4. WAIT-only stub
    """
    # ── Try Ollama first (no GPU needed) ─────────────────────────────────────
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    
    # Quick socket check to avoid hanging on urlopen
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect(("localhost", 11434))
        sock.close()
    except (socket.timeout, socket.error, ConnectionRefusedError, OSError):
        logger.warning("Ollama not reachable at {} – skipping to fallback LLM", ollama_url)
    else:
        for model_name in ("trading-assistant", "mistral"):
            try:
                import urllib.request as _ureq, json as _json
                probe = _ureq.Request(
                    f"{ollama_url}/api/tags",
                    headers={"Content-Type": "application/json"},
                )
                resp = _ureq.urlopen(probe, timeout=2)
                tags = _json.loads(resp.read().decode())
                available = [m["name"].split(":")[0] for m in tags.get("models", [])]
                if model_name in available or model_name == "mistral":
                    chain = _OllamaLLMChain(ollama_url, model_name)
                    # Quick connectivity check
                    chain.invoke({"input": "ping"})
                    logger.info("Using Ollama model '{}' at {}", model_name, ollama_url)
                    return chain
            except Exception:  # noqa: BLE001
                break

    # ── Try fine-tuned local HuggingFace model (requires GPU) ────────────────
    model_path = os.environ.get("LLM_MODEL_PATH", "models/trading-lora-adapter")
    if Path(model_path).exists():
        logger.info("Loading fine-tuned LLM from {}...", model_path)
        try:
            from langchain_community.llms import HuggingFacePipeline  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline  # type: ignore
            import torch  # type: ignore
            from peft import PeftModel  # type: ignore

            base_model_id = os.environ.get("LLM_BASE_MODEL", "meta-llama/Meta-Llama-3-8B")
            tokenizer = AutoTokenizer.from_pretrained(base_model_id)
            base_model = AutoModelForCausalLM.from_pretrained(
                base_model_id,
                load_in_4bit=True,
                device_map="auto",
                torch_dtype=torch.float16,
            )
            model = PeftModel.from_pretrained(base_model, model_path)
            pipe = pipeline(
                "text-generation",
                model=model,
                tokenizer=tokenizer,
                max_new_tokens=128,
                temperature=0.1,
            )
            return HuggingFacePipeline(pipeline=pipe)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load fine-tuned LLM ({}). Using stub.", exc)

    logger.warning("No LLM available – using WAIT-only stub chain. Start Ollama for AI decisions.")
    return _StubLLMChain()


class _OllamaLLMChain:
    """LLM chain that calls a local Ollama model for trading decisions."""

    _SYSTEM = (
        "You are an expert algorithmic trading assistant. "
        "Analyse the provided market state and respond with a JSON object only. "
        "Format: {\"action\": \"BUY\" | \"SELL\" | \"WAIT\", \"reason\": \"<one sentence>\"}. "
        "Only recommend BUY/SELL when there is a strong technical signal. Default to WAIT."
    )

    def __init__(self, base_url: str, model: str) -> None:
        self._url = f"{base_url}/api/generate"
        self._model = model

    def invoke(self, inputs: dict) -> str:
        import json as _json, urllib.request as _ureq
        prompt = inputs.get("input", "")
        full_prompt = f"{self._SYSTEM}\n\n{prompt}"
        data = _json.dumps({
            "model": self._model,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 128},
        }).encode()
        req = _ureq.Request(self._url, data=data, headers={"Content-Type": "application/json"})
        with _ureq.urlopen(req, timeout=30) as r:
            body = _json.loads(r.read().decode())
            return body.get("response", '{"action":"WAIT","reason":"No response"}')


class _StubLLMChain:
    """Placeholder LLM that always returns WAIT.

    Used during development / paper-trading when no model weights are present.
    """

    def invoke(self, inputs: dict) -> str:  # noqa: ARG002
        return '{"action": "WAIT", "reason": "Stub LLM – no model loaded."}'


# ── Main loop ─────────────────────────────────────────────────────────────────

POLL_INTERVAL_SECONDS: int = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))


async def monitor_positions(
    portfolio: Any,
    order_manager: Any,
    data_pipeline_factory: Any,
    risk_manager: Any,
) -> None:
    """
    Background coroutine: runs every 30 seconds.
    Checks open positions via ExitMonitor and places exit orders if triggered.
    """
    import asyncio
    from src.utils.exit_monitor import ExitMonitor
    
    logger.info("Starting position monitor (interval=30s)")
    
    while True:
        try:
            # Check kill switch
            if risk_manager.is_kill_switch_active():
                logger.warning("Position monitor: kill switch active, stopping.")
                break
            
            # Skip monitoring if no portfolio (paper trading without positions)
            if portfolio is None:
                await asyncio.sleep(30)
                continue
            
            # Get open positions
            positions_data = portfolio.get_positions()
            # Kite returns dict with 'day' and 'net' keys
            day_positions = positions_data.get("day", [])
            net_positions = positions_data.get("net", [])
            all_positions = day_positions + net_positions
            
            if not all_positions:
                await asyncio.sleep(30)
                continue
            
            # Normalize position structure for ExitMonitor
            normalized_positions = []
            for pos in all_positions:
                # Map Kite position fields to ExitMonitor expected fields
                tradingsymbol = pos.get("tradingsymbol", "")
                quantity = pos.get("quantity", 0)
                if quantity == 0:
                    continue
                
                # Determine action based on quantity sign
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
                    "beta": 1.0,  # TODO: fetch from metadata
                })
            
            if not normalized_positions:
                await asyncio.sleep(30)
                continue
            
            # Fetch indicators for each position
            indicators_by_symbol = {}
            for pos in normalized_positions:
                symbol = pos["symbol"]
                try:
                    # Use the same pipeline factory as main loop
                    pipeline = data_pipeline_factory(symbol)
                    df = pipeline.get_ohlcv_df(
                        tradingsymbol=symbol,
                        interval="minute",
                        days_back=1,
                    )
                    if df is not None and len(df) > 14:
                        from src.utils.technical_analysis import compute_indicators
                        indicators = compute_indicators(df)
                        indicators_by_symbol[symbol] = indicators
                except Exception as e:
                    logger.warning(f"Could not fetch indicators for {symbol}: {e}")
            
            # Nifty change (approximate — use NIFTY50 if available)
            nifty_change_pct = 0.0
            
            # Check exits
            monitor = ExitMonitor()
            results = monitor.check_all_positions(normalized_positions, indicators_by_symbol, nifty_change_pct)
            
            for r in results:
                signal = r["exit_signal"]
                if signal.should_exit:
                    symbol = r["symbol"]
                    # Reverse action to close position
                    original_action = r["action"]
                    exit_action = "SELL" if original_action == "BUY" else "BUY"
                    logger.warning(f"AUTO-EXIT triggered for {symbol}: {signal.reason}")
                    
                    paper_trade = os.getenv("PAPER_TRADING", "false").lower() == "true"
                    position = r.get("position", {})
                    exit_price = position.get("current_price", 0.0)
                    pnl = position.get("pnl", 0.0)
                    
                    # ANALYSIS-ONLY MODE: Log the exit signal but do NOT place orders
                    logger.info(f"[ANALYSIS] Would exit {symbol} with {exit_action} @ market — reason: {signal.reason} (order placement disabled)")
                    
                    # Log exit to DB (non-blocking — degrades gracefully if DB unavailable)
                    from src.utils.db_logger import get_db_logger
                    db = get_db_logger()
                    db.log_trade_exit(
                        order_id=position.get("order_id", "UNKNOWN"),
                        exit_price=exit_price,
                        exit_reason=signal.reason,
                        pnl=pnl,
                    )
                
                elif signal.adjusted_sl is not None:
                    logger.info(f"TRAILING STOP updated for {r['symbol']}: new SL = {signal.adjusted_sl:.2f}")
                    # TODO: Update position SL in database/state
        
        except Exception as e:
            logger.error(f"Position monitor error: {e}")
        
        await asyncio.sleep(30)


async def async_run() -> None:
    """Main trading loop (async version)."""
    logger.info("Starting trading bot (paper={})", PAPER_TRADING)

    watchlist = [
        s.strip()
        for s in os.environ.get("WATCHLIST", "RELIANCE").split(",")
        if s.strip()
    ]
    exchange = os.environ.get("EXCHANGE", "NSE")

    # ── Authentication (skip in pure paper-trading mode without Kite creds) ──
    kite = None
    data_fetcher = None
    portfolio = None

    if not PAPER_TRADING:
        # Validate Kite authentication before starting
        from datetime import datetime
        from zoneinfo import ZoneInfo
        _IST = ZoneInfo('Asia/Kolkata')
        
        access_token = os.environ.get("KITE_ACCESS_TOKEN", "").strip()
        timestamp_str = os.environ.get("KITE_TOKEN_TIMESTAMP", "").strip()
        
        # Check if token exists
        if not access_token:
            logger.critical("KITE_ACCESS_TOKEN not found in .env file!")
            logger.critical("Please authenticate via the UI:")
            logger.critical("  1. Open http://localhost:5173/login")
            logger.critical("  2. Enter your API credentials (if first time)")
            logger.critical("  3. Click 'Login with Zerodha'")
            logger.critical("  4. Complete the login and return to this page")
            logger.critical("  5. The access token will be automatically saved")
            sys.exit(1)
        
        # Check token expiration (24 hours)
        token_expired = True
        if timestamp_str:
            try:
                from dateutil import parser
                token_time = parser.isoparse(timestamp_str)
                if token_time.tzinfo is None:
                    token_time = token_time.replace(tzinfo=_IST)
                age = datetime.now(_IST) - token_time
                token_expired = age.total_seconds() > (24 * 60 * 60 - 300)
            except Exception:
                pass
        
        if token_expired:
            logger.critical("KITE_ACCESS_TOKEN has expired (>24 hours old)!")
            logger.critical("Please re-authenticate via the UI:")
            logger.critical("  1. Open http://localhost:5173/login")
            logger.critical("  2. Click 'Login with Zerodha'")
            logger.critical("  3. Complete the login")
            logger.critical("  4. A fresh token will be automatically saved")
            sys.exit(1)
        
        # Validate token by attempting to create session
        logger.info("Validating Kite access token...")
        try:
            auth = KiteAuthManager()
            kite = auth.get_kite_session()
            # Test the connection
            profile = kite.profile()
            logger.success("✓ Kite authentication valid for user: {}", profile.get("user_name", "Unknown"))
            data_fetcher = KiteDataFetcher(kite)
            portfolio = KitePortfolio(kite)
        except Exception as exc:
            logger.critical("Kite authentication failed: {}", exc)
            logger.critical("Your access token may be invalid or revoked.")
            logger.critical("Please re-authenticate via the UI:")
            logger.critical("  1. Open http://localhost:5173/login")
            logger.critical("  2. Click 'Login with Zerodha'")
            sys.exit(1)
    else:
        logger.info("Paper-trading mode – Kite API calls will be simulated.")

    order_manager = KiteOrderManager(kite=kite)

    # ── Risk manager ──────────────────────────────────────────────────────────
    opening_capital = float(os.environ.get("OPENING_CAPITAL", "100000"))
    risk_mgr = RiskManager(
        opening_capital=opening_capital,
        redis_client=_redis_client,
    )

    # ── Build LangGraph ───────────────────────────────────────────────────────
    trading_graph = build_trading_graph()
    llm_chain = _build_llm_chain()

    # ── Per-symbol instrument token lookup ────────────────────────────────────
    instrument_tokens: dict[str, int] = {}
    if data_fetcher is not None:
        for sym in watchlist:
            try:
                token = data_fetcher.lookup_instrument_token(exchange, sym)
                instrument_tokens[sym] = token
            except KeyError:
                logger.warning("Could not find instrument token for {}.", sym)
    else:
        # In paper-trading mode, use a dummy token
        instrument_tokens = {sym: 0 for sym in watchlist}

    logger.info("Watchlist: {}", instrument_tokens)

    # ── Data pipeline factory for position monitor ───────────────────────────
    def make_pipeline(symbol: str) -> Any:
        return DataPipeline(data_fetcher) if data_fetcher else _StubPipeline(symbol)

    # ── Trading loop ──────────────────────────────────────────────────────────
    async def trading_loop() -> None:
        """Main trading decision loop."""
        import asyncio
        while True:
            if risk_mgr.is_kill_switch_active():
                logger.critical("Kill switch active – halting all trading.")
                break

            for symbol, token in instrument_tokens.items():
                logger.info("─── Processing {} ───", symbol)

                initial_state: TradingState = {
                    "symbol": symbol,
                    "instrument_token": token,
                    "exchange": exchange,
                    "pipeline": make_pipeline(symbol),
                    "order_manager": order_manager,
                    "portfolio": portfolio,
                    "risk_manager": risk_mgr,
                    "llm_chain": llm_chain,
                }

                try:
                    result = trading_graph.invoke(initial_state)

                    # ── Log market data & indicators ──────────────────────────
                    ind = result.get("indicators", {})
                    if ind:
                        logger.info(
                            "{} | close={:.2f} | RSI={:.1f} | EMA9={:.2f} | EMA21={:.2f}"
                            " | BB_upper={:.2f} | BB_lower={:.2f} | trend={} | bb_signal={}",
                            symbol,
                            ind.get("close", 0),
                            ind.get("rsi", 0),
                            ind.get("ema_fast", 0),
                            ind.get("ema_slow", 0),
                            ind.get("bb_upper", 0),
                            ind.get("bb_lower", 0),
                            ind.get("trend", "N/A"),
                            ind.get("bb_signal", "N/A"),
                        )

                    logger.info(
                        "{} | action={} | reason={} | status={} | order_id={}",
                        symbol,
                        result.get("llm_action", "N/A"),
                        result.get("llm_reason", ""),
                        result.get("execution_status", "N/A"),
                        result.get("order_id"),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("Error processing {}: {}", symbol, exc)

            logger.info("Sleeping {} seconds until next cycle...", POLL_INTERVAL_SECONDS)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    
    # ── Run both loops concurrently ───────────────────────────────────────────
    import asyncio
    try:
        await asyncio.gather(
            trading_loop(),
            monitor_positions(portfolio, order_manager, make_pipeline, risk_mgr),
        )
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down gracefully...")


def run() -> None:
    """Synchronous entry point that runs the async main loop."""
    import asyncio
    asyncio.run(async_run())


# ── Stub data pipeline (paper-trading mode without Kite) ─────────────────────


class _StubPipeline:
    """Minimal stub that returns synthetic OHLCV data for testing."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def get_ohlcv_df(
        self,
        instrument_token: int = 0,
        tradingsymbol: str = "",
        interval: str = "minute",
        days_back: int = 1,
        use_cache: bool = False,
    ) -> Any:
        import numpy as np
        import pandas as pd

        n = 50
        rng = np.random.default_rng(42)
        prices = 1000 + np.cumsum(rng.normal(0, 5, n))
        return pd.DataFrame(
            {
                "open": prices,
                "high": prices + rng.uniform(1, 5, n),
                "low": prices - rng.uniform(1, 5, n),
                "close": prices + rng.normal(0, 2, n),
                "volume": rng.integers(10_000, 100_000, n),
            }
        )

    def fetch_latest_quote(self, symbols: list[str]) -> dict[str, Any]:
        return {s: {"last_price": 1000.0} for s in symbols}


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autonomous AI Trading Agent")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--kill",
        action="store_true",
        help="Activate the manual kill switch and exit.",
    )
    group.add_argument(
        "--unkill",
        action="store_true",
        help="Deactivate the kill switch and exit.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.kill:
        _rm = RiskManager(opening_capital=0, redis_client=_redis_client)
        _rm.activate_kill_switch()
        logger.info("Kill switch activated. Exiting.")
        sys.exit(0)

    if args.unkill:
        _rm = RiskManager(opening_capital=0, redis_client=_redis_client)
        _rm.deactivate_kill_switch()
        logger.info("Kill switch deactivated. Exiting.")
        sys.exit(0)

    run()
