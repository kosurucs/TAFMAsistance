import { create } from 'zustand';

export const useMarketStore = create((set) => ({
  selectedSymbol: 'RELIANCE',
  candles: [],
  quote: null,
  indicators: null,
  interval: '1D',
  loading: false,
  refreshing: false,   // soft background refresh (no spinner)
  error: null,
  lastUpdated: null,   // timestamp of last successful fetch
  watchlist: ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK'],
  setSymbol: (symbol) => set({ selectedSymbol: symbol }),
  setCandles: (candles) => set({ candles }),
  setQuote: (quote) => set({ quote }),
  setIndicators: (indicators) => set({ indicators }),
  setInterval: (interval) => set({ interval }),
  setLoading: (loading) => set({ loading }),
  setRefreshing: (refreshing) => set({ refreshing }),
  setError: (error) => set({ error }),
  setLastUpdated: (lastUpdated) => set({ lastUpdated }),
  addToWatchlist: (symbol) => set((state) => ({
    watchlist: state.watchlist.includes(symbol) ? state.watchlist : [...state.watchlist, symbol]
  })),
  removeFromWatchlist: (symbol) => set((state) => ({
    watchlist: state.watchlist.filter(s => s !== symbol)
  })),
}));
