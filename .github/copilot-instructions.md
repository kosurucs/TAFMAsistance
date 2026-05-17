# TAFM Assistance — AI Trading Agent Project

## Architecture Overview

Five components that must work together:

| Component | Root | Purpose |
|-----------|------|---------|
| **trading_bot** | `trading_bot/` | LangGraph agent, FastAPI server, Kite Connect broker |
| **trading_ui** | `trading_ui/` | React + Vite SPA (port 5173) |
| **llm_training** | `llm_training/` | Mistral 7B fine-tuning pipeline (5–7 scripts) |
| **TimescaleDB** | `trading_bot/docker-compose.yml` | Time-series trade and market data (port 5432) |
| **Redis** | `trading_bot/docker-compose.yml` | Kill-switch signalling + caching (port 6379) |

## Build & Run Commands

```bash
# Full stack (Docker)
cd trading_bot && docker-compose up

# Backend only (dev, no Docker)
cd trading_bot && uvicorn src.ui_api:app --reload --port 8000

# UI (dev)
cd trading_ui && npm run dev

# Tests
cd trading_bot && pytest tests/ -v

# LLM inference (Ollama)
ollama run mistral:7b

# Bulk historical data download (Phase 1)
cd trading_bot && python scripts/fetch_historical.py --years 20

# Backtesting CLI (Phase 8)
cd trading_bot && python scripts/run_backtest.py --symbol RELIANCE --years 3
```

## Critical Gotchas — Read Before Every Change

1. **API module collision**: `src/api.py` is shadowed by the `src/api/` package. The correct
   uvicorn entrypoint is `src.ui_api:app` — NOT `src.api:app`.

2. **InstrumentsCache argument order**: Always `get_instrument_token(exchange, tradingsymbol)`.
   Reversing the order causes repeated master-data downloads and Kite 429 rate-limit errors.
   Symptom: repeated `/api/market-data` 500 errors while `/api/quote` still returns 200.

3. **lightweight-charts version**: Pinned to `4.2.0` in `trading_ui/package.json`.
   Do NOT upgrade to 5.x — `addCandlestickSeries is not a function` crashes the chart.

4. **Kill-switch path on Windows**: Use `Path(tempfile.gettempdir()) / "trading_kill_switch"`.
   Do NOT use `/tmp/trading_kill_switch` — that path does not exist on Windows.

5. **CORS dynamic ports**: The UI may start on 5174+ if 5173 is busy.
   Use `allow_origin_regex` in FastAPI CORS settings, not a static origin list.

6. **Analysis-only mode**: Order placement has been **DISABLED** system-wide. The bot performs
   analysis, backtesting, and recommendations only. All order placement endpoints return HTTP 403.
   UI modals (OrderModal, GTTModal) have been removed.

## System Capabilities (Analysis-Only Mode)

**IMPORTANT**: This system does NOT place live or paper trades. All order placement functionality
has been permanently disabled. The system provides:

- Real-time market data viewing and charting
- Technical analysis and indicator computation
- LLM-powered trade recommendations (logged only, not executed)
- Backtesting and strategy analysis
- Portfolio monitoring (read-only)
- Historical data management

Order placement endpoints (`POST /api/order`, `POST /api/gtt`, etc.) return HTTP 403 Forbidden.
The LangGraph trading agent logs analysis results but does not execute trades.

## Non-Negotiable Trading Rules (For Analysis Context)

- **Risk/Reward gate**: Every trade must have R:R ≥ 1:2.
  Formula: `SL = entry_price − 1.5 × ATR`, `TP = entry_price + 3 × ATR`.
- **Scenario confidence gate**: Only enter trades when the dominant scenario probability ≥ 60%.
- **Kill-switch**: Never remove or weaken the 3-tier kill-switch (in-process flag, Redis key, flag file).
- **Position sizing**: Max 5% of capital per trade. Max daily loss: 2% of opening capital.
- **Multi-timeframe confirmation**: Trading decisions use 1m + 15m + 1h + 1D confluence.
- **Indian market hours**: 09:15–15:30 IST. All timestamps displayed in IST (+05:30).

