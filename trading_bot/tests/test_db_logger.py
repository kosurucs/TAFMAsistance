"""
test_db_logger.py — Unit tests for TimescaleDB logging.

Tests graceful degradation when DB is unavailable.
"""
import os
from unittest.mock import patch

import pytest


@pytest.fixture
def clean_env(monkeypatch):
    """Remove DATABASE_URL from environment for testing graceful degradation."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Reset the module-level pool before each test
    import src.utils.db_logger as db_module
    db_module._pool = None
    db_module._db_logger = None
    yield
    # Cleanup after test
    db_module._pool = None
    db_module._db_logger = None


def test_dblogger_degrades_gracefully_without_database_url(clean_env):
    """Test that DBLogger methods return False when DATABASE_URL is not set."""
    from src.utils.db_logger import get_db_logger
    
    db = get_db_logger()
    
    # Test log_trade_entry returns False
    result = db.log_trade_entry(
        order_id="TEST123",
        symbol="RELIANCE",
        action="BUY",
        entry_price=1000.0,
        quantity=10,
        sl=985.0,
        tp=1045.0,
        rr_ratio=2.0,
        scenario="STRONG_UPTREND",
        confidence=75.0,
        paper_trade=True,
    )
    assert result is False
    
    # Test log_trade_exit returns False
    result = db.log_trade_exit(
        order_id="TEST123",
        exit_price=1040.0,
        exit_reason="Target hit",
        pnl=400.0,
    )
    assert result is False
    
    # Test log_market_snapshot returns False
    result = db.log_market_snapshot(
        symbol="RELIANCE",
        timeframe="1min",
        indicators={"rsi": 65.5, "close": 1010.0},
        scenarios=[{"name": "STRONG_UPTREND", "probability": 75.0}],
    )
    assert result is False


def test_dblogger_close_does_not_error_when_pool_is_none(clean_env):
    """Test that close() does not raise an exception when pool is None."""
    from src.utils.db_logger import get_db_logger
    
    db = get_db_logger()
    
    # Should not raise any exception
    db.close()


def test_dblogger_handles_psycopg2_import_error():
    """Test graceful degradation when psycopg2 is not available."""
    # Mock psycopg2 import to fail
    with patch.dict('sys.modules', {'psycopg2': None}):
        # Force reimport of db_logger module
        import importlib
        import src.utils.db_logger as db_module
        importlib.reload(db_module)
        
        # Reset module-level state
        db_module._pool = None
        db_module._db_logger = None
        
        db = db_module.get_db_logger()
        
        # All methods should return False
        assert db.log_trade_entry(
            order_id="TEST",
            symbol="TCS",
            action="BUY",
            entry_price=3000.0,
            quantity=5,
            sl=2950.0,
            tp=3150.0,
            rr_ratio=2.5,
            scenario="TEST",
            confidence=60.0,
            paper_trade=True,
        ) is False
        
        assert db.log_trade_exit(
            order_id="TEST",
            exit_price=3100.0,
            exit_reason="Manual exit",
            pnl=500.0,
        ) is False
        
        assert db.log_market_snapshot(
            symbol="TCS",
            timeframe="1h",
            indicators={},
        ) is False


def test_dblogger_handles_connection_failure(clean_env, monkeypatch):
    """Test graceful degradation when DB connection fails."""
    # Set DATABASE_URL but simulate connection failure
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid:invalid@localhost:9999/invalid")
    
    # Reset module state
    import src.utils.db_logger as db_module
    db_module._pool = None
    db_module._db_logger = None
    
    db = db_module.get_db_logger()
    
    # Methods should return False on connection failure
    result = db.log_trade_entry(
        order_id="TEST456",
        symbol="INFY",
        action="SELL",
        entry_price=1500.0,
        quantity=20,
        sl=1520.0,
        tp=1440.0,
        rr_ratio=2.0,
        scenario="TEST",
        confidence=70.0,
        paper_trade=True,
    )
    assert result is False


def test_dblogger_singleton_pattern(clean_env, monkeypatch):
    """Test that get_db_logger returns the same instance."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    
    from src.utils.db_logger import get_db_logger
    
    db1 = get_db_logger()
    db2 = get_db_logger()
    
    assert db1 is db2
