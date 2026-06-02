"""
research.py – Comprehensive instrument analysis router.

POST /research/analyze
    Full pipeline: Kite live data → technical indicators → Yahoo Finance
    fundamentals + shareholding + financials → screener.in (best-effort) →
    local GPT-2 decision → knowledge cache update → training data append.

GET  /research/knowledge
    List all symbols with cached knowledge.

GET  /research/knowledge/{symbol}
    Return the full cached record for one symbol.

GET  /research/training-stats
    How many training examples have been accumulated.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_data_fetcher
from src.api.routers.market import _make_stub_df
from src.tools.comprehensive_data import ComprehensiveDataFetcher
from src.tools.data_pipeline import DataPipeline
from src.tools.kite_tools import KiteDataFetcher
from src.utils.instrument_knowledge import (
    get_cached,
    list_cached_symbols,
    save_analysis,
    training_example_count,
)
from src.utils.local_llm import build_compact_context, is_model_cached, query_local_llm
from src.utils.rr_calculator import calculate_sl_tp
from src.utils.technical_analysis import compute_indicators

router = APIRouter(prefix="/research")

_comprehensive = ComprehensiveDataFetcher()


# ── Request model ─────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    deep: bool = True       # False → skip screener.in (faster)
    use_cache: bool = True  # True  → reuse fundamentals cached < 24 h


# ── Main analysis endpoint ────────────────────────────────────────────────────

@router.post("/analyze", summary="Full multi-source analysis with local LLM decision")
def research_analyze(
    body: ResearchRequest,
    fetcher: KiteDataFetcher | None = Depends(get_data_fetcher),
) -> dict[str, Any]:
    """
    Seven-step pipeline:

    1. Load knowledge cache (if use_cache=True and cache < 24 h old, skip
       fundamental re-fetch from external sources).
    2. Fetch live OHLCV from Kite for the requested exchange (NSE or BSE).
    3. Compute technical indicators (RSI, EMA, MACD, Bollinger Bands, ATR …).
    4. Compute R:R with ATR-based SL/TP (SL = 1.5×ATR, TP = 3×ATR).
    5. Fetch fundamentals + shareholding + quarterly financials from Yahoo
       Finance for both NSE (".NS") and BSE (".BO"), plus screener.in scrape
       (best-effort).
    6. Run local GPT-2 inference on a compact context string.
    7. Persist the analysis to the knowledge cache and append an Alpaca-format
       training example to llm_training/data/dataset/train.jsonl.
    """
    symbol = body.symbol.upper().strip()

    # ── Step 1: check knowledge cache ────────────────────────────────────────
    cached = get_cached(symbol, max_age_hours=24.0) if body.use_cache else None
    from_cache = bool(cached)

    # ── Step 2: live OHLCV via Kite ──────────────────────────────────────────
    if fetcher is not None:
        try:
            pipeline = DataPipeline(fetcher)
            token = fetcher.lookup_instrument_token(body.exchange, symbol)
            df = pipeline.get_ohlcv_df(
                instrument_token=token,
                tradingsymbol=symbol,
                interval="minute",
                days_back=1,
            )
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail=f"Instrument '{symbol}' not found on '{body.exchange}'. "
                       "Check the symbol spelling or try exchange='BSE'.",
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Kite data error: {exc}")
    else:
        df = _make_stub_df(symbol)

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No market data for '{symbol}'.")

    # ── Step 3: technical indicators ─────────────────────────────────────────
    try:
        indicators = compute_indicators(df)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Indicator error: {exc}")

    # ── Step 4: R:R calculation (non-negotiable: SL=1.5×ATR, TP=3×ATR) ──────
    rr_result = None
    try:
        rr_result = calculate_sl_tp("BUY", indicators["close"], indicators["atr"])
    except Exception:  # noqa: BLE001
        pass

    # ── Step 5: multi-source fundamentals ────────────────────────────────────
    if from_cache:
        fundamentals_data: dict[str, Any] = cached.get("fundamentals_data", {})  # type: ignore[union-attr]
        sources_used: list[str] = cached.get("sources_used", ["knowledge-cache"])
    else:
        raw = _comprehensive.fetch_all(
            symbol,
            body.exchange,
            include_screener=body.deep,
        )
        sources_used = raw.pop("sources_used", [])
        fundamentals_data = raw

    # Always mark live Kite data in sources
    kite_source = f"kite-{body.exchange.lower()}"
    if kite_source not in sources_used:
        sources_used = [kite_source, *sources_used]

    # ── Step 6: build compact context + run local LLM ────────────────────────
    compact_ctx = build_compact_context(symbol, indicators, rr_result)

    # Enrich context with key fundamentals
    fund = fundamentals_data.get("fundamentals", {})
    extras: list[str] = []
    if fund.get("pe_ratio") is not None:
        extras.append(f"PE={fund['pe_ratio']:.1f}")
    if fund.get("market_cap") is not None:
        mc_cr = fund["market_cap"] / 1e7  # convert to crores
        extras.append(f"mcap={mc_cr:.0f}Cr")
    if fund.get("sector"):
        extras.append(f"sector={fund['sector']}")
    if fund.get("roe") is not None:
        extras.append(f"ROE={fund['roe'] * 100:.1f}%")
    if extras:
        compact_ctx += "," + ",".join(extras)

    llm_result = query_local_llm(compact_ctx)

    # Overlay ATR-based SL/TP when model returned a non-WAIT action
    if rr_result is not None and llm_result.get("action") != "WAIT":
        llm_result.setdefault("suggested_sl", round(rr_result.sl, 2))
        llm_result.setdefault("suggested_tp", round(rr_result.tp, 2))

    # ── Step 7: persist knowledge + training data ─────────────────────────────
    try:
        save_analysis(
            symbol,
            llm_result,
            compact_ctx,
            fundamentals_data=fundamentals_data,
        )
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: log and continue
        from loguru import logger  # noqa: PLC0415
        logger.warning(f"Knowledge save failed for {symbol}: {exc}")

    return {
        "symbol":              symbol,
        "exchange":            body.exchange,
        "source":              "local-gpt2",
        "stub_data":           fetcher is None,
        "weights_cached":      is_model_cached(),
        "sources_used":        sources_used,
        "from_knowledge_cache": from_cache,
        "technicals":          indicators,
        **fundamentals_data,
        **llm_result,
    }


# ── Knowledge management endpoints ───────────────────────────────────────────

@router.get("/knowledge", summary="List symbols with cached knowledge")
def list_knowledge() -> dict[str, Any]:
    syms = list_cached_symbols()
    return {"count": len(syms), "symbols": syms}


@router.get("/knowledge/{symbol}", summary="Get cached analysis for a symbol")
def get_knowledge(symbol: str) -> dict[str, Any]:
    data = get_cached(symbol.upper(), max_age_hours=float("inf"))
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cached knowledge for '{symbol.upper()}'. Run POST /research/analyze first.",
        )
    return data


@router.get("/training-stats", summary="Accumulated training examples count")
def training_stats() -> dict[str, Any]:
    return {
        "training_examples": training_example_count(),
        "cached_symbols":    len(list_cached_symbols()),
    }
