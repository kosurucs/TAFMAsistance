import { useMarketStore } from '../../store';
import './IntervalSelector.css';

const INTERVALS = [
  { value: '1m',  label: '1m'  },
  { value: '5m',  label: '5m'  },
  { value: '15m', label: '15m' },
  { value: '1h',  label: '1h'  },
  { value: '1D',  label: '1D'  },
];

export default function IntervalSelector() {
  const { interval, setInterval } = useMarketStore();

  return (
    <div className="iv-bar">
      <span className="iv-label">TF</span>
      <span className="iv-divider">|</span>
      <div className="iv-pills">
        {INTERVALS.map((tf, idx) => (
          <span key={tf.value} className="iv-group">
            {idx > 0 && <span className="iv-pipe">|</span>}
            <button
              className={`iv-pill ${interval === tf.value ? 'iv-pill--active' : ''}`}
              onClick={() => setInterval(tf.value)}
              type="button"
            >
              {tf.label}
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}
