"""
test_technical_analysis.py – Unit tests for the technical_analysis module.

Tests are designed to run without a live Kite connection by using synthetic
OHLCV DataFrames.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

# ── Module under test ─────────────────────────────────────────────────────────
from src.utils.technical_analysis import (
    BB_PERIOD,
    EMA_FAST,
    EMA_SLOW,
    RSI_PERIOD,
    _classify_bb_signal,
    _classify_trend,
    _safe_float,
    compute_indicators,
    format_market_state_prompt,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_ohlcv(n: int = 50, seed: int = 0) -> pd.DataFrame:
    """Return a synthetic OHLCV DataFrame with *n* rows."""
    rng = np.random.default_rng(seed)
    close = 1000 + np.cumsum(rng.normal(0, 5, n))
    return pd.DataFrame(
        {
            "open": close - rng.uniform(1, 3, n),
            "high": close + rng.uniform(2, 6, n),
            "low": close - rng.uniform(2, 6, n),
            "close": close,
            "volume": rng.integers(10_000, 100_000, n).astype(float),
        }
    )


# ── Tests: compute_indicators ─────────────────────────────────────────────────


class TestComputeIndicators:
    def test_returns_all_keys(self):
        df = make_ohlcv(50)
        result = compute_indicators(df)
        expected_keys = {
            "rsi", "ema_fast", "ema_slow", "bb_upper", "bb_middle",
            "bb_lower", "close", "volume", "trend", "bb_signal",
        }
        assert expected_keys.issubset(result.keys())

    def test_rsi_in_range(self):
        df = make_ohlcv(50)
        result = compute_indicators(df)
        assert 0.0 <= result["rsi"] <= 100.0

    def test_bb_ordering(self):
        df = make_ohlcv(50)
        result = compute_indicators(df)
        # Lower ≤ Middle ≤ Upper
        assert result["bb_lower"] <= result["bb_middle"] <= result["bb_upper"]

    def test_close_matches_last_row(self):
        df = make_ohlcv(50)
        result = compute_indicators(df)
        assert abs(result["close"] - float(df["close"].iloc[-1])) < 1e-6

    def test_raises_on_empty_df(self):
        with pytest.raises(ValueError, match="empty"):
            compute_indicators(pd.DataFrame())

    def test_volume_is_int(self):
        df = make_ohlcv(50)
        result = compute_indicators(df)
        assert isinstance(result["volume"], int)


# ── Tests: trend classification ───────────────────────────────────────────────


class TestClassifyTrend:
    def test_bullish(self):
        assert _classify_trend(110.0, 100.0) == "BULLISH"

    def test_bearish(self):
        assert _classify_trend(90.0, 100.0) == "BEARISH"

    def test_neutral_equal(self):
        assert _classify_trend(100.0, 100.0) == "NEUTRAL"

    def test_neutral_zero(self):
        assert _classify_trend(0.0, 100.0) == "NEUTRAL"


# ── Tests: Bollinger Band signal ──────────────────────────────────────────────


class TestClassifyBBSignal:
    def test_above_upper(self):
        assert _classify_bb_signal(105.0, 100.0, 90.0) == "ABOVE_UPPER"

    def test_below_lower(self):
        assert _classify_bb_signal(85.0, 100.0, 90.0) == "BELOW_LOWER"

    def test_inside(self):
        assert _classify_bb_signal(95.0, 100.0, 90.0) == "INSIDE"

    def test_zero_bands_returns_inside(self):
        assert _classify_bb_signal(100.0, 0.0, 0.0) == "INSIDE"

    def test_at_upper_boundary(self):
        assert _classify_bb_signal(100.0, 100.0, 90.0) == "ABOVE_UPPER"

    def test_at_lower_boundary(self):
        assert _classify_bb_signal(90.0, 100.0, 90.0) == "BELOW_LOWER"


# ── Tests: safe float ─────────────────────────────────────────────────────────


class TestSafeFloat:
    def test_normal_value(self):
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_nan_returns_zero(self):
        assert _safe_float(float("nan")) == 0.0

    def test_none_returns_zero(self):
        assert _safe_float(None) == 0.0

    def test_string_number(self):
        assert _safe_float("42.5") == pytest.approx(42.5)

    def test_non_numeric_string(self):
        assert _safe_float("abc") == 0.0


# ── Tests: format_market_state_prompt ────────────────────────────────────────


class TestFormatMarketStatePrompt:
    def test_contains_symbol(self):
        df = make_ohlcv(50)
        indicators = compute_indicators(df)
        prompt = format_market_state_prompt("NSE:RELIANCE", indicators)
        assert "NSE:RELIANCE" in prompt

    def test_contains_action_instruction(self):
        df = make_ohlcv(50)
        indicators = compute_indicators(df)
        prompt = format_market_state_prompt("INFY", indicators)
        assert "BUY" in prompt
        assert "SELL" in prompt
        assert "WAIT" in prompt

    def test_contains_all_indicator_labels(self):
        df = make_ohlcv(50)
        indicators = compute_indicators(df)
        prompt = format_market_state_prompt("TCS", indicators)
        for label in ("RSI", "EMA Fast", "EMA Slow", "BB Upper", "BB Lower", "Trend"):
            assert label in prompt, f"Missing label: {label}"
