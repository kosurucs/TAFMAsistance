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
| **Analysis** | `src/utils/technical_analysis.py` | RSI, EMA, Bollinger Bands, LLM prompt formatter |
| **Risk** | `src/utils/risk_manager.py` | Daily-loss guardrail, position sizing, halt switch |
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
+-- models/             # Fine-tuned LoRA adapter weights
|   +-- README.md       # QLoRA fine-tuning guide
+-- scripts/
|   +-- init_db.sql     # TimescaleDB schema
+-- src/
|   +-- agents/
|   |   +-- trading_agent.py   # LangGraph state machine
|   +-- tools/
|   |   +-- kite_tools.py      # Zerodha wrappers
|   |   +-- data_pipeline.py   # OHLCV ingestion
|   +-- utils/
|   |   +-- technical_analysis.py
|   |   +-- risk_manager.py
|   +-- main.py         # Entry point
+-- tests/
|   +-- test_technical_analysis.py
|   +-- test_risk_manager.py
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
| `KITE_TOTP_SECRET` | - | Base-32 TOTP secret for 2FA |
| `LLM_MODEL_PATH` | `models/trading-lora-adapter` | Path to fine-tuned LoRA weights |
| `PAPER_TRADING` | `true` | Simulate trades without hitting Kite live API |
| `MAX_DAILY_LOSS_PCT` | `0.02` | Halt threshold (2% of capital) |
| `MAX_POSITION_SIZE_PCT` | `0.05` | Max single-trade size (5% of capital) |
| `OPENING_CAPITAL` | `100000` | Portfolio value at market open (INR) |
| `WATCHLIST` | `RELIANCE` | Comma-separated NSE symbols |

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

## Tests

```bash
cd trading_bot
python -m pytest tests/ -v
```

45 unit tests cover technical indicators, risk guardrails, halt switch,
and position sizing.

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
