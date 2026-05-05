"""
app.py – FastAPI entry point for the Trading Bot HTTP API.

Run with::

    uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload

Or via docker-compose (see docker-compose.yml).

Endpoints
---------
GET  /                   Health check
GET  /status             Bot status + kill-switch state
GET  /watchlist          Current watchlist
POST /watchlist          Replace watchlist
POST /bot/kill           Activate kill switch
POST /bot/unkill         Deactivate kill switch
GET  /market/{symbol}    Live quote + technical indicators
GET  /portfolio          Full portfolio snapshot
GET  /portfolio/positions
GET  /portfolio/holdings
GET  /portfolio/margins
POST /llm/analyze        LLM BUY/SELL/WAIT decision for a symbol
POST /llm/chat           Free-form LLM chat
POST /trade/run          Full LangGraph cycle for a symbol

Interactive docs available at /docs (Swagger UI) and /redoc.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.api.routers import bot, llm, market, portfolio, trade

app = FastAPI(
    title="TAFM Trading Bot API",
    description=(
        "REST interface for the autonomous AI trading agent. "
        "Exposes market data, LLM analysis, portfolio state, "
        "and trade execution endpoints."
    ),
    version="1.0.0",
)

# ── Register routers ──────────────────────────────────────────────────────────
app.include_router(bot.router, tags=["Bot Control"])
app.include_router(market.router, tags=["Market Data"])
app.include_router(portfolio.router, tags=["Portfolio"])
app.include_router(llm.router, tags=["LLM"])
app.include_router(trade.router, tags=["Trade Execution"])


# ── Root health check ─────────────────────────────────────────────────────────


@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {"status": "ok", "service": "TAFM Trading Bot API"}
