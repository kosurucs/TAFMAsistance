import './IndicatorPanel.css'

const TREND_COLOR  = { BULLISH: '#3fb950', BEARISH: '#f85149', NEUTRAL: '#8b949e' }
const BB_COLOR     = { ABOVE_UPPER: '#f85149', BELOW_LOWER: '#3fb950', INSIDE: '#8b949e', INSIDE_BANDS: '#8b949e' }
const MACD_COLOR   = { BULLISH: '#3fb950', BEARISH: '#f85149', NEUTRAL: '#8b949e' }
const STOCH_COLOR  = { OVERBOUGHT: '#f85149', OVERSOLD: '#3fb950', NEUTRAL: '#8b949e' }

function p(v, d = 2) { return Number(v || 0).toFixed(d) }
function rsiColor(v) {
  if (v >= 70) return '#f85149'
  if (v <= 30) return '#3fb950'
  return '#c9d1d9'
}

function Row({ label, value, color }) {
  return (
    <div className="ip-card">
      <span className="ip-label">{label}</span>
      <span className="ip-value" style={color ? { color } : undefined}>{value}</span>
    </div>
  )
}

function Section({ title }) {
  return <div className="ip-section">{title}</div>
}

export default function IndicatorPanel({ indicators: ind }) {
  if (!ind) return null
  const macdUp = (ind.macd_hist || 0) >= 0
  return (
    <div className="indicator-panel">
      <div className="ip-title">Technical Indicators</div>
      <div className="ip-grid">

        <Section title="Price" />
        <Row label="Close"  value={`₹${p(ind.close)}`} />
        <Row label="VWAP"   value={ind.vwap ? `₹${p(ind.vwap)}` : '—'} />
        <Row label="Volume" value={Number(ind.volume || 0).toLocaleString('en-IN')} />

        <Section title="Momentum" />
        <Row
          label="RSI (14)"
          value={`${p(ind.rsi, 1)} ${(ind.rsi||0)>=70?' OB':(ind.rsi||0)<=30?' OS':''}`}
          color={rsiColor(ind.rsi || 0)}
        />
        <Row
          label="Stoch %K"
          value={`${p(ind.stoch_k, 1)} / ${p(ind.stoch_d, 1)}`}
          color={STOCH_COLOR[ind.stoch_signal] || '#c9d1d9'}
        />

        <Section title="Trend / MA" />
        <Row label="EMA 9"   value={`₹${p(ind.ema_fast)}`} />
        <Row label="EMA 21"  value={`₹${p(ind.ema_slow)}`} />
        <Row label="EMA 50"  value={ind.ema_50  ? `₹${p(ind.ema_50)}`  : '—'} />
        <Row label="EMA 200" value={ind.ema_200 ? `₹${p(ind.ema_200)}` : '—'} />
        <Row
          label="Trend"
          value={ind.trend || '—'}
          color={TREND_COLOR[ind.trend] || '#8b949e'}
        />

        <Section title="MACD (12/26/9)" />
        <Row label="MACD"    value={p(ind.macd, 3)} />
        <Row label="Signal"  value={p(ind.macd_signal, 3)} />
        <Row
          label="Histogram"
          value={p(ind.macd_hist, 3)}
          color={macdUp ? '#3fb950' : '#f85149'}
        />
        <Row
          label="MACD Signal"
          value={ind.macd_label || '—'}
          color={MACD_COLOR[ind.macd_label] || '#8b949e'}
        />

        <Section title="Bollinger Bands" />
        <Row label="BB Upper"  value={`₹${p(ind.bb_upper)}`} />
        <Row label="BB Middle" value={`₹${p(ind.bb_middle)}`} />
        <Row label="BB Lower"  value={`₹${p(ind.bb_lower)}`} />
        <Row
          label="BB Signal"
          value={(ind.bb_signal || '—').replace('_', ' ')}
          color={BB_COLOR[ind.bb_signal] || '#8b949e'}
        />

        <Section title="Volatility" />
        <Row label="ATR (14)" value={ind.atr ? p(ind.atr) : '—'} />

      </div>
    </div>
  )
}
