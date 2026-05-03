"""
instruments.py – Kite instruments cache and token lookup.

Downloads the full instruments CSV from Zerodha for one or more exchanges,
stores it on disk (refreshed at most once per calendar day), and provides a
fast ``(exchange, tradingsymbol) → instrument_token`` lookup.

Environment variable
--------------------
INSTRUMENTS_CACHE_DIR   Directory for cached CSV files.  Defaults to
                        ``data/instruments_cache/``.

Typical usage::

    from src.tools.kite_client import build_kite_client
    from src.tools.instruments import InstrumentsCache

    kite = build_kite_client()
    cache = InstrumentsCache(kite)

    token = cache.get_instrument_token("NSE", "RELIANCE")
    # 738561
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.utils.retry import retry

# Default directory for on-disk instrument CSV files.
_DEFAULT_CACHE_DIR = Path(os.environ.get("INSTRUMENTS_CACHE_DIR", "data/instruments_cache"))


class InstrumentsCache:
    """Downloads, caches, and indexes Zerodha instrument master data.

    The first call to :meth:`get_instrument_token` (or :meth:`warm_up`)
    triggers a download for the requested exchange if no up-to-date cache
    exists on disk.  Subsequent calls within the same calendar day use the
    in-memory index.

    Args:
        kite: Authenticated ``KiteConnect`` instance.
        cache_dir: Directory for CSV files.  Defaults to
            ``INSTRUMENTS_CACHE_DIR`` env var or ``data/instruments_cache/``.
    """

    def __init__(
        self,
        kite: Any,
        cache_dir: Path | str | None = None,
    ) -> None:
        self._kite = kite
        self._cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # In-memory index: (exchange, tradingsymbol) -> instrument_token
        self._index: dict[tuple[str, str], int] = {}

        # Track which exchanges have been loaded this session.
        self._loaded_exchanges: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_instrument_token(self, exchange: str, tradingsymbol: str) -> int:
        """Return the numeric instrument token for *(exchange, tradingsymbol)*.

        Loads the exchange index on demand if it has not been loaded yet.

        Args:
            exchange: Exchange identifier, e.g. ``"NSE"`` or ``"BSE"``.
            tradingsymbol: Symbol on the given exchange, e.g. ``"RELIANCE"``.

        Returns:
            Integer instrument token.

        Raises:
            KeyError: If the symbol is not found on the exchange.
        """
        if exchange not in self._loaded_exchanges:
            self._load_exchange(exchange)

        key = (exchange, tradingsymbol)
        if key not in self._index:
            raise KeyError(
                f"Instrument '{tradingsymbol}' not found on exchange '{exchange}'."
            )
        return self._index[key]

    def warm_up(self, exchanges: list[str]) -> None:
        """Pre-load instrument data for a list of exchanges.

        Useful to call once at startup so the first market-data request does
        not incur a download delay.

        Args:
            exchanges: List of exchange identifiers, e.g.
                ``["NSE", "BSE", "NFO"]``.
        """
        for exchange in exchanges:
            if exchange not in self._loaded_exchanges:
                self._load_exchange(exchange)

    def get_all_instruments(self, exchange: str) -> pd.DataFrame:
        """Return all instruments for *exchange* as a DataFrame.

        Columns include at least: ``instrument_token``, ``tradingsymbol``,
        ``exchange``, ``name``, ``expiry``, ``lot_size``,
        ``instrument_type``, ``segment``.

        Args:
            exchange: Exchange identifier.

        Returns:
            DataFrame with one row per instrument.
        """
        if exchange not in self._loaded_exchanges:
            self._load_exchange(exchange)
        return self._read_cache(exchange)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_exchange(self, exchange: str) -> None:
        """Ensure the instruments for *exchange* are loaded into ``_index``."""
        cache_path = self._cache_csv_path(exchange)

        if self._is_cache_fresh(cache_path):
            logger.debug("Loading instruments from cache: {}.", cache_path)
            df = pd.read_csv(cache_path)
        else:
            logger.info("Downloading instruments for {} …", exchange)
            instruments: list[dict[str, Any]] = retry(
                lambda ex=exchange: self._kite.instruments(ex)
            )
            df = pd.DataFrame(instruments)
            df.to_csv(cache_path, index=False)
            logger.info(
                "Cached {} instruments for {} → {}.",
                len(df),
                exchange,
                cache_path,
            )

        # Build in-memory index.
        for _, row in df.iterrows():
            key = (str(row["exchange"]), str(row["tradingsymbol"]))
            self._index[key] = int(row["instrument_token"])

        self._loaded_exchanges.add(exchange)

    def _cache_csv_path(self, exchange: str) -> Path:
        today = datetime.now().strftime("%Y%m%d")
        return self._cache_dir / f"instruments_{exchange}_{today}.csv"

    @staticmethod
    def _is_cache_fresh(path: Path) -> bool:
        """Return True if *path* exists and was written today."""
        if not path.exists():
            return False
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return mtime.date() == datetime.now().date()

    def _read_cache(self, exchange: str) -> pd.DataFrame:
        cache_path = self._cache_csv_path(exchange)
        if cache_path.exists():
            return pd.read_csv(cache_path)
        # Fallback: re-download.
        self._loaded_exchanges.discard(exchange)
        self._load_exchange(exchange)
        return pd.read_csv(cache_path)
