# Historical Data Page — Complete Feature Documentation

## Overview

The Historical Data page (`trading_ui/src/pages/HistoricalData.jsx`) provides comprehensive technical analysis and trading strategy signals for any symbol with multi-timeframe support and derivative market compatibility.

**Location**: `/historical` route  
**Components**: `HistoricalData.jsx` (page), `HistoricalDataTable.jsx` (table component)  
**Added**: May 2026  
**Status**: ✅ Production Ready

---

## Page Features

### 1. Symbol Selection
- **SymbolSearch Component**: Autocomplete search with watchlist integration
- **Multi-Exchange Support**: NSE equities + NFO derivatives (futures, options)
- **Watchlist Display**: Vertical list with add/remove functionality
- **Search Results**: Shows symbol, name, exchange, instrument type, expiry, lot size

### 2. Controls Panel
- **Trade Type Dropdown**: 
  - Intraday (0DTE strategies)
  - Swing (1-5 days)
  - Long Term (weeks/months)
- **Interval Selector**: 1m, 5m, 15m, 1h, 1D, 1W, 1M
- **Row Limit**: Configurable data points (10-2000, default 100)

### 3. Data Table (22 Columns)

#### Basic OHLCV (9 columns)
| Column | Description | Format |
|--------|-------------|--------|
| # | Reverse index (newest = 1) | Integer |
| Timestamp (IST) | Indian Standard Time | DD/MM/YYYY HH:MM:SS |
| Open | Opening price | ₹XX,XXX.XX |
| High | Highest price | ₹XX,XXX.XX (highlighted) |
| Low | Lowest price | ₹XX,XXX.XX (highlighted) |
| Close | Closing price | ₹XX,XXX.XX |
| Volume | Trade volume | X,XXX,XXX |
| Type | Candle direction | 🟢 Bull / 🔴 Bear |
| Change % | Price change percentage | +/-X.XX% |

#### Volume Analysis (4 columns)
| Column | Description | Logic |
|--------|-------------|-------|
| Vol Ratio | Current volume vs 20-period average | >1.5x highlighted in yellow |
| Bull Vol | Cumulative bullish candle volume | Resets daily at 9:15 AM IST |
| Bear Vol | Cumulative bearish candle volume | Resets daily at 9:15 AM IST |
| Vol Build | Net volume direction | 📈 Bullish / 📉 Bearish + running total |

**Volume Building Algorithm**:
```javascript
// For each candle in chronological order:
if (candle_type === 'bullish') {
  cumulativeBullishVol += volume;
} else {
  cumulativeBearishVol += volume;
}
netVolume = cumulativeBullishVol - cumulativeBearishVol;
volumeDirection = netVolume > 0 ? 'Bullish' : netVolume < 0 ? 'Bearish' : 'Neutral';
```

#### Technical Indicators (4 columns)
| Column | Description | Interpretation |
|--------|-------------|----------------|
| RSI(14) | Relative Strength Index | <30 oversold (green), >70 overbought (red) |
| SMA(20) | 20-period Simple Moving Average | Support/resistance level |
| % from SMA | Distance from SMA20 | +% above, -% below (trend strength) |
| Trend | Multi-MA trend analysis | 🚀 Strong Up, 📈 Up, 📉 Down, 💥 Strong Down |

**Trend Logic**:
- **Strong Uptrend**: SMA(10) > SMA(20) AND close > SMA(20)
- **Uptrend**: SMA(10) > SMA(20)
- **Downtrend**: SMA(10) < SMA(20)
- **Strong Downtrend**: SMA(10) < SMA(20) AND close < SMA(20)

#### Candle Pattern Analysis (3 columns)
| Column | Description | Values |
|--------|-------------|--------|
| Body % | Candle body as % of total range | 0-100% |
| Range % | High-low range as % of open price | Volatility measure |
| Pattern | Auto-detected candlestick pattern | See pattern list below |

**Detected Patterns**:
- 🟢🟢 **Bullish Engulfing** — Strong reversal signal (close > prev_open AND open < prev_close)
- 🔴🔴 **Bearish Engulfing** — Strong reversal signal (close < prev_open AND open > prev_close)
- 🔨 **Hammer** — Bullish reversal (small body at top, long lower wick >60%)
- ⭐ **Shooting Star** — Bearish reversal (small body at bottom, long upper wick >60%)
- ➕ **Doji** — Indecision (body <5% of range)
- **Strong Bull/Bear** — Large body (>70% of range)
- **Normal** — No specific pattern

