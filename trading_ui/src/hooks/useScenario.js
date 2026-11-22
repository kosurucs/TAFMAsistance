import { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';

const POLL_INTERVAL = 12000; // 12 seconds (scenario doesn't change rapidly)

/**
 * useScenario hook
 * 
 * Fetches scenario analysis for the current symbol.
 * 
 * @param {string} symbol - Symbol to analyze
 * @param {string} exchange - Exchange code (NSE, NFO)
 * @param {string} interval - Candle interval
 * @param {boolean} enabled - Whether to fetch (default: true)
 * @returns {{ scenario, loading, error, refresh }}
 */
export function useScenario(symbol, exchange = 'NSE', interval = 'day', enabled = true) {
  const [scenario, setScenario] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchScenario = useCallback(async () => {
    if (!symbol || !enabled) return;

    setLoading(true);
    setError(null);

    try {
      const response = await api.get(`/api/scenario/${symbol}`, {
        params: { exchange, interval }
      });

      setScenario(response.data);
    } catch (err) {
      console.error('Failed to fetch scenario:', err);
      setError(err.message || 'Failed to fetch scenario analysis');
      setScenario(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, exchange, interval, enabled]);

  useEffect(() => {
    fetchScenario();

    if (!enabled) return;

    const intervalId = setInterval(fetchScenario, POLL_INTERVAL);
    return () => clearInterval(intervalId);
  }, [fetchScenario, enabled]);

  return { scenario, loading, error, refresh: fetchScenario };
}
