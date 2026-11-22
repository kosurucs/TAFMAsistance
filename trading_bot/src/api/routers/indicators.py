"""
indicators.py – Indicator overlay endpoint for chart rendering.

Routes:
  GET /api/indicators/{symbol}  – per-candle indicator arrays for chart overlays
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
import pandas as pd

from src.api.dependencies import get_data_fetcher
from src.tools.data_pipeline import DataPipeline
from src.utils.technical_analysis import compute_indicators

router = APIRouter(prefix="/api/indicators", tags=["Indicators"])


@router.get("/{symbol}")
def get_indicator_series(
    symbol: str,
    exchange: str = "NSE",
    interval: str = "day",
    limit: int = 200,
    fetcher: Any = Depends(get_data_fetcher),
) -> dict[str, Any]:
    """
    Return per-candle indicator arrays for chart overlay.
    
    Args:
        symbol: Trading symbol (optionally with exchange prefix like NFO:NIFTY26MAYFUT)
        exchange: Exchange (default NSE)
        interval: Candle interval (minute, 15minute, 60minute, day)
        limit: Maximum candles to return (default 200)
    
    Returns:
        {
            "symbol": str,
            "exchange": str,
            "interval": str,
            "indicators": {
                "ema20": [{"time": unix_ts, "value": float}, ...],
                "ema50": [...],
                "ema200": [...],
                "rsi": [...],
                ...
            }
        }
    """
    if fetcher is None:
        raise HTTPException(status_code=503, detail="Data fetcher not available.")

    # Parse exchange prefix if present
    if ":" in symbol:
        exchange, tradingsymbol = symbol.split(":", 1)
        exchange = exchange.upper()
    else:
        tradingsymbol = symbol

    # Resolve instrument token
    try:
        if hasattr(fetcher, 'lookup_instrument_token'):
            token = fetcher.lookup_instrument_token(exchange, tradingsymbol)
        else:
            token = 0  # Stub mode
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{tradingsymbol}' not found on {exchange}"
        )

    # Fetch OHLCV data
    try:
        pipeline = DataPipeline(fetcher)
        df = pipeline.get_ohlcv_df(
            instrument_token=token,
            tradingsymbol=tradingsymbol,
            interval=interval,
            days_back=0,  # Use default lookback
            use_cache=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch OHLCV: {exc}")

    if df is None or df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No OHLCV data for '{tradingsymbol}' on {exchange}"
        )

    # Keep last N candles
    if len(df) > limit:
        df = df.tail(limit)

    # Compute indicators with pandas_ta
    try:
        import pandas_ta as ta
        from zoneinfo import ZoneInfo
        
        _IST = ZoneInfo("Asia/Kolkata")
        
        # EMA indicators
        df["ema_20"] = ta.ema(df["close"], length=20)
        df["ema_50"] = ta.ema(df["close"], length=50)
        df["ema_200"] = ta.ema(df["close"], length=200)
        
        # RSI
        df["rsi"] = ta.rsi(df["close"], length=14)
        
        # MACD
        macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd_df is not None:
            df = pd.concat([df, macd_df], axis=1)
        
        # Bollinger Bands
        bb = ta.bbands(df["close"], length=20, std=2.0)
        if bb is not None:
            df = pd.concat([df, bb], axis=1)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Indicator computation failed: {exc}"
        )

    # Build per-candle series for each indicator
    indicator_series = {}
    
    # Helper to convert timestamp to IST Unix seconds
    def to_ist_unix(dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_IST)
        return int(dt.timestamp()) + 19800  # Add IST offset (UTC+05:30)

    # EMA series
    for ema_name in ["ema_20", "ema_50", "ema_200"]:
        if ema_name in df.columns:
            series = []
            for idx, val in df[ema_name].items():
                if pd.notna(val):
                    series.append({
                        "time": to_ist_unix(idx),
                        "value": round(float(val), 2)
                    })
            if series:
                indicator_series[ema_name.replace("_", "")] = series

    # RSI series
    if "rsi" in df.columns:
        series = []
        for idx, val in df["rsi"].items():
            if pd.notna(val):
                series.append({
                    "time": to_ist_unix(idx),
                    "value": round(float(val), 2)
                })
        if series:
            indicator_series["rsi"] = series

    # MACD series (main line)
    macd_col = next((c for c in df.columns if c.startswith("MACD_")), None)
    if macd_col:
        series = []
        for idx, val in df[macd_col].items():
            if pd.notna(val):
                series.append({
                    "time": to_ist_unix(idx),
                    "value": round(float(val), 4)
                })
        if series:
            indicator_series["macd"] = series

    # Bollinger Bands (upper, middle, lower)
    bb_upper = next((c for c in df.columns if "BBU" in c), None)
    bb_middle = next((c for c in df.columns if "BBM" in c), None)
    bb_lower = next((c for c in df.columns if "BBL" in c), None)
    
    for bb_name, bb_col in [("bb_upper", bb_upper), ("bb_middle", bb_middle), ("bb_lower", bb_lower)]:
        if bb_col and bb_col in df.columns:
            series = []
            for idx, val in df[bb_col].items():
                if pd.notna(val):
                    series.append({
                        "time": to_ist_unix(idx),
                        "value": round(float(val), 2)
                    })
            if series:
                indicator_series[bb_name] = series

    return {
        "symbol": tradingsymbol,
        "exchange": exchange,
        "interval": interval,
        "indicators": indicator_series,
    }
