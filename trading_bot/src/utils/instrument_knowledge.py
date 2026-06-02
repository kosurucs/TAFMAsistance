"""
instrument_knowledge.py – Per-instrument knowledge cache + continuous LLM training data.

After every analysis the result is:
  1. Written to  trading_bot/data/knowledge/<SYMBOL>.json   (fast repeated lookup)
  2. Appended to llm_training/data/dataset/train.jsonl       (Alpaca-format training examples)

Cache freshness policy:
  - Fundamentals (from Yahoo Finance / screener) : 24 hours
  - A caller may pass ``max_age_hours=float("inf")`` to always use cache.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")

# Both paths live under llm_training/ so the training pipeline and the
# trading bot share the same local data store.
# __file__ = .../trading_bot/src/utils/instrument_knowledge.py
# parents[3] = workspace root
_LLM_TRAINING_DIR: Path = Path(__file__).resolve().parents[3] / "llm_training"

# Per-instrument knowledge cache
_KNOWLEDGE_DIR: Path = _LLM_TRAINING_DIR / "data" / "knowledge"

# Alpaca-format training dataset (grows with every analysis)
_TRAIN_FILE: Path = _LLM_TRAINING_DIR / "data" / "dataset" / "train.jsonl"

_LOCK = threading.Lock()


def _ensure_dirs() -> None:
    _KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    _TRAIN_FILE.parent.mkdir(parents=True, exist_ok=True)


# ── Write ─────────────────────────────────────────────────────────────────────

def save_analysis(
    symbol: str,
    analysis: dict[str, Any],
    compact_context: str,
    fundamentals_data: dict[str, Any] | None = None,
) -> None:
    """
    Persist the analysis result to:
      - knowledge cache  (JSON, per symbol)
      - training dataset (JSONL, Alpaca format)

    ``fundamentals_data`` is stored in the cache so future requests can skip
    re-fetching from external sources.
    """
    _ensure_dirs()
    sym = symbol.upper()
    ts  = datetime.now(_IST).isoformat()

    # ── Update knowledge cache ────────────────────────────────────────────────
    cache_path = _KNOWLEDGE_DIR / f"{sym}.json"
    with _LOCK:
        cache: dict[str, Any] = {}
        if cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                cache = {}

        cache["symbol"]           = sym
        cache["last_updated"]     = ts
        cache["last_analysis"]    = analysis
        cache["last_context"]     = compact_context
        if fundamentals_data is not None:
            cache["fundamentals_data"] = fundamentals_data

        cache_path.write_text(json.dumps(cache, indent=2, default=str), encoding="utf-8")

    # ── Append Alpaca-format training example ─────────────────────────────────
    action     = analysis.get("action", "WAIT")
    reason     = analysis.get("reason", "")
    confidence = analysis.get("confidence", 0)
    sl         = analysis.get("suggested_sl", 0.0)
    tp         = analysis.get("suggested_tp", 0.0)

    training_example = {
        "instruction": (
            f"Analyse the following market context for {sym} and provide a "
            "BUY, SELL, or WAIT recommendation with reasoning."
        ),
        "input": compact_context,
        "output": json.dumps({
            "action":       action,
            "reason":       reason,
            "confidence":   confidence,
            "suggested_sl": sl,
            "suggested_tp": tp,
        }),
        "timestamp": ts,
    }

    with _LOCK:
        with open(_TRAIN_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(training_example) + "\n")

    logger.info(
        "Knowledge saved | symbol={} action={} training_file={}",
        sym, action, _TRAIN_FILE,
    )


# ── Read ──────────────────────────────────────────────────────────────────────

def get_cached(
    symbol: str,
    max_age_hours: float = 24.0,
) -> Optional[dict[str, Any]]:
    """
    Return cached knowledge for *symbol* if it exists and is younger than
    ``max_age_hours``.  Returns ``None`` if not found or stale.
    """
    cache_path = _KNOWLEDGE_DIR / f"{symbol.upper()}.json"
    if not cache_path.exists():
        return None
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        raw_ts = cache.get("last_updated", "2000-01-01T00:00:00+00:00")
        last_updated = datetime.fromisoformat(raw_ts)
        # Make timezone-aware if naive
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=_IST)
        age = datetime.now(_IST) - last_updated
        if age < timedelta(hours=max_age_hours):
            return cache
        return None
    except Exception as exc:
        logger.debug(f"get_cached({symbol}): {exc}")
        return None


def list_cached_symbols() -> list[str]:
    """Return sorted list of symbols with a knowledge cache entry."""
    _ensure_dirs()
    return sorted(p.stem for p in _KNOWLEDGE_DIR.glob("*.json"))


def training_example_count() -> int:
    """Return the number of training examples accumulated so far."""
    if not _TRAIN_FILE.exists():
        return 0
    try:
        return sum(1 for line in _TRAIN_FILE.open(encoding="utf-8") if line.strip())
    except Exception:
        return 0
