"""
test_segment_registry.py — Unit tests for SegmentRegistry.

Run: pytest trading_bot/tests/test_segment_registry.py -v
"""
from __future__ import annotations
import pytest
from src.tools.segment_registry import SegmentRegistry, SymbolInfo


@pytest.fixture
def reg():
    return SegmentRegistry()


# ── NSE Equity ────────────────────────────────────────────────────────────────

class TestNSEEquity:
    def test_reliance_yf_ticker(self, reg):
        info = reg.resolve("RELIANCE", exchange="NSE")
        assert info.yf_ticker == "RELIANCE.NS"

    def test_tcs_yf_ticker(self, reg):
        info = reg.resolve("TCS", exchange="NSE")
        assert info.yf_ticker == "TCS.NS"

    def test_mm_special_case(self, reg):
        info = reg.resolve("M&M", exchange="NSE")
        assert info.yf_ticker == "M%26M.NS"

    def test_equity_lot_size_is_one(self, reg):
        info = reg.resolve("INFY", exchange="NSE")
        assert info.lot_size == 1

    def test_equity_currency_inr(self, reg):
        info = reg.resolve("HDFCBANK", exchange="NSE")
        assert info.currency == "INR"

    def test_equity_segment(self, reg):
        info = reg.resolve("WIPRO", exchange="NSE")
        assert info.segment == "EQUITY"

    def test_delivery_commission_segment(self, reg):
        info = reg.resolve("RELIANCE", exchange="NSE", instrument="SPOT")
        assert info.commission_segment == "EQUITY_DELIVERY"

    def test_intraday_commission_segment(self, reg):
        info = reg.resolve("RELIANCE", exchange="NSE", instrument="INTRADAY")
        assert info.commission_segment == "EQUITY_INTRADAY"

    def test_lowercase_symbol_normalised(self, reg):
        info = reg.resolve("reliance", exchange="nse")
        assert info.yf_ticker == "RELIANCE.NS"

    def test_is_tradable_via_yfinance(self, reg):
        info = reg.resolve("TCS", exchange="NSE")
        assert info.is_tradable_via_yfinance()

    def test_is_not_index(self, reg):
        info = reg.resolve("TCS", exchange="NSE")
        assert not info.is_index()

    def test_scaled_turnover(self, reg):
        info = reg.resolve("RELIANCE", exchange="NSE")
        # lot_size=1, so price × qty
        assert info.scaled_turnover(2500.0, 10) == pytest.approx(25_000.0)


# ── NSE Index ─────────────────────────────────────────────────────────────────

class TestNSEIndex:
    def test_nifty50_resolves(self, reg):
        info = reg.resolve("NIFTY50", exchange="NSE")
        assert info.yf_ticker == "^NSEI"

    def test_nifty_alias(self, reg):
        info = reg.resolve("NIFTY", exchange="NSE")
        assert info.yf_ticker == "^NSEI"

    def test_banknifty_resolves(self, reg):
        info = reg.resolve("BANKNIFTY", exchange="NSE")
        assert info.yf_ticker == "^NSEBANK"

    def test_index_segment(self, reg):
        info = reg.resolve("NIFTY50", exchange="NSE")
        assert info.segment == "INDEX"

    def test_index_is_index(self, reg):
        info = reg.resolve("NIFTY50", exchange="NSE")
        assert info.is_index()

    def test_niftyit_resolves(self, reg):
        info = reg.resolve("NIFTYIT", exchange="NSE")
        assert info.yf_ticker == "^CNXIT"

    def test_is_index_method(self, reg):
        assert reg.is_index("NIFTY50")
        assert reg.is_index("BANKNIFTY")
        assert not reg.is_index("RELIANCE")


# ── BSE Equity ────────────────────────────────────────────────────────────────

