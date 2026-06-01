/**
 * CommissionBreakdown — compact table showing gross vs net PnL and commission
 * drag across all strategy reports in a backtest result.
 *
 * Props:
 *   reports  Array of strategy report objects from the API.
 *            Each has: strategy_name, timeframe, gross_total_pnl,
 *            net_total_pnl, total_commission_pct, commission_segment
 */
import './CommissionBreakdown.css';

function fmt(val, decimals = 2) {
  if (val == null || isNaN(val)) return '—';
  const s = val.toFixed(decimals);
  return val >= 0 ? `+${s}%` : `${s}%`;
}

export function CommissionBreakdown({ reports }) {
  if (!reports?.length) return null;

  // Only show if net_total_pnl is available (requires Step 4 backend)
  const hasCommission = reports.some((r) => r.net_total_pnl != null);
  if (!hasCommission) return null;

  return (
    <div className="cbd">
      <div className="cbd-header">
        <span className="cbd-title">Commission Breakdown</span>
        <span className="cbd-subtitle">
          gross vs net PnL after statutory costs (brokerage + STT + GST + SEBI + stamp)
        </span>
      </div>

      <div className="cbd-table-wrap">
        <table className="cbd-table">
          <thead>
            <tr>
              <th>Strategy</th>
              <th>TF</th>
              <th>Segment</th>
              <th className="cbd-num">Gross PnL</th>
              <th className="cbd-num">Commission</th>
              <th className="cbd-num">Net PnL</th>
              <th className="cbd-num">Drag</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r, i) => {
              const drag =
                r.gross_total_pnl != null && r.net_total_pnl != null
                  ? r.gross_total_pnl - r.net_total_pnl
                  : null;
              return (
                <tr key={i}>
                  <td className="cbd-name">{r.strategy_name?.replace(/_/g, ' ')}</td>
                  <td className="cbd-tf">{r.timeframe}</td>
                  <td className="cbd-seg">
                    <span className="cbd-seg-badge">
                      {r.commission_segment?.replace(/_/g, ' ') ?? '—'}
                    </span>
                  </td>
                  <td
                    className="cbd-num"
                    style={{
                      color:
                        r.gross_total_pnl >= 0
                          ? 'var(--color-up)'
                          : 'var(--color-down)',
                    }}
                  >
                    {fmt(r.gross_total_pnl)}
                  </td>
                  <td className="cbd-num cbd-cost">
                    {r.total_commission_pct != null
                      ? `-${r.total_commission_pct.toFixed(2)}%`
                      : '—'}
                  </td>
                  <td
                    className="cbd-num cbd-net"
                    style={{
                      color:
                        (r.net_total_pnl ?? 0) >= 0
                          ? 'var(--color-up)'
                          : 'var(--color-down)',
                    }}
                  >
                    {fmt(r.net_total_pnl)}
                  </td>
                  <td className="cbd-num cbd-drag">
                    {drag != null ? `-${drag.toFixed(2)}%` : '—'}
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
