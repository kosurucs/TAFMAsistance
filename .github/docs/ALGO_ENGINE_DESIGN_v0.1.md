# Algo Engine — Complete Design Roadmap

> **Status legend**
> - ✅ Already built and working
> - 🔧 Partially built — needs wiring
> - ❌ Not yet built — must be created

---

## 1. Overview

The Algo Engine runs a **6-stage pipeline** per symbol, per cycle. The current
codebase completes Stages 1–4 (signal discovery and validation). This roadmap
documents the full flow through Stage 6 (trade close + P&L) so all six stages
are end-to-end connected via the Kite Connect API.


```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ALGO ENGINE — FULL PIPELINE                       │
│                                                                          │
│  Trigger (manual click / scheduler tick every 120 s)                     │
│         │                                                                │
│  STAGE 1 ─ Data Ingestion ✅                                             │
│         │  lookup_instrument_token → get_ohlcv_df (60d daily)            │
│         ▼                                                                │
│  STAGE 2 ─ Indicator + Scenario ✅                                       │
│         │  compute_indicators() → ScenarioEngine.score_scenarios()       │
│         ▼                                                                │
│  STAGE 3 ─ Strategy Evaluation ✅                                        │
│         │  evaluate_all() → list[AlgoSignal]                             │
│         ▼                                                                │
│  STAGE 4 ─ Pre-Execution Checklist ✅                                    │
│         │  confidence ≥ 60%, R:R ≥ 2.0, kill-switch off,                │
│         │  market hours, daily-loss limit                                │
│         ▼                                                                │
│  STAGE 5 ─ Order Execution 🔧                                            │
│         │  RiskManager.calculate_quantity()                              │
│         │  KiteOrderManager.place_order() [entry + SL bracket order]     │
│         │  Store ActivePosition in position registry                     │
│         ▼                                                                │
│  STAGE 6 ─ Position Monitoring + Close ❌                                │
│         │  Poll price every 30 s                                         │
│         │  ExitMonitor.should_exit() — 6 exit rules                      │
│         │  If exit triggered → KiteOrderManager.place_order() [close]   │
│         │  Record P&L, update RiskManager daily-loss counter             │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. File Map — What Exists vs What Is Needed

### Backend

| File | Status | Purpose |
|------|--------|---------|
| `src/utils/algo_strategies.py` | ✅ | 4 strategy classes, `AlgoSignal`, `STRATEGY_REGISTRY` |
| `src/utils/algo_engine.py` | ✅ | `EngineState`, `run_cycle()`, checklist, scheduler loop |
| `src/api/routers/algo.py` | ✅ | 6 REST endpoints at `/algo/*` |
| `src/utils/technical_analysis.py` | ✅ | `compute_indicators()` — full indicator dict |
| `src/utils/scenario_engine.py` | ✅ | `ScenarioEngine.score_scenarios()` |
| `src/utils/rr_calculator.py` | ✅ | `calculate_sl_tp()` — SL/TP from ATR (R:R ≥ 2.0 gate) |
| `src/utils/risk_manager.py` | ✅ | Kill-switch (3-tier), daily-loss gate, `calculate_quantity()` |
| `src/utils/exit_monitor.py` | ✅ | `ExitMonitor.should_exit()` — 6 exit conditions |
| `src/tools/kite_tools.py` | ✅ | `KiteOrderManager.place_order()` — live + paper mode |
| `src/tools/data_pipeline.py` | ✅ | `DataPipeline.get_ohlcv_df()` |
| `src/utils/position_manager.py` | ❌ | `ActivePosition` registry + P&L tracker |
| `src/utils/position_monitor_loop.py` | ❌ | Async polling loop → ExitMonitor → close order |
| `src/api/routers/positions.py` | ❌ | `/positions/*` REST endpoints for UI |

### Frontend

| File | Status | Purpose |
|------|--------|---------|
| `src/pages/Algo.jsx` | ✅ | Main page layout (4-panel grid) |
| `src/features/algo/AlgoEngine.jsx` | ✅ | Engine Status + Run button |
| `src/features/algo/StrategyConfig.jsx` | ✅ | Strategy list + toggle buttons |
| `src/features/algo/SignalFeed.jsx` | ✅ | Live signal cards |
| `src/features/algo/ExecutionReport.jsx` | ✅ | Checklist table per signal |
| `src/features/algo/OpenPositions.jsx` | ❌ | Active trade cards (entry, SL, TP, current P&L) |
| `src/features/algo/TradeHistory.jsx` | ❌ | Closed trade log with P&L |
| `src/services/api.js` | 🔧 | Needs 4 new position API functions added |

---

## 3. Full Data Flow — One Cycle With Execution

```
POST /algo/run  (or scheduler tick)
        │
        │  symbols = watchlist || body.symbols
        │
        ▼
┌─ STAGE 1 + 2 ─────────────────────────────────────────────────────────────┐
│  for each symbol:                                                          │
│    token  = fetcher.lookup_instrument_token(exchange, symbol)              │
│    df     = pipeline.get_ohlcv_df(token, symbol, "day", 60)               │
│    indic  = compute_indicators(df)           ← full indicator dict        │
│    sc     = ScenarioEngine().score_scenarios(indic)  ← dominant + conf%   │
└────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ STAGE 3 ─────────────────────────────────────────────────────────────────┐
│  signals = evaluate_all(symbol, indic, sc.dominant.name, sc.confidence)   │
│  → each strategy checks its own conditions and returns AlgoSignal or None │
└────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ STAGE 4 — Pre-Execution Checklist ────────────────────────────────────────┐
│  for each signal in signals:                                               │
│    checklist = run_checklist(signal, risk_mgr)                             │
│    ┌──────────────────────────────────────────────────────┐               │
│    │  1. market_hours          09:15–15:30 IST Mon–Fri    │               │
│    │  2. kill_switch_off       3-tier check               │               │
│    │  3. rr_ratio_ok           signal.rr_ratio ≥ 2.0      │               │
│    │  4. scenario_confidence   sc.confidence ≥ 60%        │               │
│    │  5. daily_loss_ok         current P&L within limit   │               │
│    │  6. valid_price           entry_price > 0            │               │
│    │  7. execution_note        always False (audit trail) │               │
│    └──────────────────────────────────────────────────────┘               │
│    if items 1-6 all True → signal.checklist_pass = True                   │
└────────────────────────────────────────────────────────────────────────────┘
        │
        │  signal.checklist_pass == True ?
        ├─── NO  → log signal as recommendation only, skip execution
        │
        └─── YES ▼
┌─ STAGE 5 — Order Execution 🔧 ─────────────────────────────────────────────┐
│  qty = risk_mgr.calculate_quantity(signal.entry_price)                     │
│     = floor( opening_capital × 5% / entry_price )                         │
│                                                                            │
│  order_id = order_manager.place_order(                                     │
│      tradingsymbol = signal.symbol,                                        │
│      exchange      = "NSE",                                                │
│      transaction_type = signal.action,   # "BUY" or "SELL"                │
│      quantity      = qty,                                                  │
│      order_type    = "MARKET",                                             │
│      product       = "MIS",              # intraday                        │
│  )                                                                         │
│                                                                            │
│  position = ActivePosition(                                                │
│      order_id    = order_id,                                               │
│      signal_id   = signal.id,                                              │
│      symbol      = signal.symbol,                                          │
│      action      = signal.action,                                          │
│      entry_price = signal.entry_price,                                     │
│      sl          = signal.suggested_sl,                                    │
│      tp          = signal.suggested_tp,                                    │
│      atr         = indic["atr"],                                           │
│      quantity    = qty,                                                    │
│      opened_at   = now_ist(),                                              │
│  )                                                                         │
│  PositionManager.add(position)                                             │
└────────────────────────────────────────────────────────────────────────────┘
        │
        └─── spawns monitoring task ▼
┌─ STAGE 6 — Position Monitoring + Close ❌ ─────────────────────────────────┐
│  monitor_loop runs every 30 s (async):                                     │
│    current_price = fetcher.get_quote(["NSE:" + symbol])[last_price]        │
│    exit_sig = ExitMonitor().should_exit(                                   │
│        action, entry_price, current_price,                                 │
│        sl, tp, atr, volume, avg_volume,                                    │
│        nifty_change_pct, beta, rsi                                         │
│    )                                                                       │
│                                                                            │
│    if exit_sig.adjusted_sl:       # trailing stop activated                │
│        position.sl = exit_sig.adjusted_sl                                  │
│                                                                            │
│    if exit_sig.should_exit:                                                │
│        close_order_id = order_manager.place_order(                         │
│            tradingsymbol = symbol,                                         │
│            transaction_type = "SELL" if action=="BUY" else "BUY",          │
│            quantity = position.quantity,                                   │
│            order_type = "MARKET",                                          │
│        )                                                                   │
│        pnl = (current_price - entry_price) * qty   # if BUY               │
│        risk_mgr.check_daily_loss(total_pnl + pnl)  # kill-switch if blown │
│        PositionManager.close(position, current_price, exit_sig.reason)    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Strategies

All four strategies inherit from `BaseStrategy` and implement `evaluate()`.

### 4.1 BullishBreakout ✅

**Direction:** BUY

| Condition | Required value |
|-----------|---------------|
| RSI | 55 ≤ RSI ≤ 75 |
| Price vs EMA50 | `close > ema_50` |
| MACD label | `"BUY"` or `"BULLISH"` |
| Trend | `"BULLISH"` |
| Scenario | `BULLISH_BREAKOUT` + confidence ≥ 60% |

Confidence: `min(95, 60 + scenario_confidence × 0.4)`

---

### 4.2 BearishBreakdown ✅

**Direction:** SELL

| Condition | Required value |
|-----------|---------------|
| RSI | 25 ≤ RSI ≤ 45 |
| Price vs EMA50 | `close < ema_50` |
| MACD label | `"SELL"` or `"BEARISH"` |
| Trend | `"BEARISH"` |
| Scenario | `BEARISH_BREAKDOWN` + confidence ≥ 60% |

Confidence: `min(95, 60 + scenario_confidence × 0.4)`

---

### 4.3 MeanReversionBuy ✅

**Direction:** BUY — oversold bounce, no scenario requirement.

| Condition | Required value |
|-----------|---------------|
| RSI | RSI < 30 |
| Stochastic %K | Stoch_K < 25 |
| Bollinger Band | `close ≤ BB_lower × 1.015` |

Confidence: `min(85, 55 + (30 − RSI) × 1.2)`

---

### 4.4 MomentumFollower ✅

**Direction:** BUY or SELL based on EMA stack alignment.

| Condition | BUY | SELL |
|-----------|-----|------|
| EMA stack | EMA9 > EMA21 > EMA50 | EMA9 < EMA21 < EMA50 |
| RSI | ≥ 45 | ≤ 55 |
| Scenario | `BULLISH_BREAKOUT` or `REVERSAL_UP` | `BEARISH_BREAKDOWN` or `REVERSAL_DOWN` |
| Scenario confidence | ≥ 65% | ≥ 65% |

Confidence: `min(90, 60 + scenario_confidence × 0.35)`

---

## 5. AlgoSignal — Data Contract ✅

```python
@dataclass
class AlgoSignal:
    id: str                    # 8-char UUID fragment
    symbol: str                # e.g. "RELIANCE"
    strategy: str              # e.g. "BullishBreakout"
    action: str                # "BUY" | "SELL"
    reason: str                # one-sentence explanation
    confidence: float          # 0–100
    entry_price: float         # close price at signal time
    suggested_sl: float        # entry − 1.5×ATR  (BUY) / entry + 1.5×ATR  (SELL)
    suggested_tp: float        # entry + 3.0×ATR  (BUY) / entry − 3.0×ATR  (SELL)
    rr_ratio: float            # reward / risk  ← must be ≥ 2.0
    checklist: dict            # {check_name: bool}  — 7 items
    checklist_pass: bool       # True only when items 1-6 all pass
    timestamp: str             # IST ISO-8601 string
    indicators: dict           # indicator snapshot at signal time
    scenario: str              # dominant scenario name
    scenario_confidence: float # 0–100
```

**R:R formula** (`rr_calculator.py`, hardcoded constants — not overridable):

$$SL_{BUY} = entry - 1.5 \times ATR \qquad TP_{BUY} = entry + 3.0 \times ATR$$

$$SL_{SELL} = entry + 1.5 \times ATR \qquad TP_{SELL} = entry - 3.0 \times ATR$$

$$R:R = \frac{|TP - entry|}{|entry - SL|} = \frac{3.0 \times ATR}{1.5 \times ATR} = 2.0$$

Additional gate: `SL must not exceed 3% loss from entry` (`MAX_SL_PCT = 0.03`).

---

## 6. Pre-Execution Checklist ✅

| # | Key | Pass condition | Blocks execution? |
|---|-----|---------------|-------------------|
| 1 | `market_hours` | 09:15–15:30 IST, Mon–Fri | Yes |
| 2 | `kill_switch_off` | All 3 kill-switch tiers inactive | Yes |
| 3 | `rr_ratio_ok` | `signal.rr_ratio >= 2.0` | Yes |
| 4 | `scenario_confidence` | `scenario_confidence >= 60` | Yes |
| 5 | `daily_loss_ok` | `check_daily_loss(pnl) == True` | Yes |
| 6 | `valid_price` | `entry_price > 0` | Yes |
| 7 | `execution_note` | **Always False** — audit trail only | No (excluded from pass calc) |

`checklist_pass = items 1–6 all True`.

---

## 7. Stage 5 — Order Execution Detail 🔧

### Position Sizing

```python
# risk_manager.py — already built
qty = risk_mgr.calculate_quantity(entry_price)
# = floor( opening_capital × max_position_size_pct / entry_price )
# = floor( 100_000 × 0.05  / entry_price )        # max 5% per trade
```

### Entry Order

```python
# kite_tools.py — KiteOrderManager.place_order() already built
order_id = order_manager.place_order(
    tradingsymbol    = symbol,          # e.g. "RELIANCE"
    exchange         = "NSE",
    transaction_type = signal.action,   # "BUY" or "SELL"
    quantity         = qty,
    order_type       = "MARKET",        # immediate fill
    product          = "MIS",           # intraday (auto-squared off at 15:15)
    tag              = f"algo_{signal.id}",
)
```

### ActivePosition (to be created)

```python
# src/utils/position_manager.py — NOT YET BUILT
@dataclass
class ActivePosition:
    order_id: str
    signal_id: str
    symbol: str
    action: str          # "BUY" | "SELL"
    entry_price: float
    sl: float            # updated by trailing stop
    tp: float
    atr: float
    quantity: int
    opened_at: str       # IST ISO string
    # populated on close:
    closed_at: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0
    status: str = "OPEN"  # "OPEN" | "CLOSED"
```

---

## 8. Stage 6 — Position Monitoring + Exit Detail ❌

### ExitMonitor Rules (already in `exit_monitor.py`) ✅

| Priority | Condition | Exit type |
|----------|-----------|-----------|
| 1 | `BUY: current_price ≤ SL` | IMMEDIATE — stop-loss hit |
| 2 | `BUY: current_price ≥ TP` | IMMEDIATE — take-profit hit |
| 3 | `SELL: current_price ≥ SL` | IMMEDIATE — stop-loss hit |
| 4 | `SELL: current_price ≤ TP` | IMMEDIATE — take-profit hit |
| 5 | `volume < 0.5 × avg_volume` | IMMEDIATE — illiquidity risk |
| 6 | `nifty_change < −1.5% AND beta > 1.2` | IMMEDIATE — market crash |
| 7 | `BUY price > entry + 2×ATR` | MONITOR — raise SL to entry+ATR (trailing) |
| 8 | `BUY: RSI > 75` | MONITOR — weakening momentum advisory |

### Monitoring Loop (to be built)

```python
# src/utils/position_monitor_loop.py — NOT YET BUILT
async def _monitor_position(position: ActivePosition, fetcher, order_manager, risk_mgr):
    POLL_SECONDS = 30
    exit_mon = ExitMonitor()

    while position.status == "OPEN":
        await asyncio.sleep(POLL_SECONDS)

        # Fetch live quote
        quote = fetcher.get_quote([f"NSE:{position.symbol}"])
        current = quote[f"NSE:{position.symbol}"]["last_price"]
        volume  = quote[f"NSE:{position.symbol}"]["volume"]

        # Fetch Nifty for market-crash check
        nifty   = fetcher.get_quote(["NSE:NIFTY 50"])
        nifty_chg = _nifty_change_pct(nifty)

        # Re-compute RSI from latest data
        indicators = _latest_indicators(position.symbol, fetcher)
        rsi = indicators.get("rsi", 50)
        avg_vol = indicators.get("avg_volume", 0)

        exit_sig = exit_mon.should_exit(
            action         = position.action,
            entry_price    = position.entry_price,
            current_price  = current,
            sl             = position.sl,
            tp             = position.tp,
            atr            = position.atr,
            volume         = volume,
            avg_volume     = avg_vol,
            nifty_change_pct = nifty_chg,
            beta           = 1.0,    # from fundamentals (future enhancement)
            rsi            = rsi,
        )

        if exit_sig.adjusted_sl:
            position.sl = exit_sig.adjusted_sl   # trailing stop update

        if exit_sig.should_exit:
            _close_position(position, current, exit_sig.reason,
                            order_manager, risk_mgr)
            break
```

### Close Position

```python
def _close_position(position, exit_price, reason, order_manager, risk_mgr):
    close_txn = "SELL" if position.action == "BUY" else "BUY"
    order_manager.place_order(
        tradingsymbol    = position.symbol,
        exchange         = "NSE",
        transaction_type = close_txn,
        quantity         = position.quantity,
        order_type       = "MARKET",
        product          = "MIS",
        tag              = f"algo_exit_{position.signal_id}",
    )
    pnl = (exit_price - position.entry_price) * position.quantity
    if position.action == "SELL":
        pnl = -pnl

    position.exit_price  = exit_price
    position.exit_reason = reason
    position.pnl         = round(pnl, 2)
    position.closed_at   = now_ist()
    position.status      = "CLOSED"

    risk_mgr.check_daily_loss(PositionManager.total_pnl())  # may activate kill-switch
    logger.info(f"CLOSED {position.symbol} | {reason} | P&L={pnl:+.2f}")
```

---

## 9. Engine State ✅

Module-level singleton (`_state: EngineState`):

```python
@dataclass
class EngineState:
    running: bool          # True when background scheduler is active
    cycle_count: int       # total cycles completed
    last_run_ist: str      # ISO timestamp of last cycle
    last_error: str        # last error message (if any)
    interval_sec: int      # scheduler sleep interval (default 120s)
    watchlist: list[str]   # symbols passed to start_engine()
    signals: list[dict]    # ring buffer — newest first, max 200
    _task: Any             # asyncio.Task (background scheduler)
```

> **Note:** `watchlist` is only populated when `start_engine()` is called.
> Manual `POST /algo/run` uses the API-dependency watchlist but does not
> update `state.watchlist`.

---

## 10. REST API — Current ✅ + Planned ❌

### Existing (all working)

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/algo/status` | Engine state, cycle count, strategies list |
| `POST` | `/algo/run` | Trigger one cycle; returns signals |
| `GET`  | `/algo/signals?limit=50` | Recent signals from ring buffer |
| `GET`  | `/algo/strategies` | All strategies with enabled/disabled state |
| `POST` | `/algo/strategies/{name}/toggle` | Enable / disable a strategy |
| `DELETE` | `/algo/signals` | Clear the ring buffer |

### To Be Added (`src/api/routers/positions.py`) ❌

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/positions` | All active (open) positions |
| `GET`  | `/positions/history` | Closed trades with P&L |
| `POST` | `/positions/{id}/close` | Force-close a position immediately |
| `GET`  | `/positions/pnl` | Today's total realised + unrealised P&L |

---

## 11. Frontend — Component Tree

### Existing ✅

```
pages/Algo.jsx
└── layouts/AppLayout
    └── main
        ├── Header ("Algo Engine")
        └── 2-column grid
            ├── Left
            │   ├── AlgoEngine.jsx    ← cycles, watchlist, Run button
            │   └── StrategyConfig.jsx ← 4 strategies + toggle
            └── Right
                ├── SignalFeed.jsx     ← signal cards (action pill, confidence, SL/TP)
                └── ExecutionReport.jsx ← 7-item checklist table
```

### To Be Added ❌

```
pages/Algo.jsx  (add 3rd row below the 2-column grid)
└── main
    └── 2-column grid (row 2)
        ├── features/algo/OpenPositions.jsx
        │   └── for each open position:
        │       ├── Symbol + Action pill + Entry price
        │       ├── Live P&L (polled every 5s via GET /positions)
        │       ├── Current SL + TP (updated on trailing stop)
        │       ├── Time in trade
        │       └── [Force Close] button → POST /positions/{id}/close
        └── features/algo/TradeHistory.jsx
            └── for each closed trade:
                ├── Symbol + Action + Entry / Exit
                ├── P&L (green/red)
                ├── Exit reason (SL hit / TP hit / trailing / manual)
                └── Duration
```

---

## 12. Frontend — API Service Functions

### Existing (`api.js`) ✅

```javascript
getAlgoStatus()                         // GET  /algo/status
runAlgoCycle(body = {})                 // POST /algo/run
getAlgoSignals(limit = 50)              // GET  /algo/signals?limit=N
getAlgoStrategies()                     // GET  /algo/strategies
toggleAlgoStrategy(name)                // POST /algo/strategies/{name}/toggle
clearAlgoSignals()                      // DELETE /algo/signals
```

### To Be Added (`api.js`) ❌

```javascript
getOpenPositions()                      // GET  /positions
getTradeHistory()                       // GET  /positions/history
forceClosePosition(id)                  // POST /positions/{id}/close
getDailyPnl()                           // GET  /positions/pnl
```

---

## 13. Implementation Roadmap — Phase by Phase

### Phase A — Enable Execution (Wire Stage 5) 🔧

**Goal:** After checklist passes, actually place the order.

1. Create `src/utils/position_manager.py`
   - `ActivePosition` dataclass (see Section 7)
   - `PositionManager` singleton: `add()`, `close()`, `get_open()`, `get_history()`, `total_pnl()`

2. Modify `src/utils/algo_engine.py` → `run_cycle()`
   - After `sig.checklist_pass == True`: call `order_manager.place_order()`
   - Compute qty via `risk_mgr.calculate_quantity(signal.entry_price)`
   - Build `ActivePosition` and add to `PositionManager`

3. Update `src/api/routers/algo.py` → `algo_run()`
   - Pass `order_manager` as a dependency
   - Return `positions_opened` count in response

4. Set `PAPER_TRADING=false` in environment to route orders through Kite live API

---

### Phase B — Position Monitoring (Stage 6) ❌

**Goal:** Poll each open position every 30 s, apply exit rules, close when triggered.

1. Create `src/utils/position_monitor_loop.py`
   - `monitor_position(position, fetcher, order_manager, risk_mgr)` async function
   - Calls `ExitMonitor().should_exit()` with live quote data
   - On IMMEDIATE exit: calls `_close_position()`
   - On MONITOR with `adjusted_sl`: updates `position.sl` in registry

2. Modify `algo_engine.py` → when a position is opened, spawn monitoring task:
   ```python
   asyncio.get_event_loop().create_task(
       monitor_position(position, fetcher, order_manager, risk_mgr)
   )
   ```

3. Handle market-close auto-square-off (15:15 IST):
   - If `_market_open_ist()` returns False and position is still OPEN
   - Mark as `CLOSED` with reason `"Market close — auto square-off by broker"`
   - Do NOT place a redundant close order (Kite MIS products are auto-closed)

---

### Phase C — Positions REST API + UI ❌

**Goal:** Expose open positions and history via API; show them in the Algo page.

1. Create `src/api/routers/positions.py` with 4 endpoints (see Section 10)
2. Mount router in `src/ui_api.py`:
   ```python
   from src.api.routers import positions
   app.include_router(positions.router, tags=["Positions"])
   ```
3. Add proxy in `vite.config.js`: `'^/positions/'`
4. Build `OpenPositions.jsx` and `TradeHistory.jsx` (see Section 11)
5. Add 4 API functions in `api.js` (see Section 12)

---

## 14. Kill-Switch — 3-Tier Protection ✅

The kill-switch is checked at every checklist gate AND re-checked at every
monitoring poll. All three tiers are checked in priority order:

```
Tier 1 — In-process flag   risk_mgr._killed == True
          ↓ (if not set)
Tier 2 — Redis key         redis.get("trading:kill_switch") != None
          ↓ (if not set)
Tier 3 — Flag file         Path(tempfile.gettempdir()) / "trading_kill_switch"
```

**Automatic activation** when `check_daily_loss()` detects P&L ≤ −2% of
opening capital — all three tiers are set simultaneously.

**Manual activation** via `risk_mgr.activate_kill_switch()` or by creating
the flag file from any shell:
```bash
# Windows
echo 1 > %TEMP%\trading_kill_switch
# PowerShell
New-Item "$env:TEMP\trading_kill_switch" -ItemType File
```

---

## 15. Non-Functional Constraints

| Constraint | Value | Source |
|------------|-------|--------|
| Max signals in ring buffer | 200 (newest first) | `_MAX_SIGNALS = 200` |
| Scheduler interval | 120 s (env `ALGO_INTERVAL_SEC`) | `algo_engine.py` |
| Position monitor poll | 30 s | `position_monitor_loop.py` (to build) |
| Min OHLCV rows required | 20 candles | `algo_engine.py` |
| Historical window | 60 calendar days, `"day"` interval | `run_cycle()` |
| Max position size | 5% of opening capital per trade | `MAX_POSITION_SIZE_PCT = 0.05` |
| Max daily loss | 2% of opening capital | `MAX_DAILY_LOSS_PCT = 0.02` |
| SL max distance | 3% of entry price | `MAX_SL_PCT = 0.03` (rr_calculator) |
| Min R:R ratio | 2.0 | `MIN_RR_RATIO = 2.0` (rr_calculator) |
| Exchange | NSE (default) | configurable per request |
| Order type | MARKET (entry + exit) | `KiteOrderManager.place_order()` |
| Product | MIS (intraday) | auto square-off by broker at 15:15 IST |

---

## 16. Adding a New Strategy ✅

1. Open `trading_bot/src/utils/algo_strategies.py`
2. Add a class extending `BaseStrategy`:
   ```python
   class MyNewStrategy(BaseStrategy):
       name = "MyNewStrategy"
       description = "One-line description shown in the UI."
       enabled = True

       def evaluate(self, symbol, indicators, scenario, scenario_confidence):
           if not self.enabled:
               return None
           # ... check your conditions ...
           return _make_signal(symbol, self.name, "BUY", reason,
                               confidence, indicators, scenario, scenario_confidence)
   ```
3. Append to `STRATEGY_REGISTRY`:
   ```python
   STRATEGY_REGISTRY: list[BaseStrategy] = [
       BullishBreakoutStrategy(),
       BearishBreakdownStrategy(),
       MeanReversionBuyStrategy(),
       MomentumFollowerStrategy(),
       MyNewStrategy(),          # ← add here
   ]
   ```
4. No router or frontend changes needed — `evaluate_all()` and `GET /algo/strategies`
   pick it up automatically. Restart API (`uvicorn --reload` does this automatically).

---

## 17. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PAPER_TRADING` | `true` | `true` = KiteOrderManager simulates orders locally; `false` = live Kite API orders |
| `ALGO_INTERVAL_SEC` | `120` | Background scheduler sleep interval (seconds) |
| `WATCHLIST` | `RELIANCE` | Comma-separated default watchlist symbols |
| `OPENING_CAPITAL` | `100000` | Capital (INR) used by RiskManager for position sizing + daily-loss gate |
| `MAX_DAILY_LOSS_PCT` | `0.02` | Daily loss limit as fraction of opening capital (2%) |
| `MAX_POSITION_SIZE_PCT` | `0.05` | Max single-trade notional as fraction of capital (5%) |
| `KILL_SWITCH_FLAG` | `%TEMP%/trading_kill_switch` | Path for the Tier-3 kill-switch flag file |

