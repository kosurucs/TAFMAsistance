---
description: "Add a new trading strategy to the system end-to-end: scenario engine, backtester, LLM training rules, and UI display."
---

Add the trading strategy `${input:strategyName}` to the TAFM trading system.

## Steps

### 1. Define Strategy Entry/Exit Rules

Before writing code, clearly define:
- **Entry condition**: which indicators must be true (e.g. RSI < 30 AND price < BB lower)
- **Exit condition**: SL = entry − 1.5×ATR, TP = entry + 3×ATR (standard R:R rules apply)
- **Required timeframe**: 1m, 15m, 1h, 1D, or combination
- **Best market condition**: trending / ranging / breakout / reversal

### 2. Add to Scenario Engine

Open `trading_bot/src/utils/scenario_engine.py`.

- Add a new `SCENARIO_<NAME>` constant to the scenario names.
- Define the scoring conditions in `score_scenarios()`:
  - Each indicator that supports the scenario adds weighted probability.
  - Total weights per scenario must sum to 100 when all conditions are met.
- Add the new scenario to the return dict.

### 3. Add to Backtester

Open `trading_bot/src/utils/backtester.py`.

- Add the strategy to the `STRATEGY_FAMILIES` list.
- Implement `_run_<strategy_name>(symbol, df)` method returning list of trade signals.
- A trade signal: `{"entry_date", "exit_date", "entry_price", "exit_price", "rr", "pnl", "why_triggered": dict}`
- Register the method in `run_all_strategies()`.

### 4. Add Training Rules

Open `llm_training/scripts/7_generate_strategy_rules.py`.

- Add 50+ Q&A pairs for the new strategy covering:
  - When to enter (indicator conditions)
  - When to exit (SL/TP/technical exits)
  - Why the strategy works in certain market conditions
  - What to do when the strategy fails (stop loss, don't average down)
- Follow the Alpaca format.

### 5. Sync Docs

After completing, invoke the `doc-sync` agent. Also manually update the Four Strategy Families table in `trading-domain.instructions.md`.

## Validation

- `cd trading_bot && pytest tests/ -v` passes.
- `python scripts/run_backtest.py --symbol RELIANCE --strategies ${input:strategyName}` runs without error and produces a non-zero trade count.
- Verify win rate is > 40% on RELIANCE 5-year backtest before declaring the strategy viable.