class TestBSEEquity:
    def test_reliance_bse_ticker(self, reg):
        info = reg.resolve("RELIANCE", exchange="BSE")
        assert info.yf_ticker == "RELIANCE.BO"

    def test_mm_bse_override(self, reg):
        info = reg.resolve("M&M", exchange="BSE")
        assert info.yf_ticker == "M%26M.BO"

    def test_bse_equity_segment(self, reg):
        info = reg.resolve("TCS", exchange="BSE")
        assert info.segment == "EQUITY"
        assert info.exchange == "BSE"

    def test_bse_delivery_commission(self, reg):
        info = reg.resolve("INFY", exchange="BSE", instrument="SPOT")
        assert info.commission_segment == "EQUITY_DELIVERY"

    def test_bse_lot_size_one(self, reg):
        info = reg.resolve("HCLTECH", exchange="BSE")
        assert info.lot_size == 1


# ── BSE Index ─────────────────────────────────────────────────────────────────

class TestBSEIndex:
    def test_sensex_resolves(self, reg):
        info = reg.resolve("SENSEX", exchange="BSE")
        assert info.yf_ticker == "^BSESN"

    def test_sensex_is_index(self, reg):
        info = reg.resolve("SENSEX", exchange="BSE")
        assert info.is_index()

    def test_bsebank_resolves(self, reg):
        info = reg.resolve("BSEBANK", exchange="BSE")
        assert info.yf_ticker == "^BSEBANK"

    def test_bse_index_is_index(self, reg):
        assert reg.is_index("SENSEX")


# ── NSE F&O ───────────────────────────────────────────────────────────────────

class TestNFOFutures:
    def test_nifty_futures_lot_size(self, reg):
        info = reg.resolve("NIFTY", exchange="NFO", instrument="FUTURES")
        assert info.lot_size == 75

    def test_banknifty_futures_lot_size(self, reg):
        info = reg.resolve("BANKNIFTY", exchange="NFO", instrument="FUTURES")
        assert info.lot_size == 15

    def test_nifty_futures_uses_index_yf_ticker(self, reg):
        info = reg.resolve("NIFTY", exchange="NFO", instrument="FUTURES")
        assert info.yf_ticker == "^NSEI"

    def test_reliance_futures_lot_size(self, reg):
        info = reg.resolve("RELIANCE", exchange="NFO", instrument="FUTURES")
        assert info.lot_size == 250

    def test_futures_commission_segment(self, reg):
        info = reg.resolve("NIFTY", exchange="NFO", instrument="FUTURES")
        assert info.commission_segment == "FNO_FUTURES"

    def test_options_commission_segment(self, reg):
        info = reg.resolve("NIFTY", exchange="NFO", instrument="OPTIONS")
        assert info.commission_segment == "FNO_OPTIONS"

    def test_fno_segment_label(self, reg):
        info = reg.resolve("NIFTY", exchange="NFO", instrument="FUTURES")
        assert info.segment == "FNO_FUTURES"

    def test_fno_notes_contains_lot_size(self, reg):
        info = reg.resolve("RELIANCE", exchange="NFO", instrument="FUTURES")
        assert "250" in info.notes

    def test_is_fno_eligible(self, reg):
        assert reg.is_fno_eligible("NIFTY")
        assert reg.is_fno_eligible("RELIANCE")
        assert not reg.is_fno_eligible("RANDOMSTOCK")

    def test_scaled_turnover_fno(self, reg):
        info = reg.resolve("NIFTY", exchange="NFO", instrument="FUTURES")
        # NIFTY lot=75, price=24000, qty=1 lot → 24000 × 75 = 1,800,000
        assert info.scaled_turnover(24_000.0, 1) == pytest.approx(1_800_000.0)


# ── MCX Commodity ─────────────────────────────────────────────────────────────

