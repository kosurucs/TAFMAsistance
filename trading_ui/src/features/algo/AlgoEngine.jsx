import { useState, useEffect, useCallback } from 'react';
import { getAlgoStatus, runAlgoCycle } from '../../services/api';
import './AlgoEngine.css';

const POLL_INTERVAL = 10_000;

export default function AlgoEngine() {
  const [status, setStatus] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const fetchStatus = useCallback(async () => {
    const { data, error: err } = await getAlgoStatus();
    if (data) setStatus(data);
    if (err) setError(err);
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const handleRun = async () => {
    setRunning(true);
    setError('');
    const { data, error: err } = await runAlgoCycle();
    if (err) setError(err);
    if (data) {
      setStatus(prev => ({
        ...prev,
        cycle_count: data.cycle_count,
        signal_count: (prev?.signal_count || 0) + data.signals_generated,
      }));
    }
    setRunning(false);
    fetchStatus();
  };

  const isEngineRunning = status?.running ?? false;
  const cycles = status?.cycle_count ?? 0;
  const signals = status?.signal_count ?? 0;
  const lastRun = status?.last_run_ist
    ? new Date(status.last_run_ist).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    : '—';
  const watchlist = status?.watchlist ?? [];

  return (
    <div className="algo-engine">
      <h2 className="algo-engine__title">
        <span className={`algo-engine__status-dot${isEngineRunning ? ' algo-engine__status-dot--running' : ''}`} />
        Engine Status
      </h2>

      <div className="algo-engine__stat-row">
        <div className="algo-engine__stat">
          <div className="algo-engine__stat-label">Cycles Run</div>
          <div className="algo-engine__stat-value">{cycles}</div>
        </div>
        <div className="algo-engine__stat">
          <div className="algo-engine__stat-label">Signals</div>
          <div className="algo-engine__stat-value">{signals}</div>
        </div>
      </div>

      <div className="algo-engine__watchlist">
        <strong>Watchlist: </strong>
        {watchlist.length > 0 ? watchlist.join(', ') : 'No symbols configured'}
      </div>

      <button
        className="algo-engine__btn"
        onClick={handleRun}
        disabled={running}
      >
        {running ? 'Running cycle…' : 'Run Cycle Now'}
      </button>

      {error && <div className="algo-engine__error">{error}</div>}

      {status?.last_run_ist && (
        <div className="algo-engine__last-run">Last run: {lastRun} IST</div>
      )}

      <div className="algo-engine__analysis-note">
        Analysis-only mode — no orders placed
      </div>
    </div>
  );
}
