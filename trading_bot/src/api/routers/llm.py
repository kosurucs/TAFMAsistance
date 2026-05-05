"""
llm.py – LLM analysis endpoints.

Routes:
  POST /llm/analyze  – compute indicators for a symbol and ask the LLM
  POST /llm/chat     – free-form question sent directly to the LLM
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_data_fetcher, get_llm_chain
from src.api.routers.market import _make_stub_df
from src.tools.data_pipeline import DataPipeline
from src.tools.kite_tools import KiteDataFetcher
from src.utils.technical_analysis import compute_indicators, format_market_state_prompt

router = APIRouter(prefix="/llm")


# ── Request / response models ─────────────────────────────────────────────────


class AnalyzeRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    question: str | None = None


class ChatRequest(BaseModel):
    prompt: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_llm_output(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*?\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"action": "WAIT", "reason": "Could not parse LLM response."}


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/analyze", summary="Get LLM BUY/SELL/WAIT decision for a symbol")
def llm_analyze(
    body: AnalyzeRequest,
    llm_chain: Any = Depends(get_llm_chain),
    fetcher: KiteDataFetcher | None = Depends(get_data_fetcher),
) -> dict[str, Any]:
    """Fetch live market data, compute indicators, and ask the LLM to decide.

    An optional *question* field lets you override or append custom context
    to the standard market-state prompt.
    """
    symbol = body.symbol.upper()

    # ── Fetch OHLCV ──────────────────────────────────────────────────────────
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
                detail=f"Instrument '{symbol}' not found on '{body.exchange}'.",
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Kite data error: {exc}")
    else:
        df = _make_stub_df(symbol)

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for '{symbol}'.")

    # ── Compute indicators ────────────────────────────────────────────────────
    try:
        indicators = compute_indicators(df)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Indicator error: {exc}")

    prompt = format_market_state_prompt(symbol, indicators)
    if body.question:
        prompt += f"\nAdditional context: {body.question}"

    # ── LLM call ─────────────────────────────────────────────────────────────
    try:
        raw_output: str = llm_chain.invoke({"input": prompt})
        parsed = _parse_llm_output(raw_output)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"LLM error: {exc}")

    return {
        "symbol": symbol,
        "action": parsed.get("action", "WAIT"),
        "reason": parsed.get("reason", ""),
        "indicators": indicators,
        "stub_data": fetcher is None,
    }


@router.post("/chat", summary="Send a free-form prompt directly to the LLM")
def llm_chat(
    body: ChatRequest,
    llm_chain: Any = Depends(get_llm_chain),
) -> dict[str, str]:
    """Send any text prompt to the LLM and receive its raw response.

    Useful for exploratory / diagnostic use-cases.
    """
    try:
        response: str = llm_chain.invoke({"input": body.prompt})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"LLM error: {exc}")
    return {"response": response}