class TestMCXCommodity:
    def test_gold_resolves(self, reg):
        info = reg.resolve("GOLD", exchange="MCX")
        assert info.yf_ticker == "GC=F"

    def test_gold_usd_proxy(self, reg):
        info = reg.resolve("GOLD", exchange="MCX")
        assert info.usd_proxy is True
        assert info.currency == "USD"

    def test_crudeoil_lot_size(self, reg):
        info = reg.resolve("CRUDEOIL", exchange="MCX")
        assert info.lot_size == 100

    def test_silver_lot_size(self, reg):
        info = reg.resolve("SILVER", exchange="MCX")
        assert info.lot_size == 30

    def test_naturalgas_resolves(self, reg):
        info = reg.resolve("NATURALGAS", exchange="MCX")
        assert info.yf_ticker == "NG=F"

    def test_mcx_commission_segment(self, reg):
        info = reg.resolve("GOLD", exchange="MCX")
        assert info.commission_segment == "MCX_COMMODITY"

    def test_commodity_segment_label(self, reg):
        info = reg.resolve("COPPER", exchange="MCX")
        assert info.segment == "COMMODITY"

    def test_unknown_mcx_symbol_raises(self, reg):
        with pytest.raises(ValueError, match="Unknown MCX symbol"):
            reg.resolve("PLATINUM", exchange="MCX")

    def test_goldm_mini_contract(self, reg):
        info = reg.resolve("GOLDM", exchange="MCX")
        assert info.lot_size == 1     # GOLDM = 1g contract

    def test_mcx_notes_mention_usd(self, reg):
        info = reg.resolve("CRUDEOIL", exchange="MCX")
        assert "USD" in info.notes or "proxy" in info.notes.lower()


# ── NSE CDS Currency ──────────────────────────────────────────────────────────

class TestCDSCurrency:
    def test_usdinr_resolves(self, reg):
        info = reg.resolve("USDINR", exchange="CDS")
        assert info.yf_ticker == "USDINR=X"

    def test_eurinr_resolves(self, reg):
        info = reg.resolve("EURINR", exchange="CDS")
        assert info.yf_ticker == "EURINR=X"

    def test_currency_lot_size(self, reg):
        info = reg.resolve("USDINR", exchange="CDS")
        assert info.lot_size == 1000

    def test_currency_segment(self, reg):
        info = reg.resolve("GBPINR", exchange="CDS")
        assert info.segment == "CURRENCY"

    def test_currency_commission_segment(self, reg):
        info = reg.resolve("USDINR", exchange="CDS")
        assert info.commission_segment == "CDS_CURRENCY"

    def test_unknown_cds_symbol_raises(self, reg):
        with pytest.raises(ValueError, match="Unknown CDS symbol"):
            reg.resolve("CHFINR", exchange="CDS")

    def test_currency_tick_size(self, reg):
        info = reg.resolve("USDINR", exchange="CDS")
        assert info.tick_size == pytest.approx(0.0025)


# ── auto_detect ───────────────────────────────────────────────────────────────

class TestAutoDetect:
    def test_gold_auto_detects_mcx(self, reg):
        info = reg.auto_detect("GOLD")
        assert info.exchange == "MCX"

    def test_usdinr_auto_detects_cds(self, reg):
        info = reg.auto_detect("USDINR")
        assert info.exchange == "CDS"

    def test_nifty50_auto_detects_nse_index(self, reg):
        info = reg.auto_detect("NIFTY50")
        assert info.segment == "INDEX"

    def test_sensex_auto_detects_bse_index(self, reg):
        info = reg.auto_detect("SENSEX")
        assert info.exchange == "BSE"

    def test_reliance_defaults_to_nse(self, reg):
        info = reg.auto_detect("RELIANCE")
        assert info.exchange == "NSE"
        assert info.yf_ticker == "RELIANCE.NS"


# ── get_commission_segment ────────────────────────────────────────────────────

class TestGetCommissionSegment:
    def test_nse_delivery(self, reg):
        assert reg.get_commission_segment("RELIANCE", "NSE", "SPOT") == "EQUITY_DELIVERY"

    def test_nse_intraday(self, reg):
        assert reg.get_commission_segment("RELIANCE", "NSE", "INTRADAY") == "EQUITY_INTRADAY"

    def test_nfo_futures(self, reg):
        assert reg.get_commission_segment("NIFTY", "NFO", "FUTURES") == "FNO_FUTURES"

    def test_nfo_options(self, reg):
        assert reg.get_commission_segment("NIFTY", "NFO", "OPTIONS") == "FNO_OPTIONS"

    def test_mcx_commodity(self, reg):
        assert reg.get_commission_segment("GOLD", "MCX") == "MCX_COMMODITY"

    def test_cds_currency(self, reg):
        assert reg.get_commission_segment("USDINR", "CDS") == "CDS_CURRENCY"


# ── get_lot_size ──────────────────────────────────────────────────────────────

