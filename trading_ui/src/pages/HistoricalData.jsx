import { useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card } from '../design-system';
import { HistoricalDataTable } from '../features/historical/HistoricalDataTable';
import { SymbolSearch } from '../features/trading/SymbolSearch';
import { useMarketStore } from '../store';
import './HistoricalData.css';

const INTERVALS = [
  { label: '1m',  value: 'minute'   },
  { label: '5m',  value: '5minute'  },
  { label: '15m', value: '15minute' },
  { label: '1h',  value: '60minute' },
  { label: '1D',  value: 'day'      },
];

const TRADE_TYPES = [
  { label: 'Intraday',  value: 'intraday' },
  { label: 'Swing',     value: 'swing'    },
  { label: 'Long Term', value: 'long'     },
];

const ROW_OPTIONS = [50, 100, 200, 500, 1000];

export default function HistoricalData() {
  const { selectedSymbol } = useMarketStore();
  const [interval,  setInterval]  = useState('day');
  const [limit,     setLimit]     = useState(100);
  const [tradeType, setTradeType] = useState('intraday');

  return (
    <AppLayout>
      <div className="hd-page">
        {/* -- Single horizontal toolbar ----------------------- */}
        <div className="hd-toolbar">

          {/* Watchlist + symbol search */}
          <SymbolSearch />

          <span className="hd-sep">|</span>

          {/* Timeframe pills */}
          <span className="hd-group-label">TF</span>
          <span className="hd-sep">|</span>
          <div className="hd-pills">
            {INTERVALS.map((tf, idx) => (
              <span key={tf.value} className="hd-pill-group">
                {idx > 0 && <span className="hd-pipe">|</span>}
                <button
                  className={`hd-pill ${interval === tf.value ? 'hd-pill--active' : ''}`}
                  onClick={() => setInterval(tf.value)}
                  type="button"
                >
                  {tf.label}
                </button>
              </span>
            ))}
          </div>

          <span className="hd-sep">|</span>

          {/* Trade type pills */}
          <span className="hd-group-label">Type</span>
          <span className="hd-sep">|</span>
          <div className="hd-pills">
            {TRADE_TYPES.map((t, idx) => (
              <span key={t.value} className="hd-pill-group">
                {idx > 0 && <span className="hd-pipe">|</span>}
                <button
                  className={`hd-pill ${tradeType === t.value ? 'hd-pill--active' : ''}`}
                  onClick={() => setTradeType(t.value)}
                  type="button"
                >
                  {t.label}
                </button>
              </span>
            ))}
          </div>

          <span className="hd-sep">|</span>

          {/* Rows pills */}
          <span className="hd-group-label">Rows</span>
          <span className="hd-sep">|</span>
          <div className="hd-pills">
            {ROW_OPTIONS.map((n, idx) => (
              <span key={n} className="hd-pill-group">
                {idx > 0 && <span className="hd-pipe">|</span>}
                <button
                  className={`hd-pill ${limit === n ? 'hd-pill--active' : ''}`}
                  onClick={() => setLimit(n)}
                  type="button"
                >
                  {n}
                </button>
              </span>
            ))}
          </div>

        </div>

        {/* -- Data table --------------------------------------- */}
        <Card title={`${selectedSymbol} — Historical Data`}>
          <HistoricalDataTable
            symbol={selectedSymbol}
            interval={interval}
            limit={limit}
            tradeType={tradeType}
          />
        </Card>
      </div>
    </AppLayout>
  );
}
