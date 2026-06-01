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
from src.tools.segment_registry import SegmentRegistry

_registry = SegmentRegistry()

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

# In-memory job store (sufficient for single-server deployment)
_jobs: dict[str, dict] = {}


@router.post("/{symbol}")
async def start_backtest(
    symbol: str,
    background_tasks: BackgroundTasks,
    years: int = 20,
    strategies: str = "all",
    # multi-segment params
    exchange: str = "NSE",
    instrument: str = "SPOT",
    commission_segment: Optional[str] = None,
    lot_size: Optional[int] = None,
    walk_forward: bool = False,
    # strategy tuning
    rsi_oversold: int = 30,
    rsi_overbought: int = 70,
    ema_fast: int = 9,
    ema_slow: int = 21,
    atr_mult_sl: float = 1.5,
    atr_mult_tp: float = 3.0,
    volume_confirm: bool = True,
):
    """Start a background backtest job. Returns job_id immediately.

    exchange: NSE | BSE | NFO | MCX | CDS  (default NSE)
    instrument: SPOT | INTRADAY | FUTURES | OPTIONS  (default SPOT)
    commission_segment: override auto-detection from segment_registry
    lot_size: override auto-detection from segment_registry
    walk_forward: run anchored walk-forward validation on winning strategy
    """
    sym_upper = symbol.upper()
    exchange_upper = exchange.upper()
    instrument_upper = instrument.upper()

    # Auto-detect commission_segment and lot_size via SegmentRegistry
    resolved_segment = commission_segment
    resolved_lot = lot_size
    try:
        info = _registry.resolve(sym_upper, exchange_upper, instrument_upper)
        if resolved_segment is None:
            resolved_segment = _registry.get_commission_segment(sym_upper, exchange_upper, instrument_upper)
        if resolved_lot is None:
            resolved_lot = _registry.get_lot_size(sym_upper, exchange_upper) or 1
    except Exception as exc:
        logger.warning("SegmentRegistry lookup failed for {}/{}/{}: {} — using defaults",
                       sym_upper, exchange_upper, instrument_upper, exc)
        resolved_segment = resolved_segment or "EQUITY_DELIVERY"
        resolved_lot = resolved_lot or 1

    job_id = str(uuid.uuid4())
    custom_params = {
        "rsi_oversold": rsi_oversold,
        "rsi_overbought": rsi_overbought,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "atr_mult_sl": atr_mult_sl,
        "atr_mult_tp": atr_mult_tp,
        "volume_confirm": volume_confirm,
    }
    _jobs[job_id] = {
        "status": "RUNNING",
        "progress": 0,
        "symbol": sym_upper,
        "exchange": exchange_upper,
        "instrument": instrument_upper,
        "years": years,
        "strategies": strategies,
        "commission_segment": resolved_segment,
        "lot_size": resolved_lot,
        "walk_forward": walk_forward,
        "custom_params": custom_params,
        "result": None,
        "error": None,
    }
    background_tasks.add_task(
        _run_backtest_job,
        job_id, sym_upper, years, strategies, custom_params,
        exchange_upper, instrument_upper, resolved_segment, resolved_lot, walk_forward,
    )
    return {
        "job_id": job_id,
        "symbol": sym_upper,
        "exchange": exchange_upper,
        "instrument": instrument_upper,
        "commission_segment": resolved_segment,
        "lot_size": resolved_lot,
        "walk_forward": walk_forward,
        "status": "RUNNING",
    }


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


async def _run_backtest_job(
    job_id: str,
    symbol: str,
    years: int,
    strategies: str = "all",
    custom_params: dict | None = None,
    exchange: str = "NSE",
    instrument: str = "SPOT",
    commission_segment: str = "EQUITY_DELIVERY",
    lot_size: int = 1,
    walk_forward: bool = False,
):
    """Background task: runs the full backtest with commission and optional walk-forward."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from src.tools.historical_data import HistoricalDataManager
    from src.utils.backtester import Backtester

    try:
        _jobs[job_id]["progress"] = 10

        # Fetch historical data (multi-exchange)
        mgr = HistoricalDataManager()
        period = f"{years}y" if years <= 25 else "max"
        df = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: mgr.get_symbol_data(symbol, period, "1d",
                                        exchange=exchange, instrument=instrument),
        )
        if df is None or len(df) < 100:
            _jobs[job_id]["status"] = "ERROR"
            _jobs[job_id]["error"] = (
                f"Insufficient data for {symbol}/{exchange} "
                f"({len(df) if df is not None else 0} rows)"
            )
            return

        # Set DatetimeIndex for resampling
        if "timestamp" in df.columns:
            df = df.set_index(pd.to_datetime(df["timestamp"])).drop(
                columns=["timestamp"], errors="ignore"
            )

        _jobs[job_id]["progress"] = 30

        # Parse strategy filter
        if strategies and strategies.lower() != "all":
            strategy_filter = [s.strip().upper() for s in strategies.split(",") if s.strip()]
        else:
            strategy_filter = None

        # Run backtest with commission + walk-forward
        backtester = Backtester()
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: backtester.run_all_strategies(
                symbol, df,
                strategy_filter=strategy_filter,
                custom_params=custom_params,
                commission_segment=commission_segment,
                lot_size=lot_size,
                walk_forward=walk_forward,
            ),
        )

        _jobs[job_id]["progress"] = 90

        # Serialize walk-forward report
        def serialize_wf(wf):
            if wf is None:
                return None
            return {
                "n_windows": wf.n_windows,
                "avg_stability": round(wf.avg_stability, 4),
                "is_robust": wf.is_robust,
                "windows": [
                    {
                        "window_id": w.window_id,
                        "train_start": w.train_start,
                        "train_end": w.train_end,
                        "test_start": w.test_start,
                        "test_end": w.test_end,
                        "train_win_rate": round(w.train_win_rate, 4),
                        "test_win_rate": round(w.test_win_rate, 4),
                        "train_pnl": round(w.train_pnl, 4),
                        "test_pnl": round(w.test_pnl, 4),
                        "stability_score": round(w.stability_score, 4),
                    }
                    for w in wf.windows
                ],
            }

        # Serialize strategy report
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
                # commission-aware fields (Step 4)
                "gross_total_pnl": r.gross_total_pnl,
                "net_total_pnl": r.net_total_pnl,
                "total_commission_pct": r.total_commission_pct,
                "commission_segment": r.commission_segment,
                "walk_forward": serialize_wf(r.walk_forward),
                # analytics
                "why_it_works": r.why_it_works,
                "best_period": r.best_period,
                "worst_period": r.worst_period,
                "expectancy": r.expectancy,
                "profitable_months_count": len(r.profitable_months),
                "loss_months_count": len(r.loss_months),
            }

        serialized = {
            "symbol": result.symbol,
            "exchange": exchange,
            "instrument": instrument,
            "years_analysed": result.years_analysed,
            "commission_segment": result.commission_segment,
            "walk_forward_enabled": result.walk_forward_enabled,
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
        logger.info("Backtest job {} complete for {}/{} — segment={} wf={}",
                    job_id, symbol, exchange, commission_segment, walk_forward)

    except Exception as exc:
        logger.error("Backtest job {} failed: {}", job_id, exc)
        _jobs[job_id]["status"] = "ERROR"
        _jobs[job_id]["error"] = str(exc)
