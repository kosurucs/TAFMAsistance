import { useEffect, useCallback } from 'react';
import { getAlgoSignals } from '../services/api';

const POLL_INTERVAL = 8000; // 8 seconds

/**
 * useSignalMarkers hook
 * 
 * Polls /algo/signals and converts them to chart marker format.
 * Calls setSignals on the chart adapter to render BUY/SELL/WAIT arrows.
 * 
 * @param {string} symbol - Current symbol being displayed
 * @param {function} setSignals - Chart adapter's setSignals function
 * @param {boolean} enabled - Whether to poll (default: true)
 */
export function useSignalMarkers(symbol, setSignals, enabled = true) {
  const fetchAndSetSignals = useCallback(async () => {
    if (!symbol || !setSignals || !enabled) return;

    try {
      const { data, error } = await getAlgoSignals(50);
      
      if (error) {
        console.error('Failed to fetch algo signals:', error);
        return;
      }

      if (!data?.signals) return;

      // Filter signals for current symbol only
      const symbolSignals = data.signals.filter(s => 
        s.symbol?.toUpperCase() === symbol.toUpperCase()
      );

      // Convert to chart marker format
      const markers = symbolSignals
        .filter(s => s.action && s.action !== 'WAIT')
        .map(s => ({
          time: s.timestamp,
          side: s.action === 'BUY' ? 'buy' : 'sell',
          reason: s.reason || '',
          score: Math.round(s.confidence || 0),
        }));

      setSignals(markers);
    } catch (err) {
      console.error('Error in useSignalMarkers:', err);
    }
  }, [symbol, setSignals, enabled]);

  useEffect(() => {
    fetchAndSetSignals();
    
    if (!enabled) return;

    const intervalId = setInterval(fetchAndSetSignals, POLL_INTERVAL);
    return () => clearInterval(intervalId);
  }, [fetchAndSetSignals, enabled]);

  return { refresh: fetchAndSetSignals };
}
