---
description: "Use when writing or modifying Python backend code in the trading_bot: LangGraph nodes, FastAPI routers, tools, utils, risk management, data pipeline, Kite Connect wrappers."
applyTo: "trading_bot/**/*.py"
---

# Python Backend Conventions

## LangGraph State Machine

- Every node function receives a `TradingState` TypedDict and must return `{**state, <new_keys>: <values>}` — never mutate state in place.
- Node signature: `def node_name(state: TradingState) -> TradingState:`
- Route functions (conditional edges) must return string literals matching graph node names or `"__end__"`.
- New TradingState fields: add to `TradingState` TypedDict in `trading_agent.py` with `total=False` (all optional).
- Always inject runtime dependencies (pipeline, order_manager, risk_manager, llm_chain) via the state dict before calling `graph.invoke(initial_state)`.

## Dependency Injection

- All singletons (Kite session, RiskManager, LLM chain, watchlist) live in `trading_bot/src/api/dependencies.py`.
- Use FastAPI `Depends()` in router functions — never instantiate singletons directly in router code.
- Pattern: `def get_risk_manager() -> RiskManager: return _risk_manager_singleton`

## Error Handling & Logging

- Use `loguru` for all logging — `from loguru import logger`. Never use `print()` or `logging.getLogger()`.
- Never catch bare `Exception` without logging: always `except Exception as exc: logger.error("...: {}", exc)`.
- For Kite API calls, wrap with `@retry_with_backoff` from `trading_bot/src/utils/retry.py`.
- Return sensible defaults (WAIT, empty dict, 0) on failure — never let an exception propagate past a LangGraph node.

## API Routers

- Every new router file goes in `trading_bot/src/api/routers/`.
- Register the router in `trading_bot/src/api/app.py` using `app.include_router(router, prefix="/api")`.
- Use Pydantic `BaseModel` for all request and response bodies — no raw dicts in endpoint signatures.
- All endpoints that call Kite must handle `PAPER_TRADING=true` gracefully (stub response or skip).

## Kite Connect

- Import via `from src.tools.kite_tools import KiteDataFetcher, KiteOrderManager, KitePortfolio`.
- `InstrumentsCache.get_instrument_token(exchange, tradingsymbol)` — argument order is ALWAYS `(exchange, tradingsymbol)`.
- Use `from src.tools.instruments import InstrumentsCache` — never call `kite.instruments()` directly (triggers download every call).
- Paper trading guard: `if PAPER_TRADING: return f"PAPER-{timestamp}"` before any real order placement.

## Historical Data (Phase 1)

- Import: `from src.tools.historical_data import HistoricalDataManager`
- Provides yfinance-based 20-year OHLCV data for Nifty 50 + indices.
- Key methods:
  - `fetch_symbol(symbol, period="20y", interval="1d")` — fetch from yfinance
  - `get_symbol_data(symbol, period, interval, use_cache=True)` — fetch or load from CSV cache
  - `save_to_csv(symbol, df, interval)` — persist to `data/historical/{symbol}_{interval}.csv`
  - `load_from_csv(symbol, interval)` — load from cache
  - `save_to_db(symbol, df, interval)` — insert into `historical_ohlcv` TimescaleDB table
- NSE symbols auto-converted: `RELIANCE` → `RELIANCE.NS`
- Index symbols stay as-is: `^NSEI`, `^BSESN`
- Supported intervals: `1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo`
- Retry logic: 3 attempts with 2s delay for network failures
- CLI: `python scripts/fetch_historical.py --symbols RELIANCE TCS --years 20 --interval 1d --indices`

## Multi-Timeframe Indicators (Phase 2)

- Import: `from src.utils.technical_analysis import compute_indicators_multi_timeframe, format_mtf_section`
- `compute_indicators_multi_timeframe(symbol, pipeline)` returns dict with keys `1m`, `15m`, `1h`, `1D`.
- Each timeframe dict contains: RSI, EMA9, EMA21, EMA50, EMA200, BB, MACD, ATR, Stochastic, volume.
- `format_mtf_section(mtf_data)` converts to markdown table for LLM input.
- TradingState fields added: `mtf_indicators`, `mtf_confluence_score`, `mtf_bias`.
- Confluence score: +1 for each timeframe where EMA9 > EMA21 (max 4).

