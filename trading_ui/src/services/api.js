const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options = {}) {
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      return { data: null, error: err.detail || `HTTP ${res.status}` };
    }
    const data = await res.json();
    return { data, error: null };
  } catch (err) {
    return { data: null, error: err.message };
  }
}

// Map UI interval labels to Kite API interval names
const UI_TO_KITE_INTERVAL = {
  '1m': 'minute', '3m': '3minute', '5m': '5minute', '15m': '15minute',
  '30m': '30minute', '1h': '60minute', '1D': 'day', '1W': 'week', '1M': 'month',
};

// Market data
export const fetchQuote = (symbol) => request(`/api/quote/${symbol}`);
export const fetchCandles = (symbol, interval = '1D', count = 200) => {
  const kiteInterval = UI_TO_KITE_INTERVAL[interval] || interval;
  return request(`/api/market-data/${symbol}?interval=${kiteInterval}&limit=${count}`);
};
export const fetchMarketData = (symbol, interval = 'day', limit = 200) => {
  // Direct pass-through for historical data table (interval already in Kite format)
  return request(`/api/market-data/${symbol}?interval=${interval}&limit=${limit}`);
};
export const fetchIndicators = (symbol) =>
  request(`/api/market-data/${symbol}?interval=day&limit=1`)
    .then(({ data, error }) => ({
      data: data?.indicators ?? null,
      error,
    }));

// Portfolio
export const fetchPortfolio = () => request('/api/portfolio');
export const fetchPositions = () => request('/api/positions');
export const fetchMonitorStatus = () => request('/portfolio/monitor');

// Orders
export const placeOrder = (order) => request('/api/order', { method: 'POST', body: JSON.stringify(order) });

// LLM Chat
export const sendChatMessage = (message, symbol, indicators) =>
  request('/api/chat', { method: 'POST', body: JSON.stringify({ message, symbol, indicators }) });

// Backtest
export const startBacktest = (symbol, years = 20) =>
  request(`/api/backtest/${symbol}?years=${years}`, { method: 'POST' });
export const getBacktestStatus = (jobId) => request(`/api/backtest/status/${jobId}`);
export const getBacktestResult = (jobId) => request(`/api/backtest/result/${jobId}`);

// Bot control
export const getBotStatus = () => request('/api/bot/status');
export const startBot = () => request('/api/bot/start', { method: 'POST' });
export const stopBot = () => request('/api/bot/stop', { method: 'POST' });
