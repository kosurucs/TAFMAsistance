"""
test_commission.py — Unit tests for the Indian market commission calculator.

Run: pytest trading_bot/tests/test_commission.py -v
"""
from __future__ import annotations
import pytest
from src.utils.commission import (
    CommissionCalculator,
    CommissionBreakdown,
    RoundTripCost,
    _VALID_SEGMENTS,
)


@pytest.fixture
def calc():
    return CommissionCalculator(broker_preset="zerodha")


@pytest.fixture
def calc_no_slippage():
    return CommissionCalculator(broker_preset="zerodha")


# ── Validation ─────────────────────────────────────────────────────────────────

class TestValidation:
    def test_invalid_segment_raises(self, calc):
        with pytest.raises(ValueError, match="Unknown segment"):
            calc.calculate("INVALID_SEGMENT", 100_000)

    def test_invalid_trade_type_raises(self, calc):
        with pytest.raises(ValueError, match="trade_type"):
            calc.calculate("EQUITY_INTRADAY", 100_000, trade_type="HOLD")

    def test_negative_turnover_raises(self, calc):
        with pytest.raises(ValueError, match="turnover"):
            calc.calculate("EQUITY_INTRADAY", -1)

    def test_zero_turnover_returns_zero(self, calc):
        bd = calc.calculate("EQUITY_INTRADAY", 0, include_slippage=False)
        assert bd.total == 0.0

    def test_invalid_broker_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown broker_preset"):
            CommissionCalculator(broker_preset="badbroker")


# ── Equity Intraday ────────────────────────────────────────────────────────────

class TestEquityIntraday:
    """EQUITY_INTRADAY: STT on sell only (0.025%), brokerage ≤ ₹20."""

    def test_brokerage_capped_at_20(self, calc):
        # ₹100,000 × 0.03% = ₹30 → capped at ₹20
        bd = calc.calculate("EQUITY_INTRADAY", 100_000, "BUY", include_slippage=False)
        assert bd.brokerage == 20.0

    def test_brokerage_below_cap(self, calc):
        # ₹50,000 × 0.03% = ₹15 → under cap
        bd = calc.calculate("EQUITY_INTRADAY", 50_000, "BUY", include_slippage=False)
        assert bd.brokerage == pytest.approx(15.0, abs=0.01)

    def test_stt_zero_on_buy(self, calc):
        bd = calc.calculate("EQUITY_INTRADAY", 100_000, "BUY", include_slippage=False)
        assert bd.stt == 0.0

    def test_stt_on_sell(self, calc):
        # 0.025% on sell = ₹25 on ₹100k
        bd = calc.calculate("EQUITY_INTRADAY", 100_000, "SELL", include_slippage=False)
        assert bd.stt == pytest.approx(25.0, abs=0.1)

    def test_ctt_zero_for_equity(self, calc):
        bd = calc.calculate("EQUITY_INTRADAY", 100_000, "SELL", include_slippage=False)
        assert bd.ctt == 0.0

    def test_stamp_duty_only_on_buy(self, calc):
        buy  = calc.calculate("EQUITY_INTRADAY", 100_000, "BUY",  include_slippage=False)
        sell = calc.calculate("EQUITY_INTRADAY", 100_000, "SELL", include_slippage=False)
        assert buy.stamp_duty > 0
        assert sell.stamp_duty == 0.0

    def test_gst_positive(self, calc):
        bd = calc.calculate("EQUITY_INTRADAY", 100_000, "BUY", include_slippage=False)
        assert bd.gst > 0

    def test_total_is_sum_of_components(self, calc):
        bd = calc.calculate("EQUITY_INTRADAY", 100_000, "SELL", include_slippage=False)
        expected = (
            bd.brokerage + bd.stt + bd.ctt +
            bd.exchange_fee + bd.sebi_fee +
            bd.gst + bd.stamp_duty + bd.slippage
        )
        assert bd.total == pytest.approx(expected, abs=0.001)

    def test_round_trip_sell_more_than_buy(self, calc):
        # Sell has STT; buy does not → sell leg should cost more
        buy  = calc.calculate("EQUITY_INTRADAY", 100_000, "BUY",  include_slippage=False)
        sell = calc.calculate("EQUITY_INTRADAY", 100_000, "SELL", include_slippage=False)
        assert sell.total > buy.total


# ── Equity Delivery ────────────────────────────────────────────────────────────

