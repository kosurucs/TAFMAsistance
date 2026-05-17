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
├── pages/                 ← Dashboard, Portfolio, Backtest, Simulate, LLMStudio
├── features/
│   ├── chart/             ← CandleChart (IST-aware)
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
