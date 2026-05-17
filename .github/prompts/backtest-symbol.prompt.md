---
description: "Run a full multi-strategy backtest for a symbol and present an interpreted report with strategy recommendations, WHY-it-works attribution, and entry plan."
---

Run a full backtest for `${input:symbol}` and interpret the results.

## Steps

### 1. Trigger the Backtest

Call the backtest API:
```
POST /api/backtest/${input:symbol}?years=${input:years|20}
```

Capture the `job_id` from the response.

### 2. Poll for Completion

Poll `GET /api/backtest/status/{job_id}` every 5 seconds until `progress == 100`.
Show progress updates as you poll.

### 3. Fetch the Result

Call `GET /api/backtest/result/{job_id}` and retrieve the full `BacktestResult`.

### 4. Present the Strategy Matrix

Format a table showing all strategies × timeframes:

| Strategy | Timeframe | Win Rate | Avg R:R | Sharpe | Max DD | Best Period |
|----------|-----------|----------|---------|--------|--------|-------------|
| ... | ... | ...% | ...:1 | ... | ...% | ... |

Colour-code: ≥ 60% win rate = ✅, 45–60% = ⚠️, < 45% = ❌

### 5. WHY-It-Works Attribution

For the top 2 strategies, show the signal attribution breakdown:
```
TREND_FOLLOWING (1D):  Volume-driven 35% | EMA-confluence 42% | RSI-divergence 23%
Best: 2017–2019 (78% win rate) | Worst: 2020 COVID crash (31% win rate)
```

### 6. Recommendation

State clearly:
- **Best strategy** for `${input:symbol}`: name + timeframe
- **Recommended R:R**: historical average
- **Best entry timing**: daily / weekly / monthly / quarterly
- **When to AVOID**: which market conditions the strategy fails in

### 7. Entry Plan

Present the recommended entry plan:
```
Entry Zone  : [price range]
Stop Loss   : [price] (1.5 × ATR below entry)
Take Profit : [price] (3.0 × ATR above entry)
Timeframe   : [best timeframe]
Win Rate    : [%]
Avg R:R     : [ratio]
```

### 8. Sync

After presenting results, note whether any new insights should be captured in `trading-domain.instructions.md` (e.g. a strategy that consistently underperforms for certain instrument types).
