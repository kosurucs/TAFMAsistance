import { useEffect, useRef, useState } from 'react';
import { createChart } from 'lightweight-charts';
import { useMarketStore } from '../../store';
import './CandleChart.css';

const MIN_HEIGHT = 200;
const MAX_HEIGHT = 1200;
const MIN_WIDTH = 320;

// Convert UTC timestamp to IST (UTC+5:30 = +19800 seconds)
const toIST = (utcTimestamp) => utcTimestamp + 19800;

// Interval mapping for display
const INTERVAL_MAP = {
  '1m': 'minute', 
  '5m': '5minute', 
  '15m': '15minute', 
  '30m': '30minute',
  '1h': '60minute', 
  '1D': 'day', 
  '1W': 'week', 
  '1M': 'month'
};

export function CandleChart() {
  const { selectedSymbol, candles, interval } = useMarketStore();
  const hostRef = useRef(null);
  const wrapperRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const volSeriesRef = useRef(null);
  const [canvasHeight, setCanvasHeight] = useState(520);
  const [wrapperWidth, setWrapperWidth] = useState(null);

  // Get colors from CSS variables
  const upColor = getComputedStyle(document.documentElement).getPropertyValue('--color-up').trim();
  const downColor = getComputedStyle(document.documentElement).getPropertyValue('--color-down').trim();
  const bgPrimary = getComputedStyle(document.documentElement).getPropertyValue('--color-bg-primary').trim();
  const textPrimary = getComputedStyle(document.documentElement).getPropertyValue('--color-text-primary').trim();
  const borderColor = getComputedStyle(document.documentElement).getPropertyValue('--color-border').trim();
  const borderMuted = getComputedStyle(document.documentElement).getPropertyValue('--color-border-muted').trim();

  // Create chart once on mount; destroy on unmount
  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;

    const chart = createChart(el, {
      layout: {
        background: { color: bgPrimary },
        textColor: textPrimary,
      },
      grid: {
        vertLines: { color: borderMuted },
        horzLines: { color: borderMuted },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor },
      timeScale: {
        borderColor,
        timeVisible: true,
        secondsVisible: false,
      },
      width: el.clientWidth,
      height: canvasHeight,
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor,
      downColor,
      borderUpColor: upColor,
      borderDownColor: downColor,
      wickUpColor: upColor,
      wickDownColor: downColor,
    });
    candleSeriesRef.current = candleSeries;

    const volSeries = chart.addHistogramSeries({
      color: `${upColor}44`,
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volSeriesRef.current = volSeries;

    // Fit on window resize
    const ro = new ResizeObserver(() => {
      if (chartRef.current) {
        chartRef.current.applyOptions({ width: el.clientWidth });
      }
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volSeriesRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Update height when user drags handle
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.applyOptions({ height: canvasHeight });
    }
  }, [canvasHeight]);

  // Feed new candle data whenever candles change
  useEffect(() => {
    if (!candleSeriesRef.current || !volSeriesRef.current) return;
    if (!candles || candles.length === 0) {
      candleSeriesRef.current.setData([]);
      volSeriesRef.current.setData([]);
      return;
    }

    const ohlc = candles.map(c => {
      // Convert timestamp to IST
      const timestamp = c.timestamp || c.time;
      // Backend sends Unix seconds (number), not milliseconds or ISO strings
      const utcSeconds = typeof timestamp === 'number' ? timestamp : Math.floor(new Date(timestamp).getTime() / 1000);
      return {
        time: toIST(utcSeconds),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      };
    });

    const vol = candles.map(c => {
      const timestamp = c.timestamp || c.time;
      // Backend sends Unix seconds (number), not milliseconds or ISO strings
      const utcSeconds = typeof timestamp === 'number' ? timestamp : Math.floor(new Date(timestamp).getTime() / 1000);
      return {
        time: toIST(utcSeconds),
        value: c.volume,
        color: c.close >= c.open ? `${upColor}44` : `${downColor}44`,
      };
    });

    candleSeriesRef.current.setData(ohlc);
    volSeriesRef.current.setData(vol);
    chartRef.current.timeScale().fitContent();
  }, [candles, upColor, downColor]);

  const startDrag = (e, type) => {
    e.preventDefault();
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const startY = e.clientY;
    const startX = e.clientX;
    const startH = hostRef.current.getBoundingClientRect().height;
    const startW = wrapper.getBoundingClientRect().width;

    const onMouseMove = (ev) => {
      if (type === 'bottom' || type === 'corner') {
        const newH = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, startH + (ev.clientY - startY)));
        setCanvasHeight(Math.round(newH));
      }
      if (type === 'right' || type === 'corner') {
        const newW = Math.max(MIN_WIDTH, startW + (ev.clientX - startX));
        setWrapperWidth(Math.round(newW));
      }
    };

    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  };

  const displayInterval = INTERVAL_MAP[interval] || interval;

  return (
    <div
      ref={wrapperRef}
      className="chart-wrapper"
      style={wrapperWidth ? { width: wrapperWidth } : undefined}
    >
      <div className="chart-title">
        <span>{selectedSymbol} — Candlestick Chart ({displayInterval})</span>
        <div className="chart-title-right">
          <span className="chart-size-hint">{canvasHeight}px{wrapperWidth ? ` × ${wrapperWidth}px` : ''}</span>
          <span className="chart-note">Data source: Zerodha Kite (IST)</span>
        </div>
      </div>
      <div
        ref={hostRef}
        className="chart-canvas"
        role="img"
        aria-label={`${selectedSymbol} candlestick chart`}
        style={{ height: canvasHeight }}
      />
      <div
        className="chart-resize-handle-bottom"
        onMouseDown={(e) => startDrag(e, 'bottom')}
        title="Drag to resize height"
      />
      <div
        className="chart-resize-handle-corner"
        onMouseDown={(e) => startDrag(e, 'corner')}
        title="Drag corner to resize width and height"
      />
    </div>
  );
}
