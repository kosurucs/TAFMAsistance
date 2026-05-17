"""
technical_analysis.py – Technical indicator calculations via pandas_ta.

Computes RSI, EMA, Bollinger Bands, MACD, VWAP, ATR, Stochastic, and more.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

try:
    import pandas_ta as ta  # type: ignore
except ImportError:  # pragma: no cover
    ta = None  # type: ignore


# ── Constants ─────────────────────────────────────────────────────────────────

RSI_PERIOD: int = 14
EMA_FAST: int = 9
EMA_SLOW: int = 21
EMA_MID: int = 50
EMA_LONG: int = 200
BB_PERIOD: int = 20
BB_STD: float = 2.0
MACD_FAST: int = 12
MACD_SLOW: int = 26
MACD_SIGNAL: int = 9
ATR_PERIOD: int = 14
STOCH_K: int = 14
STOCH_D: int = 3


# ── Public API ────────────────────────────────────────────────────────────────


def compute_indicators(df: pd.DataFrame) -> dict[str, Any]:
    """Calculate a full suite of technical indicators.

    Returns the *latest* values for:
        rsi, ema_fast, ema_slow, ema_50, ema_200,
        bb_upper, bb_middle, bb_lower,
        macd, macd_signal, macd_hist,
        vwap, atr, stoch_k, stoch_d,
        close, volume, trend, bb_signal, macd_signal_label, stoch_signal
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
    df[f"ema_{EMA_MID}"]  = ta.ema(df["close"], length=EMA_MID)
    df[f"ema_{EMA_LONG}"] = ta.ema(df["close"], length=EMA_LONG)

    # Bollinger Bands
    bb = ta.bbands(df["close"], length=BB_PERIOD, std=BB_STD)
    if bb is not None:
        df = pd.concat([df, bb], axis=1)

    # MACD
    macd_df = ta.macd(df["close"], fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    if macd_df is not None:
        df = pd.concat([df, macd_df], axis=1)

    # ATR
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=ATR_PERIOD)

    # Stochastic
    stoch_df = ta.stoch(df["high"], df["low"], df["close"], k=STOCH_K, d=STOCH_D)
    if stoch_df is not None:
        df = pd.concat([df, stoch_df], axis=1)

    # VWAP (requires intraday; gracefully skips if not available)
    try:
        df["vwap"] = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    except Exception:
        df["vwap"] = float("nan")

    # Pull latest row
    latest = df.iloc[-1]

    close = float(latest["close"])
    rsi = _safe_float(latest.get("rsi"))
    ema_fast  = _safe_float(latest.get(f"ema_{EMA_FAST}"))
    ema_slow  = _safe_float(latest.get(f"ema_{EMA_SLOW}"))
    ema_50    = _safe_float(latest.get(f"ema_{EMA_MID}"))
    ema_200   = _safe_float(latest.get(f"ema_{EMA_LONG}"))

    # BB column names vary by pandas_ta version
    bb_upper  = _safe_float(latest.get(f"BBU_{BB_PERIOD}_{BB_STD}") or latest.get("BBU"))
    bb_middle = _safe_float(latest.get(f"BBM_{BB_PERIOD}_{BB_STD}") or latest.get("BBM"))
    bb_lower  = _safe_float(latest.get(f"BBL_{BB_PERIOD}_{BB_STD}") or latest.get("BBL"))

    # MACD column names
    macd_val    = _safe_float(latest.get(f"MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}") or latest.get("MACD"))
    macd_sig    = _safe_float(latest.get(f"MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}") or latest.get("MACDs"))
    macd_hist   = _safe_float(latest.get(f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}") or latest.get("MACDh"))

    atr = _safe_float(latest.get("atr"))
    vwap = _safe_float(latest.get("vwap"))

    # Stochastic column names
    stoch_k_val = _safe_float(latest.get(f"STOCHk_{STOCH_K}_{STOCH_D}_3") or latest.get("STOCHk"))
    stoch_d_val = _safe_float(latest.get(f"STOCHd_{STOCH_K}_{STOCH_D}_3") or latest.get("STOCHd"))

    trend = _classify_trend(ema_fast, ema_slow)
    bb_signal = _classify_bb_signal(close, bb_upper, bb_lower)
    macd_label = _classify_macd(macd_val, macd_sig)
    stoch_signal = _classify_stoch(stoch_k_val)

    return {
        "close":        close,
        "volume":       int(latest.get("volume", 0)),
        # Momentum
        "rsi":          rsi,
        "stoch_k":      round(stoch_k_val, 1),
        "stoch_d":      round(stoch_d_val, 1),
        "stoch_signal": stoch_signal,
        # Trend / MA
        "ema_fast":     ema_fast,
        "ema_slow":     ema_slow,
        "ema_50":       ema_50,
        "ema_200":      ema_200,
        "trend":        trend,
        # MACD
        "macd":         round(macd_val, 4),
        "macd_signal":  round(macd_sig, 4),
        "macd_hist":    round(macd_hist, 4),
        "macd_label":   macd_label,
        # Volatility
        "bb_upper":     bb_upper,
        "bb_middle":    bb_middle,
        "bb_lower":     bb_lower,
        "bb_signal":    bb_signal,
        "atr":          round(atr, 2),
        # Volume / price
        "vwap":         round(vwap, 2) if vwap else 0.0,
    }


def compute_indicators_multi_timeframe(
    symbol: str,
    timeframe_dfs: dict[str, pd.DataFrame]
) -> dict[str, dict]:
    """
    Compute technical indicators for multiple timeframes.
    
    Args:
        symbol: NSE symbol (e.g. "RELIANCE")
        timeframe_dfs: dict mapping timeframe label → OHLCV DataFrame
                       e.g. {"1d": df_daily, "1h": df_hourly, "15min": df_15m}
    
    Returns:
        dict mapping timeframe → indicators dict (same shape as compute_indicators returns)
        Plus a top-level "confluence" key with aggregate scores.
    """
    result = {}
    for tf, df in timeframe_dfs.items():
        if df is not None and len(df) >= 20:
            try:
                result[tf] = compute_indicators(df)
            except Exception as e:
                logger.warning(f"MTF indicators failed for {symbol} {tf}: {e}")
                result[tf] = {}
        else:
            result[tf] = {}
    
    # Compute MTF confluence score
    bullish_count = 0
    bearish_count = 0
    total_tfs = len([tf for tf in result if result[tf]])
    
    for tf, ind in result.items():
        if not ind:
            continue
        ema_fast = ind.get("ema_fast", 0)
        ema_slow = ind.get("ema_slow", 0)
        if ema_fast > ema_slow:
            bullish_count += 1
        elif ema_fast < ema_slow:
            bearish_count += 1
    
    result["confluence"] = {
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "total_timeframes": total_tfs,
        "score": bullish_count - bearish_count,  # positive = bullish bias
        "bias": "BULLISH" if bullish_count > bearish_count else ("BEARISH" if bearish_count > bullish_count else "NEUTRAL"),
    }
    return result


def format_mtf_section(mtf_indicators: dict[str, dict]) -> str:
    """
    Format multi-timeframe indicator data as a string section for the LLM prompt.
    Returns a formatted multi-line string like:
    
    Multi-Timeframe Analysis:
      1D  : EMA9=2450 > EMA21=2380 → BULLISH | RSI=62 | MACD Bullish
      1h  : EMA9=2440 < EMA21=2460 → BEARISH | RSI=44 | MACD Bearish
      15min: EMA9=2448 > EMA21=2435 → BULLISH | RSI=58 | MACD Neutral
    MTF Confluence: 2/3 BULLISH (score: +1) → Bias: BULLISH
    """
    lines = ["Multi-Timeframe Analysis:"]
    tf_order = ["1d", "1h", "15min", "5min", "1min"]
    
    for tf in tf_order:
        if tf not in mtf_indicators or not mtf_indicators[tf]:
            continue
        ind = mtf_indicators[tf]
        ema9 = ind.get("ema_fast", 0)
        ema21 = ind.get("ema_slow", 0)
        trend = "BULLISH" if ema9 > ema21 else "BEARISH"
        rsi = ind.get("rsi", 50)
        macd_line = ind.get("macd", 0)
        macd_signal = ind.get("macd_signal", 0)
        macd_bias = "Bullish" if macd_line > macd_signal else "Bearish"
        lines.append(
            f"  {tf:<6}: EMA9={ema9:.0f} {'>' if ema9>ema21 else '<'} EMA21={ema21:.0f} → {trend}"
            f" | RSI={rsi:.0f} | MACD {macd_bias}"
        )
    
    conf = mtf_indicators.get("confluence", {})
    if conf:
        lines.append(
            f"MTF Confluence: {conf['bullish_count']}/{conf['total_timeframes']} BULLISH"
            f" (score: {conf['score']:+d}) → Bias: {conf['bias']}"
        )
    
    return "\n".join(lines)


def format_market_state_prompt(
    symbol: str,
    indicators: dict[str, Any],
    mtf_indicators: dict | None = None
) -> str:
    """Render a structured prompt string for the LLM."""
    prompt = (
        f"Instruction: Analyse the current market state for {symbol}.\n"
        f"Market State:\n"
        f"  - Close Price  : {indicators['close']:.2f}\n"
        f"  - RSI ({RSI_PERIOD})      : {indicators['rsi']:.2f}\n"
        f"  - Stoch K/D    : {indicators['stoch_k']:.1f} / {indicators['stoch_d']:.1f} ({indicators['stoch_signal']})\n"
        f"  - EMA Fast ({EMA_FAST})  : {indicators['ema_fast']:.2f}\n"
        f"  - EMA Slow ({EMA_SLOW})  : {indicators['ema_slow']:.2f}\n"
        f"  - EMA 50       : {indicators['ema_50']:.2f}\n"
        f"  - EMA 200      : {indicators['ema_200']:.2f}\n"
        f"  - MACD         : {indicators['macd']:.4f} / Signal: {indicators['macd_signal']:.4f} ({indicators['macd_label']})\n"
        f"  - BB Upper     : {indicators['bb_upper']:.2f}\n"
        f"  - BB Middle    : {indicators['bb_middle']:.2f}\n"
        f"  - BB Lower     : {indicators['bb_lower']:.2f}\n"
        f"  - ATR ({ATR_PERIOD})      : {indicators['atr']:.2f}\n"
        f"  - VWAP         : {indicators['vwap']:.2f}\n"
        f"  - Trend        : {indicators['trend']}\n"
        f"  - BB Signal    : {indicators['bb_signal']}\n"
    )
    
    if mtf_indicators:
        prompt += "\n" + format_mtf_section(mtf_indicators) + "\n"
    
    prompt += (
        f"Output: Respond ONLY with valid JSON of the form "
        '{"action": "BUY"|"SELL"|"WAIT", "reason": "<one sentence>"}'
    )
    return prompt


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


def _classify_macd(macd_val: float, macd_sig: float) -> str:
    """Classify MACD crossover signal."""
    if macd_val == 0.0 and macd_sig == 0.0:
        return "NEUTRAL"
    if macd_val > macd_sig:
        return "BULLISH"
    if macd_val < macd_sig:
        return "BEARISH"
    return "NEUTRAL"


def _classify_stoch(k: float) -> str:
    """Classify Stochastic %K signal."""
    if k == 0.0:
        return "NEUTRAL"
    if k >= 80:
        return "OVERBOUGHT"
    if k <= 20:
        return "OVERSOLD"
    return "NEUTRAL"
