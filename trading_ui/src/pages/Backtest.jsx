import { useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card, Badge, Spinner } from '../design-system';
import { useBacktestStore } from '../store';
import { useMarketStore } from '../store';
import { SymbolSearch } from '../features/trading/SymbolSearch';
import { WalkForwardChart } from '../features/backtest/WalkForwardChart';
import { CommissionBreakdown } from '../features/backtest/CommissionBreakdown';
import { startBacktest, getBacktestStatus, getBacktestResult } from '../services/api';
import './Backtest.css';

const YEAR_OPTIONS = [
  { label: '1Y', value: 1 },
  { label: '3Y', value: 3 },
  { label: '5Y', value: 5 },
  { label: '10Y', value: 10 },
  { label: '15Y', value: 15 },
  { label: '20Y', value: 20 },
];

const STRATEGY_OPTIONS = [
  { label: 'All', value: 'all' },
  { label: 'Trend', value: 'TREND_FOLLOWING' },
  { label: 'Momentum', value: 'MOMENTUM' },
  { label: 'Mean Rev', value: 'MEAN_REVERSION' },
  { label: 'Price Action', value: 'PRICE_ACTION' },
];

const EXCHANGE_OPTIONS = [
  { label: 'NSE', value: 'NSE' },
  { label: 'BSE', value: 'BSE' },
  { label: 'NFO', value: 'NFO' },
  { label: 'MCX', value: 'MCX' },
  { label: 'CDS', value: 'CDS' },
];

const INSTRUMENT_OPTIONS = [
  { label: 'SPOT', value: 'SPOT' },
  { label: 'INTRA', value: 'INTRADAY' },
  { label: 'FUT', value: 'FUTURES' },
  { label: 'OPT', value: 'OPTIONS' },
];

function WinBar({ pct }) {
  const pctSafe = Math.min(100, Math.max(0, pct || 0));
  const color = pctSafe >= 55 ? 'var(--color-up)' : pctSafe >= 40 ? '#f59e0b' : 'var(--color-down)';
  return (
    <div className="bt-winbar">
      <div className="bt-winbar-fill" style={{ width: `${pctSafe}%`, background: color }} />
      <span className="bt-winbar-label" style={{ color }}>{pctSafe.toFixed(1)}%</span>
    </div>
  );
}

