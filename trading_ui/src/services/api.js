const BASE_URL = import.meta.env.VITE_API_URL || '';

async function request(path, options = {}) {
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    if (!res.ok) {
      // Handle 401 Unauthorized - redirect to login
      if (res.status === 401) {
        // Only redirect if we're not already on the login page
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      }
      
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

// Research – comprehensive multi-source instrument analysis
export const researchAnalyze = (symbol, exchange = 'NSE', deep = true, useCache = true) =>
  request('/research/analyze', {
    method: 'POST',
    body: JSON.stringify({ symbol, exchange, deep, use_cache: useCache }),
  });
export const getResearchKnowledge = (symbol) => request(`/research/knowledge/${symbol}`);
export const listResearchKnowledge = () => request('/research/knowledge');
export const getTrainingStats = () => request('/research/training-stats');

// Backtest
export const startBacktest = (symbol, years = 20, options = {}) => {
  const params = new URLSearchParams({ years });
  if (options.strategies) params.set('strategies', options.strategies);
  if (options.exchange) params.set('exchange', options.exchange);
  if (options.instrument) params.set('instrument', options.instrument);
  if (options.walk_forward != null) params.set('walk_forward', options.walk_forward);
  if (options.rsiOversold != null) params.set('rsi_oversold', options.rsiOversold);
  if (options.rsiOverbought != null) params.set('rsi_overbought', options.rsiOverbought);
  if (options.emaFast != null) params.set('ema_fast', options.emaFast);
  if (options.emaSlow != null) params.set('ema_slow', options.emaSlow);
  if (options.atrMultSl != null) params.set('atr_mult_sl', options.atrMultSl);
  if (options.atrMultTp != null) params.set('atr_mult_tp', options.atrMultTp);
  if (options.volumeConfirm != null) params.set('volume_confirm', options.volumeConfirm);
  return request(`/api/backtest/${symbol}?${params}`, { method: 'POST' });
};
export const getBacktestStatus = (jobId) => request(`/api/backtest/status/${jobId}`);
export const getBacktestResult = (jobId) => request(`/api/backtest/result/${jobId}`);

// Bot control
export const getBotStatus = () => request('/api/bot/status');
export const startBot = () => request('/api/bot/start', { method: 'POST' });
export const stopBot = () => request('/api/bot/stop', { method: 'POST' });

// Authentication
export const checkAuthStatus = () => request('/api/auth/status');
export const getLoginUrl = () => request('/api/auth/login-url');
export const exchangeToken = (callbackUrl) =>
  request('/api/auth/exchange', { method: 'POST', body: JSON.stringify({ callback_url: callbackUrl }) });
export const checkCredentialsStatus = () => request('/api/auth/credentials-status');
export const saveCredentials = (apiKey, apiSecret) =>
  request('/api/auth/save-credentials', { method: 'POST', body: JSON.stringify({ api_key: apiKey, api_secret: apiSecret }) });
export const testConnection = () => request('/api/auth/test-connection', { method: 'POST' });

// Algo Engine
export const getAlgoStatus      = ()           => request('/algo/status');
export const runAlgoCycle       = (body = {})  => request('/algo/run', { method: 'POST', body: JSON.stringify(body) });
export const getAlgoSignals     = (limit = 50) => request(`/algo/signals?limit=${limit}`);
export const getAlgoStrategies  = ()           => request('/algo/strategies');
export const toggleAlgoStrategy = (name)       => request(`/algo/strategies/${encodeURIComponent(name)}/toggle`, { method: 'POST' });
export const clearAlgoSignals   = ()           => request('/algo/signals', { method: 'DELETE' });

// Axios-compatible API object for zustand store
export const api = {
  get: (path) => request(path).then(({ data, error }) => {
    if (error) throw new Error(error);
    return { data };
  }),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }).then(({ data, error }) => {
    if (error) throw new Error(error);
    return { data };
  }),
};
