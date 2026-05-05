"""
market.py – Live market-data endpoints.

Routes:
  GET /market/{symbol}  – latest quote + technical indicators
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_data_fetcher
from src.tools.kite_tools import KiteDataFetcher
from src.tools.data_pipeline import DataPipeline
from src.utils.technical_analysis import compute_indicators

router = APIRouter(prefix="/market")


def _make_stub_df(symbol: str) -> Any:
    """Return synthetic OHLCV data when Kite is unavailable (paper-trade mode)."""
    import numpy as np
    import pandas as pd

    n = 50
    rng = np.random.default_rng(42)
    prices = 1000.0 + float(abs(hash(symbol)) % 500) + np.cumsum(rng.normal(0, 5, n))
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + rng.uniform(1, 5, n),
            "low": prices - rng.uniform(1, 5, n),
            "close": prices + rng.normal(0, 2, n),
            "volume": rng.integers(10_000, 100_000, n),
        }
    )


@router.get("/{symbol}", summary="Live quote + technical indicators for a symbol")
def get_market_data(
    symbol: str,
    exchange: str = "NSE",
    fetcher: KiteDataFetcher | None = Depends(get_data_fetcher),
) -> dict[str, Any]:
    """Return the latest quote and computed technical indicators for *symbol*.

    Falls back to synthetic stub data when Kite is unavailable (paper-trading).
    """
    symbol = symbol.upper()

    # ── Fetch OHLCV ──────────────────────────────────────────────────────────
    if fetcher is not None:
        try:
            pipeline = DataPipeline(fetcher)
            # Look up instrument token
            token: int = fetcher.lookup_instrument_token(exchange, symbol)
            df = pipeline.get_ohlcv_df(
                instrument_token=token,
                tradingsymbol=symbol,
                interval="minute",
                days_back=1,
            )
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail=f"Instrument '{symbol}' not found on exchange '{exchange}'.",
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Kite data error: {exc}")
    else:
        df = _make_stub_df(symbol)

    if df.empty:
        raise HTTPException(
            status_code=404, detail=f"No OHLCV data returned for '{symbol}'."
        )

    # ── Compute indicators ────────────────────────────────────────────────────
    try:
        indicators = compute_indicators(df)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Indicator computation failed: {exc}"
        )

    # ── Latest quote ──────────────────────────────────────────────────────────
    quote: dict[str, Any] = {}
    if fetcher is not None:
        try:
            raw = fetcher.get_quote([f"{exchange}:{symbol}"])
            quote = raw.get(f"{exchange}:{symbol}", {})
        except Exception:  # noqa: BLE001
            pass

    return {
        "symbol": symbol,
        "exchange": exchange,
        "indicators": indicators,
        "quote": quote,
        "stub_data": fetcher is None,
    }
