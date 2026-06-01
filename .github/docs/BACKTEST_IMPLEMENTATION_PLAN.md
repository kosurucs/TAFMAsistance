# Backtest Implementation Plan
# Indian Multi-Segment Backtesting Engine
# Status: PLAN — NOT IMPLEMENTED — REVIEW BEFORE PROCEEDING

---

## 1. Current State Audit (What Exists Today)

### ✅ What Works
| Component | File | Status |
|-----------|------|--------|
| Core backtester | `trading_bot/src/utils/backtester.py` | Working — 4 strategies, 3 timeframes |
| API endpoint | `trading_bot/src/api/routers/backtest.py` | Working — async job, poll pattern |
| Historical data | `trading_bot/src/tools/historical_data.py` | Working — yfinance, NSE only (.NS suffix) |
| Technical indicators | `trading_bot/src/utils/technical_analysis.py` | Working — RSI/EMA/BB/MACD/ATR via pandas_ta |
| UI page | `trading_ui/src/pages/Backtest.jsx` | Working — toolbar, strategy picker, results table |
| R:R calculator | `trading_bot/src/utils/rr_calculator.py` | Working — enforces 1:2 minimum gate |

### ❌ What Is Missing / Broken
| Gap | Impact | Priority |
|-----|--------|----------|
| Only NSE equity — no BSE, no F&O, no commodity | Can't backtest NIFTY options, MCX Gold, BSE mid-cap | HIGH |
| No walk-forward validation | Curve-fit risk on full 20-year history | HIGH |
| No commission/STT/slippage model | Win rates inflated by ~2-3% | HIGH |
| Hardcoded EMA(9/21), ATR(1.5x/3.0x) | No parameter optimization per symbol | MEDIUM |
| No expiry/rollover logic for F&O | Cannot backtest options or futures accurately | MEDIUM |
| Single-segment data fetch (_nse_to_yfinance_symbol only adds .NS) | BSE, MCX, CDS symbols silently fail | HIGH |
| No segment selector in UI | User cannot choose Equity / F&O / Commodity | HIGH |
| In-memory job store (_jobs dict) | Job results lost on server restart | LOW |

---

## 2. Segment Coverage — What We Need to Support

### Indian Market Segments
```
NSE Equity       → RELIANCE, TCS, HDFCBANK  → yfinance: RELIANCE.NS
BSE Equity       → 500325, 532540           → yfinance: 500325.BO
NSE Indices      → NIFTY50, BANKNIFTY       → yfinance: ^NSEI, ^NSEBANK
BSE Indices      → SENSEX                   → yfinance: ^BSESN
NSE F&O (Futures)→ NIFTY24DECFUT           → Kite Connect (yfinance has limited F&O)
NSE F&O (Options)→ NIFTY24DEC24000CE       → Kite Connect only (no yfinance)
MCX Commodity    → GOLD, SILVER, CRUDEOIL  → yfinance: GC=F (Gold futures, USD)
NSE CDS (Currency)→ USDINR, EURINR         → yfinance: INR=X (limited)
```

### Data Source Decision Matrix
| Segment | Source | Suffix / Format | Supported? |
|---------|--------|-----------------|------------|
| NSE Equity | yfinance | `SYMBOL.NS` | ✅ Current |
| BSE Equity | yfinance | `ISIN.BO` or `SYMBOL.BO` | 🔴 Add |
| NSE Index | yfinance | `^NSEI`, `^NSEBANK` | ✅ Current (INDEX_SYMBOLS dict) |
| BSE Index (SENSEX) | yfinance | `^BSESN` | ✅ Current |
| NSE Futures | Kite Connect | `NFO:NIFTY24DECFUT` | 🔴 Add (post-login) |
| NSE Options | Kite Connect | `NFO:NIFTY...CE/PE` | 🔴 Add (complex — expiry aware) |
| MCX Commodity | yfinance (proxy) | `GC=F`, `SI=F`, `CL=F` | 🔴 Add (USD proxy) |
| NSE CDS (Forex) | yfinance | `USDINR=X` | 🔴 Add |

---

## 3. Chosen Backtesting Approach

### Decision: Enhance Custom Engine (Do NOT switch to backtrader/vectorbt)

