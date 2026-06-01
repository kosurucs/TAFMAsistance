import { useEffect, useCallback, useRef } from 'react';
import { useMarketStore } from '../store';
import { fetchCandles, fetchQuote } from '../services/api';

const REFRESH_INTERVAL_MS = 15_000; // 15-second live refresh

export function useMarketData() {
  const {
    selectedSymbol, interval,
    setCandles, setIndicators, setQuote,
    setLoading, setRefreshing, setError, setLastUpdated,
    candles,
  } = useMarketStore();

  // Track whether the initial load for this symbol has already happened
  const initialLoadDone = useRef(false);
  const prevSymbolRef = useRef(selectedSymbol);

  const loadData = useCallback(async (isInitial = false) => {
    if (!selectedSymbol) return;

    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    const [marketRes, quoteRes] = await Promise.all([
      fetchCandles(selectedSymbol, interval),
      fetchQuote(selectedSymbol),
    ]);

    if (marketRes.data) {
      setCandles(marketRes.data.candles || []);
      setIndicators(marketRes.data.indicators || null);
    }
    if (quoteRes.data) setQuote(quoteRes.data);
    if (marketRes.error) setError(marketRes.error);

    setLastUpdated(Date.now());
    setLoading(false);
    setRefreshing(false);
  }, [selectedSymbol, interval, setCandles, setIndicators, setQuote, setLoading, setRefreshing, setError, setLastUpdated]);

  useEffect(() => {
    const symbolChanged = prevSymbolRef.current !== selectedSymbol;
    prevSymbolRef.current = selectedSymbol;

    // Full spinner on symbol/interval change or first load
    const isInitial = symbolChanged || !initialLoadDone.current;
    initialLoadDone.current = true;

    loadData(isInitial);

    const id = setInterval(() => loadData(false), REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [loadData]);

  return { reload: () => loadData(true), refreshIntervalMs: REFRESH_INTERVAL_MS };
}
