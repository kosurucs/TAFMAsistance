import { AppLayout } from '../layouts/AppLayout';
import { useMarketData } from '../hooks/useMarketData';
import { useMarketStore } from '../store';
import { Card, Spinner } from '../design-system';
import { CandleChart } from '../features/chart/CandleChart';
import IntervalSelector from '../features/chart/IntervalSelector';
import { IndicatorPanel } from '../features/analysis/IndicatorPanel';
import { QuoteBar } from '../features/trading/QuoteBar';
import { SymbolSearch } from '../features/trading/SymbolSearch';
import { ScenarioPanel } from '../features/analysis/ScenarioPanel';
import { DecisionReport } from '../features/algo/DecisionReport';
import { EngineStatus } from '../features/algo/EngineStatus';
import './Dashboard.css';

export default function Dashboard() {
  const { loading, refreshing } = useMarketStore();
  useMarketData();

  return (
    <AppLayout>
      <div className="dashboard">
        <div className="dashboard__toolbar">
          <SymbolSearch />
          <div className="dashboard__toolbar-divider" />
          <IntervalSelector />
        </div>

        <QuoteBar />

        <div className="dashboard__grid">
          <Card className="dashboard__chart" title="Price Chart" refreshing={refreshing}>
            {loading ? (
              <div className="dashboard__chart-loading">
                <Spinner size="lg" />
              </div>
            ) : (
              <CandleChart />
            )}
          </Card>

          <div className="dashboard__sidebar">
            <IndicatorPanel />
            <ScenarioPanel />
          </div>
        </div>

        <div className="dashboard__monitor-hub">
          <div className="dashboard__monitor-section">
            <h2 className="dashboard__monitor-title">Monitor Hub</h2>
          </div>
          <div className="dashboard__monitor-grid">
            <DecisionReport />
            <EngineStatus />
          </div>
        </div>

      </div>
    </AppLayout>
  );
}
