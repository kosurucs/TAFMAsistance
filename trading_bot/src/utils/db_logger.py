"""
db_logger.py — TimescaleDB logging for trades, market snapshots, and decisions.

Uses psycopg2 connection pool. Gracefully degrades if DB is unavailable.
All writes are non-blocking (fire-and-forget pattern with error logging).

Tables (defined in scripts/init_db.sql):
- trade_log: entry, exit, P&L, scenario, confidence, R:R
- market_snapshots: per-interval indicator snapshots (JSONB)
- historical_ohlcv: handled by fetch_historical.py separately
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from loguru import logger

try:
    import psycopg2
    from psycopg2 import pool

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available — DB logging disabled")

# Module-level connection pool (singleton)
_pool: Any = None


def _get_pool():
    """Get or create the psycopg2 connection pool."""
    global _pool
    if not PSYCOPG2_AVAILABLE:
        return None
    if _pool is not None:
        return _pool

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        logger.debug("DATABASE_URL not set — DB logging disabled")
        return None

    try:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=db_url,
        )
        logger.info("TimescaleDB connection pool initialized")
        return _pool
    except Exception as e:
        logger.warning(f"Could not connect to TimescaleDB: {e} — DB logging disabled")
        return None


class DBLogger:
    """
    Logs trades, market snapshots, and exit events to TimescaleDB.
    All methods degrade gracefully if DB is unavailable.
    """

    def _execute(self, sql: str, params: tuple) -> bool:
        """Execute a SQL write. Returns True on success, False on failure."""
        pool_ = _get_pool()
        if pool_ is None:
            return False
        conn = None
        try:
            conn = pool_.getconn()
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"DB write failed: {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return False
        finally:
            if conn and pool_:
                try:
                    pool_.putconn(conn)
                except Exception:
                    pass

    def log_trade_entry(
        self,
        *,
        order_id: str,
        symbol: str,
        action: str,
        entry_price: float,
        quantity: int,
        sl: float,
        tp: float,
        rr_ratio: float,
        scenario: str,
        confidence: float,
        paper_trade: bool = True,
    ) -> bool:
        sql = """
            INSERT INTO trades
                (order_id, symbol, action, entry_price, quantity, sl, tp, rr_ratio,
                 scenario, confidence, paper_trade, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            order_id,
            symbol,
            action,
            entry_price,
            quantity,
            sl,
            tp,
            rr_ratio,
            scenario,
            int(confidence),  # Convert float to int to match schema
            paper_trade,
            datetime.now(timezone.utc),
        )
        success = self._execute(sql, params)
        if success:
            logger.info(f"Logged trade entry: {action} {symbol} @ {entry_price}")
        return success

    def log_trade_exit(
        self,
        *,
        order_id: str,
        exit_price: float,
        exit_reason: str,
        pnl: float,
    ) -> bool:
        sql = """
            UPDATE trades
            SET exit_price = %s, pnl = %s, exit_reason = %s, closed_at = %s
            WHERE order_id = %s
        """
        params = (exit_price, pnl, exit_reason, datetime.now(timezone.utc), order_id)
        success = self._execute(sql, params)
        if success:
            logger.info(f"Logged trade exit: order {order_id} @ {exit_price} pnl={pnl:.2f}")
        return success

    def log_market_snapshot(
        self,
        *,
        symbol: str,
        timeframe: str,
        indicators: dict,
        scenarios: list[dict] | None = None,
    ) -> bool:
        sql = """
            INSERT INTO market_snapshots (symbol, timeframe, timestamp, indicators, scenarios)
            VALUES (%s, %s, %s, %s, %s)
        """
        params = (
            symbol,
            timeframe,
            datetime.now(timezone.utc),
            json.dumps(indicators),
            json.dumps(scenarios or []),
        )
        return self._execute(sql, params)

    def close(self):
        """Close the connection pool."""
        global _pool
        if _pool:
            try:
                _pool.closeall()
            except Exception:
                pass
            _pool = None


# Module-level singleton
_db_logger: DBLogger | None = None


def get_db_logger() -> DBLogger:
    """Get or create the module-level DBLogger singleton."""
    global _db_logger
    if _db_logger is None:
        _db_logger = DBLogger()
    return _db_logger
