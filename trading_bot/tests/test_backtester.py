"""
test_backtester.py — Unit tests for multi-strategy backtester.

Tests:
- calculate_sl_tp is used (R:R constraint)
- _compute_report with known trade list
- Empty trades returns zero report
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
import pytest
from utils.backtester import Backtester, TradeRecord, StrategyReport
from utils.rr_calculator import MIN_RR_RATIO


@pytest.fixture
def sample_ohlcv_df():
    """Generate a simple OHLCV dataframe for testing."""
    dates = pd.date_range(start="2020-01-01", periods=100, freq="D")
    df = pd.DataFrame({
        "open": [100 + i * 0.5 for i in range(100)],
        "high": [101 + i * 0.5 for i in range(100)],
        "low": [99 + i * 0.5 for i in range(100)],
        "close": [100 + i * 0.5 for i in range(100)],
        "volume": [1000000] * 100,
    }, index=dates)
    return df


@pytest.fixture
def sample_trades():
    """Sample trade records for testing report calculation."""
    return [
        TradeRecord(
            entry_date="2020-01-05", exit_date="2020-01-10",
            entry_price=100.0, exit_price=105.0, action="BUY",
            sl=97.0, tp=106.0, pnl=5.0, rr_achieved=2.0,
            exit_reason="TP_HIT", signals_fired={"ema_cross": True}
        ),
        TradeRecord(
            entry_date="2020-01-15", exit_date="2020-01-20",
            entry_price=110.0, exit_price=108.0, action="BUY",
            sl=107.0, tp=116.0, pnl=-1.82, rr_achieved=0.67,
            exit_reason="SL_HIT", signals_fired={"ema_cross": True}
        ),
        TradeRecord(
            entry_date="2020-01-25", exit_date="2020-02-01",
            entry_price=115.0, exit_price=121.0, action="BUY",
            sl=112.0, tp=121.0, pnl=5.22, rr_achieved=2.0,
            exit_reason="TP_HIT", signals_fired={"ema_cross": True, "volume_confirmation": True}
        ),
    ]


class TestBacktester:
    def test_backtester_initialization(self):
        """Test that Backtester can be instantiated."""
        bt = Backtester()
        assert bt.MAX_HOLD_DAYS == 20
        assert bt.INITIAL_CAPITAL == 100_000.0
    
    def test_resample_daily_unchanged(self, sample_ohlcv_df):
        """Test that 1D timeframe returns unchanged dataframe."""
        bt = Backtester()
        resampled = bt._resample(sample_ohlcv_df, "1D")
        assert len(resampled) == len(sample_ohlcv_df)
    
    def test_resample_weekly(self, sample_ohlcv_df):
        """Test weekly resampling."""
        bt = Backtester()
        resampled = bt._resample(sample_ohlcv_df, "1W")
        assert len(resampled) < len(sample_ohlcv_df)
        assert "open" in resampled.columns
        assert "close" in resampled.columns
    
    def test_compute_report_empty_trades(self):
        """Test that empty trade list produces zero report."""
        bt = Backtester()
        df = pd.DataFrame({"close": [100, 101, 102]}, index=pd.date_range("2020-01-01", periods=3))
        report = bt._compute_report("TEST", "1D", [], df)
        
        assert report.total_trades == 0
        assert report.winning_trades == 0
        assert report.win_rate_pct == 0.0
        assert report.avg_rr == 0.0
    
    def test_compute_report_with_trades(self, sample_trades, sample_ohlcv_df):
        """Test report calculation with known trades."""
        bt = Backtester()
        report = bt._compute_report("TREND_FOLLOWING", "1D", sample_trades, sample_ohlcv_df)
        
        # Should have 3 trades, 2 winning, 1 losing
        assert report.total_trades == 3
        assert report.winning_trades == 2
        assert report.losing_trades == 1
        assert report.win_rate_pct == pytest.approx(66.7, abs=0.1)
        
        # Check R:R stats
        assert report.avg_rr > 0
        assert report.best_rr == 2.0
        assert report.worst_rr < 1.0
        
        # Check WHY it works attribution
        assert "ema_cross" in report.why_it_works
        assert report.why_it_works["ema_cross"] == 100  # Present in all winning trades
    
    def test_rr_constraint_enforced(self, sample_ohlcv_df):
        """Test that strategies use calculate_sl_tp and respect MIN_RR_RATIO."""
        bt = Backtester()
        
        # Run trend following strategy
        trades = bt._strategy_trend_following(sample_ohlcv_df, "TEST")
        
        # All trades that got entered should have acceptable R:R
        # (This is implicit because calculate_sl_tp returns acceptable=False when R:R < 2.0)
        # and the strategy only enters when rr_result.acceptable is True
        for trade in trades:
            # The intended R:R from SL/TP should be >= MIN_RR_RATIO
            risk = abs(trade.entry_price - trade.sl)
            reward = abs(trade.tp - trade.entry_price)
            intended_rr = reward / risk if risk > 0 else 0
            assert intended_rr >= MIN_RR_RATIO - 0.01  # Small tolerance for rounding
    
    def test_get_best_strategy(self):
        """Test best strategy selection logic."""
        bt = Backtester()
        
        reports = [
            StrategyReport(
                strategy_name="A", timeframe="1D", total_trades=10,
                winning_trades=6, losing_trades=4, win_rate_pct=60.0,
                avg_rr=2.5, best_rr=3.0, worst_rr=1.5,
                max_drawdown_pct=5.0, sharpe_ratio=1.2, total_pnl=15.0
            ),
            StrategyReport(
                strategy_name="B", timeframe="1W", total_trades=8,
                winning_trades=5, losing_trades=3, win_rate_pct=62.5,
                avg_rr=3.0, best_rr=4.0, worst_rr=2.0,
                max_drawdown_pct=4.0, sharpe_ratio=1.5, total_pnl=20.0
            ),
            StrategyReport(
                strategy_name="C", timeframe="1D", total_trades=3,  # Too few trades
                winning_trades=3, losing_trades=0, win_rate_pct=100.0,
                avg_rr=5.0, best_rr=5.0, worst_rr=5.0,
                max_drawdown_pct=0.0, sharpe_ratio=2.0, total_pnl=30.0
            ),
        ]
        
        best = bt._get_best_strategy(reports)
        
        # Should pick B: 62.5 * 3.0 = 187.5 vs A: 60.0 * 2.5 = 150.0
        # C is ignored because total_trades <= 5
        assert best.strategy_name == "B"
    
    def test_run_all_strategies_integration(self, sample_ohlcv_df):
        """Integration test: run all strategies on sample data."""
        bt = Backtester()
        result = bt.run_all_strategies("TEST", sample_ohlcv_df)
        
        # Should return a valid BacktestResult
        assert result.symbol == "TEST"
        assert isinstance(result.strategy_reports, list)
        assert isinstance(result.entry_plan, dict)
        
        # With small sample data, we may or may not get trades
        # Just verify structure is correct
        if result.strategy_reports:
            assert result.recommended_strategy != "N/A"
            assert "entry_zone" in result.entry_plan


# ── Commission integration tests ─────────────────────────────────────────────

class TestCommissionIntegration:
    """Verify that _compute_report correctly applies CommissionCalculator."""

    @pytest.fixture
    def bt(self):
        return Backtester()

    @pytest.fixture
    def winning_trades(self):
        """Three clearly-winning trades (gross pnl > any realistic commission)."""
        return [
            TradeRecord(
                entry_date="2020-01-05", exit_date="2020-01-10",
                entry_price=100.0, exit_price=106.0, action="BUY",
                sl=97.0, tp=106.0, pnl=6.0, rr_achieved=2.0,
                exit_reason="TP_HIT", signals_fired={"ema_cross": True},
            ),
            TradeRecord(
                entry_date="2020-01-15", exit_date="2020-01-20",
                entry_price=110.0, exit_price=116.0, action="BUY",
                sl=107.0, tp=116.0, pnl=5.45, rr_achieved=2.0,
                exit_reason="TP_HIT", signals_fired={"ema_cross": True},
            ),
            TradeRecord(
                entry_date="2020-01-25", exit_date="2020-02-01",
                entry_price=115.0, exit_price=107.0, action="BUY",
                sl=112.0, tp=121.0, pnl=-6.96, rr_achieved=0.5,
                exit_reason="SL_HIT", signals_fired={"ema_cross": True},
            ),
        ]

    def test_trade_records_enriched_with_net_pnl(self, bt, winning_trades, sample_ohlcv_df):
        report = bt._compute_report(
            "TREND_FOLLOWING", "1D", winning_trades, sample_ohlcv_df,
            commission_segment="EQUITY_DELIVERY",
        )
        for t in report.trade_records:
            assert t.gross_pnl != 0.0 or t.pnl == 0.0  # gross_pnl is populated
            assert t.commission_pct > 0.0                # commission deducted
            assert t.net_pnl == pytest.approx(t.gross_pnl - t.commission_pct, abs=0.001)

    def test_net_pnl_less_than_gross_pnl(self, bt, winning_trades, sample_ohlcv_df):
        report = bt._compute_report(
            "TREND_FOLLOWING", "1D", winning_trades, sample_ohlcv_df,
            commission_segment="EQUITY_DELIVERY",
        )
        # Net must always be strictly less than gross (commission is always positive)
        assert report.net_total_pnl < report.gross_total_pnl

    def test_gross_and_net_totals_populated(self, bt, winning_trades, sample_ohlcv_df):
        report = bt._compute_report(
            "TREND_FOLLOWING", "1D", winning_trades, sample_ohlcv_df,
            commission_segment="EQUITY_DELIVERY",
        )
        assert report.gross_total_pnl != 0.0
        assert report.net_total_pnl != 0.0
        assert report.total_commission_pct > 0.0

    def test_commission_segment_stored_in_report(self, bt, winning_trades, sample_ohlcv_df):
        report = bt._compute_report(
            "TREND_FOLLOWING", "1D", winning_trades, sample_ohlcv_df,
            commission_segment="FNO_FUTURES",
        )
        assert report.commission_segment == "FNO_FUTURES"

    def test_fno_cheaper_than_delivery(self, bt, winning_trades, sample_ohlcv_df):
        """F&O has lower STT (0.01%) vs delivery (0.1%), so net should be higher for F&O."""
        r_delivery = bt._compute_report(
            "TREND_FOLLOWING", "1D", winning_trades, sample_ohlcv_df,
            commission_segment="EQUITY_DELIVERY",
        )
        r_fno = bt._compute_report(
            "TREND_FOLLOWING", "1D", winning_trades, sample_ohlcv_df,
            commission_segment="FNO_FUTURES",
        )
        assert r_fno.total_commission_pct < r_delivery.total_commission_pct

    def test_win_rate_uses_net_pnl(self, bt, sample_ohlcv_df):
        """A marginal gross-winning trade that is net-losing should reduce win rate."""
        # pnl=0.05% is below any realistic round-trip commission (>0.1%)
        marginal_winner = TradeRecord(
            entry_date="2020-01-05", exit_date="2020-01-10",
            entry_price=100.0, exit_price=100.05, action="BUY",
            sl=97.0, tp=106.0, pnl=0.05, rr_achieved=2.0,
            exit_reason="TP_HIT", signals_fired={},
        )
        clear_loser = TradeRecord(
            entry_date="2020-01-15", exit_date="2020-01-20",
            entry_price=100.0, exit_price=95.0, action="BUY",
            sl=97.0, tp=106.0, pnl=-5.0, rr_achieved=0.5,
            exit_reason="SL_HIT", signals_fired={},
        )
        report = bt._compute_report(
            "TREND_FOLLOWING", "1D", [marginal_winner, clear_loser], sample_ohlcv_df,
            commission_segment="EQUITY_DELIVERY",
        )
        # Both trades net-losing → win rate should be 0%
        assert report.win_rate_pct == 0.0

    def test_run_all_strategies_accepts_commission_params(self, bt, sample_ohlcv_df):
        result = bt.run_all_strategies(
            "TEST", sample_ohlcv_df,
            commission_segment="EQUITY_INTRADAY",
            lot_size=1,
        )
        assert result.commission_segment == "EQUITY_INTRADAY"
        assert result.symbol == "TEST"

    def test_entry_plan_includes_commission_fields(self, bt, sample_ohlcv_df):
        result = bt.run_all_strategies(
            "TEST", sample_ohlcv_df,
            commission_segment="EQUITY_DELIVERY",
        )
        if result.entry_plan:
            assert "net_total_pnl" in result.entry_plan
            assert "commission_drag_pct" in result.entry_plan


# ── Walk-forward tests ────────────────────────────────────────────────────────

class TestWalkForwardValidator:
    """Tests for WalkForwardValidator anchored walk-forward."""

    @pytest.fixture
    def large_df(self):
        """300-bar OHLCV — enough for 3 WF windows."""
        dates = pd.date_range("2018-01-01", periods=300, freq="D")
        closes = [100.0 + i * 0.3 + (i % 30) * 0.5 for i in range(300)]
        return pd.DataFrame({
            "open":   [c - 0.5 for c in closes],
            "high":   [c + 1.0 for c in closes],
            "low":    [c - 1.0 for c in closes],
            "close":  closes,
            "volume": [1_000_000] * 300,
        }, index=dates)

    def test_walk_forward_report_structure(self, large_df):
        from utils.backtester import WalkForwardValidator, WalkForwardReport
        bt = Backtester()
        validator = WalkForwardValidator()
        report = validator.validate(
            strategy="TREND_FOLLOWING",
            df=large_df,
            symbol="TEST",
            backtester=bt,
            commission_segment="EQUITY_DELIVERY",
        )
        assert isinstance(report, WalkForwardReport)
        assert report.n_windows >= 0
        assert 0.0 <= report.avg_stability

    def test_walk_forward_windows_have_dates(self, large_df):
        from utils.backtester import WalkForwardValidator
        bt = Backtester()
        validator = WalkForwardValidator()
        report = validator.validate(
            "TREND_FOLLOWING", large_df, "TEST", bt, "EQUITY_DELIVERY"
        )
        for w in report.windows:
            assert w.train_start < w.train_end
            assert w.test_start < w.test_end
            assert w.window_id > 0

    def test_stability_score_bounded(self, large_df):
        from utils.backtester import WalkForwardValidator
        bt = Backtester()
        validator = WalkForwardValidator()
        report = validator.validate(
            "TREND_FOLLOWING", large_df, "TEST", bt, "EQUITY_DELIVERY"
        )
        for w in report.windows:
            assert 0.0 <= w.stability_score <= 1.5

    def test_run_all_with_walk_forward(self, large_df):
        bt = Backtester()
        result = bt.run_all_strategies(
            "TEST", large_df,
            commission_segment="EQUITY_DELIVERY",
            walk_forward=True,
        )
        assert result.walk_forward_enabled is True
        # If there are strategy reports, best should carry the WF report
        if result.strategy_reports:
            best = next(
                (r for r in result.strategy_reports
                 if r.strategy_name == result.recommended_strategy
                 and r.timeframe == result.recommended_timeframe),
                None
            )
            if best:
                assert best.walk_forward is not None

    def test_walk_forward_disabled_by_default(self, sample_ohlcv_df):
        bt = Backtester()
        result = bt.run_all_strategies("TEST", sample_ohlcv_df)
        assert result.walk_forward_enabled is False
        for r in result.strategy_reports:
            assert r.walk_forward is None


# ── WalkForwardReport / WalkForwardWindow dataclass tests ─────────────────────

class TestWalkForwardDataclasses:
    def test_walk_forward_window_fields(self):
        from utils.backtester import WalkForwardWindow
        w = WalkForwardWindow(
            window_id=1,
            train_start="2020-01-01", train_end="2022-01-01",
            test_start="2022-01-01", test_end="2022-07-01",
            train_win_rate=60.0, test_win_rate=55.0,
            train_pnl=12.5, test_pnl=8.3,
            stability_score=0.917,
        )
        assert w.stability_score == pytest.approx(0.917)

    def test_walk_forward_report_is_robust_flag(self):
        from utils.backtester import WalkForwardReport, WalkForwardWindow
        windows = [
            WalkForwardWindow(1, "a", "b", "c", "d", 60, 55, 12, 8, 0.917),
            WalkForwardWindow(2, "a", "b", "c", "d", 58, 25, 10, 4, 0.431),
        ]
        report = WalkForwardReport(
            n_windows=2,
            windows=windows,
            avg_stability=0.674,
            is_robust=True,
        )
        assert report.is_robust is True


# ── TradeRecord new fields backward-compat ────────────────────────────────────

class TestTradeRecordBackwardCompat:
    def test_default_net_pnl_zero(self):
        t = TradeRecord(
            entry_date="2020-01-01", exit_date="2020-01-10",
            entry_price=100.0, exit_price=105.0, action="BUY",
            sl=97.0, tp=106.0, pnl=5.0, rr_achieved=2.0,
            exit_reason="TP_HIT", signals_fired={},
        )
        assert t.net_pnl == 0.0
        assert t.gross_pnl == 0.0
        assert t.commission_pct == 0.0

