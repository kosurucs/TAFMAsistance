# Local Setup Guide – TAFMAsistance Trading Bot

This guide walks you through every step required to run the autonomous AI trading bot on your own machine, including dependency installation, service setup, Zerodha credentials, and LLM creation.

---

## Table of Contents

1. [System Prerequisites](#1-system-prerequisites)
2. [Clone & Install Python Dependencies](#2-clone--install-python-dependencies)
3. [Configure Environment Variables](#3-configure-environment-variables)
4. [Infrastructure: Redis & TimescaleDB](#4-infrastructure-redis--timescaledb)
   - [Option A – Docker (easiest)](#option-a--docker-easiest)
   - [Option B – Native install](#option-b--native-install)
5. [Zerodha Kite Connect Setup](#5-zerodha-kite-connect-setup)
6. [LLM Setup](#6-llm-setup)
   - [Option 1 – Stub (no GPU, no model)](#option-1--stub-no-gpu-no-model)
   - [Option 2 – Pre-trained Llama 3 from HuggingFace](#option-2--pre-trained-llama-3-from-huggingface)
   - [Option 3 – Fine-tune your own model (QLoRA)](#option-3--fine-tune-your-own-model-qlora)
7. [Run the Bot](#7-run-the-bot)
8. [Run the Tests](#8-run-the-tests)
9. [CLI Reference](#9-cli-reference)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. System Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Python | 3.10+ | 3.11 recommended |
| pip | 23+ | `pip install --upgrade pip` |
| Git | any | for cloning |
| Docker + Docker Compose | 24+ / v2 | only if using Option A for services |
| Redis | 6+ | only if running natively |
| PostgreSQL with TimescaleDB | PG 15 | only if running natively |
| CUDA toolkit + NVIDIA GPU | 11.8+ | only for LLM Options 2 & 3 |

> **No GPU?**  
> Use [Option 1 (Stub)](#option-1--stub-no-gpu-no-model).  
> The entire pipeline — market data, technical analysis, risk management — runs on CPU only. The stub LLM always returns `WAIT`, so no real orders are ever placed.

---

## 2. Clone & Install Python Dependencies

```bash
# Clone the repository
git clone https://github.com/kosurucs/TAFMAsistance.git
cd TAFMAsistance

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows

# Install all Python packages
pip install --upgrade pip
pip install -r trading_bot/requirements.txt
```

### What gets installed

| Group | Packages | Purpose |
|---|---|---|
| **Broker API** | `kiteconnect>=4.2.0` | Zerodha Kite Connect SDK |
| **LLM Orchestration** | `langchain>=0.2.0`, `langgraph>=0.1.0`, `langchain-community>=0.2.0` | LangGraph state machine + LangChain LLM interface |
| **Data Processing** | `pandas>=2.0.0`, `pandas-ta>=0.3.14b`, `numpy>=1.26.0` | DataFrame manipulation, technical indicators (RSI, EMA, Bollinger Bands) |
| **Database Clients** | `redis>=5.0.0`, `psycopg2-binary>=2.9.9` | Redis state memory, TimescaleDB trade logs |
| **Config / Auth** | `python-dotenv>=1.0.0`, `pyotp>=2.9.0` | `.env` file loading, TOTP 2FA for Zerodha |
| **HTTP** | `requests>=2.31.0` | Zerodha login API calls |
| **LLM / Fine-tuning** | `transformers>=4.40.0`, `peft>=0.10.0`, `torch>=2.1.0`, `accelerate>=0.27.0`, `bitsandbytes>=0.42.0`, `datasets>=2.18.0`, `trl>=0.8.6` | Load and fine-tune LLM with QLoRA |
| **Utilities** | `schedule>=1.2.1`, `loguru>=0.7.2` | Job scheduling, structured logging |
| **Testing** | `pytest>=8.0.0`, `pytest-mock>=3.12.0` | Unit test runner |

> **Note on `torch`**: The default `pip install torch` pulls the CPU build.  
> For NVIDIA GPU support, install the CUDA-specific wheel instead:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cu118   # CUDA 11.8
> pip install torch --index-url https://download.pytorch.org/whl/cu121   # CUDA 12.1
> ```

> **Note on `bitsandbytes`**: Only needed for 4-bit quantisation (LLM Options 2 & 3).  
> It requires a CUDA GPU. If you are using the stub LLM (Option 1) you can skip it:
> ```bash
> pip install -r trading_bot/requirements.txt --ignore-requires-python \
>     --constraint /dev/null   # or just comment out bitsandbytes in requirements.txt
> ```

---

## 3. Configure Environment Variables

```bash
cp trading_bot/.env.example trading_bot/.env
```

Open `trading_bot/.env` in a text editor and fill in the values described below.

### Full variable reference

#### Zerodha Kite Connect

| Variable | Required | Example | Description |
|---|---|---|---|
| `KITE_API_KEY` | Yes (live) | `abc123xyz` | Your Kite Connect API key from the [Kite developer portal](https://developers.kite.trade/) |
| `KITE_API_SECRET` | Yes (live) | `secretvalue` | API secret (keep this private) |
| `KITE_ACCESS_TOKEN` | Auto | *(empty)* | Session token — set automatically after login; you can paste it manually to skip the TOTP login |
| `KITE_TOTP_SECRET` | Yes (live) | `JBSWY3DPEHPK3PXP` | Base-32 TOTP secret shown when you enable 2FA on your Zerodha account |
| `KITE_USER_ID` | Optional | `ZJ1234` | Your Zerodha user ID; used for fully automated headless login |
| `KITE_PASSWORD` | Optional | `yourpassword` | Your Zerodha password; used for fully automated headless login |

> **Paper-trading mode** (`PAPER_TRADING=true`) never calls the live Kite API.  
> Kite credentials are not needed if you stay in paper-trading mode.

#### Instruments Cache

| Variable | Default | Description |
|---|---|---|
| `INSTRUMENTS_CACHE_DIR` | `data/instruments_cache` | Directory where per-exchange instrument CSVs are cached (refreshed daily) |

#### LLM Configuration

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL_PATH` | `models/trading-lora-adapter` | Path to your fine-tuned LoRA adapter directory (relative to `trading_bot/`) |
| `LLM_BASE_MODEL` | `meta-llama/Meta-Llama-3-8B` | HuggingFace model ID used as the base model when loading LoRA weights |

#### Redis (State Memory)

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB` | `0` | Redis database index |

#### TimescaleDB (Trade Logs)

| Variable | Default | Description |
|---|---|---|
| `TIMESCALE_HOST` | `localhost` | TimescaleDB hostname |
| `TIMESCALE_PORT` | `5432` | PostgreSQL port |
| `TIMESCALE_DB` | `trading_logs` | Database name |
| `TIMESCALE_USER` | `trader` | Database user |
| `TIMESCALE_PASSWORD` | `changeme` | Database password |

#### Risk Management

| Variable | Default | Description |
|---|---|---|
| `MAX_DAILY_LOSS_PCT` | `0.02` | Maximum intraday loss as a fraction of opening capital (e.g. `0.02` = 2%). The bot halts if this threshold is breached. |
| `MAX_POSITION_SIZE_PCT` | `0.05` | Maximum single-trade size as a fraction of portfolio value (e.g. `0.05` = 5%) |
| `OPENING_CAPITAL` | `100000` | Portfolio value at market open in INR (used to calculate loss limits and position sizes) |

#### Trading Mode & Watchlist

| Variable | Default | Description |
|---|---|---|
| `PAPER_TRADING` | `true` | `true` = simulate orders locally; `false` = place live orders via Kite |
| `WATCHLIST` | `RELIANCE` | Comma-separated NSE trading symbols to monitor (e.g. `RELIANCE,INFY,TCS`) |
| `EXCHANGE` | `NSE` | Exchange for all symbols in `WATCHLIST` |
| `POLL_INTERVAL_SECONDS` | `60` | How many seconds to wait between each analysis cycle |

---

## 4. Infrastructure: Redis & TimescaleDB

The bot uses:
- **Redis** – stores the kill-switch flag and can act as in-memory state.
- **TimescaleDB** – time-series PostgreSQL extension that logs every trade and daily P&L snapshot.

Both are optional for **paper-trading**. Redis falls back to in-process state and TimescaleDB is not actively queried by the core loop (it is available for your own analytics queries).

### Option A – Docker (easiest)

```bash
cd trading_bot

# Start Redis and TimescaleDB only (not the bot itself)
docker-compose up -d redis timescaledb
```

Verify:
```bash
docker ps          # should show trading_redis and trading_timescaledb
redis-cli ping     # should return PONG
```

The `scripts/init_db.sql` file is automatically run when TimescaleDB starts, creating the `trade_log` and `daily_pnl` hypertables.

### Option B – Native install

#### Redis

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install redis-server
sudo systemctl start redis-server
redis-cli ping    # → PONG

# macOS (Homebrew)
brew install redis
brew services start redis
redis-cli ping    # → PONG
```

#### TimescaleDB

```bash
# Ubuntu (official TimescaleDB apt repo)
sudo apt install -y postgresql-15 postgresql-client-15
# Follow the TimescaleDB install guide: https://docs.timescale.com/self-hosted/latest/install/

# After install, connect as postgres superuser and run:
sudo -u postgres psql -c "CREATE USER trader WITH PASSWORD 'changeme';"
sudo -u postgres psql -c "CREATE DATABASE trading_logs OWNER trader;"
sudo -u postgres psql -d trading_logs -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
sudo -u postgres psql -d trading_logs -U trader -f trading_bot/scripts/init_db.sql
```

---

## 5. Zerodha Kite Connect Setup

> **Skip this section if you are using `PAPER_TRADING=true`.**

### Step 1 – Create a Kite Connect app

1. Log in at [https://developers.kite.trade/](https://developers.kite.trade/).
2. Click **"Create new app"**.
3. Choose app type **"Connect"**.
4. Set the **Redirect URL** to one of:
    - `http://localhost:5173/login` (recommended)
    - `https://localhost:7049` (supported fallback)
5. Copy the **API Key** and **API Secret** into your `.env`.

### Step 2 – Enable TOTP 2FA

1. Log in to [https://kite.zerodha.com/](https://kite.zerodha.com/) → **Profile → Security**.
2. Enable **TOTP**. You will be shown a **Base-32 secret** (looks like `JBSWY3DPEHPK3PXP`).
3. Copy that secret into `KITE_TOTP_SECRET` in your `.env`.

### Step 3 – First login

Use the UI login page at `http://localhost:5173/login`.

- If credentials are missing, the app will ask for `KITE_API_KEY` and `KITE_API_SECRET`.
- Click **Login with Zerodha Kite**.
- After successful login:
    - If redirect is `http://localhost:5173/login`, exchange is automatic.
    - If redirect is `https://localhost:7049`, copy callback URL or `request_token` and use the manual exchange box in the login page.

The access token is valid for one trading day. The bot caches it in the `KITE_ACCESS_TOKEN` environment variable so subsequent restarts within the same day skip the login step.

---

## 6. LLM Setup

The LLM is the "brain" of the bot. It receives a formatted prompt containing the latest technical indicators and returns a JSON decision:

```json
{"action": "BUY", "reason": "EMA-9 crossed above EMA-21 with RSI at 55."}
```

You have three options:

### Option 1 – Stub (no GPU, no model)

**Use this if you have no GPU or just want to test the pipeline.**

No extra steps needed. If `LLM_MODEL_PATH` does not exist, the bot automatically uses a stub LLM that always returns `WAIT`. All other parts of the pipeline (market data, technical analysis, risk management) run normally.

```
# .env
LLM_MODEL_PATH=models/trading-lora-adapter   # leave as-is; directory won't exist
```

You will see this log line on startup:
```
WARNING | LLM model not found – using WAIT-only stub chain.
```

### Option 2 – Pre-trained Llama 3 from HuggingFace

**Use this for better trading decisions without fine-tuning. Requires a GPU with ≥ 16 GB VRAM (or ≥ 8 GB with 4-bit quantisation).**

#### 2a. Accept the Llama 3 license

Visit [https://huggingface.co/meta-llama/Meta-Llama-3-8B](https://huggingface.co/meta-llama/Meta-Llama-3-8B) and accept the license agreement.

#### 2b. Log in to HuggingFace CLI

```bash
pip install huggingface_hub
huggingface-cli login
# paste your HuggingFace access token when prompted
```

#### 2c. Download the model

The model is downloaded automatically on first use if `LLM_BASE_MODEL` is set and weights are accessible. Alternatively, pre-download it:

```bash
python -c "
from transformers import AutoModelForCausalLM, AutoTokenizer
model_id = 'meta-llama/Meta-Llama-3-8B'
AutoTokenizer.from_pretrained(model_id)
AutoModelForCausalLM.from_pretrained(model_id, load_in_4bit=True, device_map='auto')
print('Model downloaded.')
"
```

#### 2d. Point the bot at the base model (no LoRA adapter)

```
# .env
LLM_MODEL_PATH=models/trading-lora-adapter   # keep this; it will be missing
LLM_BASE_MODEL=meta-llama/Meta-Llama-3-8B
```

The code in `src/main.py` (`_build_llm_chain`) loads the LoRA adapter from `LLM_MODEL_PATH`. If that path does not exist it falls back to the stub. To load only the base model without a LoRA adapter, create a minimal adapter directory manually or modify `_build_llm_chain` to skip `PeftModel.from_pretrained` when no adapter is present.

> **Alternative lighter models** (if 8B parameters is too large):
> - `Qwen/Qwen2.5-1.5B-Instruct` (1.5 B parameters, very fast on CPU/low-end GPU)
> - `microsoft/phi-3-mini-4k-instruct` (3.8 B parameters)
>
> Change `LLM_BASE_MODEL` in `.env` to use a different model.

### Option 3 – Fine-tune your own model (QLoRA)

**Best trading performance. Requires a GPU with ≥ 16 GB VRAM and your own labelled training data.**

This adapts a base LLM to understand stock-market prompts and respond with valid JSON trading decisions.

#### 3a. Prepare training data

Create a JSONL file at `trading_bot/data/training_data.jsonl`.  
Each line is one training sample:

```json
{"instruction": "Analyse the current market state for NSE:RELIANCE.\nMarket State:\n  - Close Price  : 2450.35\n  - RSI (14)      : 72.4\n  - EMA Fast (9)  : 2440.10\n  - EMA Slow (21)  : 2415.80\n  - Trend        : BULLISH\n  - BB Signal    : ABOVE_UPPER", "output": "{\"action\": \"SELL\", \"reason\": \"RSI overbought above 70 and price above upper Bollinger Band – potential reversal.\"}"}
{"instruction": "Analyse the current market state for NSE:INFY.\nMarket State:\n  - Close Price  : 1540.20\n  - RSI (14)      : 48.1\n  - EMA Fast (9)  : 1542.00\n  - EMA Slow (21)  : 1530.50\n  - Trend        : NEUTRAL\n  - BB Signal    : INSIDE_BANDS", "output": "{\"action\": \"WAIT\", \"reason\": \"No clear signal; RSI neutral and price inside Bollinger Bands.\"}"}
```

Minimum recommended: **200–500 samples** covering BUY, SELL, and WAIT scenarios.

#### 3b. Install fine-tuning dependencies (already in requirements.txt)

```bash
pip install transformers peft trl datasets accelerate bitsandbytes
```

#### 3c. Run the fine-tuning script

Save the script below as `trading_bot/scripts/finetune.py` and run it:

```python
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
import torch

MODEL_ID  = "meta-llama/Meta-Llama-3-8B"   # or any other base model
DATA_PATH = "data/training_data.jsonl"
OUTPUT_DIR = "models/trading-lora-adapter"

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    load_in_4bit=True,      # QLoRA: 4-bit quantisation (saves GPU memory)
    device_map="auto",
    torch_dtype=torch.float16,
)
model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=16,                           # LoRA rank
    lora_alpha=32,                  # scaling factor
    target_modules=["q_proj", "v_proj"],  # which layers to adapt
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)

dataset = load_dataset("json", data_files=DATA_PATH, split="train")

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,  # effective batch = 16
    learning_rate=2e-4,
    fp16=True,
    logging_steps=10,
    save_strategy="epoch",
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=training_args,
    dataset_text_field="instruction",
    max_seq_length=512,
)

trainer.train()
trainer.save_model(OUTPUT_DIR)
print(f"Saved LoRA adapter to {OUTPUT_DIR}")
```

```bash
cd trading_bot
python scripts/finetune.py
```

Training takes **~1–3 hours** on a single A100/RTX 3090 for 500 samples with Llama 3 8B.

#### 3d. Verify the adapter

After training, `trading_bot/models/trading-lora-adapter/` should contain:

```
models/trading-lora-adapter/
├── adapter_config.json
├── adapter_model.safetensors
└── tokenizer_config.json
```

The bot will automatically load these weights on next startup.

---

## 7. Run the Bot

```bash
cd trading_bot

# Paper-trading mode (default – safe, no real orders)
python src/main.py

# Live trading (ensure PAPER_TRADING=false in .env and Kite creds are set)
python src/main.py
```

You should see structured log output like:

```
INFO  | Starting trading bot (paper=True)
INFO  | Redis connected at localhost:6379
WARNING | LLM model not found – using WAIT-only stub chain.
INFO  | Watchlist: {'RELIANCE': 0}
INFO  | ─── Processing RELIANCE ───
INFO  | [Node] fetch_market_state  –  RELIANCE
INFO  | [Node] technical_analysis
INFO  | [Node] llm_reasoning
INFO  | LLM decision: WAIT – Stub LLM – no model loaded.
INFO  | RELIANCE | action=WAIT | status=N/A | order_id=None
INFO  | Sleeping 60 seconds until next cycle...
```

### Run with Docker (full stack)

```bash
cd trading_bot
docker-compose up --build
```

This builds the bot image and starts Redis + TimescaleDB + the trading bot all together.

---

## 8. Run the Tests

```bash
cd trading_bot
python -m pytest tests/ -v
```

Expected output: **69 tests pass** covering technical indicators, risk guardrails, halt switch, position sizing, retry/backoff, market data batching, instruments cache, and portfolio wrappers.

Run a specific test file:
```bash
python -m pytest tests/test_risk_manager.py -v
python -m pytest tests/test_technical_analysis.py -v
python -m pytest tests/test_kite_data_layer.py -v
```

---

## 9. CLI Reference

```bash
# Start the trading loop (paper-trading by default)
python src/main.py

# Activate the manual kill switch (halts all trading immediately)
python src/main.py --kill

# Deactivate the kill switch (resume trading)
python src/main.py --unkill
```

The kill switch is also stored in:
- **Redis** key `trading:kill_switch` (if Redis is running)
- **File** `/tmp/trading_kill_switch` (always)

You can activate it from another terminal without restarting the bot:

```bash
touch /tmp/trading_kill_switch       # activate
rm   /tmp/trading_kill_switch        # deactivate
# or via redis-cli:
redis-cli set trading:kill_switch 1  # activate
redis-cli del trading:kill_switch    # deactivate
```

---

## 10. Troubleshooting

### `ModuleNotFoundError: No module named 'kiteconnect'`

```bash
pip install kiteconnect
```

### `ModuleNotFoundError: No module named 'langgraph'`

```bash
pip install langgraph langchain langchain-community
```

### Redis connection refused

```bash
# Check Redis is running
redis-cli ping

# Start Redis (native)
sudo systemctl start redis-server     # Linux
brew services start redis              # macOS

# Or use Docker
docker run -d -p 6379:6379 redis:7-alpine
```

The bot falls back gracefully if Redis is unavailable — you will see:
```
WARNING | Redis not available – using in-process state only.
```

### `CUDA out of memory` when loading the LLM

- Use 4-bit quantisation: ensure `load_in_4bit=True` is set (already the default in `src/main.py`).
- Switch to a smaller base model (e.g. `Qwen/Qwen2.5-1.5B-Instruct`).
- Use the stub LLM (Option 1) by removing the adapter directory.

### `bitsandbytes` install fails on macOS / Windows

`bitsandbytes` only supports Linux + NVIDIA CUDA. On macOS or Windows without an NVIDIA GPU:

```bash
# Comment out bitsandbytes in requirements.txt, then:
pip install -r trading_bot/requirements.txt

# And use the stub LLM (Option 1) – it works without bitsandbytes.
```

### Kite API: `Invalid api_key or access_token`

- Ensure `KITE_API_KEY` and `KITE_ACCESS_TOKEN` match a valid Kite session.
- Access tokens expire daily at midnight. Clear `KITE_ACCESS_TOKEN` in `.env` to force a fresh login.

### `KeyError: 'KITE_API_KEY'` when `PAPER_TRADING=true`

This should not happen — the bot skips Kite auth in paper-trading mode. If you see it, ensure `PAPER_TRADING=true` is set in your `.env` **and** that the `.env` file is in the `trading_bot/` directory.

### HuggingFace `OSError: You are trying to access a gated repo`

```bash
huggingface-cli login
# then accept the model licence at https://huggingface.co/meta-llama/Meta-Llama-3-8B
```

---

## Quick-Start Cheat Sheet

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r trading_bot/requirements.txt

# 2. Configure
cp trading_bot/.env.example trading_bot/.env
# Edit .env if needed (leave PAPER_TRADING=true for safe testing)

# 3. Start Redis (optional but recommended)
docker run -d -p 6379:6379 redis:7-alpine

# 4. Run
cd trading_bot
python src/main.py

# 5. Test
python -m pytest tests/ -v
```
