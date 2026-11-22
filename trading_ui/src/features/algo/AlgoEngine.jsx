import { useState, useEffect, useCallback, useRef } from 'react';
import { getAlgoStatus, runAlgoCycle, searchSymbols } from '../../services/api';
import { useMarketStore } from '../../store';
import './AlgoEngine.css';

const POLL_INTERVAL = 10_000;
const SEARCH_DEBOUNCE_MS = 300;
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

export default function AlgoEngine() {
  const { selectedSymbol } = useMarketStore();
  const [status, setStatus] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [runSymbol, setRunSymbol] = useState(selectedSymbol || '');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [interval, setIntervalValue] = useState('minute');
  const [startTime, setStartTime] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return toDateTimeLocal(d);
  });
  const [endTime, setEndTime] = useState(() => toDateTimeLocal(new Date()));
  const debounceRef = useRef(null);

  useEffect(() => {
    if (!runSymbol && selectedSymbol) {
      setRunSymbol(selectedSymbol);
    }
  }, [selectedSymbol, runSymbol]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setResults([]);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      const { data } = await searchSymbols(query.trim());
      setResults(data?.symbols || []);
      setSearching(false);
    }, SEARCH_DEBOUNCE_MS);

    return () => clearTimeout(debounceRef.current);
  }, [query]);

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
    if (!startTime || !endTime) {
      setError('Start time and end time are required.');
      setSuccess('');
      return;
    }

    setRunning(true);
    setError('');
    setSuccess('');
    const payload = {
      symbols: runSymbol ? [runSymbol] : undefined,
      interval,
      startTime: new Date(startTime).toISOString(),
      endTime: new Date(endTime).toISOString(),
    };
    const { data, error: err } = await runAlgoCycle(payload);
    if (err) setError(err);
    if (data) {
      setStatus(prev => ({
        ...prev,
        cycle_count: data.cycle_count,
        signal_count: (prev?.signal_count || 0) + data.signals_generated,
      }));
      setSuccess(
        `${data.message || 'Strategy run completed.'} Signals: ${data.signals_generated}`
      );
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

      <div className="algo-engine__lookup">
        <label className="algo-engine__lookup-label" htmlFor="algo-symbol-search">Run Symbol</label>
        <input
          id="algo-symbol-search"
          type="text"
          className="algo-engine__lookup-input"
          value={query}
          onChange={(e) => setQuery(e.target.value.toUpperCase())}
          placeholder="Search symbol (e.g. RELIANCE)"
        />
        <div className="algo-engine__lookup-meta">
          {searching ? 'Searching…' : runSymbol ? `Selected: ${runSymbol}` : 'No symbol selected'}
        </div>
        {results.length > 0 && (
          <div className="algo-engine__lookup-results">
            {results.slice(0, 6).map((item) => (
              <button
                key={item.instrument_token}
                className="algo-engine__lookup-item"
                onClick={() => {
                  setRunSymbol(item.tradingsymbol);
                  setQuery(item.tradingsymbol);
                  setResults([]);
                }}
              >
                <span>{item.tradingsymbol}</span>
                <span className="algo-engine__lookup-name">{item.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="algo-engine__run-config">
        <label className="algo-engine__lookup-label" htmlFor="algo-interval">Interval</label>
        <select
          id="algo-interval"
          className="algo-engine__lookup-input"
          value={interval}
          onChange={(e) => setIntervalValue(e.target.value)}
        >
          {INTERVAL_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        <div className="algo-engine__time-grid">
          <div>
            <label className="algo-engine__lookup-label" htmlFor="algo-start-time">Start Time</label>
            <input
              id="algo-start-time"
              type="datetime-local"
              className="algo-engine__lookup-input"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="algo-engine__lookup-label" htmlFor="algo-end-time">End Time</label>
            <input
              id="algo-end-time"
              type="datetime-local"
              className="algo-engine__lookup-input"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              required
            />
          </div>
        </div>
      </div>

      <button
        className="algo-engine__btn"
        onClick={handleRun}
        disabled={running}
      >
        {running ? 'Running cycle…' : 'Run Cycle Now'}
      </button>

      {error && <div className="algo-engine__error">{error}</div>}
      {success && <div className="algo-engine__success">{success}</div>}

      {status?.last_run_ist && (
        <div className="algo-engine__last-run">Last run: {lastRun} IST</div>
      )}

      <div className="algo-engine__analysis-note">
        Analysis-only mode — no orders placed
      </div>
    </div>
  );
}
