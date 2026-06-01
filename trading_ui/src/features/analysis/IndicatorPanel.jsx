import { useMarketStore } from '../../store';
import { Card } from '../../design-system';
import './IndicatorPanel.css';

const TREND_META = {
  BULLISH: { color: 'var(--color-up)',   label: '▲ Bullish' },
  BEARISH: { color: 'var(--color-down)', label: '▼ Bearish' },
  NEUTRAL: { color: 'var(--color-neutral)', label: '↔ Neutral' },
};
const BB_META = {
  ABOVE_UPPER:  { color: 'var(--color-down)',    label: 'Above Upper' },
  BELOW_LOWER:  { color: 'var(--color-up)',      label: 'Below Lower' },
  INSIDE:       { color: 'var(--color-neutral)', label: 'Inside Bands' },
  INSIDE_BANDS: { color: 'var(--color-neutral)', label: 'Inside Bands' },
};
const MACD_META = {
  BULLISH: { color: 'var(--color-up)',   label: '▲ Bullish' },
  BEARISH: { color: 'var(--color-down)', label: '▼ Bearish' },
  NEUTRAL: { color: 'var(--color-neutral)', label: '↔ Neutral' },
};
const STOCH_META = {
  OVERBOUGHT: { color: 'var(--color-down)', label: 'Overbought' },
  OVERSOLD:   { color: 'var(--color-up)',   label: 'Oversold' },
  NEUTRAL:    { color: 'var(--color-neutral)', label: 'Neutral' },
};

function p(v, d = 2) { return Number(v || 0).toFixed(d); }

function rsiColor(v) {
  if (v >= 70) return 'var(--color-down)';
  if (v <= 30) return 'var(--color-up)';
  return 'var(--color-text-primary)';
}

function RsiBar({ value }) {
  const pct = Math.min(100, Math.max(0, value));
  const color = rsiColor(value);
  return (
    <div className="rsi-bar-track" title={`RSI: ${p(value, 1)}`}>
      <div className="rsi-bar-fill" style={{ width: `${pct}%`, background: color }} />
      <span className="rsi-bar-ob" />
      <span className="rsi-bar-os" />
    </div>
  );
}

function Row({ label, value, color, sub }) {
  return (
    <div className="ip-row">
      <span className="ip-label">{label}</span>
      <span className="ip-value-wrap">
        <span className="ip-value" style={color ? { color } : undefined}>{value}</span>
        {sub && <span className="ip-sub">{sub}</span>}
      </span>
    </div>
  );
}

function Section({ title }) {
  return <div className="ip-section">{title}</div>;
}

export function IndicatorPanel() {
  const { indicators: ind, refreshing } = useMarketStore();

  if (!ind) {
    return (
      <Card title="Technical Indicators">
        <p className="ip-empty">Loading indicators…</p>
      </Card>
    );
  }

  const macdUp    = (ind.macd_hist || 0) >= 0;
  const trendMeta = TREND_META[ind.trend] || TREND_META.NEUTRAL;
  const macdMeta  = MACD_META[ind.macd_label] || MACD_META.NEUTRAL;
  const bbMeta    = BB_META[ind.bb_signal] || BB_META.INSIDE;
  const stochMeta = STOCH_META[ind.stoch_signal] || STOCH_META.NEUTRAL;
  const rsiVal    = Number(ind.rsi || 0);

  return (
    <Card title="Technical Indicators" refreshing={refreshing}>
      <div className="ip-grid">
        {/* Price */}
        <Section title="Price" />
        <Row label="Close"  value={`₹${p(ind.close)}`} />
        <Row label="VWAP"   value={ind.vwap ? `₹${p(ind.vwap)}` : '—'} />
        <Row label="Volume" value={Number(ind.volume || 0).toLocaleString('en-IN')} />

        {/* Momentum */}
        <Section title="Momentum" />
        <div className="ip-rsi-row">
          <span className="ip-label">RSI (14)</span>
          <div className="ip-rsi-right">
            <span className="ip-value" style={{ color: rsiColor(rsiVal) }}>
              {p(rsiVal, 1)}
              {rsiVal >= 70 ? ' OB' : rsiVal <= 30 ? ' OS' : ''}
            </span>
            <RsiBar value={rsiVal} />
          </div>
        </div>
        <Row
          label="Stoch %K/%D"
          value={`${p(ind.stoch_k, 1)} / ${p(ind.stoch_d, 1)}`}
          color={stochMeta.color}
          sub={stochMeta.label}
        />

        {/* Trend / MA */}
        <Section title="Trend / MA" />
        <Row label="EMA 9"   value={`₹${p(ind.ema_fast)}`} />
        <Row label="EMA 21"  value={`₹${p(ind.ema_slow)}`} />
        <Row label="EMA 50"  value={ind.ema_50  ? `₹${p(ind.ema_50)}`  : '—'} />
        <Row label="EMA 200" value={ind.ema_200 ? `₹${p(ind.ema_200)}` : '—'} />
        <Row label="Trend"   value={trendMeta.label} color={trendMeta.color} />

        {/* MACD */}
        <Section title="MACD (12/26/9)" />
        <Row label="MACD"      value={p(ind.macd,       3)} />
        <Row label="Signal"    value={p(ind.macd_signal, 3)} />
        <Row label="Histogram" value={p(ind.macd_hist,   3)} color={macdUp ? 'var(--color-up)' : 'var(--color-down)'} />
        <Row label="Signal"    value={macdMeta.label}        color={macdMeta.color} />

        {/* Bollinger Bands */}
        <Section title="Bollinger Bands" />
        <Row label="Upper"    value={`₹${p(ind.bb_upper)}`} />
        <Row label="Middle"   value={`₹${p(ind.bb_middle)}`} />
        <Row label="Lower"    value={`₹${p(ind.bb_lower)}`} />
        <Row label="Signal"   value={bbMeta.label} color={bbMeta.color} />

        {/* Volatility */}
        <Section title="Volatility" />
        <Row label="ATR (14)" value={ind.atr ? p(ind.atr) : '—'} />
      </div>
    </Card>
  );
}
