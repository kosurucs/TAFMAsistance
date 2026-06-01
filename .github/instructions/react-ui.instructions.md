---
description: "Use when writing or modifying the React trading UI: JSX components, JavaScript hooks, CSS, services, store, pages, design-system primitives. Enforces design system, folder structure, and no-prop-drilling rules."
applyTo: "trading_ui/src/**/*.{jsx,js,css}"
---

# React UI Conventions

## Design System — Non-Negotiable

- **All colours, spacing, typography, and shadows must come from CSS custom properties** defined in `trading_ui/src/design-system/theme.css`.
- Never write raw hex values, px sizes, or font names in component files — reference `var(--token-name)` only.
- Token definitions live in `trading_ui/src/design-system/tokens.js` (JS) and are mirrored as CSS vars in `theme.css`.
- Primitive UI atoms (Button, Badge, Card, Modal, Spinner, Tooltip, Select, Input, Table, Tabs) live in `trading_ui/src/design-system/`. Use them — do not recreate styled equivalents in feature folders.

## Folder Structure

```
trading_ui/src/
├── design-system/         ← tokens.js, theme.css, primitive components
├── layouts/               ← AppLayout, Sidebar, Header, Toolbar
├── pages/                 ← Dashboard, Portfolio, Historical, Backtest, Simulate, LLMStudio
├── features/
│   ├── chart/             ← CandleChart (IST-aware)
│   ├── historical/        ← HistoricalDataTable (22-column analysis table)
│   ├── trading/           ← OrderModal, GTTModal, QuoteBar
│   ├── analysis/          ← IndicatorPanel, ScenarioPanel
│   ├── chat/              ← ChatPanel
│   ├── portfolio/         ← PortfolioPanel
│   ├── backtest/          ← BacktestPage, StrategyCard, PnLChart
│   └── simulate/          ← SimulatePage, SimulateParamsForm, SimulateResultBoard
├── hooks/                 ← useMarketData, useBacktest, useSimulation, useLLM
├── services/              ← api.js (all HTTP calls)
└── store/                 ← zustand slices
```

- Feature components go in `features/<domain>/` — not in a flat `components/` folder.
- Page-level components go in `pages/` — one file per page.

## HTTP Calls

- **All API calls must go through `trading_ui/src/services/api.js`**.
- Never call `axios` directly in a component or hook — import named functions from `api.js`.
- `api.js` exports: `fetchQuote`, `fetchOHLCV`, `fetchIndicators`, `runBacktest`, `getBacktestStatus`, `getBacktestResult`, `runSimulation`, `chatWithLLM`, `executeTrade`, `placeOrder`, `placeGTT`, `getPositions`, `getHoldings`, `getBotStatus`, `updateBotConfig`.
- All functions handle errors and return `{ data, error }` — never throw from `api.js`.

## State Management (Phase 9)

- Global state lives in the zustand store at `trading_ui/src/store/`.
- No prop-drilling beyond 2 levels — use `useStore()` hooks for anything deeper.
- Each domain gets its own store slice file: `marketStore.js`, `chatStore.js`, `backtestStore.js`.
- Local component state (`useState`) is fine for UI-only concerns (modal open/close, form input).

## CSS Rules

- No per-component `.css` files. All styling via CSS custom properties + utility classes in `theme.css`.
- Use CSS modules or inline `style={{ color: 'var(--color-up)' }}` syntax — never hardcoded values.
- Responsive design: use `--spacing-*` tokens and flexbox/grid — no fixed pixel widths.

## Chart (CandleChart — Phase 9)

- All timestamps must be converted to IST (+05:30) before passing to lightweight-charts.
- Interval → Kite API mapping: `1m`→`minute`, `5m`→`5minute`, `15m`→`15minute`, `1h`→`60minute`, `1D`→`day`, `1W`→`week`, `1M`→`month`.
- Session hours: 09:15–15:30 IST. Add vertical marker lines at these boundaries for intraday charts.
- lightweight-charts is pinned to `4.2.0` — do NOT upgrade to 5.x.

## ChatPanel (Phase 9)

- Displays structured LLM responses with visual components:
  - **Confidence badge**: color-coded by confidence level (red < 40, yellow 40–60, green > 60)
  - **Action pill**: BUY (green), SELL (red), WAIT (gray)
  - **Key factors tags**: chips for scenario, R:R ratio, MTF confluence
