# TAFMAsistance - Autonomous AI Trading Agent

A stateful, LLM-powered trading application for the **Indian Stock Market (NSE/BSE)**
built on Zerodha Kite Connect and LangGraph.

---

## Architecture

The system follows a **Reasoning-Action** loop implemented as a LangGraph state machine:

```
fetch_market_state  (OHLCV + live quote via Kite API)
       |
technical_analysis  (RSI, EMA-9/21, Bollinger Bands via pandas_ta)
       |
llm_reasoning ----WAIT----> END
       | BUY / SELL
risk_validator -- REJECTED --> END
       | APPROVED
execute_order  (live Kite order or paper-trade simulation)
       |
      END
```

### Component Map

| Layer | File | Responsibility |
|---|---|---|
| **Broker** | `src/tools/kite_tools.py` | Auth (TOTP), OHLCV fetch, order placement, portfolio |
| **Data** | `src/tools/data_pipeline.py` | OHLCV to pandas DataFrame, CSV cache |
| **Kite client** | `src/tools/kite_client.py` | Factory: build authenticated `KiteConnect` from env vars |
| **Market data** | `src/tools/market_data.py` | LTP, quote, OHLC, historical candles (batched, retried) |
| **Portfolio** | `src/tools/portfolio.py` | Margins, positions, holdings, orders, order trades |
| **Instruments** | `src/tools/instruments.py` | Download/cache instruments; `(exchange, symbol) → token` |
| **Analysis** | `src/utils/technical_analysis.py` | RSI, EMA, Bollinger Bands, LLM prompt formatter |
| **Risk** | `src/utils/risk_manager.py` | Daily-loss guardrail, position sizing, halt switch |
| **Retry** | `src/utils/retry.py` | Exponential-backoff retry helper |
| **Brain** | `src/agents/trading_agent.py` | LangGraph state machine (5 nodes) |
| **Entry** | `src/main.py` | Trading loop, LLM loading, CLI |

---

## Tech Stack

| Component | Technology |
|---|---|
| Broker API | Zerodha Kite Connect (Python SDK) |
| Orchestration | LangGraph (Stateful LangChain) |
| Custom LLM | Llama 3 / Qwen-2.5 (fine-tuned via QLoRA) |
| Data Processing | pandas_ta |
| State Memory | Redis |
| Trade Logs | TimescaleDB |
| Runtime | Docker + Python 3.10+ |

---

## Folder Structure

```
trading_bot/
+-- data/               # CSVs, historical data, training_data.jsonl
|   +-- instruments_cache/  # per-exchange instruments CSVs (auto-generated)
+-- models/             # Fine-tuned LoRA adapter weights
|   +-- README.md       # QLoRA fine-tuning guide
+-- scripts/
|   +-- init_db.sql     # TimescaleDB schema
+-- src/
|   +-- agents/
|   |   +-- trading_agent.py   # LangGraph state machine
|   +-- tools/
|   |   +-- kite_tools.py      # Zerodha auth, OHLCV fetch, order placement
|   |   +-- data_pipeline.py   # OHLCV ingestion
|   |   +-- kite_client.py     # Factory: build KiteConnect from env vars
|   |   +-- market_data.py     # LTP / quote / OHLC / historical (batched)
|   |   +-- portfolio.py       # Margins, positions, holdings, orders
|   |   +-- instruments.py     # Instruments cache + token lookup
|   +-- utils/
|   |   +-- technical_analysis.py
|   |   +-- risk_manager.py
|   |   +-- retry.py           # Exponential-backoff retry helper
|   +-- main.py         # Entry point
+-- tests/
|   +-- test_technical_analysis.py
|   +-- test_risk_manager.py
|   +-- test_kite_data_layer.py  # Tests for data layer (retry, batching, cache)
+-- .env.example
+-- docker-compose.yml
+-- Dockerfile
+-- requirements.txt
```

---

## Quick Start

### 1. Configure

```bash
cp trading_bot/.env.example trading_bot/.env
# Edit .env with your Zerodha credentials, or leave PAPER_TRADING=true
```

### 2. Run with Docker (recommended)

```bash
cd trading_bot
docker-compose up -d
```

This starts **Redis**, **TimescaleDB**, and the **trading bot** container.

### 3. Run locally

```bash
cd trading_bot
pip install -r requirements.txt
python src/main.py
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KITE_API_KEY` | - | Zerodha API key |
| `KITE_API_SECRET` | - | Zerodha API secret |
| `KITE_ACCESS_TOKEN` | - | Session token (set automatically after login) |
| `KITE_TOTP_SECRET` | - | Base-32 TOTP secret for 2FA |
| `KITE_USER_ID` | - | Zerodha user-id (used by automated TOTP login) |
| `LLM_MODEL_PATH` | `models/trading-lora-adapter` | Path to fine-tuned LoRA weights |
| `PAPER_TRADING` | `true` | Simulate trades without hitting Kite live API |
| `MAX_DAILY_LOSS_PCT` | `0.02` | Halt threshold (2% of capital) |
| `MAX_POSITION_SIZE_PCT` | `0.05` | Max single-trade size (5% of capital) |
| `OPENING_CAPITAL` | `100000` | Portfolio value at market open (INR) |
| `WATCHLIST` | `RELIANCE` | Comma-separated NSE symbols |
| `INSTRUMENTS_CACHE_DIR` | `data/instruments_cache` | Directory for cached instruments CSVs |

