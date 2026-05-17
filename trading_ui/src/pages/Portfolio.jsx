import { AppLayout } from '../layouts/AppLayout';
import { Card } from '../design-system';
import { PortfolioPanel } from '../features/portfolio/PortfolioPanel';

export default function Portfolio() {
  return (
    <AppLayout>
      <Card title="Portfolio">
        <PortfolioPanel />
      </Card>
    </AppLayout>
  );
}
