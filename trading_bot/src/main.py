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

    _redis_client = redis_lib.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        db=int(os.environ.get("REDIS_DB", 0)),
        decode_responses=True,
        socket_connect_timeout=2,
    )
    _redis_client.ping()
    logger.info("Redis connected at {}:{}", os.environ.get("REDIS_HOST", "localhost"), os.environ.get("REDIS_PORT", 6379))
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
    """Return a LangChain Runnable backed by the fine-tuned local LLM.

    Falls back to a stub chain when the model weights are not present, so the
    rest of the pipeline can be exercised without a GPU.
    """
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

    logger.warning("LLM model not found – using WAIT-only stub chain.")
    return _StubLLMChain()


class _StubLLMChain:
    """Placeholder LLM that always returns WAIT.

    Used during development / paper-trading when no model weights are present.
    """

    def invoke(self, inputs: dict) -> str:  # noqa: ARG002
        return '{"action": "WAIT", "reason": "Stub LLM – no model loaded."}'


# ── Main loop ─────────────────────────────────────────────────────────────────

POLL_INTERVAL_SECONDS: int = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))


def run() -> None:
    """Main trading loop."""
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
        auth = KiteAuthManager()
        kite = auth.get_kite_session()
        data_fetcher = KiteDataFetcher(kite)
        portfolio = KitePortfolio(kite)
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

    # ── Trading loop ──────────────────────────────────────────────────────────
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
                "pipeline": DataPipeline(data_fetcher) if data_fetcher else _StubPipeline(symbol),
                "order_manager": order_manager,
                "portfolio": portfolio,
                "risk_manager": risk_mgr,
                "llm_chain": llm_chain,
            }

            try:
                result = trading_graph.invoke(initial_state)
                logger.info(
                    "{} | action={} | status={} | order_id={}",
                    symbol,
                    result.get("llm_action", "N/A"),
                    result.get("execution_status", "N/A"),
                    result.get("order_id"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Error processing {}: {}", symbol, exc)

        logger.info("Sleeping {} seconds until next cycle...", POLL_INTERVAL_SECONDS)
        time.sleep(POLL_INTERVAL_SECONDS)


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
