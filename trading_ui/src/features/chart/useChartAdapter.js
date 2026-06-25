/**
 * useChartAdapter
 *
 * Manages a lightweight-charts instance and exposes four clean update methods:
 *   setCandles(candles)              – OHLCV data
 *   setIndicators(indicatorMap)      – overlay line series  { ema20: [{time,value}], ema50: [...] }
 *   setSignals(signals)              – buy/sell arrow markers [{ time, side:'buy'|'sell', reason, score }]
 *   setSPWarnings(events)            – SP-case caution markers [{ time, tags, note }]
 *
 * The chart is "dumb": it only renders data passed in.
 * Strategy, SP-case logic and data fetching stay outside.
 */

import { useEffect, useRef, useCallback } from 'react';
import { createChart } from 'lightweight-charts';

// Convert UTC Unix seconds → IST Unix seconds (UTC+05:30 = +19800 s)
const toIST = (utcSeconds) => utcSeconds + 19800;

const toUtcSeconds = (raw) =>
  typeof raw === 'number' ? raw : Math.floor(new Date(raw).getTime() / 1000);

// Default colours for well-known indicator keys
const INDICATOR_COLORS = {
  ema20:  '#f59e0b',
  ema50:  '#3b82f6',
  ema200: '#8b5cf6',
  rsi:    '#10b981',
  macd:   '#ec4899',
};

/**
 * @param {React.RefObject<HTMLElement>} containerRef  – element to mount the chart in
 * @param {{ height?: number, chartOptions?: object }} options
 * @returns {{ setCandles, setIndicators, setSignals, setSPWarnings, chartRef }}
 */
