"""
data_pipeline.py – Market data ingestion & persistence.

Responsibilities:
  - Fetch 1-minute OHLCV candles from Zerodha.
  - Optionally cache / persist them to the local ``data/`` directory as CSV.
  - Provide a convenience function that returns a pandas DataFrame ready for
    technical analysis.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.tools.kite_tools import KiteDataFetcher

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))


class DataPipeline:
    """Orchestrates OHLCV data fetching and local caching."""

    def __init__(self, fetcher: KiteDataFetcher) -> None:
        self._fetcher = fetcher
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_ohlcv_df(
        self,
        instrument_token: int,
        tradingsymbol: str,
        interval: str = "minute",
        days_back: int = 1,
        use_cache: bool = False,
    ) -> pd.DataFrame:
        """Return a pandas DataFrame of OHLCV candles.

        Columns: ``date, open, high, low, close, volume``

        Args:
            instrument_token: Zerodha numeric instrument token.
            tradingsymbol: Human-readable symbol (used for the cache filename).
            interval: Kite candle interval string (e.g. ``"minute"``).
            days_back: How many calendar days of data to request.
            use_cache: If True and a CSV cache for today exists, use it.

        Returns:
            DataFrame indexed by ``date`` (UTC-aware timestamps).
        """
        cache_path = self._cache_path(tradingsymbol, interval)

        if use_cache and cache_path.exists():
            df = pd.read_csv(cache_path, parse_dates=["date"])
            logger.info("Loaded {} rows from cache {}.", len(df), cache_path)
            return df.set_index("date")

        candles: list[dict[str, Any]] = self._fetcher.get_ohlcv(
            instrument_token, interval=interval, days_back=days_back
        )

        if not candles:
            logger.warning("No candles returned for token {}.", instrument_token)
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(candles)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df[["open", "high", "low", "close", "volume"]].apply(
            pd.to_numeric, errors="coerce"
        )

        if use_cache:
            df.reset_index().to_csv(cache_path, index=False)
            logger.debug("Cached {} rows to {}.", len(df), cache_path)

        return df

    def fetch_latest_quote(self, symbols: list[str]) -> dict[str, Any]:
        """Return the latest full quote for a list of symbols.

        Args:
            symbols: e.g. ``["NSE:RELIANCE", "NSE:INFY"]``

        Returns:
            Raw Kite quote dict.
        """
        return self._fetcher.get_quote(symbols)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_path(tradingsymbol: str, interval: str) -> Path:
        today = datetime.now().strftime("%Y%m%d")
        return DATA_DIR / f"{tradingsymbol}_{interval}_{today}.csv"