export default function Backtest() {
  const { selectedSymbol } = useMarketStore();
  const [years, setYears] = useState(20);
  const [strategyFilter, setStrategyFilter] = useState('all');
  const [builderOpen, setBuilderOpen] = useState(false);

  const {
    status, progress, result, error,
    exchange, setExchange,
    instrument, setInstrument,
    walkForward, setWalkForward,
    customStrategy, setCustomStrategy,
    setJobId, setStatus, setProgress, setResult, setError, reset,
  } = useBacktestStore();

  async function runBacktest() {
    reset();
    const options = {
      strategies: strategyFilter,
      exchange,
      instrument,
      walk_forward: walkForward,
    };
    if (customStrategy.enabled) {
      const filter = strategyFilter === 'all'
        ? 'TREND_FOLLOWING,MEAN_REVERSION,MOMENTUM,PRICE_ACTION,CUSTOM'
        : `${strategyFilter},CUSTOM`;
      options.strategies = filter;
      options.rsiOversold = customStrategy.rsiOversold;
      options.rsiOverbought = customStrategy.rsiOverbought;
      options.emaFast = customStrategy.emaFast;
      options.emaSlow = customStrategy.emaSlow;
      options.atrMultSl = customStrategy.atrMultSl;
      options.atrMultTp = customStrategy.atrMultTp;
      options.volumeConfirm = customStrategy.volumeConfirm;
    }

    const { data, error: err } = await startBacktest(selectedSymbol, years, options);
    if (err) { setError(err); return; }

    const id = data.job_id;
    setJobId(id);
    setStatus('RUNNING');

    const poll = setInterval(async () => {
      const { data: sd } = await getBacktestStatus(id);
      if (!sd) return;
      setProgress(sd.progress || 0);
      if (sd.status === 'COMPLETE') {
        clearInterval(poll);
        const { data: rd } = await getBacktestResult(id);
        if (rd?.result) { setResult(rd.result); setStatus('COMPLETE'); }
      } else if (sd.status === 'ERROR') {
        clearInterval(poll);
        setError(sd.error || 'Backtest failed');
        setStatus('ERROR');
      }
    }, 3000);
  }

  function numInput(field, step = 1, min = 1) {
    return (
      <input
        className="bt-num-input"
        type="number"
        step={step}
        min={min}
        value={customStrategy[field]}
        onChange={(e) => setCustomStrategy({ [field]: step === 1 ? parseInt(e.target.value) : parseFloat(e.target.value) })}
      />
    );
  }

  return (
    <AppLayout>
      <div className="bt">

        {/* ── Toolbar ─────────────────────────────────────────── */}
        <div className="bt-toolbar">
          <SymbolSearch />

          <span className="bt-sep">|</span>
          <span className="bt-label">DATA</span>
          <span className="bt-sep">|</span>
          <div className="bt-pills">
            {YEAR_OPTIONS.map((opt, idx) => (
              <span key={opt.value} className="bt-pill-group">
                {idx > 0 && <span className="bt-pipe">|</span>}
                <button
                  type="button"
                  className={`bt-pill ${years === opt.value ? 'bt-pill--active' : ''}`}
                  onClick={() => setYears(opt.value)}
                >{opt.label}</button>
              </span>
            ))}
          </div>

          <span className="bt-sep">|</span>
          <span className="bt-label">STRATEGY</span>
          <span className="bt-sep">|</span>
          <div className="bt-pills">
            {STRATEGY_OPTIONS.map((opt, idx) => (
              <span key={opt.value} className="bt-pill-group">
                {idx > 0 && <span className="bt-pipe">|</span>}
                <button
                  type="button"
                  className={`bt-pill ${strategyFilter === opt.value ? 'bt-pill--active' : ''}`}
                  onClick={() => setStrategyFilter(opt.value)}
                >{opt.label}</button>
              </span>
            ))}
          </div>

          <span className="bt-sep">|</span>
          <span className="bt-label">EXCHANGE</span>
          <span className="bt-sep">|</span>
          <div className="bt-pills">
            {EXCHANGE_OPTIONS.map((opt, idx) => (
              <span key={opt.value} className="bt-pill-group">
                {idx > 0 && <span className="bt-pipe">|</span>}
                <button
                  type="button"
                  className={`bt-pill ${exchange === opt.value ? 'bt-pill--active' : ''}`}
                  onClick={() => setExchange(opt.value)}
                >{opt.label}</button>
              </span>
            ))}
          </div>

          <span className="bt-sep">|</span>
          <span className="bt-label">INSTRUMENT</span>
          <span className="bt-sep">|</span>
          <div className="bt-pills">
            {INSTRUMENT_OPTIONS.map((opt, idx) => (
              <span key={opt.value} className="bt-pill-group">
                {idx > 0 && <span className="bt-pipe">|</span>}
                <button
                  type="button"
                  className={`bt-pill ${instrument === opt.value ? 'bt-pill--active' : ''}`}
                  onClick={() => setInstrument(opt.value)}
                >{opt.label}</button>
              </span>
            ))}
          </div>

          <span className="bt-sep">|</span>
          <button
            type="button"
            className={`bt-pill bt-wf-toggle ${walkForward ? 'bt-pill--active bt-wf-toggle--on' : ''}`}
            onClick={() => setWalkForward(!walkForward)}
            title="Run anchored walk-forward validation on the winning strategy"
          >
            WF {walkForward ? 'ON' : 'OFF'}
          </button>

          <button
            className={`bt-run-btn ${status === 'RUNNING' ? 'bt-run-btn--running' : ''}`}
            onClick={runBacktest}
            disabled={status === 'RUNNING'}
            type="button"
          >
            {status === 'RUNNING' ? <><Spinner size="sm" /> Running…</> : '▶ Run Backtest'}
          </button>
        </div>

        {/* ── Custom Strategy Builder ──────────────────────────── */}
        <div className="bt-builder">
          <button
            type="button"
            className="bt-builder-toggle"
            onClick={() => setBuilderOpen(!builderOpen)}
          >
            <span className={`bt-builder-chevron ${builderOpen ? 'bt-builder-chevron--open' : ''}`}>›</span>
            Custom Strategy Builder
            {customStrategy.enabled && <span className="bt-builder-active-badge">ACTIVE</span>}
          </button>

          {builderOpen && (
            <div className="bt-builder-body">
              <div className="bt-builder-row">
                <span className="bt-builder-section-label">RSI</span>
                <label className="bt-builder-field">
                  Oversold {numInput('rsiOversold', 1, 10)}
                </label>
                <label className="bt-builder-field">
                  Overbought {numInput('rsiOverbought', 1, 50)}
                </label>
              </div>
              <div className="bt-builder-row">
                <span className="bt-builder-section-label">EMA</span>
                <label className="bt-builder-field">
                  Fast {numInput('emaFast', 1, 3)}
                </label>
                <label className="bt-builder-field">
                  Slow {numInput('emaSlow', 1, 5)}
                </label>
              </div>
              <div className="bt-builder-row">
                <span className="bt-builder-section-label">ATR</span>
                <label className="bt-builder-field">
                  SL mult {numInput('atrMultSl', 0.1, 0.5)}
                </label>
                <label className="bt-builder-field">
                  TP mult {numInput('atrMultTp', 0.1, 1.0)}
                </label>
              </div>
              <div className="bt-builder-row">
                <label className="bt-builder-checkbox">
                  <input
                    type="checkbox"
                    checked={customStrategy.volumeConfirm}
                    onChange={(e) => setCustomStrategy({ volumeConfirm: e.target.checked })}
                  />
                  Volume confirmation
                </label>
                <label className="bt-builder-checkbox bt-builder-checkbox--enable">
                  <input
                    type="checkbox"
                    checked={customStrategy.enabled}
                    onChange={(e) => setCustomStrategy({ enabled: e.target.checked })}
                  />
                  Include in next backtest
                </label>
              </div>
              <p className="bt-builder-hint">
                Signal: EMA{customStrategy.emaFast} crosses EMA{customStrategy.emaSlow} +
                RSI not past {customStrategy.rsiOversold}/{customStrategy.rsiOverbought}
                {customStrategy.volumeConfirm ? ' + volume ≥ 1.2× avg' : ''} →
                SL {customStrategy.atrMultSl}×ATR / TP {customStrategy.atrMultTp}×ATR
              </p>
            </div>
          )}
        </div>

        {/* ── Progress / Error ─────────────────────────────────── */}
        {status === 'RUNNING' && (
          <div className="bt-progress">
            <div className="bt-progress-bar" style={{ width: `${progress}%` }} />
            <span>{progress}%</span>
          </div>
        )}
        {error && <p className="bt-error">{error}</p>}

        {/* ── Results ──────────────────────────────────────────── */}
        {result && (
          <div className="bt-results">

            {/* Recommendation banner */}
            <div className="bt-rec-banner">
              <div className="bt-rec-left">
                <span className="bt-rec-label">Best Strategy</span>
                <span className="bt-rec-strategy">{result.recommended_strategy?.replace(/_/g, ' ')}</span>
                <span className="bt-rec-tf">{result.recommended_timeframe}</span>
                <span className="bt-rec-meta">{result.years_analysed}y of data · {result.symbol}</span>
              </div>
              <div className="bt-rec-metrics">
                <div className="bt-rec-metric">
                  <span>Win Rate</span>
                  <strong style={{ color: 'var(--color-up)' }}>
                    {result.recommended_win_rate?.toFixed(1)}%
                  </strong>
                </div>
                <div className="bt-rec-metric">
                  <span>Avg R:R</span>
                  <strong>{result.recommended_rr?.toFixed(2)}×</strong>
                </div>
              </div>
            </div>

            {/* Entry Plan */}
            {result.entry_plan && Object.keys(result.entry_plan).length > 0 && (
              <Card title="Entry Plan" className="bt-entry-plan">
                <div className="bt-entry-grid">
                  {Object.entries(result.entry_plan).map(([k, v]) => (
                    <div key={k} className="bt-entry-row">
                      <span className="bt-entry-key">{k.replace(/_/g, ' ')}</span>
                      <span className="bt-entry-val">{String(v)}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Strategy cards */}
            <div className="bt-strategy-grid">
              {result.strategy_reports?.map((r, i) => (
                <div
                  key={i}
                  className={`bt-sc ${r.strategy_name === result.recommended_strategy && r.timeframe === result.recommended_timeframe ? 'bt-sc--best' : ''}`}
                >
                  <div className="bt-sc-header">
                    <h4>{r.strategy_name.replace(/_/g, ' ')}</h4>
                    <Badge variant="neutral">{r.timeframe}</Badge>
                  </div>

                  <WinBar pct={r.win_rate_pct} />

                  <div className="bt-sc-metrics">
                    <div><span>Trades</span><strong>{r.total_trades}</strong></div>
                    <div><span>Wins</span><strong style={{ color: 'var(--color-up)' }}>{r.winning_trades}</strong></div>
                    <div><span>Avg R:R</span><strong>{r.avg_rr?.toFixed(2)}×</strong></div>
                    <div><span>Sharpe</span><strong>{r.sharpe_ratio?.toFixed(2)}</strong></div>
                    <div><span>Max DD</span><strong style={{ color: 'var(--color-down)' }}>{r.max_drawdown_pct?.toFixed(1)}%</strong></div>
                    <div><span>Gross PnL</span>
                      <strong style={{ color: r.total_pnl >= 0 ? 'var(--color-up)' : 'var(--color-down)' }}>
                        {(r.gross_total_pnl ?? r.total_pnl)?.toFixed(1)}%
                      </strong>
                    </div>
                  </div>

                  {/* Commission-aware net PnL row */}
                  {r.net_total_pnl != null && (
                    <div className="bt-sc-net-row">
                      <div className="bt-sc-net-item">
                        <span>Net PnL</span>
                        <strong style={{ color: r.net_total_pnl >= 0 ? 'var(--color-up)' : 'var(--color-down)' }}>
                          {r.net_total_pnl.toFixed(1)}%
                        </strong>
                      </div>
                      <div className="bt-sc-net-item">
                        <span>Commission</span>
                        <strong style={{ color: 'var(--color-down)' }}>
                          -{r.total_commission_pct?.toFixed(2)}%
                        </strong>
                      </div>
                      {r.commission_segment && (
                        <span className="bt-sc-seg-badge">
                          {r.commission_segment.replace(/_/g, ' ')}
                        </span>
                      )}
                    </div>
                  )}

                  {/* Walk-forward chart (only shown when enabled) */}
                  {r.walk_forward && (
                    <WalkForwardChart report={r.walk_forward} />
                  )}

                  {r.why_it_works && Object.keys(r.why_it_works).length > 0 && (
                    <div className="bt-sc-why">
                      <span className="bt-sc-why-label">Why it works</span>
                      <div className="bt-sc-tags">
                        {Object.entries(r.why_it_works).map(([sig, pct]) => (
                          <span key={sig} className="bt-sc-tag">
                            {sig.replace(/_/g, ' ')} {pct}%
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="bt-sc-periods">
                    <span className="bt-sc-period bt-sc-period--up">▲ {r.best_period}</span>
                    <span className="bt-sc-period bt-sc-period--dn">▼ {r.worst_period}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Commission breakdown table */}
            {result.strategy_reports?.some((r) => r.net_total_pnl != null) && (
              <CommissionBreakdown reports={result.strategy_reports} />
            )}

          </div>
        )}
      </div>
    </AppLayout>
  );
}

