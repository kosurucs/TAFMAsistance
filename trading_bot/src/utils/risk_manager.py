"""
risk_manager.py – Deterministic risk guardrails.

Implements:
  - Max daily-loss kill switch.
  - Position sizing (fraction of portfolio value).
  - Paper-trading toggle.
  - Manual kill switch (via a Redis flag or a local flag file).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from loguru import logger

# ── Constants (can be overridden by env vars) ─────────────────────────────────

MAX_DAILY_LOSS_PCT: float = float(os.environ.get("MAX_DAILY_LOSS_PCT", "0.02"))
MAX_POSITION_SIZE_PCT: float = float(os.environ.get("MAX_POSITION_SIZE_PCT", "0.05"))
PAPER_TRADING: bool = os.environ.get("PAPER_TRADING", "true").lower() == "true"

# A local flag file acts as a manual kill switch when Redis is not available.
KILL_SWITCH_FLAG: Path = Path(os.environ.get("KILL_SWITCH_FLAG", "/tmp/trading_kill_switch"))


# ── Public API ────────────────────────────────────────────────────────────────


class RiskManager:
    """Validates trade intentions against hard-coded risk rules.

    All public methods return ``True`` when the check *passes* (i.e., trading
    is safe) and ``False`` when it *fails* (i.e., trading should stop).
    """

    def __init__(
        self,
        opening_capital: float,
        max_daily_loss_pct: float = MAX_DAILY_LOSS_PCT,
        max_position_size_pct: float = MAX_POSITION_SIZE_PCT,
        paper_trading: bool = PAPER_TRADING,
        redis_client: Any | None = None,
    ) -> None:
        """
        Args:
            opening_capital: Portfolio value at market open (INR).
            max_daily_loss_pct: Maximum intraday loss as a fraction of
                ``opening_capital`` (e.g. 0.02 = 2 %).
            max_position_size_pct: Maximum single-trade notional as a fraction
                of ``opening_capital`` (e.g. 0.05 = 5 %).
            paper_trading: If True, no real orders are placed.
            redis_client: Optional ``redis.Redis`` instance for distributed
                kill-switch signalling.
        """
        self.opening_capital = opening_capital
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_position_size_pct = max_position_size_pct
        self.paper_trading = paper_trading
        self._redis = redis_client
        self._killed: bool = False

    # ------------------------------------------------------------------
    # Kill-switch
    # ------------------------------------------------------------------

    def is_kill_switch_active(self) -> bool:
        """Return True if the manual kill switch has been triggered.

        Checks (in priority order):
        1. In-process ``_killed`` flag (set programmatically).
        2. Redis key ``trading:kill_switch`` (set via CLI / mobile app).
        3. Local flag file at ``KILL_SWITCH_FLAG``.
        """
        if self._killed:
            return True

        if self._redis is not None:
            try:
                if self._redis.get("trading:kill_switch"):
                    logger.critical("Kill switch activated via Redis!")
                    self._killed = True
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis kill-switch check failed: {}", exc)

        if KILL_SWITCH_FLAG.exists():
            logger.critical("Kill switch flag file detected: {}", KILL_SWITCH_FLAG)
            self._killed = True
            return True

        return False

    def activate_kill_switch(self) -> None:
        """Activate the kill switch programmatically (e.g., from a CLI)."""
        self._killed = True
        KILL_SWITCH_FLAG.touch(exist_ok=True)
        if self._redis is not None:
            try:
                self._redis.set("trading:kill_switch", "1")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not set Redis kill-switch: {}", exc)
        logger.critical("Kill switch ACTIVATED.")

    def deactivate_kill_switch(self) -> None:
        """Deactivate the kill switch (use with caution)."""
        self._killed = False
        KILL_SWITCH_FLAG.unlink(missing_ok=True)
        if self._redis is not None:
            try:
                self._redis.delete("trading:kill_switch")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not clear Redis kill-switch: {}", exc)
        logger.info("Kill switch deactivated.")

    # ------------------------------------------------------------------
    # P&L guardrail
    # ------------------------------------------------------------------

    def check_daily_loss(self, current_pnl: float) -> bool:
        """Return False (and log a critical alert) if the loss limit is hit.

        Args:
            current_pnl: Realised + unrealised P&L for the day (negative = loss).
        """
        loss_limit = -abs(self.opening_capital * self.max_daily_loss_pct)
        if current_pnl <= loss_limit:
            logger.critical(
                "Daily loss limit breached! P&L={:.2f}, limit={:.2f}. "
                "Activating kill switch.",
                current_pnl,
                loss_limit,
            )
            self.activate_kill_switch()
            return False
        return True

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def calculate_quantity(self, price: float) -> int:
        """Return the maximum safe number of shares to trade.

        Args:
            price: Current market price per share (INR).

        Returns:
            Integer quantity (≥ 1 if within risk limits, 0 if price exceeds
            the risk-adjusted budget entirely).
        """
        if price <= 0:
            return 0
        max_notional = self.opening_capital * self.max_position_size_pct
        qty = int(max_notional // price)
        logger.debug(
            "Position sizing: max_notional={:.2f}, price={:.2f}, qty={}",
            max_notional,
            price,
            qty,
        )
        return max(0, qty)

    def validate_order(
        self,
        price: float,
        quantity: int,
        current_pnl: float,
    ) -> dict[str, Any]:
        """Run all guardrails in sequence and return a validation result.

        Args:
            price: Proposed trade price.
            quantity: Proposed trade quantity.
            current_pnl: Current day P&L.

        Returns:
            Dict with keys:
              - ``"approved"``: bool – whether the order may proceed.
              - ``"reason"``: str – human-readable explanation.
              - ``"safe_quantity"``: int – adjusted quantity (may be 0).
        """
        if self.is_kill_switch_active():
            return {
                "approved": False,
                "reason": "Kill switch is active.",
                "safe_quantity": 0,
            }

        if not self.check_daily_loss(current_pnl):
            return {
                "approved": False,
                "reason": "Daily loss limit exceeded.",
                "safe_quantity": 0,
            }

        safe_qty = self.calculate_quantity(price)
        actual_qty = min(quantity, safe_qty)

        if actual_qty == 0:
            return {
                "approved": False,
                "reason": (
                    f"Computed safe quantity is 0 for price={price:.2f} "
                    f"(max notional {self.opening_capital * self.max_position_size_pct:.2f})."
                ),
                "safe_quantity": 0,
            }

        if actual_qty < quantity:
            logger.warning(
                "Requested qty {} reduced to {} by position-size guardrail.",
                quantity,
                actual_qty,
            )

        return {
            "approved": True,
            "reason": "All risk checks passed.",
            "safe_quantity": actual_qty,
        }
