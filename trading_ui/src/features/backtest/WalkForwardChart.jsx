/**
 * WalkForwardChart — visualises anchored walk-forward stability results.
 *
 * Props:
 *   report  WalkForwardReport from the API:
 *     { n_windows, avg_stability, is_robust,
 *       windows: [{ window_id, train_start, train_end, test_start, test_end,
 *                   train_win_rate, test_win_rate, train_pnl, test_pnl, stability_score }] }
 *
 * Note: train_win_rate / test_win_rate are percentages (e.g. 60.0 = 60%).
 *       stability_score is a ratio 0–1.5 where ≥ 0.5 is considered robust.
 */
import './WalkForwardChart.css';

function StabilityBar({ score }) {
  const pct = Math.min(100, score * 100);
  const robust = score >= 0.5;
  return (
    <div className="wfc-sbar">
      <div
        className={`wfc-sbar-fill ${robust ? 'wfc-sbar-fill--robust' : 'wfc-sbar-fill--weak'}`}
        style={{ width: `${pct}%` }}
      />
      <span className={`wfc-sbar-val ${robust ? 'wfc-sbar-val--robust' : 'wfc-sbar-val--weak'}`}>
        {score.toFixed(2)}×
      </span>
    </div>
  );
}

export function WalkForwardChart({ report }) {
  if (!report || !report.windows?.length) return null;

  const { windows, avg_stability, is_robust } = report;

  return (
    <div className="wfc">
      <div className="wfc-header">
        <span className="wfc-title">Walk-Forward Validation</span>
        <div className="wfc-header-right">
          <span className="wfc-avg">avg {avg_stability.toFixed(2)}×</span>
          <span className={`wfc-robust-badge ${is_robust ? 'wfc-robust-badge--ok' : 'wfc-robust-badge--fail'}`}>
            {is_robust ? '✓ ROBUST' : '⚠ WEAK'}
          </span>
        </div>
      </div>

      <div className="wfc-windows">
        {windows.map((w) => (
          <div key={w.window_id} className="wfc-win">
            <div className="wfc-win-id">W{w.window_id}</div>

            <div className="wfc-win-bars">
              {/* Train win-rate bar */}
              <div className="wfc-bar-row">
                <span className="wfc-bar-lbl">Train</span>
                <div className="wfc-bar-track">
                  <div
                    className="wfc-bar-fill wfc-bar-fill--train"
                    style={{ width: `${Math.min(100, w.train_win_rate)}%` }}
                  />
                </div>
                <span className="wfc-bar-pct">{w.train_win_rate.toFixed(1)}%</span>
              </div>

              {/* Test win-rate bar */}
              <div className="wfc-bar-row">
                <span className="wfc-bar-lbl">Test</span>
                <div className="wfc-bar-track">
                  <div
                    className="wfc-bar-fill wfc-bar-fill--test"
                    style={{ width: `${Math.min(100, w.test_win_rate)}%` }}
                  />
                </div>
                <span className="wfc-bar-pct">{w.test_win_rate.toFixed(1)}%</span>
              </div>
            </div>

            <div className="wfc-win-right">
              <StabilityBar score={w.stability_score} />
              <div className="wfc-win-pnl">
                <span
                  className={w.test_pnl >= 0 ? 'wfc-pnl--up' : 'wfc-pnl--dn'}
                >
                  {w.test_pnl >= 0 ? '+' : ''}{w.test_pnl.toFixed(1)}%
                </span>
                <span className="wfc-pnl-label">test net</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
