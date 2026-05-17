import { useMarketStore } from '../../store';
import './QuoteBar.css';

export function QuoteBar() {
  const { selectedSymbol, quote } = useMarketStore();

  if (!quote) {
    return (
      <div className="quote-bar loading">
        <span className="qb-symbol">{selectedSymbol}</span>
        <span className="qb-loading">Loading quote…</span>
      </div>
    );
  }

  const change = Number(quote.change || 0);
  const changePct = Number(quote.change_pct || 0);
  const isUp = change >= 0;

  return (
    <div className="quote-bar">
      <div className="qb-left">
        <span className="qb-symbol">{selectedSymbol}</span>
        <span className="qb-exchange">NSE</span>
      </div>
      <div className="qb-center">
        <span className="qb-ltp">₹{Number(quote.ltp || 0).toFixed(2)}</span>
        <span className={`qb-change ${isUp ? 'up' : 'down'}`}>
          {isUp ? '▲' : '▼'} {Math.abs(change).toFixed(2)} ({Math.abs(changePct).toFixed(2)}%)
        </span>
      </div>
      <div className="qb-right">
        <div className="qb-stat"><span>O</span><strong>₹{Number(quote.open || 0).toFixed(2)}</strong></div>
        <div className="qb-stat"><span>H</span><strong style={{color:'var(--color-up)'}}>₹{Number(quote.high || 0).toFixed(2)}</strong></div>
        <div className="qb-stat"><span>L</span><strong style={{color:'var(--color-down)'}}>₹{Number(quote.low || 0).toFixed(2)}</strong></div>
        <div className="qb-stat"><span>C</span><strong>₹{Number(quote.close || 0).toFixed(2)}</strong></div>
        <div className="qb-stat"><span>Vol</span><strong>{Number(quote.volume || 0).toLocaleString()}</strong></div>
      </div>
    </div>
  );
}