## LLM Output Contract

The fine-tuned LLM and Ollama model must always return valid JSON:

```json
{
  "action": "BUY | SELL | WAIT",
  "reason": "one sentence",
  "confidence": 0,
  "suggested_sl": 0.0,
  "suggested_tp": 0.0
}
```

Any deviation is treated as WAIT. Structured response is surfaced in the UI with confidence badge,
action pill, and key-factors tags.

## Key Files

| Purpose | Path |
|---------|------|
| LangGraph agent graph | `trading_bot/src/agents/trading_agent.py` |
| Risk manager | `trading_bot/src/utils/risk_manager.py` |
| Technical indicators | `trading_bot/src/utils/technical_analysis.py` |
| R:R calculator | `trading_bot/src/utils/rr_calculator.py` |
| Scenario engine | `trading_bot/src/utils/scenario_engine.py` |
| Exit monitor | `trading_bot/src/utils/exit_monitor.py` |
| Backtester | `trading_bot/src/utils/backtester.py` |
| DB logger | `trading_bot/src/utils/db_logger.py` |
| Historical data manager | `trading_bot/src/tools/historical_data.py` |
| Historical data CLI | `trading_bot/scripts/fetch_historical.py` |
| Kite Connect wrappers | `trading_bot/src/tools/kite_tools.py` |
| API dependency injection | `trading_bot/src/api/dependencies.py` |
| LLM chat endpoint | `trading_bot/src/api/routers/llm.py` |
| Backtest endpoint | `trading_bot/src/api/routers/backtest.py` |
| DB schema | `trading_bot/scripts/init_db.sql` |
| Modelfile (Ollama) | `llm_training/Modelfile` |
| UI entry | `trading_ui/src/main.jsx` |
| UI design tokens | `trading_ui/src/design-system/tokens.js` |
| UI theme CSS vars | `trading_ui/src/design-system/theme.css` |
| UI global store | `trading_ui/src/store/` |
| UI HTTP service | `trading_ui/src/services/api.js` |

## UI Architecture Rules (Phase 9)

- All colours, spacing, and typography come from CSS custom properties in `theme.css`. No raw hex values in components.
- All HTTP calls go through `trading_ui/src/services/api.js`. No direct `axios` calls in components.
- Global state lives in the zustand store at `trading_ui/src/store/`. No prop-drilling beyond 2 levels.
- Feature components live in `trading_ui/src/features/<domain>/`.
- Pages live in `trading_ui/src/pages/`. Five pages: Dashboard, Portfolio, Backtest, Simulate, LLM Studio.
- Primitive UI atoms (Button, Badge, Card, Modal, Spinner, etc.) live in `trading_ui/src/design-system/`.

## Agent & Prompt Inventory

| Agent | Trigger | Purpose |
|-------|---------|---------|
| `trading-architect` | Cross-component changes | Full-stack architecture, cross-cutting concerns |
| `ui-developer` | UI changes only | Design system enforcement, feature folder structure |
| `backtest-analyst` | Backtesting / strategy work | Strategy analysis, WHY-it-works attribution |
| `llm-trainer` | LLM training pipeline | Dataset scripts, Modelfile, fine-tuning params |
| `risk-guardian` | Risk rule review | Read-only APPROVED/REJECTED validator |
| `doc-sync` | After code changes (subagent) | Auto-updates `.github/instructions/` files |

| Prompt | Slash command | Purpose |
|--------|---------------|---------|
| `add-indicator` | `/add-indicator` | Add a new technical indicator end-to-end |
| `add-strategy` | `/add-strategy` | Add a new trading strategy end-to-end |
| `add-ui-page` | `/add-ui-page` | Scaffold a new UI page with all layers |
| `backtest-symbol` | `/backtest-symbol` | Run and interpret a full backtest |
| `sync-docs` | `/sync-docs` | Sync `.github/instructions/` after code changes |
| `add-training-data` | `/add-training-data` | Add a new LLM training data source |