class TestEquityDelivery:
    """EQUITY_DELIVERY: zero brokerage (Zerodha), STT 0.1% both sides."""

    def test_zero_brokerage_zerodha(self, calc):
        bd = calc.calculate("EQUITY_DELIVERY", 100_000, "BUY", include_slippage=False)
        assert bd.brokerage == 0.0

    def test_stt_both_sides(self, calc):
        buy  = calc.calculate("EQUITY_DELIVERY", 100_000, "BUY",  include_slippage=False)
        sell = calc.calculate("EQUITY_DELIVERY", 100_000, "SELL", include_slippage=False)
        # 0.1% = ₹100 on ₹100k
        assert buy.stt  == pytest.approx(100.0, abs=0.1)
        assert sell.stt == pytest.approx(100.0, abs=0.1)

    def test_delivery_stt_higher_than_intraday(self, calc):
        intraday_sell = calc.calculate("EQUITY_INTRADAY", 100_000, "SELL", include_slippage=False)
        delivery_sell = calc.calculate("EQUITY_DELIVERY", 100_000, "SELL", include_slippage=False)
        assert delivery_sell.stt > intraday_sell.stt


# ── F&O Futures ───────────────────────────────────────────────────────────────

class TestFNOFutures:
    """FNO_FUTURES: STT 0.0125% on sell, flat ₹20 brokerage."""

    def test_flat_brokerage(self, calc):
        bd = calc.calculate("FNO_FUTURES", 500_000, "BUY", include_slippage=False)
        assert bd.brokerage == 20.0

    def test_stt_zero_on_buy(self, calc):
        bd = calc.calculate("FNO_FUTURES", 500_000, "BUY", include_slippage=False)
        assert bd.stt == 0.0

    def test_stt_on_sell(self, calc):
        # 0.0125% on ₹500k = ₹62.5
        bd = calc.calculate("FNO_FUTURES", 500_000, "SELL", include_slippage=False)
        assert bd.stt == pytest.approx(62.5, abs=0.5)

    def test_no_ctt(self, calc):
        bd = calc.calculate("FNO_FUTURES", 500_000, "SELL", include_slippage=False)
        assert bd.ctt == 0.0


# ── F&O Options ───────────────────────────────────────────────────────────────

class TestFNOOptions:
    """FNO_OPTIONS: STT 0.0625% on sell (on premium), wider exchange fee."""

    def test_stt_on_sell_premium(self, calc):
        # premium_turnover = 100 (premium) × 50 (lot) = ₹5000
        premium_tv = 5_000
        bd = calc.calculate("FNO_OPTIONS", premium_tv, "SELL", include_slippage=False)
        # 0.0625% of ₹5000 = ₹3.125
        assert bd.stt == pytest.approx(3.125, abs=0.05)

    def test_options_exchange_fee_higher_than_futures(self, calc):
        bd_opt = calc.calculate("FNO_OPTIONS",  100_000, "BUY", include_slippage=False)
        bd_fut = calc.calculate("FNO_FUTURES",  100_000, "BUY", include_slippage=False)
        assert bd_opt.exchange_fee > bd_fut.exchange_fee


# ── MCX Commodity ─────────────────────────────────────────────────────────────

class TestMCXCommodity:
    """MCX_COMMODITY: No STT, CTT 0.01% on sell (non-agri)."""

    def test_no_stt(self, calc):
        bd = calc.calculate("MCX_COMMODITY", 200_000, "SELL", include_slippage=False)
        assert bd.stt == 0.0

    def test_ctt_on_sell(self, calc):
        # 0.01% of ₹200k = ₹20
        bd = calc.calculate("MCX_COMMODITY", 200_000, "SELL", include_slippage=False)
        assert bd.ctt == pytest.approx(20.0, abs=0.1)

    def test_no_ctt_on_buy(self, calc):
        bd = calc.calculate("MCX_COMMODITY", 200_000, "BUY", include_slippage=False)
        assert bd.ctt == 0.0


# ── CDS Currency ──────────────────────────────────────────────────────────────

class TestCDSCurrency:
    """CDS_CURRENCY: No STT, No CTT, lowest exchange fee."""

    def test_no_stt_no_ctt(self, calc):
        bd = calc.calculate("CDS_CURRENCY", 100_000, "SELL", include_slippage=False)
        assert bd.stt == 0.0
        assert bd.ctt == 0.0

    def test_currency_exchange_fee_lowest(self, calc):
        """CDS exchange fee should be significantly lower than equity."""
        bd_cds    = calc.calculate("CDS_CURRENCY",     100_000, "BUY", include_slippage=False)
        bd_equity = calc.calculate("EQUITY_INTRADAY",  100_000, "BUY", include_slippage=False)
        assert bd_cds.exchange_fee < bd_equity.exchange_fee


# ── Round Trip ────────────────────────────────────────────────────────────────

class TestRoundTrip:
    def test_round_trip_cost_equals_buy_plus_sell(self, calc):
        rt = calc.round_trip_cost("EQUITY_INTRADAY", 100_000, include_slippage=False)
        buy  = calc.calculate("EQUITY_INTRADAY", 100_000, "BUY",  include_slippage=False)
        sell = calc.calculate("EQUITY_INTRADAY", 100_000, "SELL", include_slippage=False)
        assert rt.total == pytest.approx(buy.total + sell.total, abs=0.001)

    def test_round_trip_as_pct(self, calc):
        rt = calc.round_trip_cost("EQUITY_INTRADAY", 100_000, include_slippage=True)
        pct = rt.as_pct()
        # Realistic range: 0.05% – 0.2% for intraday equity
        assert 0.0 < pct < 0.5

    def test_round_trip_to_dict_keys(self, calc):
        rt = calc.round_trip_cost("FNO_FUTURES", 500_000)
        d = rt.to_dict()
        assert "buy_leg" in d
        assert "sell_leg" in d
        assert "total_pct" in d


