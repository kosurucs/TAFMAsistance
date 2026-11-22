import { Card, Badge, Spinner } from '../../design-system';
import { useMarketStore } from '../../store';
import { useScenario } from '../../hooks/useScenario';
import './ScenarioPanel.css';

const SCENARIO_COLORS = {
  BULLISH_BREAKOUT: 'success',
  BEARISH_BREAKDOWN: 'danger',
  SIDEWAYS_CONSOLIDATION: 'warning',
  REVERSAL_UP: 'info',
  REVERSAL_DOWN: 'danger',
};

export function ScenarioPanel() {
  const { selectedSymbol, interval } = useMarketStore();

  const { scenario, loading, error } = useScenario(
    selectedSymbol,
    'NSE',
    interval === '1D' ? 'day' : interval === '1h' ? '60minute' : 'day',
    !!selectedSymbol
  );

  if (!selectedSymbol) {
    return (
      <Card title="Scenario Analysis">
        <div className="scenario-panel">
          <p className="scenario-empty">Select a symbol to view scenario analysis</p>
        </div>
      </Card>
    );
  }

  if (loading && !scenario) {
    return (
      <Card title="Scenario Analysis">
        <div className="scenario-panel">
          <Spinner size="sm" />
          <span className="scenario-loading">Analyzing {selectedSymbol}...</span>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card title="Scenario Analysis">
        <div className="scenario-panel">
          <p className="scenario-error">{error}</p>
        </div>
      </Card>
    );
  }

  if (!scenario) {
    return (
      <Card title="Scenario Analysis">
        <div className="scenario-panel">
          <p className="scenario-empty">No scenario data available</p>
        </div>
      </Card>
    );
  }

  const dominantColor = SCENARIO_COLORS[scenario.dominant_scenario] || 'default';
  const topScenarios = [...scenario.scenarios]
    .sort((a, b) => b.probability - a.probability)
    .slice(0, 3);

  return (
    <Card title="Scenario Analysis">
      <div className="scenario-panel">
        <div className="scenario-dominant">
          <div className="scenario-label">Dominant Scenario</div>
          <div className="scenario-value">
            <Badge variant={dominantColor} size="lg">
              {scenario.dominant_scenario.replace(/_/g, ' ')}
            </Badge>
            <span className="scenario-confidence">{scenario.confidence}% confidence</span>
          </div>
        </div>

        <div className="scenario-bias">
          <div className="scenario-label">Trade Bias</div>
          <Badge
            variant={scenario.trade_bias === 'BUY' ? 'success' : scenario.trade_bias === 'SELL' ? 'danger' : 'warning'}
            size="md"
          >
            {scenario.trade_bias}
          </Badge>
        </div>

        <div className="scenario-breakdown">
          <div className="scenario-label">Probability Breakdown</div>
          <div className="scenario-list">
            {topScenarios.map((s) => (
              <div key={s.name} className="scenario-item">
                <span className="scenario-name">{s.name.replace(/_/g, ' ')}</span>
                <div className="scenario-bar-container">
                  <div
                    className="scenario-bar"
                    style={{
                      width: `${s.probability}%`,
                      backgroundColor: `var(--color-${SCENARIO_COLORS[s.name] || 'default'})`
                    }}
                  />
                </div>
                <span className="scenario-pct">{s.probability}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
