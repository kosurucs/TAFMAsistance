import { useCallback, useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card } from '../design-system';
import { OptionsTable } from '../features/options/OptionsTable';
import './Options.css';

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY'];

export default function Options() {
  const [symbol, setSymbol] = useState('NIFTY');
  const [expiry, setExpiry] = useState('');
  const handleExpiryChange = useCallback((value) => setExpiry(value), []);

  return (
    <AppLayout>
      <div className="options-page">
        <div className="options-toolbar">
          <span className="options-label">Underlying</span>
          <div className="options-symbols">
            {SYMBOLS.map((item) => (
              <button
                key={item}
                type="button"
                className={`options-symbol ${symbol === item ? 'options-symbol--active' : ''}`}
                onClick={() => { setSymbol(item); setExpiry(''); }}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        <Card title={`${symbol} Option Chain`}>
          <OptionsTable symbol={symbol} expiry={expiry} onExpiryChange={handleExpiryChange} />
        </Card>
      </div>
    </AppLayout>
  );
}
