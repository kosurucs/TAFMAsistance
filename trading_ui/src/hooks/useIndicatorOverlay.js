import { useEffect, useCallback } from 'react';
import { api } from '../services/api';

/**
 * useIndicatorOverlay hook
 * 
 * Fetches /api/indicators/{symbol} and converts to chart line series.
 * Calls setIndicators on the chart adapter to render EMA/RSI overlays.
 * 
 * @param {string} symbol - Current symbol being displayed
 * @param {string} exchange - Exchange code (NSE, NFO)
 * @param {string} interval - Candle interval (minute, 15minute, 60minute, day)
 * @param {function} setIndicators - Chart adapter's setIndicators function
 * @param {boolean} enabled - Whether to fetch indicators (default: true)
 */
export function useIndicatorOverlay(
  symbol,
  exchange = 'NSE',
  interval = 'day',
  setIndicators,
  enabled = true
) {
  const fetchAndSetIndicators = useCallback(async () => {
    if (!symbol || !setIndicators || !enabled) return;

    try {
      const response = await api.get(`/api/indicators/${symbol}`, {
        params: { exchange, interval, limit: 200 }
      });

      const data = response.data;
      
      if (!data?.indicators) {
        console.warn('No indicators returned from API');
        return;
      }

      // Transform API format to chart adapter format
      // API returns: { ema20: [{time, value}, ...], ... }
      // Chart expects: { ema20: [{time, value}, ...], ... } (same format!)
      
      setIndicators(data.indicators);
    } catch (err) {
      console.error('Error fetching indicators:', err);
      // Clear indicators on error
      setIndicators({});
    }
  }, [symbol, exchange, interval, setIndicators, enabled]);

  useEffect(() => {
    fetchAndSetIndicators();
  }, [fetchAndSetIndicators]);

  return { refresh: fetchAndSetIndicators };
}
