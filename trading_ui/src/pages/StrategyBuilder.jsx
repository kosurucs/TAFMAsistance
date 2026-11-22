import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card, Spinner } from '../design-system';
import { fetchOptionsChain } from '../services/api';
import './StrategyBuilder.css';

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY'];
const CATEGORIES = ['Bullish', 'Bearish', 'Neutral', 'Others'];
const PRESETS = {
  Bullish: ['Buy Call', 'Sell Put', 'Bull Call Spread', 'Bull Put Spread', 'Call Ratio Back Spread', 'Long Calendar with Calls', 'Bull Condor', 'Bull Butterfly', 'Range Forward', 'Buy Future', 'Long Synthetic Future'],
  Bearish: ['Buy Put', 'Sell Call', 'Bear Call Spread', 'Bear Put Spread', 'Put Ratio Back Spread', 'Long Calendar with Puts', 'Bear Condor', 'Bear Butterfly', 'Risk Reversal', 'Sell Future', 'Short Synthetic Future'],
  Neutral: ['Short Straddle', 'Iron Butterfly', 'Short Strangle', 'Short Iron Condor', 'Batman', 'Double Plateau', 'Jade Lizard', 'Reverse Jade Lizard'],
  Others: ['Call Ratio Spread', 'Put Ratio Spread', 'Long Straddle', 'Long Iron Butterfly', 'Long Strangle', 'Long Iron Condor', 'Strap', 'Strip'],
};

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : '—';
}

function payoffAt(spot, legs, contracts) {
  return legs.reduce((total, leg) => {
    const contract = contracts.find((item) => item.tradingsymbol === leg.tradingsymbol);
    if (!contract) return total;
    const intrinsic = contract.instrument_type === 'CE'
      ? Math.max(spot - Number(leg.strike), 0)
      : Math.max(Number(leg.strike) - spot, 0);
    const side = leg.side === 'BUY' ? 1 : -1;
    const quantity = Number(leg.lots || 1) * Number(contract.lot_size || 1);
    return total + side * (intrinsic - Number(leg.price || 0)) * quantity;
  }, 0);
}