export function useChartAdapter(containerRef, options = {}) {
  const chartRef            = useRef(null);
  const candleSeriesRef     = useRef(null);
  const volSeriesRef        = useRef(null);
  const indicatorSeriesRef  = useRef({});   // { [key]: LineSeries }
  const signalMarkersRef    = useRef([]);   // current signal markers (to merge with SP warnings)
  const spMarkersRef        = useRef([]);   // current SP warning markers

  // ── Initialize chart (once on mount) ──────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const css      = getComputedStyle(document.documentElement);
    const upColor    = css.getPropertyValue('--color-up').trim()          || '#22c55e';
    const downColor  = css.getPropertyValue('--color-down').trim()        || '#ef4444';
    const bgPrimary  = css.getPropertyValue('--color-bg-primary').trim()  || '#0f172a';
    const textPrimary= css.getPropertyValue('--color-text-primary').trim()|| '#e2e8f0';
    const borderColor= css.getPropertyValue('--color-border').trim()      || '#334155';
    const borderMuted= css.getPropertyValue('--color-border-muted').trim()|| '#1e293b';

    const chart = createChart(el, {
      layout: { background: { color: bgPrimary }, textColor: textPrimary },
      grid:   { vertLines: { color: borderMuted }, horzLines: { color: borderMuted } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor },
      timeScale: { borderColor, timeVisible: true, secondsVisible: false },
      width:  el.clientWidth,
      height: options.height || 520,
      ...options.chartOptions,
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor, downColor,
      borderUpColor: upColor, borderDownColor: downColor,
      wickUpColor:   upColor, wickDownColor:   downColor,
    });
    candleSeriesRef.current = candleSeries;

    const volSeries = chart.addHistogramSeries({
      color: `${upColor}44`,
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volSeriesRef.current = volSeries;

    // Responsive resize
    const ro = new ResizeObserver(() => {
      chartRef.current?.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current           = null;
      candleSeriesRef.current    = null;
      volSeriesRef.current       = null;
      indicatorSeriesRef.current = {};
      signalMarkersRef.current   = [];
      spMarkersRef.current       = [];
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Sync height when caller changes it ────────────────────────────────────
  useEffect(() => {
    chartRef.current?.applyOptions({ height: options.height || 520 });
  }, [options.height]);

  // ── setCandles ─────────────────────────────────────────────────────────────
  const setCandles = useCallback((candles) => {
    if (!candleSeriesRef.current || !volSeriesRef.current) return;

    if (!candles?.length) {
      candleSeriesRef.current.setData([]);
      volSeriesRef.current.setData([]);
      return;
    }

    const css      = getComputedStyle(document.documentElement);
    const upColor  = css.getPropertyValue('--color-up').trim()  || '#22c55e';
    const downColor= css.getPropertyValue('--color-down').trim()|| '#ef4444';

    const ohlc = candles.map((c) => ({
      time:  toIST(toUtcSeconds(c.timestamp ?? c.time)),
      open:  c.open,
      high:  c.high,
      low:   c.low,
      close: c.close,
    }));

    const vol = candles.map((c) => ({
      time:  toIST(toUtcSeconds(c.timestamp ?? c.time)),
      value: c.volume,
      color: c.close >= c.open ? `${upColor}44` : `${downColor}44`,
    }));

    candleSeriesRef.current.setData(ohlc);
    volSeriesRef.current.setData(vol);
    chartRef.current?.timeScale().fitContent();
  }, []);

  // ── setIndicators ──────────────────────────────────────────────────────────
  // indicators: { ema20: [{time, value}, ...], ema50: [...], ... }
  const setIndicators = useCallback((indicators) => {
    const chart    = chartRef.current;
    const existing = indicatorSeriesRef.current;
    if (!chart) return;

    // Remove series no longer in the new map
    Object.keys(existing).forEach((key) => {
      if (!(key in indicators)) {
        chart.removeSeries(existing[key]);
        delete existing[key];
      }
    });

    // Add or update each series
    Object.entries(indicators).forEach(([key, points]) => {
      if (!points?.length) return;

      if (!existing[key]) {
        existing[key] = chart.addLineSeries({
          color:             INDICATOR_COLORS[key] || '#888888',
          lineWidth:         1,
          priceLineVisible:  false,
          lastValueVisible:  false,
          title:             key.toUpperCase(),
        });
      }

      const data = points
        .map((p) => ({
          time:  toIST(toUtcSeconds(p.timestamp ?? p.time)),
          value: p.value,
        }))
        .sort((a, b) => a.time - b.time);

      existing[key].setData(data);
    });
  }, []);

  // ── Internal helper: merge signal + SP markers and apply ───────────────────
  const _applyMarkers = useCallback(() => {
    if (!candleSeriesRef.current) return;
    const merged = [...signalMarkersRef.current, ...spMarkersRef.current]
      .sort((a, b) => a.time - b.time);
    candleSeriesRef.current.setMarkers(merged);
  }, []);

  // ── setSignals ─────────────────────────────────────────────────────────────
  // signals: [{ time, side: 'buy'|'sell', reason?, score? }]
  const setSignals = useCallback((signals) => {
    if (!candleSeriesRef.current) return;

    const css      = getComputedStyle(document.documentElement);
    const upColor  = css.getPropertyValue('--color-up').trim()  || '#22c55e';
    const downColor= css.getPropertyValue('--color-down').trim()|| '#ef4444';

    signalMarkersRef.current = (signals ?? []).map((s) => {
      const isBuy = s.side === 'buy';
      return {
        time:     toIST(toUtcSeconds(s.timestamp ?? s.time)),
        position: isBuy ? 'belowBar' : 'aboveBar',
        color:    isBuy ? upColor : downColor,
        shape:    isBuy ? 'arrowUp' : 'arrowDown',
        text:     isBuy
          ? `B${s.score != null ? ' ' + s.score : ''}`
          : `S${s.score != null ? ' ' + s.score : ''}`,
      };
    }).sort((a, b) => a.time - b.time);

    _applyMarkers();
  }, [_applyMarkers]);

  // ── setSPWarnings ──────────────────────────────────────────────────────────
  // events: [{ time, tags?: string[], note?: string, blocked?: boolean }]
  const setSPWarnings = useCallback((events) => {
    if (!candleSeriesRef.current) return;

    spMarkersRef.current = (events ?? []).map((w) => ({
      time:     toIST(toUtcSeconds(w.timestamp ?? w.time)),
      position: 'inBar',
      color:    w.blocked ? '#ef4444' : '#f59e0b',
      shape:    'square',
      text:     w.tags?.join(',') || w.note || 'SP',
    })).sort((a, b) => a.time - b.time);

    _applyMarkers();
  }, [_applyMarkers]);

  return { setCandles, setIndicators, setSignals, setSPWarnings, chartRef };
}
