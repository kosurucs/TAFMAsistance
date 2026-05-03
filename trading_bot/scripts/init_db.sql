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
