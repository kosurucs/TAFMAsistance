"""
test_risk_manager.py – Unit tests for the RiskManager class.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils.risk_manager import RiskManager


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def rm() -> RiskManager:
    """Return a RiskManager with known parameters and no Redis."""
    return RiskManager(
        opening_capital=100_000.0,
        max_daily_loss_pct=0.02,     # 2 % = 2,000 INR
        max_position_size_pct=0.05,  # 5 % = 5,000 INR per trade
        paper_trading=True,
        redis_client=None,
    )


# ── Kill switch ───────────────────────────────────────────────────────────────


class TestKillSwitch:
    def test_initially_inactive(self, rm: RiskManager, tmp_path: Path):
        # Override the flag path to avoid polluting /tmp
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            assert rm.is_kill_switch_active() is False

    def test_activate_sets_internal_flag(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            rm.activate_kill_switch()
            assert rm._killed is True

    def test_activate_creates_flag_file(self, rm: RiskManager, tmp_path: Path):
        flag = tmp_path / "ks"
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", flag):
            rm.activate_kill_switch()
            assert flag.exists()

    def test_deactivate_removes_flag_file(self, rm: RiskManager, tmp_path: Path):
        flag = tmp_path / "ks"
        flag.touch()
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", flag):
            rm.activate_kill_switch()
            rm.deactivate_kill_switch()
            assert not flag.exists()
            assert rm._killed is False

    def test_flag_file_triggers_kill(self, rm: RiskManager, tmp_path: Path):
        flag = tmp_path / "ks"
        flag.touch()
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", flag):
            assert rm.is_kill_switch_active() is True

    def test_redis_kill_switch(self, tmp_path: Path):
        redis_mock = MagicMock()
        redis_mock.get.return_value = "1"
        rm_redis = RiskManager(
            opening_capital=100_000.0,
            redis_client=redis_mock,
        )
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            assert rm_redis.is_kill_switch_active() is True


# ── Daily loss check ──────────────────────────────────────────────────────────


class TestDailyLossCheck:
    def test_within_limit_passes(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            assert rm.check_daily_loss(-500.0) is True    # 0.5 % < 2 %

    def test_at_limit_fails(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            # Exactly at 2 % limit (≤ -2000)
            assert rm.check_daily_loss(-2000.0) is False

    def test_beyond_limit_fails(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            assert rm.check_daily_loss(-3000.0) is False

    def test_profit_always_passes(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            assert rm.check_daily_loss(500.0) is True

    def test_breach_activates_kill_switch(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            rm.check_daily_loss(-5000.0)
            assert rm._killed is True


# ── Position sizing ───────────────────────────────────────────────────────────


class TestPositionSizing:
    def test_standard_calculation(self, rm: RiskManager):
        # max_notional = 100_000 * 0.05 = 5_000
        # qty = floor(5_000 / 250) = 20
        assert rm.calculate_quantity(price=250.0) == 20

    def test_expensive_stock_returns_small_qty(self, rm: RiskManager):
        # 5_000 / 3500 = 1
        assert rm.calculate_quantity(price=3500.0) == 1

    def test_very_expensive_stock_returns_zero(self, rm: RiskManager):
        # 5_000 / 6000 = 0
        assert rm.calculate_quantity(price=6000.0) == 0

    def test_zero_price_returns_zero(self, rm: RiskManager):
        assert rm.calculate_quantity(price=0.0) == 0

    def test_negative_price_returns_zero(self, rm: RiskManager):
        assert rm.calculate_quantity(price=-100.0) == 0


# ── validate_order integration ────────────────────────────────────────────────


class TestValidateOrder:
    def test_happy_path(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            result = rm.validate_order(price=500.0, quantity=5, current_pnl=-100.0)
        assert result["approved"] is True
        assert result["safe_quantity"] >= 1

    def test_kill_switch_blocks_order(self, rm: RiskManager, tmp_path: Path):
        flag = tmp_path / "ks"
        flag.touch()
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", flag):
            result = rm.validate_order(price=500.0, quantity=5, current_pnl=0.0)
        assert result["approved"] is False
        assert result["safe_quantity"] == 0

    def test_loss_limit_blocks_order(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            result = rm.validate_order(price=500.0, quantity=5, current_pnl=-9999.0)
        assert result["approved"] is False

    def test_quantity_capped_by_position_limit(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            # Safe qty for price=500 = floor(5000/500)=10; we request 100
            result = rm.validate_order(price=500.0, quantity=100, current_pnl=0.0)
        assert result["approved"] is True
        assert result["safe_quantity"] == 10

    def test_zero_safe_qty_blocks_order(self, rm: RiskManager, tmp_path: Path):
        with patch("src.utils.risk_manager.KILL_SWITCH_FLAG", tmp_path / "ks"):
            # price > max_notional → qty = 0
            result = rm.validate_order(price=10_000.0, quantity=1, current_pnl=0.0)
        assert result["approved"] is False
        assert result["safe_quantity"] == 0
