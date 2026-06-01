"""
test_historical_data.py — Unit tests for the enhanced HistoricalDataManager.

All yfinance / network calls are mocked; no network required.
Run: pytest tests/test_historical_data.py -v
"""
from __future__ import annotations
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.tools.historical_data import HistoricalDataManager


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_ohlcv(n: int = 5) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame as yfinance would after reset_index."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0 + i for i in range(n)],
            "High": [105.0 + i for i in range(n)],
            "Low": [99.0 + i for i in range(n)],
            "Close": [102.0 + i for i in range(n)],
            "Volume": [1_000_000] * n,
            "Dividends": [0.0] * n,
            "Stock Splits": [0.0] * n,
        }
    )


def _mock_ticker(df: pd.DataFrame) -> MagicMock:
    ticker = MagicMock()
    ticker.history.return_value = df
    return ticker


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mgr(tmp_path):
    """HistoricalDataManager pointed at a temp dir."""
    return HistoricalDataManager(data_dir=str(tmp_path))


# ── resolve_symbol_info ──────────────────────────────────────────────────────

class TestResolveSymbolInfo:
    def test_nse_equity(self, mgr):
        info = mgr.resolve_symbol_info("RELIANCE", exchange="NSE")
        assert info.yf_ticker == "RELIANCE.NS"
        assert info.commission_segment == "EQUITY_DELIVERY"

    def test_mcx_gold(self, mgr):
        info = mgr.resolve_symbol_info("GOLD", exchange="MCX")
        assert info.yf_ticker == "GC=F"
        assert info.usd_proxy is True

    def test_cds_usdinr(self, mgr):
        info = mgr.resolve_symbol_info("USDINR", exchange="CDS")
        assert info.yf_ticker == "USDINR=X"

    def test_nfo_futures(self, mgr):
        info = mgr.resolve_symbol_info("NIFTY", exchange="NFO", instrument="FUTURES")
        assert info.lot_size == 75
        assert info.commission_segment == "FNO_FUTURES"

    def test_bse_equity(self, mgr):
        info = mgr.resolve_symbol_info("TCS", exchange="BSE")
        assert info.yf_ticker == "TCS.BO"


# ── _resolve_yf_ticker ───────────────────────────────────────────────────────

class TestResolveYfTicker:
    def test_nse_returns_dot_ns(self, mgr):
        yf_t, info = mgr._resolve_yf_ticker("RELIANCE", "NSE")
        assert yf_t == "RELIANCE.NS"

    def test_mcx_gold_proxy(self, mgr):
        yf_t, info = mgr._resolve_yf_ticker("GOLD", "MCX")
        assert yf_t == "GC=F"

    def test_no_proxy_raises(self, mgr):
        # MCX agri contracts (e.g. MENTHAOIL) have no yfinance proxy
        with pytest.raises(ValueError, match="no yfinance proxy"):
            mgr._resolve_yf_ticker("MENTHAOIL", "MCX")


# ── fetch_symbol — NSE ───────────────────────────────────────────────────────

