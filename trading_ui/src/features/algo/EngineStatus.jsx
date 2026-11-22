import { useState, useEffect, useCallback } from 'react';
import { Badge, Spinner } from '../../design-system';
import { getAlgoStatus, runAlgoCycle } from '../../services/api';
import './EngineStatus.css';

const POLL_INTERVAL = 8000; // 8 seconds
const INTERVAL_OPTIONS = [
  { label: '1 Min', value: 'minute' },
  { label: '3 Min', value: '3minute' },
  { label: '5 Min', value: '5minute' },
  { label: '15 Min', value: '15minute' },
  { label: '30 Min', value: '30minute' },
  { label: '1 Hour', value: '60minute' },
  { label: '1 Day', value: 'day' },
  { label: '1 Week', value: 'week' },
  { label: '1 Month', value: 'month' },
];

const toDateTimeLocal = (d) => {
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/**
 * EngineStatus component
 * 
 * Shows algo engine scheduler state, cycle count, and manual run trigger.
 */
export function EngineStatus() {
  const [status, setStatus] = useState(null);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [interval, setIntervalValue] = useState('minute');
  const [startTime, setStartTime] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return toDateTimeLocal(d);
  });
  const [endTime, setEndTime] = useState(() => toDateTimeLocal(new Date()));

  const fetchStatus = useCallback(async () => {
    const { data, error: err } = await getAlgoStatus();
    if (data) {
      setStatus(data);
      setLoading(false);
    }
    if (err) {
      setError(err);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const handleRunCycle = async () => {
    if (!startTime || !endTime) {
      setError('Start time and end time are required.');
      setSuccess('');
      return;
    }

    setRunning(true);
    setError('');
    setSuccess('');
    const { data, error: err } = await runAlgoCycle({
      interval,
      startTime: new Date(startTime).toISOString(),
      endTime: new Date(endTime).toISOString(),
    });
    if (err) setError(err);
    if (data) {
      setSuccess(data.message || 'Strategy run completed successfully.');
    }
    setRunning(false);
    fetchStatus();
  };

  if (loading) {
    return (
      <div className="engine-status">
        <div className="engine-status__header">
          <h3>Engine Status</h3>
        </div>
        <div className="engine-status__loading">
          <Spinner size="sm" />
          <span>Loading...</span>
        </div>
      </div>
    );
  }

  const isRunning = status?.running ?? false;
  const cycles = status?.cycle_count ?? 0;
  const signals = status?.signal_count ?? 0;
  const lastRun = status?.last_run_ist
    ? new Date(status.last_run_ist).toLocaleTimeString('en-IN', { hour12: false })
    : 'Never';

  return (
    <div className="engine-status">
      <div className="engine-status__header">
        <h3>Engine Status</h3>
        <Badge variant={isRunning ? 'success' : 'default'} size="sm">
          {isRunning ? 'RUNNING' : 'IDLE'}
        </Badge>
      </div>

      <div className="engine-status__stats">
        <div className="engine-status__stat">
          <span className="engine-status__stat-label">Cycles Run</span>
          <span className="engine-status__stat-value">{cycles}</span>
        </div>
        <div className="engine-status__stat">
          <span className="engine-status__stat-label">Signals</span>
          <span className="engine-status__stat-value">{signals}</span>
        </div>
        <div className="engine-status__stat">
          <span className="engine-status__stat-label">Last Run</span>
          <span className="engine-status__stat-value engine-status__stat-value--small">
            {lastRun}
          </span>
        </div>
      </div>

      <div className="engine-status__run-config">
        <label htmlFor="engine-interval">Interval</label>
        <select
          id="engine-interval"
          className="engine-status__control"
          value={interval}
          onChange={(e) => setIntervalValue(e.target.value)}
        >
          {INTERVAL_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        <div className="engine-status__time-grid">
          <div>
            <label htmlFor="engine-start-time">Start Time</label>
            <input
              id="engine-start-time"
              className="engine-status__control"
              type="datetime-local"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              required
            />
          </div>
          <div>
            <label htmlFor="engine-end-time">End Time</label>
            <input
              id="engine-end-time"
              className="engine-status__control"
              type="datetime-local"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              required
            />
          </div>
        </div>
      </div>

      <button
        className="engine-status__btn"
        onClick={handleRunCycle}
        disabled={running}
      >
        {running ? 'Running...' : 'Run Cycle Now'}
      </button>

      {error && <div className="engine-status__error">{error}</div>}
      {success && <div className="engine-status__success">{success}</div>}
    </div>
  );
}
