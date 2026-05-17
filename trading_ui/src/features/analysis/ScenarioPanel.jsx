import { Card } from '../../design-system';
import './ScenarioPanel.css';

export function ScenarioPanel() {
  // Placeholder — scenario data will come from indicators API response
  return (
    <Card title="Scenario Analysis">
      <div className="scenario-panel">
        <p style={{color:'var(--color-text-muted)', fontSize:'var(--font-size-sm)'}}>
          Scenario analysis available when agent is running.
        </p>
      </div>
    </Card>
  );
}
