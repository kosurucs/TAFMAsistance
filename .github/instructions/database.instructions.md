---
description: "Use when writing or modifying SQL schema, TimescaleDB migrations, or database-related Python code (db_logger, psycopg2 calls). Covers table schemas, hypertable setup, and connection pooling."
applyTo: "trading_bot/scripts/*.sql"
---

# Database Conventions

## TimescaleDB Setup

- TimescaleDB runs in Docker via `trading_bot/docker-compose.yml` on port 5432.
- All time-series tables must be converted to hypertables on the `timestamp` column.
- Schema initialised by `trading_bot/scripts/init_db.sql` — run once on fresh setup.
- Connection: `DB_URL=postgresql://user:pass@localhost:5432/trading` (from `.env`)

## Required Tables

### `historical_ohlcv` — 20-year OHLCV store (Phase 1)

```sql
CREATE TABLE IF NOT EXISTS historical_ohlcv (
    id          BIGSERIAL,
    symbol      VARCHAR(20)  NOT NULL,
    interval    VARCHAR(10)  NOT NULL DEFAULT '1d',
    timestamp   TIMESTAMPTZ  NOT NULL,
    open        NUMERIC(12,4) NOT NULL,
    high        NUMERIC(12,4) NOT NULL,
    low         NUMERIC(12,4) NOT NULL,
    close       NUMERIC(12,4) NOT NULL,
    volume      BIGINT,
    created_at  TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (id, timestamp)
);
SELECT create_hypertable('historical_ohlcv', 'timestamp', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_historical_ohlcv_symbol_interval ON historical_ohlcv (symbol, interval, timestamp DESC);
```

### `trades` — every executed or paper trade (Phase 1+)

```sql
CREATE TABLE IF NOT EXISTS trades (
    id              BIGSERIAL PRIMARY KEY,
    order_id        VARCHAR(50),
    symbol          VARCHAR(20)  NOT NULL,
    action          VARCHAR(10)  NOT NULL,  -- BUY / SELL
    entry_price     NUMERIC(12,4),
    exit_price      NUMERIC(12,4),
    quantity        INTEGER,
    sl              NUMERIC(12,4),
    tp              NUMERIC(12,4),
    rr_ratio        NUMERIC(6,3),
    pnl             NUMERIC(12,4),
    scenario        VARCHAR(50),
    confidence      INTEGER,
    exit_reason     VARCHAR(100),
    paper_trade     BOOLEAN      DEFAULT TRUE,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    closed_at       TIMESTAMPTZ
);
```

### `market_snapshots` — per-interval indicator snapshots (Phase 2+)

```sql
CREATE TABLE IF NOT EXISTS market_snapshots (
    id          BIGSERIAL,
    symbol      VARCHAR(20)  NOT NULL,
    timeframe   VARCHAR(10)  NOT NULL,
    timestamp   TIMESTAMPTZ  NOT NULL,
    indicators  JSONB,
    scenarios   JSONB,
    PRIMARY KEY (id, timestamp)
);
SELECT create_hypertable('market_snapshots', 'timestamp', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_symbol ON market_snapshots (symbol, timestamp DESC);
```

## Python DB Access

- All database interaction goes through `trading_bot/src/utils/db_logger.py`.
- Use `psycopg2.pool.ThreadedConnectionPool` — never open/close connections per call.
- Connection pool: `minconn=2`, `maxconn=10`.
- Always use parameterised queries — never string-format SQL with user data.
- Wrap all DB calls in try/except and log failures with `logger.error` — never let DB failures crash the trading loop.

## DBLogger Integration (Phase 7)

- All database writes go through `trading_bot/src/utils/db_logger.py`.
- Key methods:
  - `log_trade_entry(order_id, symbol, action, entry_price, quantity, sl, tp, rr_ratio, scenario, confidence, paper_trade)`
  - `log_trade_exit(order_id, exit_price, pnl, exit_reason, closed_at)`
  - `log_market_snapshot(symbol, timeframe, timestamp, indicators, scenarios)`
- Uses `psycopg2.pool.ThreadedConnectionPool` (minconn=2, maxconn=10).
- Always wraps queries in try/except — logs errors but never crashes trading loop.
- Automatically called from `trading_agent.py` nodes: `execute_order`, `technical_analysis`.

## Data Retention

- `historical_ohlcv`: retain indefinitely (20+ years of data).
- `market_snapshots`: use TimescaleDB retention policy, keep 90 days by default.
- `trades`: retain indefinitely for performance analysis and LLM training data.
