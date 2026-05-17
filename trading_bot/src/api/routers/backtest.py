"""
backtest.py — Async backtest API endpoints.

POST /api/backtest/{symbol}    → starts background job, returns job_id
GET  /api/backtest/status/{job_id}  → polls progress (0-100%)
GET  /api/backtest/result/{job_id}  → full BacktestResult JSON
"""
from __future__ import annotations
import asyncio
import uuid
from typing import Optional
import pandas as pd
from fastapi import APIRouter, HTTPException, BackgroundTasks
from loguru import logger

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

# In-memory job store (sufficient for single-server deployment)
_jobs: dict[str, dict] = {}


@router.post("/{symbol}")
async def start_backtest(
    symbol: str,
    background_tasks: BackgroundTasks,
    years: int = 20,
    strategies: str = "all",
):
    """Start a background backtest job. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "RUNNING",
        "progress": 0,
        "symbol": symbol.upper(),
        "years": years,
        "result": None,
        "error": None,
    }
    background_tasks.add_task(_run_backtest_job, job_id, symbol.upper(), years)
    return {"job_id": job_id, "symbol": symbol.upper(), "status": "RUNNING"}


@router.get("/status/{job_id}")
async def get_backtest_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "symbol": job["symbol"],
        "error": job.get("error"),
    }


@router.get("/result/{job_id}")
async def get_backtest_result(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job["status"] == "RUNNING":
        return {"status": "RUNNING", "progress": job["progress"]}
    if job["status"] == "ERROR":
        raise HTTPException(status_code=500, detail=job.get("error", "Unknown error"))
    return {"status": "COMPLETE", "result": job["result"]}


async def _run_backtest_job(job_id: str, symbol: str, years: int):
    """Background task: runs the full backtest."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from src.tools.historical_data import HistoricalDataManager
    from src.utils.backtester import Backtester
    
    try:
        _jobs[job_id]["progress"] = 10
        
        # Fetch historical data
        mgr = HistoricalDataManager()
        period = f"{years}y" if years <= 25 else "max"
        df = await asyncio.get_event_loop().run_in_executor(
            None, mgr.get_symbol_data, symbol, period, "1d"
        )
        if df is None or len(df) < 100:
            _jobs[job_id]["status"] = "ERROR"
            _jobs[job_id]["error"] = f"Insufficient data for {symbol} ({len(df) if df is not None else 0} rows)"
            return
        
        # Set DatetimeIndex for resampling
        if "timestamp" in df.columns:
            df = df.set_index(pd.to_datetime(df["timestamp"])).drop(columns=["timestamp"], errors="ignore")
        
        _jobs[job_id]["progress"] = 30
        
        # Run backtest
        backtester = Backtester()
        result = await asyncio.get_event_loop().run_in_executor(
            None, backtester.run_all_strategies, symbol, df
        )
        
        _jobs[job_id]["progress"] = 90
        
        # Serialize result (convert dataclasses to dicts)
        def serialize_report(r):
            return {
                "strategy_name": r.strategy_name,
                "timeframe": r.timeframe,
                "total_trades": r.total_trades,
                "winning_trades": r.winning_trades,
                "losing_trades": r.losing_trades,
                "win_rate_pct": r.win_rate_pct,
                "avg_rr": r.avg_rr,
                "best_rr": r.best_rr,
                "worst_rr": r.worst_rr,
                "max_drawdown_pct": r.max_drawdown_pct,
                "sharpe_ratio": r.sharpe_ratio,
                "total_pnl": r.total_pnl,
                "why_it_works": r.why_it_works,
                "best_period": r.best_period,
                "worst_period": r.worst_period,
                "expectancy": r.expectancy,
                "profitable_months_count": len(r.profitable_months),
                "loss_months_count": len(r.loss_months),
            }
        
        serialized = {
            "symbol": result.symbol,
            "years_analysed": result.years_analysed,
            "recommended_strategy": result.recommended_strategy,
            "recommended_timeframe": result.recommended_timeframe,
            "recommended_rr": result.recommended_rr,
            "recommended_win_rate": result.recommended_win_rate,
            "entry_plan": result.entry_plan,
            "strategy_reports": [serialize_report(r) for r in result.strategy_reports],
        }
        
        _jobs[job_id]["result"] = serialized
        _jobs[job_id]["status"] = "COMPLETE"
        _jobs[job_id]["progress"] = 100
        logger.info(f"Backtest job {job_id} complete for {symbol}")
    
    except Exception as e:
        logger.error(f"Backtest job {job_id} failed: {e}")
        _jobs[job_id]["status"] = "ERROR"
        _jobs[job_id]["error"] = str(e)
