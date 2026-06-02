import { useState, useEffect, useCallback } from 'react';
import { getAlgoSignals } from '../../services/api';
import './SignalFeed.css';

const POLL_INTERVAL = 8_000;

function ChecklistBadges({ checklist }) {
  const items = Object.entries(checklist || {});
  return (
    <div className="signal-card__checklist">
      {items.map(([key, pass]) => (
        <span
          key={key}
          className={`signal-card__check${pass ? ' signal-card__check--pass' : ' signal-card__check--fail'}`}
          title={key}
        >
          {pass ? '✓' : '✗'} {key.replace(/_/g, ' ')}
        </span>
      ))}
    </div>
  );
}

function SignalCard({ signal }) {
  const [expanded, setExpanded] = useState(false);
  const isBuy  = signal.action === 'BUY';
  const isSell = signal.action === 'SELL';

  const time = signal.timestamp
    ? new Date(signal.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
    : '—';

  return (
    <div className={`signal-card${isBuy ? ' signal-card--buy' : isSell ? ' signal-card--sell' : ''}`}>
      <div className="signal-card__header" onClick={() => setExpanded(e => !e)}>
        <div className="signal-card__left">
          <span className={`signal-card__action signal-card__action--${signal.action.toLowerCase()}`}>
            {signal.action}
          </span>
          <span className="signal-card__symbol">{signal.symbol}</span>
          <span className="signal-card__strategy">{signal.strategy}</span>
        </div>
        <div className="signal-card__right">
          <span className="signal-card__conf">{signal.confidence?.toFixed(0)}%</span>
          <span className={`signal-card__pass${signal.checklist_pass ? ' signal-card__pass--ok' : ' signal-card__pass--fail'}`}>
            {signal.checklist_pass ? 'PASS' : 'FAIL'}
          </span>
          <span className="signal-card__time">{time}</span>
          <span className="signal-card__expand">{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div className="signal-card__body">
          <div className="signal-card__reason">{signal.reason}</div>
          <div className="signal-card__prices">
            <span>Entry <strong>₹{signal.entry_price}</strong></span>
            <span>SL <strong className="signal-card__sl">₹{signal.suggested_sl}</strong></span>
            <span>TP <strong className="signal-card__tp">₹{signal.suggested_tp}</strong></span>
            <span>R:R <strong>1:{signal.rr_ratio?.toFixed(1)}</strong></span>
          </div>
          <ChecklistBadges checklist={signal.checklist} />
          <div className="signal-card__note">
            Analysis recommendation only — not executed
          </div>
        </div>
      )}
    </div>
  );
}

export default function SignalFeed() {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchSignals = useCallback(async () => {
    setLoading(true);
    const { data, error: err } = await getAlgoSignals(50);
    if (data?.signals) setSignals(data.signals);
    if (err) setError(err);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchSignals();
    const id = setInterval(fetchSignals, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [fetchSignals]);

  return (
    <div className="signal-feed">
      <div className="signal-feed__header">
        <h2 className="signal-feed__title">Live Signal Feed</h2>
        <button className="signal-feed__refresh" onClick={fetchSignals} disabled={loading}>
          {loading ? '…' : '↻'}
        </button>
      </div>
      {error && <div className="signal-feed__error">{error}</div>}
      {signals.length === 0 && !loading && (
        <div className="signal-feed__empty">
          No signals yet — run a cycle to generate recommendations.
        </div>
      )}
      <div className="signal-feed__list">
        {signals.map(sig => (
          <SignalCard key={sig.id} signal={sig} />
        ))}
      </div>
    </div>
  );
}