#### Trading Signals (2 columns)
| Column | Description | Range |
|--------|-------------|-------|
| Signal | Automated recommendation | 🟢🟢 STRONG BUY, 🟢 BUY, ⚪ HOLD, 🔴 SELL, 🔴🔴 STRONG SELL |
| Strength | Signal confidence score | -10 to +10 |

**Signal Calculation**:
```javascript
let signalStrength = 0;

// RSI component
if (rsi < 30) signalStrength += 2;      // Oversold
else if (rsi > 70) signalStrength -= 2;  // Overbought

// Trend component
if (trend === 'Strong Uptrend') signalStrength += 2;
else if (trend === 'Uptrend') signalStrength += 1;
else if (trend === 'Downtrend') signalStrength -= 1;
else if (trend === 'Strong Downtrend') signalStrength -= 2;

// Volume confirmation
if (volumeRatio > 1.5) {
  if (candle_type === 'bullish') signalStrength += 1;
  else signalStrength -= 1;
}

// Pattern signals
if (pattern === 'Bullish Engulfing' || pattern === 'Hammer') signalStrength += 2;
else if (pattern === 'Bearish Engulfing' || pattern === 'Shooting Star') signalStrength -= 2;

// Final signal
if (signalStrength >= 3) signal = 'STRONG BUY';
else if (signalStrength >= 1) signal = 'BUY';
else if (signalStrength <= -3) signal = 'STRONG SELL';
else if (signalStrength <= -1) signal = 'SELL';
else signal = 'HOLD';
```

---

## CSS Styling Classes

### Color-Coded Elements
```css
/* RSI highlighting */
.historical-table__td--rsi.oversold { color: var(--color-up); background: rgba(34, 197, 94, 0.1); }
.historical-table__td--rsi.overbought { color: var(--color-down); background: rgba(239, 68, 68, 0.1); }

/* Trend coloring */
.historical-table__td--uptrend { color: var(--color-up); }
.historical-table__td--downtrend { color: var(--color-down); }
.historical-table__td--sideways { color: var(--color-text-secondary); }

/* Pattern significance */
.pattern-significant { font-weight: var(--font-weight-bold); background: rgba(96, 165, 250, 0.1); }

/* Trading signals */
.signal-buy .signal-badge { background: rgba(34, 197, 94, 0.2); color: var(--color-up); border: 1px solid var(--color-up); }
.signal-sell .signal-badge { background: rgba(239, 68, 68, 0.2); color: var(--color-down); border: 1px solid var(--color-down); }
.signal-hold .signal-badge { background: rgba(156, 163, 175, 0.2); color: var(--color-text-secondary); }

/* Volume spike */
.volume-spike { color: var(--color-warning); font-weight: var(--font-weight-bold); }
```

---

## Component Props

### HistoricalData.jsx
```javascript
// No props - standalone page component
// Uses zustand store: useMarketStore()
// State: selectedSymbol, interval, limit, tradeType
```

### HistoricalDataTable.jsx
```javascript
PropTypes = {
  symbol: string.isRequired,      // Trading symbol (e.g., "RELIANCE", "NFO:NIFTY26MAYFUT")
  interval: string.isRequired,    // "minute", "5minute", "15minute", "60minute", "day"
  limit: number.isRequired,       // Max candles to display (10-2000)
  tradeType: string.isRequired,   // "intraday", "swing", "long"
}
```

---

## API Dependency

### Endpoint: `GET /api/market-data/{symbol}`
**Query Params**:
- `interval`: Candle interval (minute, 5minute, 15minute, 60minute, day, week, month)
- `limit`: Max candles to return (default 200)
- `days_back`: Historical lookback window (0 = max available)

**Response**:
```json
{
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "interval": "60minute",
  "candles": [
    {
      "time": 1779038400,
      "open": 2850.50,
      "high": 2865.75,
      "low": 2845.00,
      "close": 2860.25,
      "volume": 1234567
    }
  ],
  "indicators": {
    "rsi": 58.3,
    "ema9": 2855.0,
    "ema21": 2840.5
  }
}
```

---

## Derivative Market Support

### Current Implementation
- **Symbol Format**: `EXCHANGE:TRADINGSYMBOL` (e.g., `NFO:NIFTY26MAYFUT`)
- **Supported Exchanges**: NSE, NFO, BSE, MCX, CDS
- **Search Results Include**:
  - `instrument_type` (FUT, CE, PE)
  - `expiry` (YYYY-MM-DD)
  - `lot_size` (contract multiplier)

