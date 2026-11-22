import { useEffect, useMemo, useState } from 'react';
import { Button, Modal, Spinner } from '../../design-system';
import { fetchOptionsChain } from '../../services/api';
import './OptionsTable.css';

const REFRESH_INTERVAL_MS = 15_000;
const COLUMN_OPTIONS = [
  { key: 'open_interest', label: 'OI', digits: 0, defaultVisible: true },
  { key: 'volume', label: 'Vol', digits: 0, defaultVisible: true },
  { key: 'change', label: 'Change', signed: true, defaultVisible: false },
  { key: 'change_percent', label: 'Change %', digits: 2, signed: true, defaultVisible: false },
  { key: 'open', label: 'Open', defaultVisible: false },
  { key: 'high', label: 'High', defaultVisible: false },
  { key: 'low', label: 'Low', defaultVisible: false },
  { key: 'previous_close', label: 'Prev Close', defaultVisible: false },
  { key: 'average_price', label: 'Avg Price', defaultVisible: false },
  { key: 'bid', label: 'Bid', defaultVisible: false },
  { key: 'bid_quantity', label: 'Bid Qty', digits: 0, defaultVisible: false },
  { key: 'ask', label: 'Ask', defaultVisible: false },
  { key: 'ask_quantity', label: 'Ask Qty', digits: 0, defaultVisible: false },
  { key: 'iv', label: 'IV %', digits: 1, defaultVisible: true },
  { key: 'vega', label: 'Vega', defaultVisible: true },
  { key: 'gamma', label: 'Gamma', digits: 4, defaultVisible: true },
  { key: 'theta', label: 'Theta', defaultVisible: true },
  { key: 'delta', label: 'Delta', digits: 4, defaultVisible: true },
  { key: 'last_price', label: 'LTP', defaultVisible: true },
  { key: 'lot_size', label: 'Lot', digits: 0, defaultVisible: false },
];

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : '—';
}

