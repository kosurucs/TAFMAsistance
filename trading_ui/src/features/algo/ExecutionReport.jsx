import { useState, useEffect, useCallback } from 'react';
import { getAlgoSignals } from '../../services/api';
import './ExecutionReport.css';

export default function ExecutionReport() {
  const [signals, setSignals] = useState([]);

  const fetchSignals = useCallback(async () => {
    const { data } = await getAlgoSignals(200);
    if (data?.signals) setSignals(data.signals);
  }, []);

  useEffect(() => { fetchSignals(); }, [fetchSignals]);

  if (signals.length === 0) {
    return (
      <div className="exec-report">
        <h2 className="exec-report__title">Execution Report</h2>
        <p className="exec-report__empty">No signals recorded yet.</p>
      </div>
    );
  }

  // Summary stats
  const totalSignals = signals.length;
  const buys  = signals.filter(s => s.action === 'BUY').length;
  const sells = signals.filter(s => s.action === 'SELL').length;
  const passed = signals.filter(s => s.checklist_pass).length;
  const avgConf = (signals.reduce((a, s) => a + (s.confidence || 0), 0) / totalSignals).toFixed(1);

  const byStrategy = signals.reduce((acc, s) => {
    acc[s.strategy] = (acc[s.strategy] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="exec-report">
      <h2 className="exec-report__title">Execution Report</h2>

      <div className="exec-report__stats">
        <div className="exec-report__stat">
          <div className="exec-report__stat-label">Total Signals</div>
          <div className="exec-report__stat-value">{totalSignals}</div>
        </div>
        <div className="exec-report__stat">
          <div className="exec-report__stat-label">BUY / SELL</div>
          <div className="exec-report__stat-value">
            <span style={{ color: 'var(--color-up)' }}>{buys}</span>
            {' / '}
            <span style={{ color: 'var(--color-down)' }}>{sells}</span>
          </div>
        </div>
        <div className="exec-report__stat">
          <div className="exec-report__stat-label">Checklist PASS</div>
          <div className="exec-report__stat-value" style={{ color: 'var(--color-up)' }}>
            {passed}
          </div>
        </div>
        <div className="exec-report__stat">
          <div className="exec-report__stat-label">Avg Confidence</div>
          <div className="exec-report__stat-value">{avgConf}%</div>
        </div>
      </div>

      <div className="exec-report__breakdown">
        <div className="exec-report__breakdown-title">Signals by Strategy</div>
        {Object.entries(byStrategy).map(([name, count]) => (
          <div key={name} className="exec-report__breakdown-row">
            <span className="exec-report__strategy-name">{name}</span>
            <div className="exec-report__bar-wrap">
              <div
                className="exec-report__bar"
                style={{ width: `${(count / totalSignals) * 100}%` }}
              />
            </div>
            <span className="exec-report__count">{count}</span>
          </div>
        ))}
      </div>

      <div className="exec-report__table-wrap">
        <table className="exec-report__table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Strategy</th>
              <th>Action</th>
              <th>Entry</th>
              <th>SL</th>
              <th>TP</th>
              <th>R:R</th>
              <th>Conf%</th>
              <th>Checklist</th>
            </tr>
          </thead>
          <tbody>
            {signals.map(s => {
              const time = s.timestamp
                ? new Date(s.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
                : '—';
              return (
                <tr key={s.id}>
                  <td className="exec-report__td-muted">{time}</td>
                  <td><strong>{s.symbol}</strong></td>
                  <td className="exec-report__td-muted">{s.strategy}</td>
                  <td>
                    <span className={`exec-report__action exec-report__action--${s.action.toLowerCase()}`}>
                      {s.action}
                    </span>
                  </td>
                  <td>₹{s.entry_price}</td>
                  <td style={{ color: 'var(--color-down)' }}>₹{s.suggested_sl}</td>
                  <td style={{ color: 'var(--color-up)' }}>₹{s.suggested_tp}</td>
                  <td>1:{s.rr_ratio?.toFixed(1)}</td>
                  <td style={{ color: 'var(--color-gold)' }}>{s.confidence?.toFixed(0)}</td>
                  <td>
                    <span className={`exec-report__pass${s.checklist_pass ? ' exec-report__pass--ok' : ' exec-report__pass--fail'}`}>
                      {s.checklist_pass ? 'PASS' : 'FAIL'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
