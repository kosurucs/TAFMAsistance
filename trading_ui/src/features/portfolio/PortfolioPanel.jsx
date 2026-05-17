import { useState, useEffect, useCallback } from 'react';
import { fetchPortfolio } from '../../services/api';
import { Spinner } from '../../design-system';
import './PortfolioPanel.css';

const TABS = ['Positions', 'Holdings', 'Margins'];

function fmt(v, digits = 2) {
  const n = Number(v);
  return isNaN(n) ? '—' : `₹${n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

function pct(v) {
  const n = Number(v);
  return isNaN(n) ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function pnlClass(v) {
  const n = Number(v);
  if (isNaN(n) || n === 0) return '';
  return n > 0 ? 'pos' : 'neg';
}

export function PortfolioPanel() {
  const [tab, setTab] = useState('Positions');
  const [posView, setPosView] = useState('net');
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setBusy(true);
    setErr('');
    const { data: pfData, error } = await fetchPortfolio();
    if (error) {
      setErr(error);
    } else {
      setData(pfData);
    }
    setBusy(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const positions = data?.positions?.[posView] ?? [];
  const holdings = data?.holdings ?? [];
  const margins = data?.margins ?? {};
  const dayPnl = data?.day_pnl ?? 0;
  const holdPnl = data?.holdings_pnl ?? 0;

  return (
    <div className="pp-panel">
      <div className="pp-header">
        <span className="pp-title">Portfolio</span>
        <span className={`pp-pnl ${pnlClass(dayPnl)}`} title="Intraday P&L">
          Day {fmt(dayPnl)}
        </span>
        <span className={`pp-pnl ${pnlClass(holdPnl)}`} title="Holdings P&L">
          Hold {fmt(holdPnl)}
        </span>
        {data?.paper_trading && <span className="pp-paper">PAPER</span>}
        <button className="pp-refresh" onClick={load} disabled={busy} title="Refresh">⟳</button>
      </div>

      <div className="pp-tabs">
        {TABS.map(t => (
          <button
            key={t}
            className={`pp-tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {err && <div className="pp-error">{err}</div>}
      {busy && <div className="pp-loading"><Spinner size="md" /></div>}

      {tab === 'Positions' && (
        <div className="pp-content">
          <div className="pp-view-toggle">
            <button
              className={`pp-view-btn ${posView === 'net' ? 'active' : ''}`}
              onClick={() => setPosView('net')}
            >
              Net
            </button>
            <button
              className={`pp-view-btn ${posView === 'day' ? 'active' : ''}`}
              onClick={() => setPosView('day')}
            >
              Day
            </button>
          </div>
          {positions.length === 0 ? (
            <p className="pp-empty">No positions</p>
          ) : (
            <table className="pp-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Avg</th>
                  <th>LTP</th>
                  <th>P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => (
                  <tr key={i}>
                    <td className="pp-symbol">{p.tradingsymbol}</td>
                    <td>{p.quantity}</td>
                    <td>{fmt(p.average_price)}</td>
                    <td>{fmt(p.last_price)}</td>
                    <td className={pnlClass(p.pnl)}>{fmt(p.pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'Holdings' && (
        <div className="pp-content">
          {holdings.length === 0 ? (
            <p className="pp-empty">No holdings</p>
          ) : (
            <table className="pp-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Avg</th>
                  <th>LTP</th>
                  <th>P&L</th>
                  <th>Day %</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((h, i) => (
                  <tr key={i}>
                    <td className="pp-symbol">{h.tradingsymbol}</td>
                    <td>{h.quantity}</td>
                    <td>{fmt(h.average_price)}</td>
                    <td>{fmt(h.last_price)}</td>
                    <td className={pnlClass(h.pnl)}>{fmt(h.pnl)}</td>
                    <td className={pnlClass(h.day_change_percentage)}>{pct(h.day_change_percentage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'Margins' && (
        <div className="pp-content">
          <div className="pp-margins">
            <div className="pp-margin-row">
              <span>Available Cash</span>
              <strong>{fmt(margins.available?.cash)}</strong>
            </div>
            <div className="pp-margin-row">
              <span>Used Margin</span>
              <strong>{fmt(margins.utilised?.debits)}</strong>
            </div>
            <div className="pp-margin-row">
              <span>Available Margin</span>
              <strong>{fmt(margins.available?.live_balance)}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