# ── apply_to_pnl ──────────────────────────────────────────────────────────────

class TestApplyToPnl:
    def test_net_pnl_less_than_gross(self, calc):
        net_pnl, rt = calc.apply_to_pnl(
            pnl_inr=5_000,
            segment="EQUITY_INTRADAY",
            entry_turnover=100_000,
        )
        assert net_pnl < 5_000
        assert rt.total > 0

    def test_negative_pnl_worsened(self, calc):
        net_pnl, _ = calc.apply_to_pnl(
            pnl_inr=-1_000,
            segment="EQUITY_DELIVERY",
            entry_turnover=100_000,
        )
        assert net_pnl < -1_000

    def test_asymmetric_entry_exit(self, calc):
        """Exit turnover higher than entry — e.g. profitable trade."""
        net_pnl, rt = calc.apply_to_pnl(
            pnl_inr=10_000,
            segment="FNO_FUTURES",
            entry_turnover=500_000,
            exit_turnover=510_000,
        )
        assert net_pnl < 10_000


# ── Broker Presets ────────────────────────────────────────────────────────────

class TestBrokerPresets:
    def test_icici_delivery_not_zero_brokerage(self):
        calc_icici = CommissionCalculator(broker_preset="icici")
        bd = calc_icici.calculate("EQUITY_DELIVERY", 100_000, "BUY", include_slippage=False)
        # ICICI charges 0.55% — much more than Zerodha zero
        assert bd.brokerage > 0

    def test_groww_intraday_capped_at_20(self):
        calc_groww = CommissionCalculator(broker_preset="groww")
        bd = calc_groww.calculate("EQUITY_INTRADAY", 100_000, "BUY", include_slippage=False)
        assert bd.brokerage == 20.0

    def test_zerodha_cheaper_delivery_than_icici(self):
        z = CommissionCalculator(broker_preset="zerodha")
        i = CommissionCalculator(broker_preset="icici")
        bd_z = z.calculate("EQUITY_DELIVERY", 500_000, "BUY", include_slippage=False)
        bd_i = i.calculate("EQUITY_DELIVERY", 500_000, "BUY", include_slippage=False)
        assert bd_z.total < bd_i.total


# ── Slippage ──────────────────────────────────────────────────────────────────

class TestSlippage:
    def test_slippage_adds_to_total(self, calc):
        with_slip    = calc.calculate("EQUITY_INTRADAY", 100_000, include_slippage=True)
        without_slip = calc.calculate("EQUITY_INTRADAY", 100_000, include_slippage=False)
        assert with_slip.total > without_slip.total
        assert with_slip.slippage > 0

    def test_custom_slippage_override(self):
        calc_custom = CommissionCalculator(
            broker_preset="zerodha",
            slippage_override={"EQUITY_INTRADAY": 0.001}  # 0.1% — 3x default
        )
        bd = calc_custom.calculate("EQUITY_INTRADAY", 100_000, include_slippage=True)
        assert bd.slippage == pytest.approx(100.0, abs=0.1)  # 0.1% × ₹100k = ₹100


# ── Summary Table ─────────────────────────────────────────────────────────────

class TestSummaryTable:
    def test_summary_returns_all_segments(self, calc):
        rows = calc.summary_table()
        seg_names = {r["segment"] for r in rows}
        assert seg_names == _VALID_SEGMENTS

    def test_summary_round_trip_pct_positive(self, calc):
        for row in calc.summary_table():
            assert row["round_trip_cost_pct"] >= 0, f"{row['segment']} has negative cost"

    def test_delivery_costlier_than_intraday(self, calc):
        rows = {r["segment"]: r for r in calc.summary_table()}
        # STT on both sides for delivery makes it more expensive
        assert (
            rows["EQUITY_DELIVERY"]["round_trip_cost_pct"]
            > rows["EQUITY_INTRADAY"]["round_trip_cost_pct"]
        )


# ── as_pct ────────────────────────────────────────────────────────────────────

class TestAsPct:
    def test_as_pct_zero_denominator(self, calc):
        bd = calc.calculate("EQUITY_INTRADAY", 0, include_slippage=False)
        assert bd.as_pct() == 0.0

    def test_as_pct_reasonable_range(self, calc):
        bd = calc.calculate("EQUITY_INTRADAY", 100_000, "SELL", include_slippage=False)
        pct = bd.as_pct()
        # Single leg cost should be 0.01% – 0.1% for liquid equity intraday
        assert 0.01 < pct < 0.5
