-- TimescaleDB schema initialisation
-- This script runs automatically when the Docker container starts for the first time.

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Trade execution log
CREATE TABLE IF NOT EXISTS trade_log (
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT        NOT NULL,
    action      TEXT        NOT NULL,   -- BUY | SELL | WAIT
    quantity    INTEGER,
    price       NUMERIC(12, 2),
    order_id    TEXT,
    is_paper    BOOLEAN     DEFAULT TRUE,
    reasoning   TEXT,
    metadata    JSONB
);

SELECT create_hypertable('trade_log', 'time', if_not_exists => TRUE);

-- Daily P&L snapshot
CREATE TABLE IF NOT EXISTS daily_pnl (
    time        TIMESTAMPTZ NOT NULL,
    capital     NUMERIC(14, 2),
    realised_pnl NUMERIC(14, 2),
    unrealised_pnl NUMERIC(14, 2),
    kill_switch_triggered BOOLEAN DEFAULT FALSE
);

SELECT create_hypertable('daily_pnl', 'time', if_not_exists => TRUE);

-- Historical OHLCV data (TimescaleDB hypertable)
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

-- Trade log (enhanced for Phase 1+)
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

-- Market snapshots (per-minute indicator snapshots)
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
