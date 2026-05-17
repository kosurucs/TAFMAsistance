import { create } from 'zustand';

export const useMarketStore = create((set) => ({
  selectedSymbol: 'RELIANCE',
  candles: [],
  quote: null,
  indicators: null,
  interval: '1D',
  loading: false,
  error: null,
  watchlist: ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK'],
  setSymbol: (symbol) => set({ selectedSymbol: symbol }),
  setCandles: (candles) => set({ candles }),
  setQuote: (quote) => set({ quote }),
  setIndicators: (indicators) => set({ indicators }),
  setInterval: (interval) => set({ interval }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  addToWatchlist: (symbol) => set((state) => ({
    watchlist: state.watchlist.includes(symbol) ? state.watchlist : [...state.watchlist, symbol]
  })),
  removeFromWatchlist: (symbol) => set((state) => ({
    watchlist: state.watchlist.filter(s => s !== symbol)
  })),
}));
