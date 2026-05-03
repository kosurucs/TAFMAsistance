"""
market_data.py – Read-only Kite Connect market data wrapper.

Provides:
  - ``MarketData`` class with methods for LTP, full quote, OHLC, and
    historical OHLCV candles.
  - Automatic batching to avoid exceeding the Kite API's per-request symbol
    limit.

Typical usage::

    from src.tools.kite_client import build_kite_client
    from src.tools.market_data import MarketData

    kite = build_kite_client()
    md = MarketData(kite)

    ltp = md.get_ltp(["NSE:RELIANCE", "NSE:INFY"])
    # {"NSE:RELIANCE": {"instrument_token": ..., "last_price": ...}, ...}

    candles = md.get_historical(738561, "2024-01-01", "2024-01-31", "day")
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterator

from loguru import logger

from src.utils.retry import retry

# Maximum number of symbols Kite allows per quote/ltp/ohlc request.
_QUOTE_BATCH_SIZE: int = 500


def _chunks(lst: list[Any], size: int) -> Iterator[list[Any]]:
    """Yield successive *size*-length chunks from *lst*."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


class MarketData:
    """Wraps Kite Connect data endpoints for read-only market data access.

    All network calls are wrapped with :func:`src.utils.retry.retry` using
    the default parameters (3 retries, exponential back-off).

    Args:
        kite: Authenticated ``KiteConnect`` instance (from
            :func:`src.tools.kite_client.build_kite_client`).
        batch_size: Maximum symbols per API call.  Defaults to 500 (Kite's
            practical limit).
    """

    def __init__(self, kite: Any, batch_size: int = _QUOTE_BATCH_SIZE) -> None:
        self._kite = kite
        self._batch_size = batch_size

    # ------------------------------------------------------------------
    # LTP
    # ------------------------------------------------------------------

    def get_ltp(self, symbols: list[str]) -> dict[str, Any]:
        """Return the Last Traded Price for one or more symbols.

        Args:
            symbols: Fully-qualified Kite symbols, e.g.
                ``["NSE:RELIANCE", "NSE:INFY"]``.

        Returns:
            Merged dict keyed by symbol with LTP info dicts.
        """
        return self._batched_call(self._kite.ltp, symbols)

    # ------------------------------------------------------------------
    # Full quote
    # ------------------------------------------------------------------

    def get_quote(self, symbols: list[str]) -> dict[str, Any]:
        """Return the full market quote for one or more symbols.

        Args:
            symbols: Fully-qualified Kite symbols.

        Returns:
            Merged dict keyed by symbol with quote dicts.
        """
        return self._batched_call(self._kite.quote, symbols)

    # ------------------------------------------------------------------
    # OHLC
    # ------------------------------------------------------------------

    def get_ohlc(self, symbols: list[str]) -> dict[str, Any]:
        """Return OHLC data for one or more symbols.

        Args:
            symbols: Fully-qualified Kite symbols.

        Returns:
            Merged dict keyed by symbol with OHLC dicts.
        """
        return self._batched_call(self._kite.ohlc, symbols)

    # ------------------------------------------------------------------
    # Historical candles
    # ------------------------------------------------------------------

    def get_historical(
        self,
        instrument_token: int,
        from_date: str | datetime,
        to_date: str | datetime,
        interval: str = "day",
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict[str, Any]]:
        """Return historical OHLCV candles for a single instrument.

        Args:
            instrument_token: Numeric Kite instrument token.
            from_date: Start of the range.  Either a ``datetime`` object or
                an ISO-8601 date string (``"YYYY-MM-DD"``).
            to_date: End of the range.  Same format as *from_date*.
            interval: Candle interval string (e.g. ``"minute"``, ``"5minute"``,
                ``"day"``).  See Kite docs for the full list.
            continuous: If ``True``, fetch continuous (back-adjusted) data for
                F&O instruments.
            oi: If ``True``, include Open Interest in the response.

        Returns:
            List of candle dicts with keys:
            ``date, open, high, low, close, volume``.
        """
        from_dt = _parse_date(from_date)
        to_dt = _parse_date(to_date)

        candles: list[dict[str, Any]] = retry(
            lambda: self._kite.historical_data(
                instrument_token,
                from_date=from_dt,
                to_date=to_dt,
                interval=interval,
                continuous=continuous,
                oi=oi,
            )
        )
        logger.debug(
            "Fetched {} {} candles for token {}.",
            len(candles),
            interval,
            instrument_token,
        )
        return candles

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _batched_call(
        self, api_fn: Any, symbols: list[str]
    ) -> dict[str, Any]:
        """Call *api_fn* in batches and merge the results.

        Args:
            api_fn: A Kite method that accepts a list of symbol strings and
                returns a dict keyed by symbol.
            symbols: Full list of symbols to fetch.

        Returns:
            Merged response dict.
        """
        result: dict[str, Any] = {}
        for batch in _chunks(symbols, self._batch_size):
            batch_result: dict[str, Any] = retry(lambda b=batch: api_fn(b))
            result.update(batch_result)
        logger.debug(
            "Batched {} call: {} symbols in {} batch(es).",
            api_fn.__name__ if hasattr(api_fn, "__name__") else str(api_fn),
            len(symbols),
            -(-len(symbols) // self._batch_size),  # ceiling division
        )
        return result


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------


def _parse_date(value: str | datetime) -> datetime:
    """Convert an ISO-8601 date string or ``datetime`` to a ``datetime``."""
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}")
