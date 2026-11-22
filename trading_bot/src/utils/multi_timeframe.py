"""
multi_timeframe.py — Multi-timeframe data orchestrator.

Fetches OHLCV data for 4 timeframes (1m, 15m, 1h, 1D) and computes
confluence score. Used by the algo engine to meet v1.0 design requirements.

Key constraints:
- Fetch last 200 candles per timeframe (not full history)
- Compute indicators per timeframe
- Return confluence score (aligned count / 4)
- Bias: BULLISH if ≥ 3 timeframes bullish, BEARISH if ≥ 3 bearish, else NEUTRAL
"""
from __future__ import annotations

from typing import Any
import pandas as pd
from loguru import logger

from src.utils.technical_analysis import compute_indicators


# Timeframe configuration: (interval_name, days_back_estimate)
# We request 200 candles; days_back is a guideline for the data pipeline
TIMEFRAMES = {
    "1m":   ("minute",   1),    # 200 × 1min = ~200 minutes = ~1 trading day
    "15m":  ("15minute", 3),    # 200 × 15min = 3000 minutes = ~5 trading days
    "1h":   ("60minute", 12),   # 200 × 1h = 200 hours = ~25 trading days
    "1D":   ("day",      200),  # 200 × 1D = 200 trading days = ~10 months
}


def fetch_multi_timeframe(
    pipeline: Any,
    token: int,
    symbol: str,
    exchange: str = "NSE",
) -> dict[str, pd.DataFrame]:
    """
    Fetch OHLCV data for all 4 timeframes (last 200 candles each).

    Args:
        pipeline: DataPipeline instance
        token: Instrument token
        symbol: Trading symbol
        exchange: Exchange (default: NSE)

    Returns:
        dict mapping timeframe label → DataFrame
        e.g. {"1m": df_1m, "15m": df_15m, "1h": df_1h, "1D": df_1d}
    """
    result = {}
    for tf_label, (interval, days_back) in TIMEFRAMES.items():
        try:
            df = pipeline.get_ohlcv_df(
                instrument_token=token,
                tradingsymbol=symbol,
                interval=interval,
                days_back=days_back,
                use_cache=False,
            )
            if df is not None and len(df) > 0:
                # Keep last 200 candles max
                result[tf_label] = df.tail(200)
                logger.debug(f"MTF: fetched {len(result[tf_label])} candles for {symbol} {tf_label}")
            else:
                logger.warning(f"MTF: no data for {symbol} {tf_label}")
        except Exception as exc:
            logger.error(f"MTF: failed to fetch {symbol} {tf_label}: {exc}")

    return result


def compute_multi_timeframe_indicators(
    timeframe_dfs: dict[str, pd.DataFrame]
) -> dict[str, dict]:
    """
    Compute indicators for each timeframe.

    Args:
        timeframe_dfs: dict of {timeframe_label: DataFrame}

    Returns:
        dict of {timeframe_label: indicators_dict}
    """
    result = {}
    for tf_label, df in timeframe_dfs.items():
        if df is None or df.empty or len(df) < 20:
            logger.warning(f"MTF indicators: skipping {tf_label} (insufficient data)")
            continue
        try:
            indicators = compute_indicators(df)
            result[tf_label] = indicators
        except Exception as exc:
            logger.error(f"MTF indicators: failed for {tf_label}: {exc}")

    return result


def score_confluence(mtf_indicators: dict[str, dict]) -> dict[str, Any]:
    """
    Calculate multi-timeframe confluence score.

    Logic:
    - Count how many timeframes are bullish (EMA_fast > EMA_slow)
    - Count how many are bearish (EMA_fast < EMA_slow)
    - Bias: BULLISH if bullish_count > bearish_count, BEARISH if bearish > bullish, else NEUTRAL
    - Confluence score: (aligned_count - opposing_count) / total_timeframes
      where aligned is the dominant direction count

    Args:
        mtf_indicators: dict of {timeframe_label: indicators_dict}

    Returns:
        {
            "bullish_count": int,
            "bearish_count": int,
            "neutral_count": int,
            "total_timeframes": int,
            "bias": "BULLISH" | "BEARISH" | "NEUTRAL",
            "score": float,  # -1.0 to 1.0 (positive = bullish, negative = bearish)
            "confluence_pct": float,  # 0-100%, percentage of aligned timeframes
        }
    """
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    total = len(mtf_indicators)

    if total == 0:
        return {
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "total_timeframes": 0,
            "bias": "NEUTRAL",
            "score": 0.0,
            "confluence_pct": 0.0,
        }

    for tf_label, indicators in mtf_indicators.items():
        ema_fast = indicators.get("ema_fast", 0)
        ema_slow = indicators.get("ema_slow", 0)

        if ema_fast > 0 and ema_slow > 0:
            if ema_fast > ema_slow:
                bullish_count += 1
            elif ema_fast < ema_slow:
                bearish_count += 1
            else:
                neutral_count += 1
        else:
            neutral_count += 1

    # Determine bias
    if bullish_count > bearish_count:
        bias = "BULLISH"
        aligned = bullish_count
    elif bearish_count > bullish_count:
        bias = "BEARISH"
        aligned = bearish_count
    else:
        bias = "NEUTRAL"
        aligned = max(bullish_count, bearish_count)

    # Score: normalized to -1.0 (all bearish) to +1.0 (all bullish)
    score = (bullish_count - bearish_count) / total if total > 0 else 0.0

    # Confluence percentage: how many timeframes align with the dominant bias
    confluence_pct = (aligned / total * 100) if total > 0 else 0.0

    return {
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "total_timeframes": total,
        "bias": bias,
        "score": round(score, 2),
        "confluence_pct": round(confluence_pct, 1),
    }


def get_multi_timeframe_analysis(
    pipeline: Any,
    token: int,
    symbol: str,
    exchange: str = "NSE",
) -> dict[str, Any]:
    """
    Full MTF analysis pipeline: fetch → compute indicators → score confluence.

    Args:
        pipeline: DataPipeline instance
        token: Instrument token
        symbol: Trading symbol
        exchange: Exchange

    Returns:
        {
            "timeframes": {tf_label: indicators_dict, ...},
            "confluence": {bullish_count, bearish_count, bias, score, confluence_pct},
        }
    """
    # 1. Fetch data for all timeframes
    timeframe_dfs = fetch_multi_timeframe(pipeline, token, symbol, exchange)

    # 2. Compute indicators per timeframe
    timeframe_indicators = compute_multi_timeframe_indicators(timeframe_dfs)

    # 3. Score confluence
    confluence = score_confluence(timeframe_indicators)

    logger.info(
        f"MTF analysis for {symbol}: {confluence['bias']} "
        f"({confluence['confluence_pct']:.0f}% aligned, "
        f"score {confluence['score']:+.2f})"
    )

    return {
        "timeframes": timeframe_indicators,
        "confluence": confluence,
    }
