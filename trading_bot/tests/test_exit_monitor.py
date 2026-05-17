"""
test_exit_monitor.py — Unit tests for ExitMonitor.

Tests:
1. SL hit detection (BUY and SELL)
2. TP hit detection (BUY and SELL)
3. Volume crash detection
4. Market crash risk (Nifty drop + high beta)
5. Trailing stop activation (BUY and SELL)
6. RSI overbought/oversold (advisory only)
7. Normal position (no exit signals)
8. check_all_positions batch processing
"""

from __future__ import annotations

import pytest

from src.utils.exit_monitor import ExitMonitor, ExitSignal


class TestExitMonitor:
    """Tests for ExitMonitor exit logic."""

    def test_sl_hit_buy_position(self):
        """Test SL hit for BUY position — should trigger IMMEDIATE exit."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="BUY",
            entry_price=1000,
            current_price=980,  # below SL
            sl=985,
            tp=1045,
            atr=15,
        )
        assert signal.should_exit is True
        assert signal.urgency == "IMMEDIATE"
        assert "Stop-loss hit" in signal.reason
        assert signal.adjusted_sl is None

    def test_sl_hit_sell_position(self):
        """Test SL hit for SELL position — should trigger IMMEDIATE exit."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="SELL",
            entry_price=1000,
            current_price=1020,  # above SL
            sl=1015,
            tp=955,
            atr=15,
        )
        assert signal.should_exit is True
        assert signal.urgency == "IMMEDIATE"
        assert "Stop-loss hit" in signal.reason

    def test_tp_hit_buy_position(self):
        """Test TP hit for BUY position — should trigger IMMEDIATE exit."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="BUY",
            entry_price=1000,
            current_price=1050,  # above TP
            sl=985,
            tp=1045,
            atr=15,
        )
        assert signal.should_exit is True
        assert signal.urgency == "IMMEDIATE"
        assert "Take-profit hit" in signal.reason

    def test_tp_hit_sell_position(self):
        """Test TP hit for SELL position — should trigger IMMEDIATE exit."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="SELL",
            entry_price=1000,
            current_price=950,  # below TP
            sl=1015,
            tp=955,
            atr=15,
        )
        assert signal.should_exit is True
        assert signal.urgency == "IMMEDIATE"
        assert "Take-profit hit" in signal.reason

    def test_volume_crash(self):
        """Test volume deterioration — should trigger IMMEDIATE exit."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="BUY",
            entry_price=1000,
            current_price=1010,
            sl=985,
            tp=1045,
            atr=15,
            volume=25_000,  # 25% of average
            avg_volume=100_000,
        )
        assert signal.should_exit is True
        assert signal.urgency == "IMMEDIATE"
        assert "Volume crisis" in signal.reason

    def test_market_crash_risk(self):
        """Test market crash risk (Nifty drop + high beta) — should trigger IMMEDIATE exit."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="BUY",
            entry_price=1000,
            current_price=1005,
            sl=985,
            tp=1045,
            atr=15,
            nifty_change_pct=-2.0,
            beta=1.5,
        )
        assert signal.should_exit is True
        assert signal.urgency == "IMMEDIATE"
        assert "Market crash risk" in signal.reason

    def test_trailing_stop_buy_position(self):
        """Test trailing stop activation for BUY position — should NOT exit but adjust SL."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="BUY",
            entry_price=1000,
            current_price=1035,  # price moved up 2+ ATR
            sl=985,
            tp=1045,
            atr=15,  # 2*ATR = 30, so trigger = 1030
        )
        assert signal.should_exit is False
        assert signal.urgency == "MONITOR"
        assert "Trailing stop" in signal.reason
        assert signal.adjusted_sl == 1015  # entry + 1*ATR

    def test_trailing_stop_sell_position(self):
        """Test trailing stop activation for SELL position — should NOT exit but adjust SL."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="SELL",
            entry_price=1000,
            current_price=965,  # price moved down 2+ ATR
            sl=1015,
            tp=955,
            atr=15,
        )
        assert signal.should_exit is False
        assert signal.urgency == "MONITOR"
        assert "Trailing stop" in signal.reason
        assert signal.adjusted_sl == 985  # entry - 1*ATR

    def test_rsi_overbought_buy_advisory(self):
        """Test RSI overbought on BUY position — advisory only, no exit."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="BUY",
            entry_price=1000,
            current_price=1020,
            sl=985,
            tp=1045,
            atr=15,
            rsi=78,
        )
        assert signal.should_exit is False
        assert signal.urgency == "MONITOR"
        assert "RSI overbought" in signal.reason

    def test_rsi_oversold_sell_advisory(self):
        """Test RSI oversold on SELL position — advisory only, no exit."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="SELL",
            entry_price=1000,
            current_price=980,
            sl=1015,
            tp=955,
            atr=15,
            rsi=22,
        )
        assert signal.should_exit is False
        assert signal.urgency == "MONITOR"
        assert "RSI oversold" in signal.reason

    def test_normal_position_no_exit(self):
        """Test normal position within parameters — should return NONE urgency."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="BUY",
            entry_price=1000,
            current_price=1010,
            sl=985,
            tp=1045,
            atr=15,
            volume=120_000,
            avg_volume=100_000,
            nifty_change_pct=0.5,
            beta=1.0,
            rsi=55,
        )
        assert signal.should_exit is False
        assert signal.urgency == "NONE"
        assert "normal parameters" in signal.reason
        assert signal.adjusted_sl is None

    def test_check_all_positions(self):
        """Test batch processing of multiple positions."""
        monitor = ExitMonitor()
        
        positions = [
            {
                "symbol": "RELIANCE",
                "action": "BUY",
                "entry_price": 2500,
                "current_price": 2550,  # normal
                "sl": 2475,
                "tp": 2575,
                "beta": 1.0,
            },
            {
                "symbol": "TCS",
                "action": "BUY",
                "entry_price": 3500,
                "current_price": 3470,  # SL hit
                "sl": 3475,
                "tp": 3575,
                "beta": 0.9,
            },
        ]
        
        indicators = {
            "RELIANCE": {"atr": 25, "volume": 100000, "avg_volume_20": 90000, "rsi": 60},
            "TCS": {"atr": 30, "volume": 80000, "avg_volume_20": 85000, "rsi": 45},
        }
        
        results = monitor.check_all_positions(positions, indicators, nifty_change_pct=0.0)
        
        assert len(results) == 2
        
        # RELIANCE should be normal
        rel_signal = results[0]["exit_signal"]
        assert rel_signal.should_exit is False
        
        # TCS should trigger SL exit
        tcs_signal = results[1]["exit_signal"]
        assert tcs_signal.should_exit is True
        assert tcs_signal.urgency == "IMMEDIATE"
        assert "Stop-loss hit" in tcs_signal.reason

    def test_multiple_exit_conditions_priority(self):
        """Test that SL hit takes priority over other conditions."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="BUY",
            entry_price=1000,
            current_price=980,  # SL hit
            sl=985,
            tp=1045,
            atr=15,
            volume=20_000,  # also volume crisis
            avg_volume=100_000,
            rsi=80,  # also RSI overbought
        )
        # Should return SL hit first
        assert signal.should_exit is True
        assert signal.urgency == "IMMEDIATE"
        assert "Stop-loss hit" in signal.reason

    def test_zero_atr_no_trailing_stop(self):
        """Test that trailing stop doesn't activate when ATR is zero."""
        monitor = ExitMonitor()
        signal = monitor.should_exit(
            action="BUY",
            entry_price=1000,
            current_price=1100,  # price moved up significantly
            sl=985,
            tp=1150,
            atr=0,  # no ATR data
        )
        # Should not return trailing stop signal
        assert signal.adjusted_sl is None