## R:R Calculator (Phase 3)

- Import: `from src.utils.rr_calculator import RRCalculator, MIN_RR_RATIO, is_rr_acceptable`
- `MIN_RR_RATIO = 2.0` — hardcoded, non-negotiable.
- `calculate_sl_tp(action, entry_price, atr)` returns `(sl, tp)` using 1.5×ATR / 3.0×ATR formula.
- `is_rr_acceptable(entry_price, sl, tp)` returns True if R:R ≥ 2.0.
- TradingState fields added: `sl`, `tp`, `rr_ratio`, `rr_reason`.
- Wired into LangGraph: `rr_calculator_node` runs after `llm_decision_node`.

## Scenario Engine (Phase 4)

- Import: `from src.utils.scenario_engine import ScenarioEngine, SCENARIO_CONFIDENCE_THRESHOLD`
- `SCENARIO_CONFIDENCE_THRESHOLD = 60` (percentage).
- 5 scenarios: BULLISH_BREAKOUT, BEARISH_BREAKDOWN, SIDEWAYS_CONSOLIDATION, REVERSAL_UP, REVERSAL_DOWN.
- `analyze_scenarios(indicators)` returns probabilities dict (sum = 100%).
- `get_trade_bias(probabilities, threshold=60)` returns `BUY | SELL | WAIT`.
- TradingState fields added: `scenario_probabilities`, `dominant_scenario`, `scenario_bias`.
- Wired into LangGraph: `scenario_analysis_node` runs before `llm_decision_node`.

## Exit Monitor (Phase 6)

- Import: `from src.utils.exit_monitor import ExitMonitor, ExitSignal`
- 6 exit rules: TP_HIT, SL_HIT, TRAILING_STOP, TIME_DECAY, MTF_REVERSAL, KILL_SWITCH.
- `check_exit(position, current_price, indicators, mtf_data)` returns `ExitSignal | None`.
- `ExitSignal` dataclass fields: `reason`, `should_exit`, `suggested_price`.
- Runs in `monitor_positions()` async coroutine in `main.py` (every 30s).
- Endpoint: `GET /api/portfolio/monitor` (returns list of exit signals).

## Database Logger (Phase 7)

- Import: `from src.utils.db_logger import DBLogger`
- Singleton pattern: use `get_db_logger()` dependency.
- Key methods:
  - `log_trade_entry(...)` → inserts into `trades` table
  - `log_trade_exit(...)` → updates `trades` row
  - `log_market_snapshot(...)` → inserts into `market_snapshots` hypertable
- Called from `trading_agent.py` nodes: `execute_order` (trade entry/exit), `technical_analysis` (snapshots).
- Connection pool: `minconn=2`, `maxconn=10`.

## Backtest API (Phase 8)

- Router: `trading_bot/src/api/routers/backtest.py`
- Endpoints:
  - `POST /api/backtest/run` — start new backtest (async task)
  - `GET /api/backtest/status/{run_id}` — poll status (PENDING/RUNNING/COMPLETED/FAILED)
  - `GET /api/backtest/result/{run_id}` — fetch metrics + attribution
- Uses `Backtester` class from `src.utils.backtester.py`.
- Returns: total trades, win rate, total P&L, max drawdown, Sharpe ratio, WHY-it-works attribution.
- CLI: `python scripts/run_backtest.py --symbol RELIANCE --years 3 --strategy TREND_FOLLOWING`

## Risk Manager

- Import: `from src.utils.risk_manager import RiskManager`
- Always call `risk_manager.is_kill_switch_active()` before placing any order.
- P&L method: `portfolio.get_day_pnl()` — NOT `portfolio.get_pnl()` (wrong method, causes AttributeError).
- Kill-switch flag path must use `Path(tempfile.gettempdir()) / "trading_kill_switch"` — not `/tmp/...`.

## Testing

- Test files go in `trading_bot/tests/` named `test_<module>.py`.
- Use `pytest` fixtures — no `unittest.TestCase` classes.
- Mock Kite API calls with `pytest-mock` (`mocker.patch`).
- Run: `cd trading_bot && pytest tests/ -v`