---

## Risk Management

Four independent guardrails protect capital:

1. **Max Daily Loss** - If intraday P&L drops below `MAX_DAILY_LOSS_PCT` x capital,
   the halt switch triggers and all trading stops.
2. **Position Sizing** - Every order quantity is capped at
   `MAX_POSITION_SIZE_PCT` x capital / price.
3. **Manual Halt Switch** - Activate/deactivate via CLI or Redis:

   ```bash
   python src/main.py --kill    # halt immediately
   python src/main.py --unkill  # resume
   ```

4. **Paper Trading Mode** - `PAPER_TRADING=true` simulates all orders locally
   without touching the live API (default).

---

## LLM Fine-Tuning

See `trading_bot/models/README.md` for a step-by-step QLoRA fine-tuning guide
using `trl` and `peft`.

The model outputs **JSON only**:

```json
{"action": "BUY", "reason": "EMA-9 crossed above EMA-21 with RSI at 55."}
```

---

## Kite Connect Data Layer

The data connection layer wraps the official `kiteconnect` SDK for **read-only**
market and portfolio access.  It is designed to be used directly from LangGraph
nodes (e.g. `fetch_market_state`).

### Modules

| Module | Class / function | Purpose |
|---|---|---|
| `src/tools/kite_client.py` | `build_kite_client()` | Build an authenticated `KiteConnect` from env vars |
| `src/tools/market_data.py` | `MarketData` | LTP, full quote, OHLC, historical candles (auto-batched) |
| `src/tools/portfolio.py` | `Portfolio` | Margins, positions, holdings, orders, order trades |
| `src/tools/instruments.py` | `InstrumentsCache` | Download / cache instruments; `(exchange, symbol) → token` |
| `src/utils/retry.py` | `retry()` | Exponential-backoff retry helper |

### Quick usage example

```python
from src.tools.kite_client import build_kite_client
from src.tools.market_data import MarketData
from src.tools.portfolio import Portfolio
from src.tools.instruments import InstrumentsCache

kite = build_kite_client()          # reads KITE_API_KEY / KITE_ACCESS_TOKEN

# ── Market data ──────────────────────────────────────────────────────────────
md = MarketData(kite)

ltp     = md.get_ltp(["NSE:RELIANCE", "NSE:INFY"])
quotes  = md.get_quote(["NSE:RELIANCE"])
ohlc    = md.get_ohlc(["NSE:RELIANCE", "NSE:TCS"])
candles = md.get_historical(738561, "2024-01-01", "2024-01-31", "day")

# ── Portfolio ────────────────────────────────────────────────────────────────
pf = Portfolio(kite)

margins   = pf.get_margins()
positions = pf.get_positions()
holdings  = pf.get_holdings()
orders    = pf.get_orders()
trades    = pf.get_order_trades("220101000000001")
day_pnl   = pf.get_day_pnl()

# ── Instruments ──────────────────────────────────────────────────────────────
cache = InstrumentsCache(kite)
cache.warm_up(["NSE", "BSE"])       # pre-load at startup (optional)

token = cache.get_instrument_token("NSE", "RELIANCE")   # → 738561
df    = cache.get_all_instruments("NSE")                # → pandas DataFrame
```

> **Note**: `build_kite_client()` requires `KITE_API_KEY` and
> `KITE_ACCESS_TOKEN` to be set.  Use `KiteAuthManager` from
> `src/tools/kite_tools.py` to perform the initial TOTP login and obtain an
> access token.

---

## Tests

```bash
cd trading_bot
python -m pytest tests/ -v
```

69 unit tests cover technical indicators, risk guardrails, halt switch,
position sizing, retry/backoff, market data batching, instruments cache,
and portfolio wrappers.

---

## Security Checklist

- [x] API keys stored in `.env` (never committed - covered by `.gitignore`).
- [x] Manual halt switch accessible via CLI (`--kill`) and Redis.
- [x] LLM output validated by deterministic `RiskManager` before any execution.
- [x] Paper-trading mode is **on by default** - explicit opt-in required for live trading.
- [x] Non-root Docker user (`trader`).

---

## Implementation Roadmap

| Week | Milestone |
|---|---|
| 1 | Zerodha API integration and manual order testing |
| 2-3 | Data collection and QLoRA fine-tuning |
| 4 | LangGraph workflow and tool definitions |
| 5 | Backtesting and paper trading |
| 6 | Live deployment with small capital |