export default function StrategyBuilder() {
  const [symbol, setSymbol] = useState('NIFTY');
  const [expiry, setExpiry] = useState('');
  const [expiries, setExpiries] = useState([]);
  const [contracts, setContracts] = useState([]);
  const [spot, setSpot] = useState(0);
  const [target, setTarget] = useState(0);
  const [view, setView] = useState('Payoff');
  const [hoverIndex, setHoverIndex] = useState(null);
  const [legs, setLegs] = useState([]);
  const [category, setCategory] = useState('Bullish');
  const [strategyNote, setStrategyNote] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadChain = useCallback(async () => {
    setLoading(true);
    setError('');
    const { data, error: requestError } = await fetchOptionsChain(symbol, expiry, 40);
    if (requestError) {
      setError(requestError);
      setContracts([]);
    } else {
      setContracts(data.contracts ?? []);
      setExpiries(data.expiries ?? []);
      setSpot(Number(data.underlying_price ?? 0));
      if (data.expiry && data.expiry !== expiry) setExpiry(data.expiry);
    }
    setLoading(false);
  }, [symbol, expiry]);

  useEffect(() => {
    loadChain();
  }, [loadChain]);

  useEffect(() => {
    if (spot > 0 && target === 0) setTarget(spot);
  }, [spot, target]);

  const strikes = useMemo(() => [...new Set(contracts.map((item) => Number(item.strike)))].sort((a, b) => a - b), [contracts]);
  const byStrike = useMemo(() => {
    const result = new Map();
    contracts.forEach((contract) => {
      if (!result.has(Number(contract.strike))) result.set(Number(contract.strike), {});
      result.get(Number(contract.strike))[contract.instrument_type] = contract;
    });
    return result;
  }, [contracts]);
  const atmIndex = strikes.length
    ? strikes.reduce((best, strike, index) => Math.abs(strike - spot) < Math.abs(strikes[best] - spot) ? index : best, 0)
    : 0;

  const makeLeg = (side, type, strike) => {
    const contract = byStrike.get(Number(strike))?.[type];
    if (!contract) return null;
    return {
      id: `${side}-${contract.tradingsymbol}-${Date.now()}-${Math.random()}`,
      side,
      type,
      strike: Number(contract.strike),
      tradingsymbol: contract.tradingsymbol,
      price: Number(contract.last_price || 0),
      lots: 1,
    };
  };

  const applyPreset = (preset) => {
    const atm = strikes[atmIndex];
    const next = strikes[Math.min(atmIndex + 2, strikes.length - 1)];
    const prev = strikes[Math.max(atmIndex - 2, 0)];
    const farNext = strikes[Math.min(atmIndex + 4, strikes.length - 1)];
    const farPrev = strikes[Math.max(atmIndex - 4, 0)];
    const unsupported = new Set([
      'Long Calendar with Calls', 'Long Calendar with Puts', 'Buy Future', 'Sell Future',
    ]);
    if (unsupported.has(preset)) {
      setStrategyNote(`${preset} needs a futures or multi-expiry leg model. See OPTIONS_STRATEGIES.md; this single-expiry options editor will not produce an invalid approximation.`);
      return;
    }
    setStrategyNote('');
    const recipes = {
      'Buy Call': [['BUY', 'CE', atm]],
      'Sell Put': [['SELL', 'PE', atm]],
      'Bull Call Spread': [['BUY', 'CE', atm], ['SELL', 'CE', next]],
      'Bull Put Spread': [['SELL', 'PE', atm], ['BUY', 'PE', prev]],
      'Call Ratio Back Spread': [['SELL', 'CE', atm], ['BUY', 'CE', next], ['BUY', 'CE', next]],
      'Bull Condor': [['BUY', 'CE', prev], ['SELL', 'CE', atm], ['SELL', 'CE', next], ['BUY', 'CE', farNext]],
      'Bull Butterfly': [['BUY', 'CE', prev], ['SELL', 'CE', atm], ['SELL', 'CE', atm], ['BUY', 'CE', next]],
      'Range Forward': [['BUY', 'CE', next], ['SELL', 'PE', prev]],
      'Long Synthetic Future': [['BUY', 'CE', atm], ['SELL', 'PE', atm]],
      'Buy Put': [['BUY', 'PE', atm]],
      'Sell Call': [['SELL', 'CE', atm]],
      'Bear Call Spread': [['SELL', 'CE', atm], ['BUY', 'CE', next]],
      'Bear Put Spread': [['BUY', 'PE', atm], ['SELL', 'PE', prev]],
      'Put Ratio Back Spread': [['SELL', 'PE', atm], ['BUY', 'PE', prev], ['BUY', 'PE', prev]],
      'Bear Condor': [['BUY', 'PE', farPrev], ['SELL', 'PE', prev], ['SELL', 'PE', atm], ['BUY', 'PE', next]],
      'Bear Butterfly': [['BUY', 'PE', next], ['SELL', 'PE', atm], ['SELL', 'PE', atm], ['BUY', 'PE', prev]],
      'Risk Reversal': [['BUY', 'PE', prev], ['SELL', 'CE', next]],
      'Short Synthetic Future': [['SELL', 'CE', atm], ['BUY', 'PE', atm]],
      'Short Straddle': [['SELL', 'CE', atm], ['SELL', 'PE', atm]],
      'Iron Butterfly': [['BUY', 'PE', prev], ['SELL', 'PE', atm], ['SELL', 'CE', atm], ['BUY', 'CE', next]],
      'Short Strangle': [['SELL', 'PE', prev], ['SELL', 'CE', next]],
      'Short Iron Condor': [['BUY', 'PE', farPrev], ['SELL', 'PE', prev], ['SELL', 'CE', next], ['BUY', 'CE', farNext]],
      'Batman': [['BUY', 'PE', farPrev], ['SELL', 'PE', prev], ['BUY', 'PE', atm], ['BUY', 'CE', atm], ['SELL', 'CE', next], ['BUY', 'CE', farNext]],
      'Double Plateau': [['BUY', 'PE', farPrev], ['SELL', 'PE', prev], ['SELL', 'CE', atm], ['BUY', 'CE', farNext]],
      'Jade Lizard': [['SELL', 'PE', prev], ['SELL', 'CE', atm], ['BUY', 'CE', next]],
      'Reverse Jade Lizard': [['SELL', 'CE', next], ['SELL', 'PE', atm], ['BUY', 'PE', prev]],
      'Call Ratio Spread': [['BUY', 'CE', atm], ['SELL', 'CE', next], ['SELL', 'CE', next]],
      'Put Ratio Spread': [['BUY', 'PE', atm], ['SELL', 'PE', prev], ['SELL', 'PE', prev]],
      'Long Straddle': [['BUY', 'CE', atm], ['BUY', 'PE', atm]],
      'Long Iron Butterfly': [['SELL', 'PE', prev], ['BUY', 'PE', atm], ['BUY', 'CE', atm], ['SELL', 'CE', next]],
      'Long Strangle': [['BUY', 'PE', prev], ['BUY', 'CE', next]],
      'Long Iron Condor': [['BUY', 'PE', prev], ['SELL', 'PE', farPrev], ['BUY', 'CE', next], ['SELL', 'CE', farNext]],
      'Strap': [['BUY', 'CE', atm], ['BUY', 'CE', atm], ['BUY', 'PE', atm]],
      'Strip': [['BUY', 'CE', atm], ['BUY', 'PE', atm], ['BUY', 'PE', atm]],
    };
    setLegs((recipes[preset] ?? []).map(([side, type, strike]) => makeLeg(side, type, strike)).filter(Boolean));
  };

  useEffect(() => {
    if (contracts.length && legs.length === 0) applyPreset('Bull Call Spread');
  }, [contracts]);

  const updateLeg = (id, patch) => {
    setLegs((current) => current.map((leg) => {
      if (leg.id !== id) return leg;
      const updated = { ...leg, ...patch };
      const contract = byStrike.get(Number(updated.strike))?.[updated.type];
      if (contract && ('strike' in patch || 'type' in patch)) {
        updated.tradingsymbol = contract.tradingsymbol;
        updated.price = Number(contract.last_price || 0);
      }
      return updated;
    }));
  };

  const addLeg = () => {
    const leg = makeLeg('BUY', 'CE', strikes[atmIndex]);
    if (leg) setLegs((current) => [...current, leg]);
  };

  const payoff = useMemo(() => {
    if (!legs.length || !strikes.length) return [];
    const range = (strikes[strikes.length - 1] - strikes[0]) || Math.max(spot * 0.15, 1000);
    const minimum = Math.max(0, Math.min(...legs.map((leg) => leg.strike)) - range * 0.12);
    const maximum = Math.max(...legs.map((leg) => leg.strike)) + range * 0.12;
    return Array.from({ length: 61 }, (_, index) => {
      const price = minimum + ((maximum - minimum) * index) / 60;
      return { price, pnl: payoffAt(price, legs, contracts) };
    });
  }, [legs, contracts, strikes, spot]);

  const netPremium = legs.reduce((total, leg) => {
    const contract = contracts.find((item) => item.tradingsymbol === leg.tradingsymbol);
    const amount = Number(leg.price || 0) * Number(leg.lots || 1) * Number(contract?.lot_size || 1);
    return total + (leg.side === 'BUY' ? -amount : amount);
  }, 0);

  const greekTotals = legs.reduce((total, leg) => {
    const contract = contracts.find((item) => item.tradingsymbol === leg.tradingsymbol);
    const sign = leg.side === 'BUY' ? 1 : -1;
    const quantity = Number(leg.lots || 1) * Number(contract?.lot_size || 1);
    ['delta', 'gamma', 'theta', 'vega'].forEach((key) => {
      total[key] += sign * quantity * Number(contract?.[key] || 0);
    });
    return total;
  }, { delta: 0, gamma: 0, theta: 0, vega: 0 });

  const strikeRows = useMemo(() => strikes.map((strike) => ({
    strike,
    pnl: payoffAt(strike, legs, contracts),
    distanceFromSpot: strike - spot,
  })), [strikes, legs, contracts, spot]);
  const legRows = legs.map((leg) => {
    const contract = contracts.find((item) => item.tradingsymbol === leg.tradingsymbol);
    const sign = leg.side === 'BUY' ? 1 : -1;
    const quantity = Number(leg.lots || 1) * Number(contract?.lot_size || 1);
    return {
      ...leg,
      quantity,
      delta: sign * quantity * Number(contract?.delta || 0),
      gamma: sign * quantity * Number(contract?.gamma || 0),
      theta: sign * quantity * Number(contract?.theta || 0),
      vega: sign * quantity * Number(contract?.vega || 0),
    };
  });
  const targetPnl = payoffAt(Number(target || spot), legs, contracts);
  const targetStrike = strikes.length
    ? strikes.reduce((nearest, strike) => Math.abs(strike - target) < Math.abs(nearest - target) ? strike : nearest, strikes[0])
    : 0;

  const pnlValues = payoff.map((point) => point.pnl);
  const maxProfit = pnlValues.length ? Math.max(...pnlValues) : 0;
  const maxLoss = pnlValues.length ? Math.min(...pnlValues) : 0;
  const chart = (() => {
    if (!payoff.length) return null;
    const width = 820;
    const height = 320;
    const padding = { top: 28, right: 24, bottom: 42, left: 66 };
    const rawLow = Math.min(0, ...pnlValues);
    const rawHigh = Math.max(0, ...pnlValues);
    const pnlPadding = Math.max((rawHigh - rawLow) * 0.12, 1);
    const lowPnl = rawLow - pnlPadding;
    const highPnl = rawHigh + pnlPadding;
    const spanPnl = highPnl - lowPnl || 1;
    const minPrice = payoff[0].price;
    const maxPrice = payoff.at(-1).price;
    const x = (price) => padding.left + ((price - minPrice) / (maxPrice - minPrice || 1)) * (width - padding.left - padding.right);
    const y = (pnl) => height - padding.bottom - ((pnl - lowPnl) / spanPnl) * (height - padding.top - padding.bottom);
    const points = payoff.map((point) => `${x(point.price)},${y(point.pnl)}`).join(' ');
    const areaPoints = `${x(minPrice)},${y(0)} ${points} ${x(maxPrice)},${y(0)}`;
    const yTicks = Array.from({ length: 5 }, (_, index) => lowPnl + ((highPnl - lowPnl) * index) / 4);
    const xTicks = Array.from({ length: 6 }, (_, index) => minPrice + ((maxPrice - minPrice) * index) / 5);
    const breakevens = [];
    for (let index = 1; index < payoff.length; index += 1) {
      const previous = payoff[index - 1];
      const current = payoff[index];
      if (previous.pnl === 0) breakevens.push(previous.price);
      if (previous.pnl * current.pnl < 0) {
        const ratio = Math.abs(previous.pnl) / (Math.abs(previous.pnl) + Math.abs(current.pnl));
        breakevens.push(previous.price + (current.price - previous.price) * ratio);
      }
    }
    return { width, height, padding, points, areaPoints, zeroY: y(0), x, y, xTicks, yTicks, breakevens, minPrice, maxPrice };
  })();

  return (
    <AppLayout>
      <div className="strategy-page">
        <div className="strategy-toolbar">
          <div className="strategy-symbols">
            {SYMBOLS.map((item) => (
              <button
                key={item}
                type="button"
                className={symbol === item ? 'active' : ''}
                onClick={() => { setSymbol(item); setExpiry(''); setLegs([]); }}
              >{item}</button>
            ))}
          </div>
          <label>Expiry <select value={expiry} onChange={(event) => { setExpiry(event.target.value); setLegs([]); }}>
            {expiries.map((item) => <option key={item} value={item}>{item}</option>)}
          </select></label>
          <span>Spot {formatNumber(spot)}</span>
          <label>Target <input type="number" min="0" step="50" value={target || ''} onChange={(event) => setTarget(Number(event.target.value))} /></label>
          <button type="button" onClick={loadChain} disabled={loading}>Refresh</button>
        </div>

        <div className="strategy-library">
          <div className="strategy-categories" aria-label="Strategy categories">
            {CATEGORIES.map((item) => (
              <button key={item} type="button" className={category === item ? 'active' : ''} onClick={() => setCategory(item)}>{item}</button>
            ))}
          </div>
          <div className="strategy-presets" aria-label={`${category} strategies`}>
            {PRESETS[category].map((preset) => <button key={preset} type="button" onClick={() => applyPreset(preset)}>{preset}</button>)}
          </div>
        </div>
        {strategyNote && <div className="strategy-note">{strategyNote}</div>}

        {loading && !contracts.length ? <div className="strategy-loading"><Spinner size="md" /></div> : error ? (
          <div className="strategy-error">{error}</div>
        ) : (
          <div className="strategy-layout">
            <section className="strategy-builder-panel">
              <Card title="Strategy Legs" action={<button type="button" onClick={addLeg}>Add leg</button>}>
                <div className="strategy-legs">
                  {legs.length === 0 && <p className="strategy-empty">Choose a preset or add a leg.</p>}
                  {legs.map((leg) => (
                    <div className="strategy-leg" key={leg.id}>
                      <select value={leg.side} onChange={(event) => updateLeg(leg.id, { side: event.target.value })}>
                        <option value="BUY">Buy</option><option value="SELL">Sell</option>
                      </select>
                      <select value={leg.type} onChange={(event) => updateLeg(leg.id, { type: event.target.value })}>
                        <option value="CE">CALL</option><option value="PE">PUT</option>
                      </select>
                      <select value={leg.strike} onChange={(event) => updateLeg(leg.id, { strike: Number(event.target.value) })}>
                        {strikes.map((strike) => <option key={strike} value={strike}>{strike}</option>)}
                      </select>
                      <label>Lots <input type="number" min="1" value={leg.lots} onChange={(event) => updateLeg(leg.id, { lots: Math.max(1, Number(event.target.value)) })} /></label>
                      <label>Premium <input type="number" min="0" step="0.05" value={leg.price} onChange={(event) => updateLeg(leg.id, { price: Number(event.target.value) })} /></label>
                      <button type="button" className="strategy-remove" onClick={() => setLegs((current) => current.filter((item) => item.id !== leg.id))} aria-label={`Remove ${leg.type} ${leg.strike}`}>×</button>
                    </div>
                  ))}
                </div>
              </Card>

              <Card title={`${symbol} Payoff · ${expiry}`}>
                {chart ? (
                  <div className="strategy-chart-shell">
                    <div className="strategy-chart-readout">
                      <span>Spot ₹{formatNumber(spot)}</span>
                      <span>Target ₹{formatNumber(target)}</span>
                      <strong className={targetPnl >= 0 ? 'positive' : 'negative'}>Target P&L ₹{formatNumber(targetPnl)}</strong>
                      {chart.breakevens.length > 0 && <span>Breakeven {chart.breakevens.map((price) => `₹${formatNumber(price, 0)}`).join(' / ')}</span>}
                    </div>
                    <svg
                      className="strategy-chart"
                      viewBox={`0 0 ${chart.width} ${chart.height}`}
                      role="img"
                      aria-label="Interactive strategy payoff chart"
                      onMouseLeave={() => setHoverIndex(null)}
                      onMouseMove={(event) => {
                        const bounds = event.currentTarget.getBoundingClientRect();
                        const svgX = ((event.clientX - bounds.left) / bounds.width) * chart.width;
                        const price = chart.minPrice + ((svgX - chart.padding.left) / (chart.width - chart.padding.left - chart.padding.right)) * (chart.maxPrice - chart.minPrice);
                        const index = Math.round(((price - chart.minPrice) / (chart.maxPrice - chart.minPrice || 1)) * (payoff.length - 1));
                        setHoverIndex(Math.max(0, Math.min(payoff.length - 1, index)));
                      }}
                    >
                      <polygon points={chart.areaPoints} className="chart-payoff-area" />
                      {chart.yTicks.map((tick) => (
                        <g key={tick}>
                          <line x1={chart.padding.left} x2={chart.width - chart.padding.right} y1={chart.y(tick)} y2={chart.y(tick)} className="chart-grid" />
                          <text x={chart.padding.left - 8} y={chart.y(tick) + 4} textAnchor="end">{formatNumber(tick, 0)}</text>
                        </g>
                      ))}
                      {chart.xTicks.map((tick) => (
                        <g key={tick}>
                          <line x1={chart.x(tick)} x2={chart.x(tick)} y1={chart.padding.top} y2={chart.height - chart.padding.bottom} className="chart-grid chart-grid--vertical" />
                          <text x={chart.x(tick)} y={chart.height - 14} textAnchor="middle">{formatNumber(tick, 0)}</text>
                        </g>
                      ))}
                      <line x1={chart.padding.left} x2={chart.width - chart.padding.right} y1={chart.zeroY} y2={chart.zeroY} className="chart-zero" />
                      <polyline points={chart.points} className="chart-payoff" />
                      <line x1={chart.x(spot)} x2={chart.x(spot)} y1={chart.padding.top} y2={chart.height - chart.padding.bottom} className="chart-spot" />
                      <line x1={chart.x(target)} x2={chart.x(target)} y1={chart.padding.top} y2={chart.height - chart.padding.bottom} className="chart-target" />
                      <circle cx={chart.x(target)} cy={chart.y(targetPnl)} r="6" className="chart-target-point" />
                      {chart.breakevens.map((price) => <circle key={price} cx={chart.x(price)} cy={chart.zeroY} r="5" className="chart-breakeven" />)}
                      {hoverIndex !== null && (
                        <g className="chart-hover">
                          <line x1={chart.x(payoff[hoverIndex].price)} x2={chart.x(payoff[hoverIndex].price)} y1={chart.padding.top} y2={chart.height - chart.padding.bottom} />
                          <circle cx={chart.x(payoff[hoverIndex].price)} cy={chart.y(payoff[hoverIndex].pnl)} r="6" />
                          <rect x={Math.min(chart.x(payoff[hoverIndex].price) + 8, chart.width - 190)} y={chart.padding.top + 8} width="174" height="48" rx="4" />
                          <text x={Math.min(chart.x(payoff[hoverIndex].price) + 18, chart.width - 180)} y={chart.padding.top + 28}>Price ₹{formatNumber(payoff[hoverIndex].price, 0)}</text>
                          <text x={Math.min(chart.x(payoff[hoverIndex].price) + 18, chart.width - 180)} y={chart.padding.top + 46}>P&L ₹{formatNumber(payoff[hoverIndex].pnl)}</text>
                        </g>
                      )}
                      <text x={chart.x(spot)} y={chart.padding.top - 8} textAnchor="middle" className="chart-label">Spot</text>
                      <text x={chart.x(target)} y={chart.height - chart.padding.bottom + 24} textAnchor="middle" className="chart-label chart-label--target">Target</text>
                    </svg>
                  </div>
                ) : <p className="strategy-empty">Add at least one leg to plot payoff.</p>}
              </Card>
            </section>

            <aside className="strategy-summary">
              <Card title="Strategy Summary">
                <div className="strategy-stat"><span>Net premium</span><strong className={netPremium >= 0 ? 'positive' : 'negative'}>{netPremium >= 0 ? 'Receive ' : 'Pay '}{formatNumber(Math.abs(netPremium))}</strong></div>
                <div className="strategy-stat"><span>Target P&L at {formatNumber(target, 0)}</span><strong className={targetPnl >= 0 ? 'positive' : 'negative'}>{formatNumber(targetPnl)}</strong></div>
                <div className="strategy-stat"><span>Breakeven</span><strong>{chart?.breakevens.map((price) => formatNumber(price, 0)).join(' / ') || '—'}</strong></div>
                <div className="strategy-stat"><span>Max profit in range</span><strong className="positive">{formatNumber(maxProfit)}</strong></div>
                <div className="strategy-stat"><span>Max loss in range</span><strong className="negative">{formatNumber(maxLoss)}</strong></div>
                <div className="strategy-greeks">
                  <div><span>Delta</span><strong>{formatNumber(greekTotals.delta, 2)}</strong></div>
                  <div><span>Gamma</span><strong>{formatNumber(greekTotals.gamma, 4)}</strong></div>
                  <div><span>Theta</span><strong>{formatNumber(greekTotals.theta, 2)}</strong></div>
                  <div><span>Vega</span><strong>{formatNumber(greekTotals.vega, 2)}</strong></div>
                </div>
                <p className="strategy-disclaimer">Analysis only. Payoff excludes charges, slippage, assignment, and early-exit effects.</p>
              </Card>
            </aside>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
