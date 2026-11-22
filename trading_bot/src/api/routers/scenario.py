"""
scenario.py – Scenario analysis endpoint for UI components.

Routes:
  GET /api/scenario/{symbol}  – dominant scenario and probability breakdown
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
import pandas as pd

from src.api.dependencies import get_data_fetcher
from src.tools.data_pipeline import DataPipeline
from src.utils.technical_analysis import compute_indicators
from src.utils.scenario_engine import ScenarioEngine

router = APIRouter(prefix="/api/scenario", tags=["Scenario"])

_scenario_engine = ScenarioEngine()


def _fallback_scenario(
    symbol: str,
    exchange: str,
    detail: str,
) -> dict[str, Any]:
    """Return a safe scenario payload instead of HTTP errors for transient issues."""
    scenario_names = [
        "BULLISH_BREAKOUT",
        "BEARISH_BREAKDOWN",
        "SIDEWAYS_CONSOLIDATION",
        "REVERSAL_UP",
        "REVERSAL_DOWN",
    ]
    return {
        "symbol": symbol,
        "exchange": exchange,
        "dominant_scenario": "SIDEWAYS_CONSOLIDATION",
        "confidence": 0.0,
        "trade_bias": "WAIT",
        "scenarios": [{"name": name, "probability": 0.0} for name in scenario_names],
        "source": "fallback",
        "detail": detail,
    }


@router.get("/{symbol}")
def get_scenario_analysis(
    symbol: str,
    exchange: str = "NSE",
    interval: str = "day",
    fetcher: Any = Depends(get_data_fetcher),
) -> dict[str, Any]:
    """
    Return scenario analysis for a given symbol.
    
    Args:
        symbol: Trading symbol (optionally with exchange prefix like NFO:NIFTY26MAYFUT)
        exchange: Exchange (default NSE)
        interval: Candle interval (default day)
    
    Returns:
        {
            "symbol": str,
            "exchange": str,
            "dominant_scenario": str,
            "confidence": float (0-100),
            "trade_bias": "BUY|SELL|WAIT",
            "scenarios": [
                {"name": str, "probability": float},
                ...
            ]
        }
    """
    if fetcher is None:
        return _fallback_scenario(symbol.upper(), exchange, "Data fetcher not available")

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
        return _fallback_scenario(
            tradingsymbol,
            exchange,
            f"Symbol '{tradingsymbol}' not found on {exchange}",
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
        return _fallback_scenario(tradingsymbol, exchange, f"Failed to fetch OHLCV: {exc}")

    if df is None or df.empty or len(df) < 20:
        return _fallback_scenario(
            tradingsymbol,
            exchange,
            f"Insufficient OHLCV data for '{tradingsymbol}' on {exchange}",
        )

    # Compute indicators
    try:
        indicators = compute_indicators(df)
    except Exception as exc:
        return _fallback_scenario(tradingsymbol, exchange, f"Indicator computation failed: {exc}")

    # Run scenario engine
    try:
        result = _scenario_engine.score_scenarios(indicators)
    except Exception as exc:
        return _fallback_scenario(tradingsymbol, exchange, f"Scenario engine failed: {exc}")

    # Build response
    return {
        "symbol": tradingsymbol,
        "exchange": exchange,
        "dominant_scenario": result.dominant.name,
        "confidence": round(result.confidence, 1),
        "trade_bias": result.trade_bias,
        "source": "live",
        "scenarios": [
            {
                "name": s.name,
                "probability": round(s.probability, 1)
            }
            for s in result.scores
        ]
    }