- Parses LLM JSON output and handles malformed responses gracefully (shows error state).
- Auto-scrolls to latest message on new responses.

## Component Guidelines

- Each component must have a single clear responsibility.
- Props should be typed with PropTypes or JSDoc `@param` comments.
- Use `React.memo()` for pure display components that receive stable props.
- Error boundaries: wrap each page-level component in `<ErrorBoundary>`.

---

## Historical Data Page (Added May 2026)

**Route**: `/historical`  
**Files**: `pages/HistoricalData.jsx`, `features/historical/HistoricalDataTable.jsx`  
**Full Documentation**: `.github/docs/HISTORICAL_DATA_PAGE.md`

### Purpose
Comprehensive technical analysis table with 22 columns covering OHLCV, volume building, technical indicators, candle patterns, and automated trading signals.

### Key Features
1. **Multi-Exchange Support**: NSE equities + NFO derivatives (futures, options)
2. **SymbolSearch Component**: Autocomplete with watchlist integration (vertical display)
3. **Trade Type Selector**: Intraday / Swing / Long Term
4. **Interval Support**: 1m, 5m, 15m, 1h, 1D, 1W, 1M
5. **22 Analysis Columns**:
   - Basic OHLCV (9 columns)
   - Volume Analysis (4 columns): Vol Ratio, Bull Vol, Bear Vol, Vol Building
   - Technical Indicators (4 columns): RSI(14), SMA(20), % from SMA, Trend
   - Candle Patterns (3 columns): Body %, Range %, Pattern (Hammer, Engulfing, etc.)
   - Trading Signals (2 columns): Signal (BUY/SELL/HOLD), Strength score

### Volume Building Algorithm
- **Intraday**: Resets cumulative volumes at 9:15 AM IST each day
- **Calculation**: `netVolume = cumulativeBullishVol - cumulativeBearishVol`
- **Direction**: 📈 Bullish (net > 0), 📉 Bearish (net < 0), ⚪ Neutral

### Trading Signal Logic
Signal strength combines:
- **RSI**: Oversold (<30) +2, Overbought (>70) -2
- **Trend**: Strong Uptrend +2, Uptrend +1, Downtrend -1, Strong Downtrend -2
- **Volume**: High volume (>1.5x avg) confirms candle direction ±1
- **Patterns**: Bullish patterns +2, Bearish patterns -2

Final signal:
- **STRONG BUY**: strength ≥ 3
- **BUY**: strength 1-2
- **HOLD**: strength 0
- **SELL**: strength -1 to -2
- **STRONG SELL**: strength ≤ -3

### Pattern Recognition
Auto-detects:
- 🟢🟢 Bullish Engulfing (reversal)
- 🔴🔴 Bearish Engulfing (reversal)
- 🔨 Hammer (bullish reversal, long lower wick)
- ⭐ Shooting Star (bearish reversal, long upper wick)
- ➕ Doji (indecision, small body <5%)
- Strong Bull/Bear (body >70%)

### CSS Patterns
```css
/* RSI highlighting */
.historical-table__td--rsi.oversold { color: var(--color-up); background: rgba(34, 197, 94, 0.1); }
.historical-table__td--rsi.overbought { color: var(--color-down); background: rgba(239, 68, 68, 0.1); }

/* Trend direction */
.historical-table__td--uptrend { color: var(--color-up); }
.historical-table__td--downtrend { color: var(--color-down); }

/* Signal badges */
.signal-buy .signal-badge { background: rgba(34, 197, 94, 0.2); color: var(--color-up); }
.signal-sell .signal-badge { background: rgba(239, 68, 68, 0.2); color: var(--color-down); }
```

### Future Enhancements (Derivatives)
To fully support NFO derivatives, add these columns (requires backend API changes):
- **Open Interest (OI)** — from Kite `quote()` API
- **OI Change** — day-over-day OI delta
- **Implied Volatility (IV)** — option pricing volatility
- **Greeks** (Delta, Gamma, Theta, Vega) — option sensitivity metrics
- **Days to Expiry** — time decay tracking

### State Management
```javascript
// zustand marketStore additions
watchlist: ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK'],
addToWatchlist: (symbol) => {...},
removeFromWatchlist: (symbol) => {...},
```

### API Integration
Calls `fetchMarketData(symbol, interval, limit)` from `services/api.js`  
Backend: `GET /api/market-data/{symbol}?interval={interval}&limit={limit}`