class TestFetchSymbolNSE:
    @patch("src.tools.historical_data.yf.Ticker")
    def test_successful_fetch_returns_df(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(10))
        df = mgr.fetch_symbol("RELIANCE", period="1y", interval="1d", exchange="NSE")
        assert df is not None
        assert len(df) == 10
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]

    @patch("src.tools.historical_data.yf.Ticker")
    def test_empty_response_returns_none(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(pd.DataFrame())
        df = mgr.fetch_symbol("RELIANCE", exchange="NSE")
        assert df is None

    @patch("src.tools.historical_data.yf.Ticker")
    def test_nse_ticker_passed_to_yfinance(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(3))
        mgr.fetch_symbol("TCS", exchange="NSE")
        mock_ticker_cls.assert_called_once_with("TCS.NS")

    @patch("src.tools.historical_data.yf.Ticker")
    def test_mm_special_case_ticker(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(3))
        mgr.fetch_symbol("M&M", exchange="NSE")
        mock_ticker_cls.assert_called_once_with("M%26M.NS")

    @patch("src.tools.historical_data.yf.Ticker")
    def test_exception_retries_and_returns_none(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value.history.side_effect = RuntimeError("network")
        with patch("src.tools.historical_data.time.sleep"):
            df = mgr.fetch_symbol("RELIANCE", max_retries=2, exchange="NSE")
        assert df is None


# ── fetch_symbol — BSE ───────────────────────────────────────────────────────

class TestFetchSymbolBSE:
    @patch("src.tools.historical_data.yf.Ticker")
    def test_bse_ticker_has_dot_bo(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(3))
        mgr.fetch_symbol("RELIANCE", exchange="BSE")
        mock_ticker_cls.assert_called_once_with("RELIANCE.BO")

    @patch("src.tools.historical_data.yf.Ticker")
    def test_sensex_uses_bse_index_ticker(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(3))
        mgr.fetch_symbol("SENSEX", exchange="BSE")
        mock_ticker_cls.assert_called_once_with("^BSESN")


# ── fetch_symbol — MCX ───────────────────────────────────────────────────────

class TestFetchSymbolMCX:
    @patch("src.tools.historical_data.yf.Ticker")
    def test_mcx_gold_uses_gcf(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        df = mgr.fetch_symbol("GOLD", exchange="MCX")
        assert df is not None
        mock_ticker_cls.assert_called_once_with("GC=F")

    @patch("src.tools.historical_data.yf.Ticker")
    def test_mcx_crudeoil_uses_clf(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        mgr.fetch_symbol("CRUDEOIL", exchange="MCX")
        mock_ticker_cls.assert_called_once_with("CL=F")

    def test_mcx_no_proxy_returns_none(self, mgr):
        df = mgr.fetch_symbol("MENTHAOIL", exchange="MCX")
        assert df is None


# ── fetch_symbol — CDS ───────────────────────────────────────────────────────

class TestFetchSymbolCDS:
    @patch("src.tools.historical_data.yf.Ticker")
    def test_usdinr_uses_forex_ticker(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        mgr.fetch_symbol("USDINR", exchange="CDS")
        mock_ticker_cls.assert_called_once_with("USDINR=X")

    @patch("src.tools.historical_data.yf.Ticker")
    def test_eurinr_uses_correct_ticker(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        mgr.fetch_symbol("EURINR", exchange="CDS")
        mock_ticker_cls.assert_called_once_with("EURINR=X")


# ── fetch_symbol — NFO ───────────────────────────────────────────────────────

class TestFetchSymbolNFO:
    @patch("src.tools.historical_data.yf.Ticker")
    def test_nifty_futures_uses_index_ticker(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        mgr.fetch_symbol("NIFTY", exchange="NFO", instrument="FUTURES")
        mock_ticker_cls.assert_called_once_with("^NSEI")

    @patch("src.tools.historical_data.yf.Ticker")
    def test_banknifty_futures_uses_index_ticker(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        mgr.fetch_symbol("BANKNIFTY", exchange="NFO", instrument="FUTURES")
        mock_ticker_cls.assert_called_once_with("^NSEBANK")


# ── CSV cache ────────────────────────────────────────────────────────────────

class TestCSVCache:
    @patch("src.tools.historical_data.yf.Ticker")
    def test_save_and_load_roundtrip(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(10))
        df = mgr.fetch_symbol("RELIANCE", exchange="NSE")
        mgr.save_to_csv("RELIANCE", df, interval="1d", exchange="NSE")
        loaded = mgr.load_from_csv("RELIANCE", interval="1d", exchange="NSE")
        assert loaded is not None
        assert len(loaded) == len(df)

    @patch("src.tools.historical_data.yf.Ticker")
    def test_mcx_cache_key_safe(self, mock_ticker_cls, mgr):
        """MCX symbols with = are sanitised in filenames."""
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        df = mgr.fetch_symbol("GOLD", exchange="MCX")
        mgr.save_to_csv("GOLD", df, interval="1d", exchange="MCX")
        cache_file = list(mgr.data_dir.glob("GOLD_MCX_1d.csv"))
        assert len(cache_file) == 1

    def test_cache_miss_returns_none(self, mgr):
        assert mgr.load_from_csv("NONEXISTENT", "1d", "NSE") is None

    @patch("src.tools.historical_data.yf.Ticker")
    def test_bse_cache_separate_from_nse(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        df_nse = mgr.fetch_symbol("RELIANCE", exchange="NSE")
        df_bse = mgr.fetch_symbol("RELIANCE", exchange="BSE")
        mgr.save_to_csv("RELIANCE", df_nse, "1d", "NSE")
        mgr.save_to_csv("RELIANCE", df_bse, "1d", "BSE")
        files = list(mgr.data_dir.glob("RELIANCE_*.csv"))
        assert len(files) == 2


# ── get_symbol_data ───────────────────────────────────────────────────────────

class TestGetSymbolData:
    @patch("src.tools.historical_data.yf.Ticker")
    def test_returns_data_on_cache_miss(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        df = mgr.get_symbol_data("RELIANCE", exchange="NSE", use_cache=True)
        assert df is not None

    @patch("src.tools.historical_data.yf.Ticker")
    def test_cache_hit_skips_network(self, mock_ticker_cls, mgr):
        # Prime the cache
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        mgr.get_symbol_data("RELIANCE", exchange="NSE", use_cache=False)
        mock_ticker_cls.reset_mock()
        # Now load from cache — should NOT call yf.Ticker
        mgr.get_symbol_data("RELIANCE", exchange="NSE", use_cache=True)
        mock_ticker_cls.assert_not_called()

    @patch("src.tools.historical_data.yf.Ticker")
    def test_mcx_get_symbol_data(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        df = mgr.get_symbol_data("GOLD", exchange="MCX", use_cache=False)
        assert df is not None
        mock_ticker_cls.assert_called_once_with("GC=F")

    @patch("src.tools.historical_data.yf.Ticker")
    def test_cds_get_symbol_data(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        df = mgr.get_symbol_data("USDINR", exchange="CDS", use_cache=False)
        assert df is not None


# ── fetch_bulk ────────────────────────────────────────────────────────────────

class TestFetchBulk:
    @patch("src.tools.historical_data.yf.Ticker")
    def test_bulk_nse_returns_dict(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(5))
        with patch("src.tools.historical_data.time.sleep"):
            results = mgr.fetch_bulk(["RELIANCE", "TCS", "INFY"], exchange="NSE")
        assert len(results) == 3

    @patch("src.tools.historical_data.yf.Ticker")
    def test_bulk_handles_partial_failures(self, mock_ticker_cls, mgr):
        def side_effect(ticker_str):
            m = MagicMock()
            if ticker_str == "FAIL.NS":
                m.history.return_value = pd.DataFrame()
            else:
                m.history.return_value = _make_ohlcv(5)
            return m

        mock_ticker_cls.side_effect = side_effect
        results = mgr.fetch_bulk(["RELIANCE", "FAIL"], exchange="NSE")
        assert "RELIANCE" in results
        assert "FAIL" not in results

    @patch("src.tools.historical_data.yf.Ticker")
    def test_fetch_mcx_universe_calls_mcx_tickers(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(3))
        with patch("src.tools.historical_data.time.sleep"):
            results = mgr.fetch_mcx_universe()
        called_tickers = {call.args[0] for call in mock_ticker_cls.call_args_list}
        # GC=F (GOLD) and CL=F (CRUDEOIL) must have been requested
        assert "GC=F" in called_tickers
        assert "CL=F" in called_tickers

    @patch("src.tools.historical_data.yf.Ticker")
    def test_fetch_cds_universe_calls_forex_tickers(self, mock_ticker_cls, mgr):
        mock_ticker_cls.return_value = _mock_ticker(_make_ohlcv(3))
        with patch("src.tools.historical_data.time.sleep"):
            results = mgr.fetch_cds_universe()
        called_tickers = {call.args[0] for call in mock_ticker_cls.call_args_list}
        assert "USDINR=X" in called_tickers


# ── backward compat: legacy 2-arg save/load still works ──────────────────────

class TestLegacyCompat:
    @patch("src.tools.historical_data.yf.Ticker")
    def test_legacy_nse_csv_found_by_new_load(self, mock_ticker_cls, mgr, tmp_path):
        """Files written as SYMBOL_1d.csv (old format) are found by NSE load."""
        df = _make_ohlcv(5)
        # Write old-style file manually
        df.rename(columns={"Date": "timestamp", "Open": "open", "High": "high",
                            "Low": "low", "Close": "close", "Volume": "volume"},
                  inplace=True)
        legacy_path = tmp_path / "RELIANCE_1d.csv"
        df.to_csv(legacy_path, index=False)
        loaded = mgr.load_from_csv("RELIANCE", "1d", "NSE")
        assert loaded is not None
        assert len(loaded) == 5
