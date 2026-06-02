import { AppLayout } from '../layouts/AppLayout';
import AlgoEngine from '../features/algo/AlgoEngine';
import StrategyConfig from '../features/algo/StrategyConfig';
import SignalFeed from '../features/algo/SignalFeed';
import ExecutionReport from '../features/algo/ExecutionReport';
import './Algo.css';

export default function Algo() {
  return (
    <AppLayout>
      <div className="algo-page">
        <div className="algo-page__header">
          <div>
            <h1 className="algo-page__title">Algo Engine</h1>
            <p className="algo-page__subtitle">
              Automated strategy analysis — signals logged only, no live order execution
            </p>
          </div>
        </div>

        <div className="algo-page__grid">
          <div className="algo-page__left">
            <AlgoEngine />
            <StrategyConfig />
          </div>
          <div className="algo-page__right">
            <SignalFeed />
            <ExecutionReport />
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