class TestGetLotSize:
    def test_nifty_lot_size(self, reg):
        assert reg.get_lot_size("NIFTY", "NFO") == 75

    def test_banknifty_lot_size(self, reg):
        assert reg.get_lot_size("BANKNIFTY", "NFO") == 15

    def test_equity_lot_size_fallback(self, reg):
        assert reg.get_lot_size("SOMESTOCK", "NFO") == 1

    def test_gold_mcx_lot_size(self, reg):
        assert reg.get_lot_size("GOLD", "MCX") == 1

    def test_crudeoil_mcx_lot_size(self, reg):
        assert reg.get_lot_size("CRUDEOIL", "MCX") == 100

    def test_usdinr_cds_lot_size(self, reg):
        assert reg.get_lot_size("USDINR", "CDS") == 1000


# ── session_hours ─────────────────────────────────────────────────────────────

class TestSessionHours:
    def test_nse_session(self, reg):
        h = reg.session_hours("NSE")
        assert h["open"] == "09:15"
        assert h["close"] == "15:30"

    def test_mcx_session_closes_late(self, reg):
        h = reg.session_hours("MCX")
        assert h["close"] == "23:30"

    def test_cds_session(self, reg):
        h = reg.session_hours("CDS")
        assert h["open"] == "09:00"

    def test_invalid_exchange_raises(self, reg):
        with pytest.raises(ValueError):
            reg.session_hours("NASDAQ")

    def test_all_sessions_have_tz(self, reg):
        for exch in ["NSE", "BSE", "NFO", "MCX", "CDS"]:
            h = reg.session_hours(exch)
            assert h["tz"] == "Asia/Kolkata"


# ── list_symbols ──────────────────────────────────────────────────────────────

class TestListSymbols:
    def test_nse_list_contains_nifty50(self, reg):
        syms = reg.list_symbols("NSE")
        assert "RELIANCE" in syms
        assert "TCS" in syms

    def test_mcx_list_contains_gold(self, reg):
        syms = reg.list_symbols("MCX")
        assert "GOLD" in syms
        assert "CRUDEOIL" in syms

    def test_cds_list_contains_usdinr(self, reg):
        syms = reg.list_symbols("CDS")
        assert "USDINR" in syms

    def test_invalid_exchange_list_raises(self, reg):
        with pytest.raises(ValueError):
            reg.list_symbols("INVALID")


# ── list_segments ─────────────────────────────────────────────────────────────

class TestListSegments:
    def test_list_segments_returns_all(self, reg):
        segs = reg.list_segments()
        assert "NSE_EQUITY" in segs
        assert "NFO_FUTURES" in segs
        assert "MCX_COMMODITY" in segs
        assert "CDS_CURRENCY" in segs


# ── Invalid exchange ──────────────────────────────────────────────────────────

class TestInvalidExchange:
    def test_unknown_exchange_raises(self, reg):
        with pytest.raises(ValueError, match="Unknown exchange"):
            reg.resolve("RELIANCE", exchange="NASDAQ")


# ── Integration: registry + commission ────────────────────────────────────────

class TestRegistryCommissionIntegration:
    """Verify that commission_segment values are valid CommissionCalculator keys."""

    VALID_COMMISSION_SEGMENTS = {
        "EQUITY_INTRADAY", "EQUITY_DELIVERY",
        "FNO_FUTURES", "FNO_OPTIONS",
        "MCX_COMMODITY", "CDS_CURRENCY",
    }

    @pytest.mark.parametrize("symbol,exchange,instrument", [
        ("RELIANCE", "NSE",  "SPOT"),
        ("RELIANCE", "NSE",  "INTRADAY"),
        ("TCS",      "BSE",  "SPOT"),
        ("NIFTY",    "NFO",  "FUTURES"),
        ("NIFTY",    "NFO",  "OPTIONS"),
        ("GOLD",     "MCX",  "FUTURES"),
        ("USDINR",   "CDS",  "FUTURES"),
    ])
    def test_commission_segment_is_valid(self, reg, symbol, exchange, instrument):
        info = reg.resolve(symbol, exchange, instrument)
        assert info.commission_segment in self.VALID_COMMISSION_SEGMENTS, (
            f"{symbol}/{exchange}/{instrument} → '{info.commission_segment}' "
            f"not in valid set"
        )
