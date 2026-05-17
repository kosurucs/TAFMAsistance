---
description: "Add a new technical indicator to the trading system end-to-end: computation in technical_analysis.py, prompt integration, LangGraph state, and UI display."
---

Add the technical indicator `${input:indicatorName}` to the TAFM trading system.

## Steps

### 1. Implement the Indicator

Open `trading_bot/src/utils/technical_analysis.py`.

- Add the indicator computation inside `compute_indicators()` using `pandas_ta`.
- Add a new constant for the period (e.g. `WILLIAMS_PERIOD: int = 14`) near the top of the file.
- Store the latest value in the returned dict with a clear key (e.g. `"williams_r": float`).
- Handle NaN safely using `_safe_float()`.
- Add a classifier function `_classify_<name>()` if the indicator has discrete signal states (overbought/oversold/neutral).
- Add the signal key to the returned dict (e.g. `"williams_signal": str`).

### 2. Add to the LLM Prompt

In `format_market_state_prompt()`:
- Add a new line showing the indicator value and signal.
- Follow the existing format: `f"  - {INDICATOR_NAME} : {indicators['key']:.2f} ({indicators['signal_key']})\n"`

### 3. Update TradingState (if needed)

If the indicator needs to be passed between nodes, add it to `TradingState` in `trading_bot/src/agents/trading_agent.py`.
Usually the full indicators dict is already passed so no change is needed.

### 4. Expose via API

In `trading_bot/src/api/routers/market.py`, verify the `/api/indicators` endpoint returns the new indicator key.
No change is usually needed since it returns the full indicators dict.

### 5. Display in UI

In `trading_ui/src/features/analysis/IndicatorPanel.jsx`:
- Add a row for the new indicator.
- Use the existing row pattern: label + value + optional signal badge.
- Badge colour: green for bullish signal, red for bearish, grey for neutral.
- All colours via CSS vars: `var(--color-up)`, `var(--color-down)`, `var(--color-neutral)`.

### 6. Sync Docs

After completing all changes, run the `doc-sync` subagent to update `trading-domain.instructions.md`
with the new indicator in the Technical Indicators Reference table.

## Validation

- `cd trading_bot && pytest tests/test_technical_analysis.py -v` — all tests pass.
- Add a test in `test_technical_analysis.py` for the new indicator: verify it returns a float, not NaN, on valid OHLCV input.
