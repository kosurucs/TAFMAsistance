import { useRef, useState, useEffect } from 'react';
import { useMarketStore } from '../../store';
import { useChartAdapter } from './useChartAdapter';
import './CandleChart.css';

const MIN_HEIGHT = 200;
const MAX_HEIGHT = 1200;
const MIN_WIDTH = 320;

// Interval mapping for display
const INTERVAL_MAP = {
  '1m': 'minute',
  '5m': '5minute',
  '15m': '15minute',
  '30m': '30minute',
  '1h': '60minute',
  '1D': 'day',
  '1W': 'week',
  '1M': 'month',
};

export function CandleChart() {
  const { selectedSymbol, candles, interval } = useMarketStore();
  const hostRef    = useRef(null);
  const wrapperRef = useRef(null);
  const [canvasHeight, setCanvasHeight] = useState(520);
  const [wrapperWidth, setWrapperWidth] = useState(null);

  // Chart adapter — clean, decoupled update methods
  const { setCandles } = useChartAdapter(hostRef, { height: canvasHeight });

  // Feed candles whenever store data changes
  useEffect(() => {
    setCandles(candles);
  }, [candles, setCandles]);

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