export function OptionsTable({ symbol, expiry, onExpiryChange }) {
  const [contracts, setContracts] = useState([]);
  const [expiries, setExpiries] = useState([]);
  const [underlyingPrice, setUnderlyingPrice] = useState(0);
  const [strikeLength, setStrikeLength] = useState(20);
  const [visibleColumns, setVisibleColumns] = useState(() => new Set(
    COLUMN_OPTIONS.filter((column) => column.defaultVisible).map((column) => column.key),
  ));
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [plan, setPlan] = useState(null);
  const [planSaved, setPlanSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    const load = async () => {
      setLoading(true);
      setError('');
      const { data, error: requestError } = await fetchOptionsChain(symbol, expiry, strikeLength);
      if (!active) return;

      if (requestError) {
        setContracts([]);
        setError(requestError);
      } else {
        setContracts(data.contracts ?? []);
        setExpiries(data.expiries ?? []);
        setUnderlyingPrice(data.underlying_price ?? 0);
        if (data.expiry && data.expiry !== expiry) onExpiryChange(data.expiry);
      }
      setLoading(false);
    };

    load();
    const refresh = setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(refresh);
    };
  }, [symbol, expiry, strikeLength, onExpiryChange]);

  const rows = useMemo(() => {
    const byStrike = new Map();
    contracts.forEach((contract) => {
      const strike = Number(contract.strike);
      if (!byStrike.has(strike)) byStrike.set(strike, { strike, CE: null, PE: null });
      byStrike.get(strike)[contract.instrument_type] = contract;
    });
    return [...byStrike.values()].sort((left, right) => left.strike - right.strike);
  }, [contracts]);

  const atmStrike = useMemo(() => {
    if (!rows.length || underlyingPrice <= 0) return null;
    return rows.reduce((nearest, row) => (
      Math.abs(row.strike - underlyingPrice) < Math.abs(nearest - underlyingPrice)
        ? row.strike
        : nearest
    ), rows[0].strike);
  }, [rows, underlyingPrice]);

  const openPlan = (side, contract) => {
    if (!contract) return;
    setPlanSaved(false);
    setPlan({
      side,
      contract,
      lots: 1,
      orderType: 'MARKET',
      entryPrice: Number(contract.last_price || 0),
      condition: 'NONE',
      triggerPrice: Number(contract.last_price || 0),
      stopLoss: 0,
      targetPrice: 0,
    });
  };

  const updatePlan = (field, value) => setPlan((current) => ({ ...current, [field]: value }));

  const savePlan = () => {
    if (!plan) return;
    const saved = JSON.parse(localStorage.getItem('tafm_option_plans') || '[]');
    const record = {
      ...plan,
      contract: plan.contract.tradingsymbol,
      expiry,
      spot: underlyingPrice,
      status: 'ANALYSIS_ONLY',
      createdAt: new Date().toISOString(),
    };
    localStorage.setItem('tafm_option_plans', JSON.stringify([...saved, record]));
    setPlanSaved(true);
  };

  if (loading && rows.length === 0) return <div className="options-state"><Spinner size="md" /></div>;
  if (error) return <div className="options-error">{error}</div>;

  return (
    <div className="options-table-wrap">
      <div className="options-meta">
        <span>{symbol}</span>
        <label>
          Expiry
          <select value={expiry} onChange={(event) => onExpiryChange(event.target.value)}>
            {expiries.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label>
          Strike length
          <select value={strikeLength} onChange={(event) => setStrikeLength(Number(event.target.value))}>
            {[10, 20, 30, 50, 100].map((length) => (
              <option key={length} value={length}>{length}</option>
            ))}
          </select>
        </label>
        <span>Spot {formatNumber(underlyingPrice)}</span>
        <span>{rows.length} strikes · {contracts.length} contracts</span>
      </div>
      {rows.length === 0 ? (
        <p className="options-empty">No option contracts found for this symbol.</p>
      ) : (
        <table className="options-table">
          <thead>
            <tr className="options-group-head">
              <th colSpan="9">CALLS</th>
              <th>Strike</th>
              <th colSpan="9">PUTS</th>
            </tr>
            <tr>
              <th>OI</th><th>Vol</th><th>IV%</th><th>Vega</th><th>Gamma</th><th>Theta</th><th>Delta</th><th>LTP</th><th>Plan</th>
              <th>Price</th>
              <th>Plan</th><th>LTP</th><th>Delta</th><th>Theta</th><th>Gamma</th><th>Vega</th><th>IV%</th><th>Vol</th><th>OI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.strike} className={row.strike === atmStrike ? 'options-row--atm' : ''}>
                <td>{formatNumber(row.CE?.open_interest, 0)}</td>
                <td>{formatNumber(row.CE?.volume, 0)}</td>
                <td>{formatNumber(row.CE?.iv, 1)}</td>
                <td>{formatNumber(row.CE?.vega)}</td>
                <td>{formatNumber(row.CE?.gamma, 4)}</td>
                <td>{formatNumber(row.CE?.theta)}</td>
                <td>{formatNumber(row.CE?.delta, 4)}</td>
                <td className="options-price">{formatNumber(row.CE?.last_price)}</td>
                <td className="options-actions">
                  <button type="button" className="options-buy" disabled={!row.CE} onClick={() => openPlan('BUY', row.CE)}>B</button>
                  <button type="button" className="options-sell" disabled={!row.CE} onClick={() => openPlan('SELL', row.CE)}>S</button>
                </td>
                <td className="options-strike">
                  {formatNumber(row.strike, 0)}
                  {row.strike === atmStrike && <span className="options-atm-badge">ATM</span>}
                </td>
                <td className="options-actions">
                  <button type="button" className="options-buy" disabled={!row.PE} onClick={() => openPlan('BUY', row.PE)}>B</button>
                  <button type="button" className="options-sell" disabled={!row.PE} onClick={() => openPlan('SELL', row.PE)}>S</button>
                </td>
                <td className="options-price">{formatNumber(row.PE?.last_price)}</td>
                <td>{formatNumber(row.PE?.delta, 4)}</td>
                <td>{formatNumber(row.PE?.theta)}</td>
                <td>{formatNumber(row.PE?.gamma, 4)}</td>
                <td>{formatNumber(row.PE?.vega)}</td>
                <td>{formatNumber(row.PE?.iv, 1)}</td>
                <td>{formatNumber(row.PE?.volume, 0)}</td>
                <td>{formatNumber(row.PE?.open_interest, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {plan && (
        <Modal title={`${plan.side} analysis plan · ${plan.contract.tradingsymbol}`} onClose={() => setPlan(null)}>
          <div className="options-plan-warning">Analysis only. This plan is saved locally and will not place a broker order.</div>
          <div className="options-plan-grid">
            <label>Side
              <select value={plan.side} onChange={(event) => updatePlan('side', event.target.value)}>
                <option value="BUY">BUY</option><option value="SELL">SELL</option>
              </select>
            </label>
            <label>Order type
              <select value={plan.orderType} onChange={(event) => updatePlan('orderType', event.target.value)}>
                <option value="MARKET">MARKET</option><option value="LIMIT">LIMIT</option>
              </select>
            </label>
            <label>Lots
              <input type="number" min="1" value={plan.lots} onChange={(event) => updatePlan('lots', Math.max(1, Number(event.target.value)))} />
            </label>
            <label>Entry price
              <input type="number" min="0" step="0.05" disabled={plan.orderType === 'MARKET'} value={plan.entryPrice} onChange={(event) => updatePlan('entryPrice', Number(event.target.value))} />
            </label>
            <label>Condition
              <select value={plan.condition} onChange={(event) => updatePlan('condition', event.target.value)}>
                <option value="NONE">No trigger condition</option>
                <option value="ABOVE">At or above trigger</option>
                <option value="BELOW">At or below trigger</option>
              </select>
            </label>
            <label>Trigger price
              <input type="number" min="0" step="0.05" disabled={plan.condition === 'NONE'} value={plan.triggerPrice} onChange={(event) => updatePlan('triggerPrice', Number(event.target.value))} />
            </label>
            <label>Stop loss
              <input type="number" min="0" step="0.05" value={plan.stopLoss || ''} placeholder="Required" onChange={(event) => updatePlan('stopLoss', Number(event.target.value))} />
            </label>
            <label>Target
              <input type="number" min="0" step="0.05" value={plan.targetPrice || ''} placeholder="Optional" onChange={(event) => updatePlan('targetPrice', Number(event.target.value))} />
            </label>
          </div>
          <div className="options-plan-status">
            {plan.stopLoss <= 0 ? 'Set a stop-loss price to complete the plan.' : plan.condition === 'ABOVE' && plan.contract.last_price < plan.triggerPrice ? 'WAIT: live LTP is below trigger.' : plan.condition === 'BELOW' && plan.contract.last_price > plan.triggerPrice ? 'WAIT: live LTP is above trigger.' : 'READY TO REVIEW: condition is satisfied. No order will be sent.'}
          </div>
          <div className="options-plan-summary">
            <span>LTP {formatNumber(plan.contract.last_price)}</span>
            <span>Lot size {formatNumber(plan.contract.lot_size, 0)}</span>
            <span>Quantity {formatNumber(plan.lots * plan.contract.lot_size, 0)}</span>
          </div>
          <div className="options-plan-actions">
            <Button variant="secondary" onClick={() => setPlan(null)}>Cancel</Button>
            <Button onClick={savePlan} disabled={plan.stopLoss <= 0}>{planSaved ? 'Plan saved' : 'Save analysis plan'}</Button>
          </div>
          {planSaved && <p className="options-plan-saved">Saved locally as an analysis-only plan.</p>}
        </Modal>
      )}
    </div>
  );
}
