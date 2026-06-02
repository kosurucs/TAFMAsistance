import { useState } from 'react';
import { researchAnalyze } from '../../services/api';
import { Badge, Card, Spinner } from '../../design-system';
import './ResearchPanel.css';

function FundamentalRow({ label, value }) {
  if (value == null) return null;
  return (
    <div className="research-panel__row">
      <span className="research-panel__row-label">{label}</span>
      <span className="research-panel__row-value">{value}</span>
    </div>
  );
}

function ActionBadge({ action }) {
  const variant = action === 'BUY' ? 'up' : action === 'SELL' ? 'down' : 'neutral';
  return <Badge variant={variant}>{action}</Badge>;
}

function SourceTag({ source }) {
  return <span className="research-panel__source-tag">{source}</span>;
}

function ShareholdingBar({ promoter, institutional, publicPct }) {
  return (
    <div className="research-panel__holding-bar-wrap">
      <div className="research-panel__holding-bar">
        <div
          className="research-panel__holding-segment research-panel__holding-segment--promoter"
          style={{ width: `${promoter || 0}%` }}
          title={`Promoter: ${promoter?.toFixed(1)}%`}
        />
        <div
          className="research-panel__holding-segment research-panel__holding-segment--inst"
          style={{ width: `${institutional || 0}%` }}
          title={`Institutional: ${institutional?.toFixed(1)}%`}
        />
        <div
          className="research-panel__holding-segment research-panel__holding-segment--public"
          style={{ width: `${publicPct || 0}%` }}
          title={`Public: ${publicPct?.toFixed(1)}%`}
        />
      </div>
      <div className="research-panel__holding-legend">
        <span className="research-panel__holding-dot research-panel__holding-dot--promoter" />
        Promoter {promoter?.toFixed(1)}%
        <span className="research-panel__holding-dot research-panel__holding-dot--inst" />
        Institutional {institutional?.toFixed(1)}%
        <span className="research-panel__holding-dot research-panel__holding-dot--public" />
        Public {publicPct?.toFixed(1)}%
      </div>
    </div>
  );
}

