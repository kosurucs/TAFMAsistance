"""
test_kite_data_layer.py – Unit tests for the Kite Connect data layer.

Covers:
  - retry helper (backoff, success, abort on non-retryable exception)
  - _chunks utility in market_data
  - MarketData batching
  - InstrumentsCache token lookup (mock KiteConnect)
  - Portfolio convenience methods (mock KiteConnect)
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

# ── Module imports ─────────────────────────────────────────────────────────────

from src.utils.retry import retry
from src.tools.market_data import MarketData, _chunks
from src.tools.instruments import InstrumentsCache
from src.tools.portfolio import Portfolio


# ══════════════════════════════════════════════════════════════════════════════
# retry helper
# ══════════════════════════════════════════════════════════════════════════════


class TestRetry:
    def test_succeeds_on_first_call(self):
        fn = MagicMock(return_value=42)
        assert retry(fn, retries=3, base_delay_s=0) == 42
        fn.assert_called_once()

    def test_returns_value_after_transient_failures(self):
        results = [ValueError("boom"), ValueError("boom"), "ok"]

        def fn():
            v = results.pop(0)
            if isinstance(v, Exception):
                raise v
            return v

        with patch("src.utils.retry.time.sleep"):
            result = retry(fn, retries=3, base_delay_s=0)
        assert result == "ok"

    def test_raises_after_max_retries(self):
        fn = MagicMock(side_effect=RuntimeError("persistent"))
        with patch("src.utils.retry.time.sleep"):
            with pytest.raises(RuntimeError, match="persistent"):
                retry(fn, retries=2, base_delay_s=0)
        assert fn.call_count == 3  # initial + 2 retries

    def test_should_retry_false_aborts_immediately(self):
        fn = MagicMock(side_effect=ValueError("skip"))
        with pytest.raises(ValueError, match="skip"):
            retry(fn, retries=5, base_delay_s=0, should_retry=lambda _e: False)
        fn.assert_called_once()

    def test_should_retry_true_retries_all_attempts(self):
        fn = MagicMock(side_effect=ValueError("retry"))
        with patch("src.utils.retry.time.sleep"):
            with pytest.raises(ValueError):
                retry(fn, retries=2, base_delay_s=0, should_retry=lambda _e: True)
        assert fn.call_count == 3

    def test_only_retries_specified_exception_types(self):
        fn = MagicMock(side_effect=TypeError("wrong type"))
        with pytest.raises(TypeError):
            retry(fn, retries=3, base_delay_s=0, retry_on=(ValueError,))
        fn.assert_called_once()

    def test_delay_capped_at_max(self):
        fn = MagicMock(side_effect=[RuntimeError(), RuntimeError(), "done"])
        sleep_calls: list[float] = []

        def fn2():
            v = fn()
            return v

        with patch("src.utils.retry.time.sleep", side_effect=lambda d: sleep_calls.append(d)):
            result = retry(fn2, retries=2, base_delay_s=10.0, max_delay_s=3.0)

        assert result == "done"
        assert all(d <= 3.0 for d in sleep_calls)


# ══════════════════════════════════════════════════════════════════════════════
# _chunks utility
# ══════════════════════════════════════════════════════════════════════════════


class TestChunks:
    def test_exact_multiple(self):
        result = list(_chunks([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]

    def test_remainder(self):
        result = list(_chunks([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_larger_than_list(self):
        result = list(_chunks([1, 2], 10))
        assert result == [[1, 2]]

    def test_empty_list(self):
        result = list(_chunks([], 5))
        assert result == []

    def test_chunk_size_one(self):
        result = list(_chunks([10, 20, 30], 1))
        assert result == [[10], [20], [30]]


# ══════════════════════════════════════════════════════════════════════════════
# MarketData – batching
# ══════════════════════════════════════════════════════════════════════════════


def _make_kite_mock() -> MagicMock:
    """Return a minimal mock KiteConnect object."""
    kite = MagicMock()
    kite.ltp.__name__ = "ltp"
    kite.quote.__name__ = "quote"
    kite.ohlc.__name__ = "ohlc"
    return kite


class TestMarketDataBatching:
    def test_ltp_single_batch(self):
        kite = _make_kite_mock()
        kite.ltp.return_value = {"NSE:RELIANCE": {"last_price": 2500.0}}
        md = MarketData(kite, batch_size=500)

        result = md.get_ltp(["NSE:RELIANCE"])
        assert result == {"NSE:RELIANCE": {"last_price": 2500.0}}
        kite.ltp.assert_called_once_with(["NSE:RELIANCE"])

    def test_ltp_splits_into_batches(self):
        kite = _make_kite_mock()
        kite.ltp.side_effect = [
            {"NSE:A": {"last_price": 1.0}, "NSE:B": {"last_price": 2.0}},
            {"NSE:C": {"last_price": 3.0}},
        ]
        md = MarketData(kite, batch_size=2)

        result = md.get_ltp(["NSE:A", "NSE:B", "NSE:C"])

        assert len(result) == 3
        assert result["NSE:C"]["last_price"] == 3.0
        assert kite.ltp.call_count == 2

    def test_quote_merges_batches(self):
        kite = _make_kite_mock()
        kite.quote.side_effect = [
            {"NSE:X": {"last_price": 10.0}},
            {"NSE:Y": {"last_price": 20.0}},
        ]
        md = MarketData(kite, batch_size=1)

        result = md.get_quote(["NSE:X", "NSE:Y"])
        assert result["NSE:X"]["last_price"] == 10.0
        assert result["NSE:Y"]["last_price"] == 20.0

    def test_ohlc_single_call(self):
        kite = _make_kite_mock()
        kite.ohlc.return_value = {
            "NSE:INFY": {"ohlc": {"open": 1500.0, "high": 1520.0, "low": 1490.0, "close": 1510.0}}
        }
        md = MarketData(kite, batch_size=500)

        result = md.get_ohlc(["NSE:INFY"])
        assert "NSE:INFY" in result

    def test_get_historical_passes_args(self):
        kite = _make_kite_mock()
        kite.historical_data.return_value = [
            {"date": "2024-01-02", "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1000}
        ]
        md = MarketData(kite)

        result = md.get_historical(738561, "2024-01-01", "2024-01-02", "day")
        assert len(result) == 1
        kite.historical_data.assert_called_once()
        args = kite.historical_data.call_args
        assert args[0][0] == 738561
        assert args[1]["interval"] == "day"


# ══════════════════════════════════════════════════════════════════════════════
# InstrumentsCache – token lookup
# ══════════════════════════════════════════════════════════════════════════════


def _make_instruments_csv(rows: list[dict[str, Any]]) -> str:
    """Serialise *rows* to a CSV string for use as a mock instruments list."""
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


_SAMPLE_INSTRUMENTS = [
    {
        "instrument_token": 738561,
        "exchange_token": 2884,
        "tradingsymbol": "RELIANCE",
        "name": "RELIANCE INDUSTRIES",
        "last_price": 0.0,
        "expiry": "",
        "strike": 0.0,
        "tick_size": 0.05,
        "lot_size": 1,
        "instrument_type": "EQ",
        "segment": "NSE",
        "exchange": "NSE",
    },
    {
        "instrument_token": 408065,
        "exchange_token": 1594,
        "tradingsymbol": "INFY",
        "name": "INFOSYS",
        "last_price": 0.0,
        "expiry": "",
        "strike": 0.0,
        "tick_size": 0.05,
        "lot_size": 1,
        "instrument_type": "EQ",
        "segment": "NSE",
        "exchange": "NSE",
    },
]


class TestInstrumentsCache:
    def test_get_instrument_token_known_symbol(self, tmp_path: Path):
        kite = MagicMock()
        kite.instruments.return_value = _SAMPLE_INSTRUMENTS

        cache = InstrumentsCache(kite, cache_dir=tmp_path)
        token = cache.get_instrument_token("NSE", "RELIANCE")

        assert token == 738561

    def test_get_instrument_token_second_symbol(self, tmp_path: Path):
        kite = MagicMock()
        kite.instruments.return_value = _SAMPLE_INSTRUMENTS

        cache = InstrumentsCache(kite, cache_dir=tmp_path)
        token = cache.get_instrument_token("NSE", "INFY")

        assert token == 408065

    def test_raises_for_unknown_symbol(self, tmp_path: Path):
        kite = MagicMock()
        kite.instruments.return_value = _SAMPLE_INSTRUMENTS

        cache = InstrumentsCache(kite, cache_dir=tmp_path)
        with pytest.raises(KeyError, match="UNKNOWN"):
            cache.get_instrument_token("NSE", "UNKNOWN")

    def test_download_called_once_per_exchange(self, tmp_path: Path):
        kite = MagicMock()
        kite.instruments.return_value = _SAMPLE_INSTRUMENTS

        cache = InstrumentsCache(kite, cache_dir=tmp_path)
        cache.get_instrument_token("NSE", "RELIANCE")
        cache.get_instrument_token("NSE", "INFY")

        kite.instruments.assert_called_once_with("NSE")

    def test_csv_cache_written_to_disk(self, tmp_path: Path):
        kite = MagicMock()
        kite.instruments.return_value = _SAMPLE_INSTRUMENTS

        cache = InstrumentsCache(kite, cache_dir=tmp_path)
        cache.get_instrument_token("NSE", "RELIANCE")

        csv_files = list(tmp_path.glob("instruments_NSE_*.csv"))
        assert len(csv_files) == 1

    def test_cache_reused_on_fresh_file(self, tmp_path: Path):
        """If a fresh CSV exists, kite.instruments should NOT be called."""
        kite = MagicMock()
        kite.instruments.return_value = _SAMPLE_INSTRUMENTS

        # First instance writes the cache.
        cache1 = InstrumentsCache(kite, cache_dir=tmp_path)
        cache1.get_instrument_token("NSE", "RELIANCE")
        assert kite.instruments.call_count == 1

        # Second instance should read from the fresh CSV.
        kite2 = MagicMock()
        cache2 = InstrumentsCache(kite2, cache_dir=tmp_path)
        token = cache2.get_instrument_token("NSE", "RELIANCE")

        assert token == 738561
        kite2.instruments.assert_not_called()

    def test_warm_up_loads_multiple_exchanges(self, tmp_path: Path):
        kite = MagicMock()
        bse_instruments = [
            {
                **_SAMPLE_INSTRUMENTS[0],
                "exchange": "BSE",
                "segment": "BSE",
                "instrument_token": 500325,
            }
        ]
        kite.instruments.side_effect = lambda ex: (
            _SAMPLE_INSTRUMENTS if ex == "NSE" else bse_instruments
        )

        cache = InstrumentsCache(kite, cache_dir=tmp_path)
        cache.warm_up(["NSE", "BSE"])

        assert "NSE" in cache._loaded_exchanges
        assert "BSE" in cache._loaded_exchanges
        assert kite.instruments.call_count == 2

    def test_get_all_instruments_returns_dataframe(self, tmp_path: Path):
        kite = MagicMock()
        kite.instruments.return_value = _SAMPLE_INSTRUMENTS

        cache = InstrumentsCache(kite, cache_dir=tmp_path)
        df = cache.get_all_instruments("NSE")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "tradingsymbol" in df.columns


# ══════════════════════════════════════════════════════════════════════════════
# Portfolio
# ══════════════════════════════════════════════════════════════════════════════


class TestPortfolio:
    def _make_pf(self) -> tuple[Portfolio, MagicMock]:
        kite = MagicMock()
        return Portfolio(kite), kite

    def test_get_margins_calls_kite(self):
        pf, kite = self._make_pf()
        kite.margins.return_value = {"equity": {"available": {"cash": 50000.0}}}
        result = pf.get_margins()
        kite.margins.assert_called_once()
        assert "equity" in result

    def test_get_margins_with_segment(self):
        pf, kite = self._make_pf()
        kite.margins.return_value = {"available": {"cash": 30000.0}}
        result = pf.get_margins(segment="equity")
        kite.margins.assert_called_once_with(segment="equity")

    def test_get_positions(self):
        pf, kite = self._make_pf()
        kite.positions.return_value = {
            "day": [{"tradingsymbol": "RELIANCE", "pnl": 200.0}],
            "net": [],
        }
        result = pf.get_positions()
        assert len(result["day"]) == 1

    def test_get_holdings(self):
        pf, kite = self._make_pf()
        kite.holdings.return_value = [{"tradingsymbol": "TCS", "quantity": 5}]
        result = pf.get_holdings()
        assert result[0]["tradingsymbol"] == "TCS"

    def test_get_orders(self):
        pf, kite = self._make_pf()
        kite.orders.return_value = [{"order_id": "12345", "status": "COMPLETE"}]
        result = pf.get_orders()
        assert result[0]["order_id"] == "12345"

    def test_get_order_trades(self):
        pf, kite = self._make_pf()
        kite.order_trades.return_value = [{"trade_id": "T001", "quantity": 10}]
        result = pf.get_order_trades("12345")
        kite.order_trades.assert_called_once_with("12345")
        assert result[0]["trade_id"] == "T001"

    def test_get_day_pnl_sums_positions(self):
        pf, kite = self._make_pf()
        kite.positions.return_value = {
            "day": [
                {"tradingsymbol": "RELIANCE", "pnl": 200.0},
                {"tradingsymbol": "INFY", "pnl": -50.0},
            ],
            "net": [],
        }
        assert pf.get_day_pnl() == pytest.approx(150.0)

    def test_get_day_pnl_empty_positions(self):
        pf, kite = self._make_pf()
        kite.positions.return_value = {"day": [], "net": []}
        assert pf.get_day_pnl() == pytest.approx(0.0)
