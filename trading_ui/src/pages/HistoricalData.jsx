import { useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card } from '../design-system';
import { HistoricalDataTable } from '../features/historical/HistoricalDataTable';
import SymbolSearch from '../components/SymbolSearch';
import { useMarketStore } from '../store';
import './HistoricalData.css';

const INTERVALS = [
  { label: '1 Minute', value: 'minute' },
  { label: '5 Minutes', value: '5minute' },
  { label: '15 Minutes', value: '15minute' },
  { label: '1 Hour', value: '60minute' },
  { label: '1 Day', value: 'day' },
];

const TRADE_TYPES = [
  { label: 'Intraday', value: 'intraday' },
  { label: 'Swing', value: 'swing' },
  { label: 'Long Term', value: 'long' },
];

export default function HistoricalData() {
  const { watchlist, addToWatchlist, removeFromWatchlist } = useMarketStore();
  const [selectedSymbol, setSelectedSymbol] = useState('RELIANCE');
  const [interval, setInterval] = useState('day');
  const [limit, setLimit] = useState(100);
  const [tradeType, setTradeType] = useState('intraday');

  const handleSymbolSelect = (symbol) => {
    setSelectedSymbol(symbol);
  };

  return (
    <AppLayout>
      <Card title="Historical Data">
        <div className="historical-data">
          <div className="historical-data__controls">
            <div className="historical-data__control-group historical-data__symbol-section">
              <label className="historical-data__label">Symbol Search</label>
              <div className="historical-data__symbol-search">
                <SymbolSearch 
                  watchlist={watchlist}
                  selected={selectedSymbol}
                  onSelect={handleSymbolSelect}
                  onAdd={addToWatchlist}
                  onRemove={removeFromWatchlist}
                />
              </div>
            </div>

            <div className="historical-data__control-group">
              <label className="historical-data__label">Trade Type</label>
              <select 
                className="historical-data__select"
                value={tradeType}
                onChange={(e) => setTradeType(e.target.value)}
              >
                {TRADE_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            <div className="historical-data__control-group">
              <label className="historical-data__label">Interval</label>
              <select 
                className="historical-data__select"
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
              >
                {INTERVALS.map(i => (
                  <option key={i.value} value={i.value}>{i.label}</option>
                ))}
              </select>
            </div>

            <div className="historical-data__control-group">
              <label className="historical-data__label">Rows</label>
              <input
                type="number"
                className="historical-data__input"
                value={limit}
                onChange={(e) => setLimit(parseInt(e.target.value) || 100)}
                min="10"
                max="2000"
                step="10"
              />
            </div>
          </div>

          <div className="historical-data__table-container">
            <HistoricalDataTable 
              symbol={selectedSymbol}
              interval={interval}
              limit={limit}
              tradeType={tradeType}
            />
          </div>
        </div>
      </Card>
    </AppLayout>
  );
}
