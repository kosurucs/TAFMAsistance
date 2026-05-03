"""
technical_analysis.py – Technical indicator calculations via pandas_ta.

Computes RSI, EMA (fast/slow), and Bollinger Bands on a price DataFrame and
returns a structured dict that can be passed directly to the LLM prompt.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

try:
    import pandas_ta as ta  # type: ignore
except ImportError:  # pragma: no cover
    ta = None  # type: ignore


# ── Constants ─────────────────────────────────────────────────────────────────

RSI_PERIOD: int = 14
EMA_FAST: int = 9
EMA_SLOW: int = 21
BB_PERIOD: int = 20
BB_STD: float = 2.0


# ── Public API ────────────────────────────────────────────────────────────────


def compute_indicators(df: pd.DataFrame) -> dict[str, Any]:
    """Calculate RSI, EMA (fast/slow), and Bollinger Bands.

    Args:
        df: OHLCV DataFrame with columns ``open, high, low, close, volume``
            and a datetime index.  Must have at least ``BB_PERIOD`` (20) rows.

    Returns:
        Dict containing the *latest* values for every indicator:

        .. code-block:: python

            {
                "rsi":        float,   # 0-100
                "ema_fast":   float,   # EMA-9
                "ema_slow":   float,   # EMA-21
                "bb_upper":   float,
                "bb_middle":  float,
                "bb_lower":   float,
                "close":      float,   # last close price
                "volume":     int,
                "trend":      str,     # "BULLISH" | "BEARISH" | "NEUTRAL"
                "bb_signal":  str,     # "ABOVE_UPPER" | "BELOW_LOWER" | "INSIDE"
            }
    """
    if ta is None:
        raise RuntimeError(
            "pandas_ta is not installed. Run: pip install pandas-ta"
        )

    if df.empty:
        raise ValueError("DataFrame is empty – cannot compute indicators.")

    df = df.copy()

    # RSI
    df["rsi"] = ta.rsi(df["close"], length=RSI_PERIOD)

    # EMAs
    df[f"ema_{EMA_FAST}"] = ta.ema(df["close"], length=EMA_FAST)
    df[f"ema_{EMA_SLOW}"] = ta.ema(df["close"], length=EMA_SLOW)

    # Bollinger Bands  (pandas_ta returns BBL_*, BBM_*, BBU_* columns)
    bb = ta.bbands(df["close"], length=BB_PERIOD, std=BB_STD)
    if bb is not None:
        df = pd.concat([df, bb], axis=1)

    # Pull latest row, dropping any NaN indicators
    latest = df.iloc[-1]

    close = float(latest["close"])
    rsi = _safe_float(latest.get("rsi"))
    ema_fast = _safe_float(latest.get(f"ema_{EMA_FAST}"))
    ema_slow = _safe_float(latest.get(f"ema_{EMA_SLOW}"))

    # Bollinger Band column names vary by pandas_ta version
    bb_upper = _safe_float(
        latest.get(f"BBU_{BB_PERIOD}_{BB_STD}") or latest.get("BBU")
    )
    bb_middle = _safe_float(
        latest.get(f"BBM_{BB_PERIOD}_{BB_STD}") or latest.get("BBM")
    )
    bb_lower = _safe_float(
        latest.get(f"BBL_{BB_PERIOD}_{BB_STD}") or latest.get("BBL")
    )

    trend = _classify_trend(ema_fast, ema_slow)
    bb_signal = _classify_bb_signal(close, bb_upper, bb_lower)

    return {
        "rsi": rsi,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "bb_upper": bb_upper,
        "bb_middle": bb_middle,
        "bb_lower": bb_lower,
        "close": close,
        "volume": int(latest.get("volume", 0)),
        "trend": trend,
        "bb_signal": bb_signal,
    }


def format_market_state_prompt(
    symbol: str,
    indicators: dict[str, Any],
) -> str:
    """Render a structured prompt string for the LLM.

    Args:
        symbol: Instrument symbol, e.g. ``"NSE:RELIANCE"``.
        indicators: Output of :func:`compute_indicators`.

    Returns:
        A formatted Instruction string ready to be appended to the LLM context.
    """
    return (
        f"Instruction: Analyse the current market state for {symbol}.\n"
        f"Market State:\n"
        f"  - Close Price  : {indicators['close']:.2f}\n"
        f"  - RSI ({RSI_PERIOD})      : {indicators['rsi']:.2f}\n"
        f"  - EMA Fast ({EMA_FAST})  : {indicators['ema_fast']:.2f}\n"
        f"  - EMA Slow ({EMA_SLOW})  : {indicators['ema_slow']:.2f}\n"
        f"  - BB Upper     : {indicators['bb_upper']:.2f}\n"
        f"  - BB Middle    : {indicators['bb_middle']:.2f}\n"
        f"  - BB Lower     : {indicators['bb_lower']:.2f}\n"
        f"  - Trend        : {indicators['trend']}\n"
        f"  - BB Signal    : {indicators['bb_signal']}\n"
        f"Output: Respond ONLY with valid JSON of the form "
        '{"action": "BUY"|"SELL"|"WAIT", "reason": "<one sentence>"}'
    )


# ── Internal helpers ──────────────────────────────────────────────────────────


def _safe_float(value: Any) -> float:
    """Return float or NaN-safe 0.0."""
    try:
        v = float(value)
        return v if not pd.isna(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _classify_trend(ema_fast: float, ema_slow: float) -> str:
    """Simple EMA crossover trend classification."""
    if ema_fast == 0.0 or ema_slow == 0.0:
        return "NEUTRAL"
    if ema_fast > ema_slow:
        return "BULLISH"
    if ema_fast < ema_slow:
        return "BEARISH"
    return "NEUTRAL"


def _classify_bb_signal(close: float, bb_upper: float, bb_lower: float) -> str:
    """Classify price position relative to Bollinger Bands."""
    if bb_upper == 0.0 or bb_lower == 0.0:
        return "INSIDE"
    if close >= bb_upper:
        return "ABOVE_UPPER"
    if close <= bb_lower:
        return "BELOW_LOWER"
    return "INSIDE"
