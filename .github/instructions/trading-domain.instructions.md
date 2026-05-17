---
description: "Use when writing trading logic, strategy rules, risk management, technical indicators, LangGraph nodes, backtesting, or market data code. Covers Indian market conventions, R:R rules, scenario gates, and strategy definitions."
applyTo: "trading_bot/**"
---

# Trading Domain Rules

## Risk / Reward — Non-Negotiable

- Every trade must have R:R ≥ 1:2 before entry is allowed.
- Standard calculation:
  - `SL = entry_price - 1.5 * ATR(14)` for BUY
  - `TP = entry_price + 3.0 * ATR(14)` for BUY
  - Invert signs for SELL
- If `(TP - entry) / (entry - SL) < 2.0` → force `action = WAIT`.
- Never override the R:R gate with a comment or flag.

## Scenario Confidence Gate

- The dominant scenario must have probability ≥ 60% before a trade is entered.
- `ScenarioEngine.get_trade_bias(threshold=0.60)` returns `"WAIT"` below threshold.
- Scenario probabilities come from indicator confluence — never hardcode.

## Position Sizing & Daily Loss

- Max position per trade: 5% of `opening_capital` (`MAX_POSITION_SIZE_PCT = 0.05`).
- Max daily loss: 2% of `opening_capital` (`MAX_DAILY_LOSS_PCT = 0.02`).
- Both limits are enforced by `RiskManager.validate_order()`.

## Kill-Switch (3-tier)

1. In-process `_killed` flag — set by `activate_kill_switch()`
2. Redis key `trading:kill_switch`
3. Flag file at `Path(tempfile.gettempdir()) / "trading_kill_switch"`

Never remove any of these three tiers. Always check `is_kill_switch_active()` before placing an order.

## Four Strategy Families

| Strategy | Entry Trigger | Key Indicators |
|----------|--------------|----------------|
| TREND_FOLLOWING | EMA9 crosses above EMA21 with MTF confluence ≥ 3/4 | EMA9, EMA21, EMA50, EMA200, volume |
| MEAN_REVERSION | RSI < 30 + price at/below BB lower band | RSI(14), BB(20,2), ATR |
| MOMENTUM | MACD histogram turns positive + volume > 1.5× avg | MACD(12,26,9), volume, Stochastic |
| PRICE_ACTION | Hammer/engulfing at support with above-avg volume | Candlestick pattern, VWAP, volume |

## Multi-Timeframe Confluence

- Use 4 timeframes: 1m (entry timing), 15m (short trend), 1h (medium trend), 1D (macro trend).
- Confluence score: +1 for each timeframe where EMA9 > EMA21 (max 4 = all bullish).
- Only TREND_FOLLOWING entries require confluence ≥ 3/4. Other strategies require ≥ 2/4.

## Five Scenario Types

| Scenario | Conditions |
|----------|-----------|
| BULLISH_BREAKOUT | RSI > 60, MACD bullish, EMA trend BULLISH, price > BB middle |
| BEARISH_BREAKDOWN | RSI < 40, MACD bearish, EMA trend BEARISH, price < BB middle |
| SIDEWAYS_CONSOLIDATION | RSI 40–60, MACD near zero, price between BB bands |
| REVERSAL_UP | RSI < 30 (oversold), price at/below BB lower, volume spike |
| REVERSAL_DOWN | RSI > 70 (overbought), price at/above BB upper, volume spike |

## Exit Rules (Phase 6)

6 exit conditions monitored every 30 seconds by `ExitMonitor`:

| Rule | Trigger | Action |
|------|---------|--------|
| TP_HIT | Current price ≥ TP (BUY) or ≤ TP (SELL) | Exit at market |
| SL_HIT | Current price ≤ SL (BUY) or ≥ SL (SELL) | Exit at market |
| TRAILING_STOP | Price moves 2×ATR in favor, then reverses 1×ATR | Exit at market |
| TIME_DECAY | Position held > 24 hours with P&L < 0 | Exit at market |
| MTF_REVERSAL | 3+ timeframes flip trend direction | Exit at market |
| KILL_SWITCH | Kill-switch activated | Exit all positions |

- Exit monitor runs in `monitor_positions()` coroutine in `main.py`.
- All exits logged via `DBLogger.log_trade_exit(exit_reason="...")`.

## Indian Market Conventions

- Market hours: **09:15–15:30 IST** (UTC+5:30)
- All log timestamps and UI display must be in IST.
- Exchange: `NSE` (primary), `BSE` (secondary)
- NSE symbol format for Kite: `RELIANCE` (no prefix, no `.NS`), instrument token lookup via `InstrumentsCache`.
- yfinance symbol format: `RELIANCE.NS` (append `.NS` for NSE, `.BO` for BSE)
- Indices: Nifty 50 = `^NSEI` (yfinance) / `NSE:NIFTY 50` (Kite); Sensex = `^BSESN` / `BSE:SENSEX`

## Technical Indicators Reference

| Indicator | Parameters | Library |
|-----------|-----------|---------|
| RSI | period=14 | pandas_ta |
| EMA | fast=9, slow=21, mid=50, long=200 | pandas_ta |
| Bollinger Bands | period=20, std=2.0 | pandas_ta |
| MACD | fast=12, slow=26, signal=9 | pandas_ta |
| ATR | period=14 | pandas_ta |
| Stochastic | k=14, d=3 | pandas_ta |
| VWAP | intraday only | pandas_ta |

All indicator computation goes through `trading_bot/src/utils/technical_analysis.py`.

## Backtesting Methodology (Phase 8)

- Backtester runs on historical OHLCV data from `historical_ohlcv` table or yfinance.
- 4 strategy families supported: TREND_FOLLOWING, MEAN_REVERSION, MOMENTUM, PRICE_ACTION.
- Each strategy has entry/exit rules defined in `Backtester.strategies` dict.
- WHY-it-works attribution: analyzes winning trades to identify dominant patterns (e.g., "70% of wins came from EMA9 > EMA21 crossovers in uptrends").
- Metrics: total trades, win rate, total P&L, max drawdown, Sharpe ratio (annualized).
- Results cached in-memory with `run_id` (UUID).
- CLI: `python scripts/run_backtest.py --symbol RELIANCE --years 3 --strategy TREND_FOLLOWING`

## LLM Output Contract

The LLM must return:
```json
{"action": "BUY|SELL|WAIT", "reason": "one sentence", "confidence": 0-100, "suggested_sl": 0.0, "suggested_tp": 0.0}
```
Any deviation → treat as `WAIT`. Do not add new fields without updating all consumers.
