"""
portfolio.py – Read-only Kite Connect portfolio wrapper.

Provides:
  - ``Portfolio`` class with methods for margins, positions, holdings,
    orders, and order trades.

Typical usage::

    from src.tools.kite_client import build_kite_client
    from src.tools.portfolio import Portfolio

    kite = build_kite_client()
    pf = Portfolio(kite)

    margins = pf.get_margins()
    positions = pf.get_positions()
    holdings = pf.get_holdings()
    orders = pf.get_orders()
    trades = pf.get_order_trades("220101000000001")
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.utils.retry import retry


class Portfolio:
    """Read-only portfolio queries via Kite Connect.

    All network calls are wrapped with :func:`src.utils.retry.retry`.

    Args:
        kite: Authenticated ``KiteConnect`` instance.
    """

    def __init__(self, kite: Any) -> None:
        self._kite = kite

    # ------------------------------------------------------------------
    # Margins
    # ------------------------------------------------------------------

    def get_margins(self, segment: str | None = None) -> dict[str, Any]:
        """Return available margin and cash balances.

        Args:
            segment: Optional segment filter.  Pass ``"equity"`` or
                ``"commodity"`` to restrict the response; omit for both
                segments.

        Returns:
            Kite margins dict.
        """
        if segment:
            result: dict[str, Any] = retry(
                lambda s=segment: self._kite.margins(segment=s)
            )
        else:
            result = retry(self._kite.margins)
        logger.debug("Fetched margins (segment={}).", segment)
        return result

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self) -> dict[str, list[dict[str, Any]]]:
        """Return open positions (day + net).

        Returns:
            Dict with ``"day"`` and ``"net"`` lists of position dicts.
        """
        result: dict[str, list[dict[str, Any]]] = retry(self._kite.positions)
        logger.debug(
            "Fetched positions: {} day, {} net.",
            len(result.get("day", [])),
            len(result.get("net", [])),
        )
        return result

    # ------------------------------------------------------------------
    # Holdings
    # ------------------------------------------------------------------

    def get_holdings(self) -> list[dict[str, Any]]:
        """Return long-term equity holdings (CNC).

        Returns:
            List of holding dicts.
        """
        result: list[dict[str, Any]] = retry(self._kite.holdings)
        logger.debug("Fetched {} holdings.", len(result))
        return result

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_orders(self) -> list[dict[str, Any]]:
        """Return all orders placed during the current trading day.

        Returns:
            List of order dicts.
        """
        result: list[dict[str, Any]] = retry(self._kite.orders)
        logger.debug("Fetched {} orders.", len(result))
        return result

    # ------------------------------------------------------------------
    # Order trades
    # ------------------------------------------------------------------

    def get_order_trades(self, order_id: str) -> list[dict[str, Any]]:
        """Return the individual fills (trades) for a given order.

        Args:
            order_id: The Kite order-id string.

        Returns:
            List of trade dicts (may be empty if the order has not filled).
        """
        result: list[dict[str, Any]] = retry(
            lambda oid=order_id: self._kite.order_trades(oid)
        )
        logger.debug("Fetched {} trades for order {}.", len(result), order_id)
        return result

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_day_pnl(self) -> float:
        """Return total unrealised P&L across all open *day* positions.

        Returns:
            Sum of ``pnl`` values from the ``"day"`` positions list.
        """
        positions = self.get_positions()
        return sum(float(p.get("pnl", 0)) for p in positions.get("day", []))
