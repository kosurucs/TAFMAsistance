"""
dependencies.py – Shared FastAPI dependency-injection singletons.

All heavy objects (LLM chain, Kite session, RiskManager, …) are built once at
startup and then injected into route handlers via ``Depends()``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ── Optional Redis ─────────────────────────────────────────────────────────────
try:
    import redis as redis_lib

    _redis_client: Any = redis_lib.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        db=int(os.environ.get("REDIS_DB", 0)),
        decode_responses=True,
        socket_connect_timeout=2,
    )
    _redis_client.ping()
    logger.info(
        "API – Redis connected at {}:{}",
        os.environ.get("REDIS_HOST", "localhost"),
        os.environ.get("REDIS_PORT", 6379),
    )
except Exception:  # noqa: BLE001
    logger.warning("API – Redis not available; using in-process state only.")
    _redis_client = None

# ── Kite session (optional – only in live trading) ────────────────────────────
from src.tools.kite_tools import KiteAuthManager, KiteDataFetcher, KiteOrderManager, KitePortfolio  # noqa: E402
from src.utils.risk_manager import RiskManager  # noqa: E402

PAPER_TRADING: bool = os.environ.get("PAPER_TRADING", "true").lower() == "true"
OPENING_CAPITAL: float = float(os.environ.get("OPENING_CAPITAL", "100000"))

_kite: Any = None
_data_fetcher: KiteDataFetcher | None = None
_portfolio: KitePortfolio | None = None

if not PAPER_TRADING:
    try:
        _auth = KiteAuthManager()
        _kite = _auth.get_kite_session()
        _data_fetcher = KiteDataFetcher(_kite)
        _portfolio = KitePortfolio(_kite)
        logger.info("API – Kite session established.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("API – Could not init Kite session: {}", exc)

_order_manager: KiteOrderManager = KiteOrderManager(kite=_kite)
_risk_manager: RiskManager = RiskManager(
    opening_capital=OPENING_CAPITAL,
    redis_client=_redis_client,
)


# ── Watchlist (mutable in-process state) ──────────────────────────────────────
_watchlist: list[str] = [
    s.strip()
    for s in os.environ.get("WATCHLIST", "RELIANCE").split(",")
    if s.strip()
]


# ── LLM chain ─────────────────────────────────────────────────────────────────
def _build_llm_chain() -> Any:
    model_path = os.environ.get("LLM_MODEL_PATH", "models/trading-lora-adapter")
    if Path(model_path).exists():
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
            logger.info("API – LLM loaded from {}.", model_path)
            return HuggingFacePipeline(pipeline=pipe)
        except Exception as exc:  # noqa: BLE001
            logger.warning("API – Could not load fine-tuned LLM ({}). Using stub.", exc)

    logger.warning("API – LLM model not found; using WAIT-only stub.")
    return _StubLLMChain()


class _StubLLMChain:
    def invoke(self, inputs: dict) -> str:  # noqa: ARG002
        return '{"action": "WAIT", "reason": "Stub LLM – no model loaded."}'


_llm_chain: Any = _build_llm_chain()


# ── FastAPI dependency functions ───────────────────────────────────────────────

def get_redis() -> Any:
    return _redis_client


def get_risk_manager() -> RiskManager:
    return _risk_manager


def get_order_manager() -> KiteOrderManager:
    return _order_manager


def get_portfolio() -> KitePortfolio | None:
    return _portfolio


def get_data_fetcher() -> KiteDataFetcher | None:
    return _data_fetcher


def get_llm_chain() -> Any:
    return _llm_chain


def get_watchlist() -> list[str]:
    return _watchlist


def set_watchlist(symbols: list[str]) -> None:
    global _watchlist
    _watchlist = [s.strip().upper() for s in symbols if s.strip()]