**Rationale:**
- Your `backtester.py` is already integrated with `compute_indicators()`, `rr_calculator.py`, and the LangGraph agent
- backtrader uses GPL-3 — not compatible with a commercial product intent
- vectorbt is Apache 2.0 + Commons Clause — cannot sell the product
- Your engine enforces domain rules (R:R ≥ 1:2, scenario gate) that would need re-wiring in external libs
- yfinance provides 20+ years of free data for NSE/BSE equity — sufficient for backtesting

### Backtesting Method: Event-Driven with Walk-Forward Validation
```
Full history split:
├── Training window  : first 75% of data  (strategy signal generation)
├── Out-of-sample    : last 25% of data   (validation — never seen during optimization)
└── Walk-forward     : rolling 1-year windows (WFO for robustness)
```

### Commission Model (NSE/BSE Reality)
```
Equity Intraday:    0.03% brokerage + 0.025% STT (sell) + 0.00345% exchange + 18% GST on brokerage
Equity Delivery:    0.03% brokerage + 0.1% STT (both sides) + 18% GST
F&O (Futures):      0.03% brokerage + 0.0125% STT (sell) + 0.002% exchange
Commodity (MCX):    0.03% brokerage + STT exempt + 0.003% exchange
Slippage model:     0.05% default (half spread), configurable per segment
```

---

## 4. What Will Be Built — File-by-File Plan

### Phase A: Data Layer Expansion (Backend)
```
MODIFY  trading_bot/src/tools/historical_data.py
        — Add BSE suffix logic (.BO)
        — Add MCX/CDS proxy symbols mapping
        — Add segment parameter: "NSE" | "BSE" | "NFO" | "MCX" | "CDS"
        — Add Kite-based F&O fetch (with login guard)

CREATE  trading_bot/src/tools/segment_registry.py   ← NEW
        — SegmentRegistry class
        — Maps (symbol, exchange, segment) → correct yfinance ticker or Kite token
        — Knows lot sizes for F&O (NIFTY lot = 50, BANKNIFTY lot = 15, etc.)
        — Knows MCX units (Gold = 1g, CRUDEOIL = 100 bbl)
```

### Phase B: Commission Engine (Backend)
```
CREATE  trading_bot/src/utils/commission.py   ← NEW
        — CommissionCalculator class
        — calculate(segment, trade_type, turnover) → total_cost_inr
        — Segments: EQUITY_INTRADAY, EQUITY_DELIVERY, FNO_FUTURES, FNO_OPTIONS, MCX, CDS
        — Used inside Backtester._compute_report() for realistic PnL
```

### Phase C: Walk-Forward Validation (Backend)
```
MODIFY  trading_bot/src/utils/backtester.py
        — Add WalkForwardValidator class (inner)
        — run_walk_forward(df, n_splits=5) → list[WFOReport]
        — Split: TimeSeriesSplit from sklearn (or manual)
        — Each fold: train on 80%, test on 20%
        — Report OOS Sharpe, OOS Win Rate, Consistency Score
        — New dataclass: WFOReport with fold_results
```

### Phase D: Multi-Segment Strategy Rules (Backend)
```
MODIFY  trading_bot/src/utils/backtester.py
        — F&O strategies: delta-neutral, option premium decay, strangle/straddle
        — Commodity strategies: seasonal patterns (Gold pre-Diwali, CRUDEOIL rollover)
        — Currency: RBI intervention zones, INR range-bound mean reversion
        — Lot size–aware position sizing (replaces % capital model for F&O)

MODIFY  trading_bot/src/utils/risk_manager.py
        — Add F&O margin requirement checks
        — Add commodity lot size position sizing
```

### Phase E: API — Segment-Aware Endpoint (Backend)
```
MODIFY  trading_bot/src/api/routers/backtest.py
        — Add `exchange` param: "NSE" | "BSE" | "NFO" | "MCX" | "CDS"
        — Add `segment` param: "EQUITY" | "FUTURES" | "OPTIONS" | "COMMODITY" | "CURRENCY"
        — Route data fetch through SegmentRegistry
        — Route commission calculation through CommissionCalculator
        — Persist job results to TimescaleDB (replace in-memory _jobs dict)
```

