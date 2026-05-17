import { useEffect, useCallback } from 'react';
import { useMarketStore } from '../store';
import { fetchCandles, fetchQuote } from '../services/api';

export function useMarketData() {
  const { selectedSymbol, interval, setCandles, setIndicators, setQuote, setLoading, setError } = useMarketStore();
  
  const loadData = useCallback(async () => {
    if (!selectedSymbol) return;
    setLoading(true);
    setError(null);
    
    // Fetch market data (candles + indicators) and quote in parallel
    const [marketRes, quoteRes] = await Promise.all([
      fetchCandles(selectedSymbol, interval),
      fetchQuote(selectedSymbol),
    ]);
    
    // Extract candles and indicators from the market-data response
    if (marketRes.data) {
      setCandles(marketRes.data.candles || []);
      setIndicators(marketRes.data.indicators || null);
    }
    if (quoteRes.data) setQuote(quoteRes.data);
    if (marketRes.error) setError(marketRes.error);
    
    setLoading(false);
  }, [selectedSymbol, interval, setCandles, setIndicators, setQuote, setLoading, setError]);
  
  useEffect(() => {
    loadData();
    const id = setInterval(loadData, 60_000); // refresh every 60s
    return () => clearInterval(id);
  }, [loadData]);
  
  return { reload: loadData };
}
