import { useState, useEffect, useCallback } from 'react';
import { getAlgoStrategies, toggleAlgoStrategy } from '../../services/api';
import './StrategyConfig.css';

export default function StrategyConfig() {
  const [strategies, setStrategies] = useState([]);
  const [toggling, setToggling] = useState('');

  const fetchStrategies = useCallback(async () => {
    const { data } = await getAlgoStrategies();
    if (data?.strategies) setStrategies(data.strategies);
  }, []);

  useEffect(() => { fetchStrategies(); }, [fetchStrategies]);

  const handleToggle = async (name) => {
    setToggling(name);
    const { data } = await toggleAlgoStrategy(name);
    if (data) {
      setStrategies(prev =>
        prev.map(s => s.name === name ? { ...s, enabled: data.enabled } : s)
      );
    }
    setToggling('');
  };

  return (
    <div className="strategy-config">
      <h2 className="strategy-config__title">Strategies</h2>
      {strategies.length === 0 && (
        <p className="strategy-config__empty">Loading strategies…</p>
      )}
      {strategies.map(s => (
        <div key={s.name} className={`strategy-config__item${s.enabled ? ' strategy-config__item--on' : ''}`}>
          <div className="strategy-config__info">
            <div className="strategy-config__name">{s.name}</div>
            <div className="strategy-config__desc">{s.description}</div>
          </div>
          <button
            className={`strategy-config__toggle${s.enabled ? ' strategy-config__toggle--on' : ''}`}
            onClick={() => handleToggle(s.name)}
            disabled={toggling === s.name}
            aria-label={`Toggle ${s.name}`}
          >
            {s.enabled ? 'ON' : 'OFF'}
          </button>
        </div>
      ))}
    </div>
  );
}
