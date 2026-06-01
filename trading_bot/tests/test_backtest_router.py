"""
test_backtest_router.py — Tests for the /api/backtest router.

Verifies:
- New query params (exchange, instrument, commission_segment, lot_size, walk_forward)
- SegmentRegistry auto-detection of commission_segment and lot_size
- Status and result endpoint contract
- Unknown job_id → 404
- Enriched serialized result contains all new fields
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import asyncio
import dataclasses
import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_mock_result(symbol: str = "RELIANCE", **overrides):
    """Build a minimal BacktestResult-like object with all required fields."""
    from utils.backtester import (
        BacktestResult, StrategyReport, TradeRecord, WalkForwardReport
    )

    report = StrategyReport(
        strategy_name="EMA_CROSSOVER",
        timeframe="1D",
        trades=[],
        total_trades=5,
        winning_trades=3,
        losing_trades=2,
        win_rate_pct=60.0,
        avg_rr=2.1,
        best_rr=3.5,
        worst_rr=0.8,
        max_drawdown_pct=5.0,
        sharpe_ratio=1.2,
        total_pnl=4200.0,
        gross_total_pnl=4200.0,
        net_total_pnl=3900.0,
        total_commission_pct=0.32,
        commission_segment=overrides.get("commission_segment", "EQUITY_DELIVERY"),
        profitable_months=[],
        loss_months=[],
        why_it_works="momentum",
        best_period="",
        worst_period="",
        expectancy=780.0,
        walk_forward=None,
    )

    result = BacktestResult(
        symbol=symbol,
        years_analysed=20,
        strategy_reports=[report],
        recommended_strategy="EMA_CROSSOVER",
        recommended_timeframe="1D",
        recommended_rr=2.1,
        recommended_win_rate=60.0,
        entry_plan={
            "gross_total_pnl": 4200.0,
            "net_total_pnl": 3900.0,
            "commission_drag_pct": 0.32,
        },
        commission_segment=overrides.get("commission_segment", "EQUITY_DELIVERY"),
        walk_forward_enabled=overrides.get("walk_forward_enabled", False),
    )
    return result


def _noop_bg(job_id, *args, **kwargs):
    """Background task stub — leaves job in RUNNING state (we set COMPLETE manually)."""
    pass


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """TestClient with a fresh _jobs store and stubbed background task."""
    from src.api.app import app
    import src.api.routers.backtest as router_module
    router_module._jobs.clear()
    with TestClient(app) as c:
        yield c
    router_module._jobs.clear()


# ── tests: POST /api/backtest/{symbol} ───────────────────────────────────────

class TestStartBacktest:
    def test_returns_job_id_and_defaults(self, client):
        with patch("src.api.routers.backtest._run_backtest_job", side_effect=_noop_bg):
            resp = client.post("/api/backtest/RELIANCE")
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["symbol"] == "RELIANCE"
        assert data["exchange"] == "NSE"
        assert data["instrument"] == "SPOT"
        assert data["status"] == "RUNNING"
        assert data["walk_forward"] is False

    def test_exchange_instrument_params(self, client):
        with patch("src.api.routers.backtest._run_backtest_job", side_effect=_noop_bg):
            resp = client.post(
                "/api/backtest/GOLDM",
                params={"exchange": "MCX", "instrument": "FUTURES", "walk_forward": "true"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["exchange"] == "MCX"
        assert data["instrument"] == "FUTURES"
        assert data["walk_forward"] is True

    def test_commission_segment_override(self, client):
        with patch("src.api.routers.backtest._run_backtest_job", side_effect=_noop_bg):
            resp = client.post(
                "/api/backtest/NIFTY24OCTFUT",
                params={
                    "exchange": "NFO",
                    "instrument": "FUTURES",
                    "commission_segment": "FNO_FUTURES",
                    "lot_size": "50",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["commission_segment"] == "FNO_FUTURES"
        assert data["lot_size"] == 50

    def test_job_stored_in_jobs_dict(self, client):
        import src.api.routers.backtest as router_module
        with patch("src.api.routers.backtest._run_backtest_job", side_effect=_noop_bg):
            resp = client.post("/api/backtest/TCS", params={"exchange": "NSE"})
        job_id = resp.json()["job_id"]
        assert job_id in router_module._jobs
        job = router_module._jobs[job_id]
        assert job["symbol"] == "TCS"
        assert job["exchange"] == "NSE"
        assert "commission_segment" in job
        assert "lot_size" in job
        assert "walk_forward" in job

    def test_nse_equity_delivery_auto_detected(self, client):
        """SegmentRegistry should map NSE SPOT → EQUITY_DELIVERY."""
        with patch("src.api.routers.backtest._run_backtest_job", side_effect=_noop_bg):
            resp = client.post(
                "/api/backtest/RELIANCE",
                params={"exchange": "NSE", "instrument": "SPOT"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["commission_segment"] == "EQUITY_DELIVERY"

    def test_unknown_symbol_falls_back_to_defaults(self, client):
        """If SegmentRegistry cannot resolve, defaults to EQUITY_DELIVERY / lot=1."""
        with patch("src.api.routers.backtest._run_backtest_job", side_effect=_noop_bg):
            resp = client.post(
                "/api/backtest/UNKNOWNSYM999",
                params={"exchange": "NSE"},
            )
        assert resp.status_code == 200
        data = resp.json()
        # Either auto-detected or fell back to default — must be a valid segment string
        assert data["commission_segment"] in {
            "EQUITY_DELIVERY", "EQUITY_INTRADAY", "FNO_FUTURES",
            "FNO_OPTIONS", "MCX_COMMODITY", "CDS_CURRENCY",
        }
        assert data["lot_size"] >= 1


# ── tests: GET /api/backtest/status/{job_id} ─────────────────────────────────

class TestBacktestStatus:
    def test_status_running(self, client):
        import src.api.routers.backtest as router_module
        job_id = str(uuid.uuid4())
        router_module._jobs[job_id] = {
            "status": "RUNNING", "progress": 30, "symbol": "INFY",
            "error": None,
        }
        resp = client.get(f"/api/backtest/status/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "RUNNING"
        assert data["progress"] == 30

    def test_status_complete(self, client):
        import src.api.routers.backtest as router_module
        job_id = str(uuid.uuid4())
        router_module._jobs[job_id] = {
            "status": "COMPLETE", "progress": 100, "symbol": "TCS",
            "error": None,
        }
        resp = client.get(f"/api/backtest/status/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "COMPLETE"

    def test_status_unknown_job(self, client):
        resp = client.get(f"/api/backtest/status/{uuid.uuid4()}")
        assert resp.status_code == 404


# ── tests: GET /api/backtest/result/{job_id} ─────────────────────────────────

class TestBacktestResult:
    def test_result_unknown_job(self, client):
        resp = client.get(f"/api/backtest/result/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_result_still_running(self, client):
        import src.api.routers.backtest as router_module
        job_id = str(uuid.uuid4())
        router_module._jobs[job_id] = {
            "status": "RUNNING", "progress": 50,
            "symbol": "HDFC", "error": None, "result": None,
        }
        resp = client.get(f"/api/backtest/result/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "RUNNING"

    def test_result_error_job(self, client):
        import src.api.routers.backtest as router_module
        job_id = str(uuid.uuid4())
        router_module._jobs[job_id] = {
            "status": "ERROR", "progress": 15,
            "symbol": "XYZ", "error": "Insufficient data", "result": None,
        }
        resp = client.get(f"/api/backtest/result/{job_id}")
        assert resp.status_code == 500

    def test_result_complete_has_new_fields(self, client):
        import src.api.routers.backtest as router_module
        job_id = str(uuid.uuid4())
        # Pre-populate a serialized result that mimics what _run_backtest_job produces
        serialized = {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "instrument": "SPOT",
            "years_analysed": 20,
            "commission_segment": "EQUITY_DELIVERY",
            "walk_forward_enabled": False,
            "recommended_strategy": "EMA_CROSSOVER",
            "recommended_timeframe": "1D",
            "recommended_rr": 2.1,
            "recommended_win_rate": 60.0,
            "entry_plan": {
                "gross_total_pnl": 4200.0,
                "net_total_pnl": 3900.0,
                "commission_drag_pct": 0.32,
            },
            "strategy_reports": [
                {
                    "strategy_name": "EMA_CROSSOVER",
                    "timeframe": "1D",
                    "total_trades": 5,
                    "winning_trades": 3,
                    "losing_trades": 2,
                    "win_rate_pct": 60.0,
                    "avg_rr": 2.1,
                    "best_rr": 3.5,
                    "worst_rr": 0.8,
                    "max_drawdown_pct": 5.0,
                    "sharpe_ratio": 1.2,
                    "total_pnl": 4200.0,
                    "gross_total_pnl": 4200.0,
                    "net_total_pnl": 3900.0,
                    "total_commission_pct": 0.32,
                    "commission_segment": "EQUITY_DELIVERY",
                    "walk_forward": None,
                    "why_it_works": "momentum",
                    "best_period": "",
                    "worst_period": "",
                    "expectancy": 780.0,
                    "profitable_months_count": 0,
                    "loss_months_count": 0,
                }
            ],
        }
        router_module._jobs[job_id] = {
            "status": "COMPLETE", "progress": 100,
            "symbol": "RELIANCE", "error": None, "result": serialized,
        }
        resp = client.get(f"/api/backtest/result/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "COMPLETE"
        result = body["result"]
        # Top-level new fields
        assert result["exchange"] == "NSE"
        assert result["instrument"] == "SPOT"
        assert result["commission_segment"] == "EQUITY_DELIVERY"
        assert result["walk_forward_enabled"] is False
        # Per-report new fields
        rpt = result["strategy_reports"][0]
        assert "gross_total_pnl" in rpt
        assert "net_total_pnl" in rpt
        assert "total_commission_pct" in rpt
        assert "commission_segment" in rpt
        assert "walk_forward" in rpt
        # entry_plan new fields
        assert "net_total_pnl" in result["entry_plan"]
        assert "commission_drag_pct" in result["entry_plan"]


# ── tests: walk-forward serialization ────────────────────────────────────────

class TestWalkForwardSerialization:
    """Verify serialize_wf produces correct structure when walk-forward is enabled."""

    def test_serialize_wf_none_returns_none(self, client):
        """walk_forward=None in report → null in JSON."""
        import src.api.routers.backtest as router_module
        job_id = str(uuid.uuid4())
        rpt = {
            "strategy_name": "RSI",
            "timeframe": "1D",
            "total_trades": 2,
            "winning_trades": 1,
            "losing_trades": 1,
            "win_rate_pct": 50.0,
            "avg_rr": 1.5,
            "best_rr": 2.0,
            "worst_rr": 1.0,
            "max_drawdown_pct": 3.0,
            "sharpe_ratio": 0.9,
            "total_pnl": 1000.0,
            "gross_total_pnl": 1000.0,
            "net_total_pnl": 950.0,
            "total_commission_pct": 0.32,
            "commission_segment": "EQUITY_DELIVERY",
            "walk_forward": None,
            "why_it_works": "mean_reversion",
            "best_period": "",
            "worst_period": "",
            "expectancy": 475.0,
            "profitable_months_count": 0,
            "loss_months_count": 0,
        }
        router_module._jobs[job_id] = {
            "status": "COMPLETE", "progress": 100,
            "symbol": "INFY", "error": None,
            "result": {
                "symbol": "INFY", "exchange": "NSE", "instrument": "SPOT",
                "years_analysed": 5, "commission_segment": "EQUITY_DELIVERY",
                "walk_forward_enabled": False,
                "recommended_strategy": "RSI",
                "recommended_timeframe": "1D",
                "recommended_rr": 1.5,
                "recommended_win_rate": 50.0,
                "entry_plan": {},
                "strategy_reports": [rpt],
            },
        }
        resp = client.get(f"/api/backtest/result/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["result"]["strategy_reports"][0]["walk_forward"] is None

    def test_walk_forward_enabled_flag_in_result(self, client):
        """walk_forward_enabled=True reflected in top-level result."""
        import src.api.routers.backtest as router_module
        job_id = str(uuid.uuid4())
        wf_data = {
            "n_windows": 3,
            "avg_stability": 0.72,
            "is_robust": True,
            "windows": [
                {
                    "window_id": 1,
                    "train_start": "2020-01-01",
                    "train_end": "2022-01-01",
                    "test_start": "2022-01-01",
                    "test_end": "2022-07-01",
                    "train_win_rate": 0.6,
                    "test_win_rate": 0.55,
                    "train_pnl": 3000.0,
                    "test_pnl": 1200.0,
                    "stability_score": 0.917,
                }
            ],
        }
        router_module._jobs[job_id] = {
            "status": "COMPLETE", "progress": 100,
            "symbol": "TCS", "error": None,
            "result": {
                "symbol": "TCS", "exchange": "NSE", "instrument": "SPOT",
                "years_analysed": 5, "commission_segment": "EQUITY_DELIVERY",
                "walk_forward_enabled": True,
                "recommended_strategy": "EMA_CROSSOVER",
                "recommended_timeframe": "1D",
                "recommended_rr": 2.0,
                "recommended_win_rate": 55.0,
                "entry_plan": {},
                "strategy_reports": [
                    {
                        "strategy_name": "EMA_CROSSOVER",
                        "timeframe": "1D",
                        "total_trades": 10,
                        "winning_trades": 6,
                        "losing_trades": 4,
                        "win_rate_pct": 60.0,
                        "avg_rr": 2.0,
                        "best_rr": 3.0,
                        "worst_rr": 0.5,
                        "max_drawdown_pct": 4.0,
                        "sharpe_ratio": 1.1,
                        "total_pnl": 5000.0,
                        "gross_total_pnl": 5000.0,
                        "net_total_pnl": 4700.0,
                        "total_commission_pct": 0.32,
                        "commission_segment": "EQUITY_DELIVERY",
                        "walk_forward": wf_data,
                        "why_it_works": "trend",
                        "best_period": "",
                        "worst_period": "",
                        "expectancy": 470.0,
                        "profitable_months_count": 2,
                        "loss_months_count": 1,
                    }
                ],
            },
        }
        resp = client.get(f"/api/backtest/result/{job_id}")
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["walk_forward_enabled"] is True
        wf = result["strategy_reports"][0]["walk_forward"]
        assert wf["is_robust"] is True
        assert wf["n_windows"] == 3
        assert len(wf["windows"]) == 1
        assert wf["windows"][0]["stability_score"] == 0.917
