import { useMarketStore } from '../../store';
import './IntervalSelector.css';

const INTERVALS = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1h' },
  { value: '1D', label: '1D' },
];

export default function IntervalSelector() {
  const { interval, setInterval } = useMarketStore();

  return (
    <div className="interval-selector">
      <label className="interval-selector__label">Timeframe:</label>
      <div className="interval-selector__buttons">
        {INTERVALS.map((int) => (
          <button
            key={int.value}
            className={`interval-selector__button ${
              interval === int.value ? 'interval-selector__button--active' : ''
            }`}
            onClick={() => setInterval(int.value)}
            type="button"
          >
            {int.label}
          </button>
        ))}
      </div>
    </div>
  );
}