export function ResearchPanel() {
  const [symbol, setSymbol] = useState('');
  const [exchange, setExchange] = useState('NSE');
  const [deep, setDeep] = useState(true);
  const [useCache, setUseCache] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const run = async () => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError(null);
    setResult(null);

    const { data, error: err } = await researchAnalyze(sym, exchange, deep, useCache);
    setLoading(false);
    if (err) {
      setError(err);
    } else {
      setResult(data);
    }
  };

  const fund  = result?.fundamentals || {};
  const share = result?.shareholding || {};
  const fins  = result?.financials   || {};
  const techs = result?.technicals   || {};

  return (
    <div className="research-panel">
      {/* ── Input row ── */}
      <div className="research-panel__input-row">
        <input
          className="research-panel__symbol-input"
          placeholder="Symbol, e.g. TATACAPITAL"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
        />
        <select
          className="research-panel__exchange-select"
          value={exchange}
          onChange={(e) => setExchange(e.target.value)}
        >
          <option value="NSE">NSE</option>
          <option value="BSE">BSE</option>
        </select>
        <label className="research-panel__toggle">
          <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} />
          &nbsp;Deep (screener.in)
        </label>
        <label className="research-panel__toggle">
          <input type="checkbox" checked={useCache} onChange={(e) => setUseCache(e.target.checked)} />
          &nbsp;Use cache
        </label>
        <button className="research-panel__run-btn" onClick={run} disabled={loading || !symbol.trim()}>
          {loading ? <Spinner size="sm" /> : 'Analyse'}
        </button>
      </div>

      {error && <p className="research-panel__error">⚠ {error}</p>}

      {result && (
        <div className="research-panel__results">
          {/* ── LLM Decision ── */}
          <Card title="AI Decision" className="research-panel__card">
            <div className="research-panel__decision-row">
              <ActionBadge action={result.action || 'WAIT'} />
              {result.confidence != null && (
                <Badge variant="accent">{result.confidence}% confidence</Badge>
              )}
              {result.from_knowledge_cache && <Badge variant="neutral">cached</Badge>}
              {result.weights_cached === false && (
                <Badge variant="down">weights downloading…</Badge>
              )}
            </div>
            {result.reason && (
              <p className="research-panel__reason">{result.reason}</p>
            )}
            {result.suggested_sl != null && (
              <p className="research-panel__levels">
                SL ₹{result.suggested_sl}&nbsp;&nbsp;|&nbsp;&nbsp;TP ₹{result.suggested_tp}
              </p>
            )}
            <div className="research-panel__sources">
              {(result.sources_used || []).map((s) => <SourceTag key={s} source={s} />)}
            </div>
          </Card>

          {/* ── Company Overview ── */}
          {fund.company_name && (
            <Card title="Company Overview" className="research-panel__card">
              <p className="research-panel__company-name">{fund.company_name}</p>
              {fund.description && (
                <p className="research-panel__description">{fund.description}</p>
              )}
              <div className="research-panel__grid">
                <FundamentalRow label="Sector"        value={fund.sector} />
                <FundamentalRow label="Industry"      value={fund.industry} />
                <FundamentalRow label="Market Cap"    value={fund.market_cap ? `₹${(fund.market_cap / 1e7).toFixed(0)} Cr` : null} />
                <FundamentalRow label="52W High"      value={fund.week_52_high ? `₹${fund.week_52_high}` : null} />
                <FundamentalRow label="52W Low"       value={fund.week_52_low  ? `₹${fund.week_52_low}`  : null} />
                <FundamentalRow label="Analyst Rating" value={fund.analyst_rating} />
                <FundamentalRow label="Target Price"  value={fund.target_mean_price ? `₹${fund.target_mean_price}` : null} />
              </div>
            </Card>
          )}

          {/* ── Valuation Ratios ── */}
          {(fund.pe_ratio != null || fund.pb_ratio != null) && (
            <Card title="Valuation" className="research-panel__card">
              <div className="research-panel__grid">
                <FundamentalRow label="P/E Ratio"     value={fund.pe_ratio} />
                <FundamentalRow label="P/B Ratio"     value={fund.pb_ratio} />
                <FundamentalRow label="EPS"           value={fund.eps} />
                <FundamentalRow label="Dividend Yield" value={fund.dividend_yield != null ? `${(fund.dividend_yield * 100).toFixed(2)}%` : null} />
                <FundamentalRow label="ROE"           value={fund.roe != null ? `${(fund.roe * 100).toFixed(1)}%` : null} />
                <FundamentalRow label="ROA"           value={fund.roa != null ? `${(fund.roa * 100).toFixed(1)}%` : null} />
                <FundamentalRow label="Profit Margin" value={fund.profit_margin != null ? `${(fund.profit_margin * 100).toFixed(1)}%` : null} />
                <FundamentalRow label="Debt/Equity"   value={fund.debt_to_equity} />
                <FundamentalRow label="Beta"          value={fund.beta} />
              </div>
            </Card>
          )}

          {/* ── Shareholding ── */}
          {(share.promoter_pct != null) && (
            <Card title="Shareholding Pattern" className="research-panel__card">
              <ShareholdingBar
                promoter={share.promoter_pct}
                institutional={share.institutional_pct}
                publicPct={share.public_pct}
              />
              {share.top_holders?.length > 0 && (
                <table className="research-panel__table">
                  <thead>
                    <tr><th>Holder</th><th>% Out</th></tr>
                  </thead>
                  <tbody>
                    {share.top_holders.map((h, i) => (
                      <tr key={i}>
                        <td>{h.holder}</td>
                        <td>{h.pct_out != null ? `${(h.pct_out * 100).toFixed(2)}%` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          )}

          {/* ── Quarterly Financials ── */}
          {fins.quarterly_revenue?.length > 0 && (
            <Card title="Quarterly Financials" className="research-panel__card">
              <table className="research-panel__table">
                <thead>
                  <tr><th>Period</th><th>Revenue</th><th>Net Profit</th></tr>
                </thead>
                <tbody>
                  {fins.quarterly_revenue.map((rev, i) => {
                    const profit = fins.quarterly_profit?.[i];
                    return (
                      <tr key={rev.period}>
                        <td>{rev.period}</td>
                        <td>₹{(rev.value / 1e7).toFixed(0)} Cr</td>
                        <td>{profit ? `₹${(profit.value / 1e7).toFixed(0)} Cr` : '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          )}

          {/* ── Technical Indicators ── */}
          {Object.keys(techs).length > 0 && (
            <Card title="Technical Indicators" className="research-panel__card">
              <div className="research-panel__grid">
                <FundamentalRow label="Close"      value={techs.close ? `₹${techs.close?.toFixed(2)}` : null} />
                <FundamentalRow label="RSI"        value={techs.rsi?.toFixed(1)} />
                <FundamentalRow label="Trend"      value={techs.trend} />
                <FundamentalRow label="MACD"       value={techs.macd_label} />
                <FundamentalRow label="BB Signal"  value={techs.bb_signal} />
                <FundamentalRow label="ATR"        value={techs.atr} />
                <FundamentalRow label="VWAP"       value={techs.vwap ? `₹${techs.vwap?.toFixed(2)}` : null} />
                <FundamentalRow label="Stochastic" value={techs.stoch_signal} />
              </div>
            </Card>
          )}

          {/* ── screener.in extras ── */}
          {result.screener && Object.keys(result.screener).length > 0 && (
            <Card title="screener.in Data" className="research-panel__card">
              <div className="research-panel__grid">
                {Object.entries(result.screener).map(([k, v]) => (
                  <FundamentalRow key={k} label={k.replace(/_/g, ' ')} value={v} />
                ))}
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