### Future Enhancements (Derivatives-Specific Columns)
To fully support derivatives analysis, add these columns:

| Column | Description | Data Source |
|--------|-------------|-------------|
| **Open Interest (OI)** | Total contracts outstanding | Kite `quote()` API → `oi` |
| **OI Change** | Change in OI from previous close | `oi_day_high - oi_day_low` |
| **Strike Price** | Option strike price | Instruments cache → `strike` |
| **Days to Expiry** | Time decay tracking | `(expiry - today).days` |
| **Implied Volatility** | Option pricing volatility | Kite market depth → `iv` |
| **Greeks** | Delta, Gamma, Theta, Vega | Calculated or from Kite Greeks API |

**Backend API Changes Required**:
```python
# In api.py get_market_data() endpoint
if symbol.startswith("NFO:"):
    # Fetch additional derivative data
    quote = _market.get_quote([symbol])
    candles_with_derivatives = [{
        **candle,
        "oi": quote.get("oi", 0),
        "oi_change": quote.get("oi_day_change", 0),
        "iv": quote.get("implied_volatility", 0),
    } for candle in candles]
```

---

## Performance Considerations

1. **Data Limits**: Default 100 rows, max 2000 to prevent UI freezing
2. **Calculation Efficiency**:
   - RSI requires 14+ candles
   - SMA(20) requires 20+ candles
   - SMA(10) requires 10+ candles
   - Early rows show "N/A" for indicators with insufficient data
3. **Volume Reset**: Intraday intervals reset cumulative volumes at 9:15 AM IST each day
4. **Timestamp Deduplication**: Backend removes duplicate timestamps before sending (lightweight-charts requirement)

---

## Testing Checklist

- [x] NSE equity symbols (RELIANCE, TCS, INFY, HDFCBANK)
- [x] NFO derivatives (NIFTY 50, NIFTY BANK futures)
- [x] All intervals (1m, 5m, 15m, 1h, 1D)
- [x] Volume building calculation (bullish/bearish accumulation)
- [x] Technical indicators (RSI, SMA, trend detection)
- [x] Pattern recognition (engulfing, hammer, shooting star)
- [x] Trading signals (strength scoring)
- [x] Watchlist add/remove
- [x] Trade type dropdown (intraday/swing/long)
- [x] Row limit adjustment (10-2000)
- [ ] Derivative-specific columns (OI, Greeks) — **Pending backend enhancement**

---

## Known Limitations

1. **No Real-Time Updates**: Table does not auto-refresh — user must manually reload
2. **No Export**: No CSV/Excel export functionality (future enhancement)
3. **No Filtering**: Cannot filter by signal type or pattern (future enhancement)
4. **No Sorting**: Table rows are fixed in reverse chronological order
5. **Derivative Data Incomplete**: Missing OI, IV, Greeks columns (requires backend API update)

---

## Future Enhancements

1. **Auto-Refresh**: WebSocket integration for live data updates
2. **Export to CSV**: Download table data for external analysis
3. **Column Customization**: Show/hide columns based on user preference
4. **Advanced Filters**: Filter by signal strength, RSI range, volume threshold
5. **Sortable Columns**: Click headers to sort by any metric
6. **Pattern Highlighting**: Visual markers on chart for detected patterns
7. **Alert Creation**: Set alerts when signal strength crosses threshold
8. **Backtesting Integration**: Click row → run backtest from that entry point

---

## Related Files

| File | Purpose |
|------|---------|
| `trading_ui/src/pages/HistoricalData.jsx` | Page component with controls |
| `trading_ui/src/pages/HistoricalData.css` | Page-level styles |
| `trading_ui/src/features/historical/HistoricalDataTable.jsx` | Table component with calculations |
| `trading_ui/src/features/historical/HistoricalDataTable.css` | Table styles |
| `trading_ui/src/components/SymbolSearch.jsx` | Symbol autocomplete component |
| `trading_ui/src/components/SymbolSearch.css` | Symbol search styles |
| `trading_ui/src/store/marketStore.js` | Zustand store with watchlist |
| `trading_ui/src/services/api.js` | HTTP service (fetchMarketData) |
| `trading_bot/src/api.py` | Backend API endpoint (/api/market-data) |
