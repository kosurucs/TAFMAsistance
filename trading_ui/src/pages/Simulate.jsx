import { AppLayout } from '../layouts/AppLayout';
import { Card } from '../design-system';

export default function Simulate() {
  return (
    <AppLayout>
      <Card title="Strategy Simulator">
        <p style={{ color: 'var(--color-text-secondary)' }}>
          Simulation engine coming soon. Use the Backtest page to run historical analysis.
        </p>
      </Card>
    </AppLayout>
  );
}
