import { useRef, useEffect, useState } from 'react';
import { useMarketStore } from '../../store';
import './QuoteBar.css';

// Returns 'up' | 'down' | null based on previous vs current value
function useFlash(value) {
  const prev = useRef(value);
  const [flash, setFlash] = useState(null);

  useEffect(() => {
    if (prev.current === null || prev.current === value) {
      prev.current = value;
      return;
    }
    const dir = value > prev.current ? 'up' : 'down';
    prev.current = value;
    setFlash(dir);
    const id = setTimeout(() => setFlash(null), 900);
    return () => clearTimeout(id);
  }, [value]);

  return flash;
}

function StatCell({ label, value, colorClass }) {
  return (
    <div className="qb-stat">
      <span className="qb-stat__label">{label}</span>
      <strong className={`qb-stat__val ${colorClass || ''}`}>{value}</strong>
    </div>
  );
}

export function QuoteBar() {
  const { selectedSymbol, quote, refreshing } = useMarketStore();
  const ltp = Number(quote?.ltp || 0);
  const flash = useFlash(ltp);

  if (!quote) {
    return (
      <div className="quote-bar quote-bar--loading">
        <span className="qb-symbol">{selectedSymbol}</span>
        <span className="qb-skeleton">Loading quote…</span>
      </div>
    );
  }

  const change    = Number(quote.change    || 0);
  const changePct = Number(quote.change_pct || 0);
  const isUp      = change >= 0;

  return (
    <div className={`quote-bar ${refreshing ? 'quote-bar--refreshing' : ''}`}>
      {/* Symbol badge */}
      <div className="qb-left">
        <span className="qb-symbol">{selectedSymbol}</span>
        <span className="qb-exchange">NSE</span>
      </div>

      {/* LTP + change */}
      <div className="qb-center">
        <span className={`qb-ltp qb-ltp--flash-${flash || 'none'}`}>
          ₹{ltp.toFixed(2)}
        </span>
        <div className={`qb-change-pill ${isUp ? 'qb-change-pill--up' : 'qb-change-pill--down'}`}>
          <span>{isUp ? '▲' : '▼'}</span>
          <span>{Math.abs(change).toFixed(2)}</span>
          <span>({Math.abs(changePct).toFixed(2)}%)</span>
        </div>
      </div>

      {/* OHLCV stats */}
      <div className="qb-right">
        <StatCell label="Open"   value={`₹${Number(quote.open  || 0).toFixed(2)}`} />
        <StatCell label="High"   value={`₹${Number(quote.high  || 0).toFixed(2)}`} colorClass="qb-stat__val--up" />
        <StatCell label="Low"    value={`₹${Number(quote.low   || 0).toFixed(2)}`} colorClass="qb-stat__val--down" />
        <StatCell label="Close"  value={`₹${Number(quote.close || 0).toFixed(2)}`} />
        <StatCell label="Volume" value={Number(quote.volume || 0).toLocaleString('en-IN')} />
      </div>
    </div>
  );
}