### Phase F: UI — Segment Selector & Enhanced Results (Frontend)
```
MODIFY  trading_ui/src/pages/Backtest.jsx
        — Add Exchange selector: NSE | BSE | NFO | MCX | CDS
        — Add Segment selector: Equity | Futures | Options | Commodity | Currency
        — Show commission impact in results (gross PnL vs net PnL)
        — Show walk-forward OOS score badge

MODIFY  trading_ui/src/services/api.js
        — Update startBacktest() to pass exchange + segment params

CREATE  trading_ui/src/features/backtest/WalkForwardChart.jsx   ← NEW
        — Visualize OOS vs in-sample performance per fold
        — Bar chart: fold 1-5, each bar = OOS Sharpe

CREATE  trading_ui/src/features/backtest/CommissionBreakdown.jsx   ← NEW
        — Shows gross vs net PnL
        — Lists STT, brokerage, exchange fees, GST
```

---

## 5. File Dependency Graph

```
segment_registry.py
    ↓ used by
historical_data.py  →  backtester.py  →  backtest.py (router)  →  Backtest.jsx
    ↑                       ↑
commission.py ──────────────┘
    (PnL adjustment)
```

---

## 6. What Does NOT Change

- `rr_calculator.py` — R:R ≥ 1:2 gate stays exactly as-is
- `technical_analysis.py` — indicators unchanged (same for all segments)
- Kill-switch logic — untouched
- Order placement remains disabled (HTTP 403)
- `HistoricalDataManager.NIFTY50_SYMBOLS` — keep as-is, extend don't replace

---

## 7. Segment-Specific Strategy Rules (Summary)

### NSE/BSE Equity (current + enhanced)
- Trend Following: EMA9/21 crossover + volume (existing)
- Mean Reversion: RSI + Bollinger Bands (existing)
- Momentum: RSI 50-70 + MACD + EMA200 (existing)
- Price Action: Hammer/Engulfing patterns (existing)
- **NEW**: Sector rotation — compare scrip to index (Nifty 50)

### NSE F&O Futures
- **NEW**: Carry trade (spot-future basis narrowing)
- **NEW**: Rollover arbitrage (near vs far month)
- **NEW**: Index futures vs options premium parity
- Uses lot size for position sizing (no % capital model)

### MCX Commodity
- **NEW**: Gold seasonal (Oct–Nov Diwali demand, pre-Budget)
- **NEW**: Crude oil rollover (last Thursday before expiry)
- **NEW**: Silver/Gold ratio mean reversion
- MCX session: 09:00–23:30 IST (different from equity)

### NSE CDS (Currency)
- **NEW**: USDINR range-bound (RBI intervention at key levels)
- **NEW**: Cross-currency carry (EURINR vs USDINR)

---

## 8. Implementation Order (Suggested)

```
Step 1  →  commission.py           (standalone, no deps, easy to test)
Step 2  →  segment_registry.py     (standalone lookup table)
Step 3  →  historical_data.py      (add BSE/MCX/CDS fetch using registry)
Step 4  →  backtester.py           (walk-forward + commission integration)
Step 5  →  backtest.py (router)    (segment params + DB persistence)
Step 6  →  Backtest.jsx + api.js   (UI segment selectors)
Step 7  →  WalkForwardChart.jsx    (visualization)
Step 8  →  CommissionBreakdown.jsx (visualization)
```

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| F&O data unavailable without Kite login | Fall back to NSE equity only; show "Login required for F&O" message |
| MCX yfinance proxies are in USD not INR | Apply USD→INR conversion using USDINR=X rate; note in UI |
| BSE symbols differ from NSE (name vs ISIN) | SegmentRegistry maps common names to both .NS and .BO tickers |
| Walk-forward splits produce too few trades | Minimum 20 trades per fold guard — skip fold if below threshold |
| In-memory job store loses results on restart | Phase E adds TimescaleDB persistence (backtest_jobs table) |

---

## 10. Empty Skeleton Files (Ready to Review)

The following files will be created as empty skeletons for your review:

```
trading_bot/src/utils/commission.py        ← Commission model
trading_bot/src/tools/segment_registry.py  ← Segment + symbol mapping
```

These are the two foundational files. Everything else builds on them.
All existing files will be modified, not replaced.

---

## STATUS: AWAITING YOUR APPROVAL BEFORE ANY IMPLEMENTATION
## Review this plan, confirm or adjust, then say "proceed with Step N"
