import { useState, useEffect, useCallback } from 'react';
import { Badge } from '../../design-system';
import { getAlgoSignals } from '../../services/api';
import './DecisionReport.css';

const POLL_INTERVAL = 6000; // 6 seconds

/**
 * DecisionReport component
 * 
 * Shows the most recent actionable (BUY/SELL) signal across all symbols.
 * This is the "decision report" from v1.0 design.
 */
export function DecisionReport() {
  const [bestSignal, setBestSignal] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchBestSignal = useCallback(async () => {
    const { data } = await getAlgoSignals(50);
    
    if (!data?.signals) {
      setLoading(false);
      return;
    }

    // Find most recent actionable signal (BUY or SELL with checklist pass)
    const actionable = data.signals.filter(
      s => (s.action === 'BUY' || s.action === 'SELL') && s.checklist_pass
    );

    if (actionable.length > 0) {
      // Sort by timestamp descending and take most recent
      const sorted = actionable.sort((a, b) => 
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
      setBestSignal(sorted[0]);
    } else {
      setBestSignal(null);
    }
    
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchBestSignal();
    const id = setInterval(fetchBestSignal, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [fetchBestSignal]);

  if (loading) {
    return (
      <div className="decision-report">
        <div className="decision-report__header">
          <h3>Decision Report</h3>
        </div>
        <div className="decision-report__empty">Loading signals...</div>
      </div>
    );
  }

  if (!bestSignal) {
    return (
      <div className="decision-report">
        <div className="decision-report__header">
          <h3>Decision Report</h3>
        </div>
        <div className="decision-report__empty">
          No actionable signals. All symbols returned WAIT.
        </div>
      </div>
    );
  }

  const actionColor = bestSignal.action === 'BUY' ? 'success' : 'danger';
  const rrColor = bestSignal.rr_ratio >= 2.0 ? 'success' : 'warning';
  const confColor = bestSignal.confidence >= 80 ? 'success' : 
                    bestSignal.confidence >= 60 ? 'warning' : 'default';

  return (
    <div className="decision-report">
      <div className="decision-report__header">
        <h3>Decision Report</h3>
        <Badge variant={actionColor} size="lg">
          {bestSignal.action}
        </Badge>
      </div>

      <div className="decision-report__symbol">
        <span className="decision-report__symbol-name">{bestSignal.symbol}</span>
        <span className="decision-report__exchange">{bestSignal.exchange}</span>
      </div>

      <div className="decision-report__strategy">
        <span className="decision-report__label">Strategy</span>
        <span className="decision-report__value">{bestSignal.strategy}</span>
      </div>

      <div className="decision-report__metrics">
        <div className="decision-report__metric">
          <span className="decision-report__label">Entry</span>
          <span className="decision-report__value">
            ₹{bestSignal.entry_price?.toFixed(2)}
          </span>
        </div>
        <div className="decision-report__metric">
          <span className="decision-report__label">SL</span>
          <span className="decision-report__value">
            ₹{bestSignal.suggested_sl?.toFixed(2)}
          </span>
        </div>
        <div className="decision-report__metric">
          <span className="decision-report__label">TP</span>
          <span className="decision-report__value">
            ₹{bestSignal.suggested_tp?.toFixed(2)}
          </span>
        </div>
      </div>

      <div className="decision-report__quality">
        <div className="decision-report__quality-item">
          <span className="decision-report__label">R:R Ratio</span>
          <Badge variant={rrColor} size="sm">
            1:{bestSignal.rr_ratio?.toFixed(1)}
          </Badge>
        </div>
        <div className="decision-report__quality-item">
          <span className="decision-report__label">Confidence</span>
          <Badge variant={confColor} size="sm">
            {Math.round(bestSignal.confidence)}%
          </Badge>
        </div>
      </div>

      <div className="decision-report__reason">
        <span className="decision-report__label">Reason</span>
        <p className="decision-report__reason-text">{bestSignal.reason}</p>
      </div>

      {bestSignal.scenario && (
        <div className="decision-report__scenario">
          <span className="decision-report__label">Scenario</span>
          <div className="decision-report__scenario-value">
            <span>{bestSignal.scenario.replace(/_/g, ' ')}</span>
            <Badge variant="info" size="sm">
              {Math.round(bestSignal.scenario_confidence)}%
            </Badge>
          </div>
        </div>
      )}

      <div className="decision-report__timestamp">
        Last updated: {new Date(bestSignal.timestamp).toLocaleTimeString('en-IN', { hour12: false })} IST
      </div>
    </div>
  );
}
