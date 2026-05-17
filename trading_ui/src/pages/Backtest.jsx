import { useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card, Button, Badge, Spinner } from '../design-system';
import { useBacktestStore } from '../store';
import { startBacktest, getBacktestStatus, getBacktestResult } from '../services/api';
import './Backtest.css';

export default function Backtest() {
  const [symbol, setSymbol] = useState('RELIANCE');
  const [years, setYears] = useState(20);
  const { jobId, status, progress, result, error, setJobId, setStatus, setProgress, setResult, setError, reset } = useBacktestStore();
  
  async function runBacktest() {
    reset();
    const { data, error: err } = await startBacktest(symbol, years);
    if (err) { 
      setError(err); 
      return; 
    }
    const id = data.job_id;
    setJobId(id);
    setStatus('RUNNING');
    
    // Poll for completion
    const poll = setInterval(async () => {
      const { data: statusData } = await getBacktestStatus(id);
      if (!statusData) return;
      setProgress(statusData.progress || 0);
      if (statusData.status === 'COMPLETE') {
        clearInterval(poll);
        const { data: resultData } = await getBacktestResult(id);
        if (resultData?.result) { 
          setResult(resultData.result); 
          setStatus('COMPLETE'); 
        }
      } else if (statusData.status === 'ERROR') {
        clearInterval(poll);
        setError(statusData.error || 'Backtest failed');
        setStatus('ERROR');
      }
    }, 3000);
  }
  
  return (
    <AppLayout>
      <div className="backtest">
        <Card title="Multi-Strategy Backtest" className="backtest__config">
          <div className="backtest__form">
            <div className="backtest__field">
              <label>Symbol</label>
              <input 
                className="backtest__input" 
                value={symbol} 
                onChange={e => setSymbol(e.target.value.toUpperCase())} 
                placeholder="RELIANCE" 
              />
            </div>
            <div className="backtest__field">
              <label>Years of History</label>
              <select className="backtest__input" value={years} onChange={e => setYears(Number(e.target.value))}>
                {[1,3,5,10,15,20].map(y => <option key={y} value={y}>{y} years</option>)}
              </select>
            </div>
            <Button onClick={runBacktest} disabled={status === 'RUNNING'}>
              {status === 'RUNNING' ? <><Spinner size="sm" /> Running...</> : 'Run Full Backtest'}
            </Button>
          </div>
          {status === 'RUNNING' && (
            <div className="backtest__progress">
              <div className="backtest__progress-bar" style={{ width: `${progress}%` }} />
              <span>{progress}%</span>
            </div>
          )}
          {error && <p className="backtest__error">{error}</p>}
        </Card>
        
        {result && (
          <div className="backtest__results">
            <Card title={`Recommendation for ${result.symbol}`} className="backtest__recommendation">
              <div className="backtest__rec-grid">
                <div><span className="backtest__label">Best Strategy</span><strong>{result.recommended_strategy}</strong></div>
                <div><span className="backtest__label">Timeframe</span><strong>{result.recommended_timeframe}</strong></div>
                <div><span className="backtest__label">Win Rate</span><strong className="text--up">{result.recommended_win_rate?.toFixed(1)}%</strong></div>
                <div><span className="backtest__label">Avg R:R</span><strong>{result.recommended_rr?.toFixed(2)}:1</strong></div>
              </div>
              {result.entry_plan && (
                <div className="backtest__entry-plan">
                  <h4>Entry Plan</h4>
                  {Object.entries(result.entry_plan).map(([k,v]) => (
                    <div key={k} className="backtest__entry-row">
                      <span className="backtest__label">{k.replace(/_/g,' ')}</span>
                      <span>{String(v)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            
            <div className="backtest__strategy-grid">
              {result.strategy_reports?.map((r, i) => (
                <Card key={i} className="strategy-card">
                  <div className="strategy-card__header">
                    <h4>{r.strategy_name}</h4>
                    <Badge variant={r.win_rate_pct >= 55 ? 'up' : r.win_rate_pct >= 40 ? 'warning' : 'down'}>
                      {r.win_rate_pct?.toFixed(1)}% win
                    </Badge>
                    <Badge variant="neutral">{r.timeframe}</Badge>
                  </div>
                  <div className="strategy-card__metrics">
                    <div><span>Trades</span><strong>{r.total_trades}</strong></div>
                    <div><span>Avg R:R</span><strong>{r.avg_rr?.toFixed(2)}x</strong></div>
                    <div><span>Sharpe</span><strong>{r.sharpe_ratio?.toFixed(2)}</strong></div>
                    <div><span>Max DD</span><strong className="text--down">{r.max_drawdown_pct?.toFixed(1)}%</strong></div>
                  </div>
                  {r.why_it_works && Object.keys(r.why_it_works).length > 0 && (
                    <div className="strategy-card__why">
                      <span className="backtest__label">Why it works:</span>
                      <div className="strategy-card__tags">
                        {Object.entries(r.why_it_works).map(([sig, pct]) => (
                          <Badge key={sig} variant="accent">{sig.replace(/_/g,' ')} {pct}%</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="strategy-card__periods">
                    <p className="text--up">▲ {r.best_period}</p>
                    <p className="text--down">▼ {r.worst_period}</p>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
