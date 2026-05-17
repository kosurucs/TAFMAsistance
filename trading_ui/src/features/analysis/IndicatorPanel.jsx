import { useMarketStore } from '../../store';
import { Card } from '../../design-system';
import './IndicatorPanel.css';

const TREND_COLOR = { BULLISH: 'var(--color-up)', BEARISH: 'var(--color-down)', NEUTRAL: 'var(--color-neutral)' };
const BB_COLOR = { ABOVE_UPPER: 'var(--color-down)', BELOW_LOWER: 'var(--color-up)', INSIDE: 'var(--color-neutral)', INSIDE_BANDS: 'var(--color-neutral)' };
const MACD_COLOR = { BULLISH: 'var(--color-up)', BEARISH: 'var(--color-down)', NEUTRAL: 'var(--color-neutral)' };
const STOCH_COLOR = { OVERBOUGHT: 'var(--color-down)', OVERSOLD: 'var(--color-up)', NEUTRAL: 'var(--color-neutral)' };

function p(v, d = 2) { 
  return Number(v || 0).toFixed(d); 
}

function rsiColor(v) {
  if (v >= 70) return 'var(--color-down)';
  if (v <= 30) return 'var(--color-up)';
  return 'var(--color-text-primary)';
}

function Row({ label, value, color }) {
  return (
    <div className="ip-card">
      <span className="ip-label">{label}</span>
      <span className="ip-value" style={color ? { color } : undefined}>{value}</span>
    </div>
  );
}

function Section({ title }) {
  return <div className="ip-section">{title}</div>;
}

export function IndicatorPanel() {
  const { indicators: ind } = useMarketStore();
  
  if (!ind) {
    return (
      <Card title="Technical Indicators">
        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}>
          Loading indicators...
        </p>
      </Card>
    );
  }

  const macdUp = (ind.macd_hist || 0) >= 0;

  return (
    <Card title="Technical Indicators">
      <div className="ip-grid">
        <Section title="Price" />
        <Row label="Close" value={`₹${p(ind.close)}`} />
        <Row label="VWAP" value={ind.vwap ? `₹${p(ind.vwap)}` : '—'} />
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
          color={STOCH_COLOR[ind.stoch_signal] || 'var(--color-text-primary)'}
        />

        <Section title="Trend / MA" />
        <Row label="EMA 9" value={`₹${p(ind.ema_fast)}`} />
        <Row label="EMA 21" value={`₹${p(ind.ema_slow)}`} />
        <Row label="EMA 50" value={ind.ema_50 ? `₹${p(ind.ema_50)}` : '—'} />
        <Row label="EMA 200" value={ind.ema_200 ? `₹${p(ind.ema_200)}` : '—'} />
        <Row
          label="Trend"
          value={ind.trend || '—'}
          color={TREND_COLOR[ind.trend] || 'var(--color-neutral)'}
        />

        <Section title="MACD (12/26/9)" />
        <Row label="MACD" value={p(ind.macd, 3)} />
        <Row label="Signal" value={p(ind.macd_signal, 3)} />
        <Row
          label="Histogram"
          value={p(ind.macd_hist, 3)}
          color={macdUp ? 'var(--color-up)' : 'var(--color-down)'}
        />
        <Row
          label="MACD Signal"
          value={ind.macd_label || '—'}
          color={MACD_COLOR[ind.macd_label] || 'var(--color-neutral)'}
        />

        <Section title="Bollinger Bands" />
        <Row label="BB Upper" value={`₹${p(ind.bb_upper)}`} />
        <Row label="BB Middle" value={`₹${p(ind.bb_middle)}`} />
        <Row label="BB Lower" value={`₹${p(ind.bb_lower)}`} />
        <Row
          label="BB Signal"
          value={(ind.bb_signal || '—').replace('_', ' ')}
          color={BB_COLOR[ind.bb_signal] || 'var(--color-neutral)'}
        />

        <Section title="Volatility" />
        <Row label="ATR (14)" value={ind.atr ? p(ind.atr) : '—'} />
      </div>
    </Card>
  );
}
