import { useRef, useState, useMemo, useCallback } from 'react'
import { CrosshairMode } from 'lightweight-charts'
import { Chart, CandlestickSeries, HistogramSeries, PriceScale } from 'lightweight-charts-react-wrapper'
import './CandleChart.css'

function fmtPrice(v) {
  return v != null ? `₹${Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'
}
function fmtVol(v) {
  return v != null ? Number(v).toLocaleString('en-IN') : '—'
}
function fmtTime(unixSec) {
  if (!unixSec) return ''
  return new Date(unixSec * 1000).toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  })
}

function colorCandle(c) {
  const range = c.high - c.low
  const body = Math.abs(c.close - c.open)
  if (range === 0 || body / range < 0.5)
    return { ...c, color: 'rgba(88,166,255,0.85)', wickColor: '#58a6ff', borderColor: '#58a6ff' }
  return c.close >= c.open
    ? { ...c, color: '#3fb950', wickColor: '#3fb950', borderColor: '#3fb950' }
    : { ...c, color: '#f85149', wickColor: '#f85149', borderColor: '#f85149' }
}

const CHART_OPTIONS = {
  height: 420,
  layout: {
    background: { color: '#161b22' },
    textColor: '#8b949e',
  },
  grid: {
    vertLines: { color: '#21262d' },
    horzLines: { color: '#21262d' },
  },
  crosshair: { mode: CrosshairMode.Normal },
  rightPriceScale: { borderColor: '#30363d' },
  timeScale: {
    borderColor: '#30363d',
    timeVisible: true,
    secondsVisible: false,
  },
  localization: {
    timezone: 'Asia/Kolkata',
  },
}

export default function CandleChart({ symbol, candles }) {
  const chartRef = useRef(null)
  const candleRef = useRef(null)
  const [tooltip, setTooltip] = useState(null)

  const candleData = useMemo(() => (candles || []).map(colorCandle), [candles])
  const volData = useMemo(() => (candles || []).map(c => ({
    time: c.time,
    value: c.volume,
    color: c.close >= c.open ? 'rgba(63,185,80,0.5)' : 'rgba(248,81,73,0.5)',
  })), [candles])

  const handleCrosshairMove = useCallback((param) => {
    if (!param?.time || !param?.seriesData || !candleRef.current) {
      setTooltip(null)
      return
    }
    const bar = param.seriesData.get(candleRef.current)
    if (bar) {
      const c = (candles || []).find(x => x.time === param.time)
      setTooltip({
        time: param.time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: c?.volume ?? null,
      })
    } else {
      setTooltip(null)
    }
  }, [candles])

  const isUp = tooltip && tooltip.close >= tooltip.open
  const last = candles && candles.length > 0 ? candles[candles.length - 1] : null
  const lastUp = last && last.close >= last.open

  return (
    <div className="chart-wrapper">
      <div className="chart-title">
        <span>{symbol} — Candlestick</span>
        {tooltip ? (
          <span className="chart-ohlcv">
            <span className="ohlcv-time">{fmtTime(tooltip.time)}</span>
            <span>O <strong>{fmtPrice(tooltip.open)}</strong></span>
            <span>H <strong className="ohlcv-high">{fmtPrice(tooltip.high)}</strong></span>
            <span>L <strong className="ohlcv-low">{fmtPrice(tooltip.low)}</strong></span>
            <span className={isUp ? 'ohlcv-up' : 'ohlcv-down'}>
              C <strong>{fmtPrice(tooltip.close)}</strong>
            </span>
            <span>Vol <strong>{fmtVol(tooltip.volume)}</strong></span>
          </span>
        ) : last ? (
          <span className="chart-ohlcv">
            <span className="ohlcv-time">{fmtTime(last.time)}</span>
            <span>O <strong>{fmtPrice(last.open)}</strong></span>
            <span>H <strong className="ohlcv-high">{fmtPrice(last.high)}</strong></span>
            <span>L <strong className="ohlcv-low">{fmtPrice(last.low)}</strong></span>
            <span className={lastUp ? 'ohlcv-up' : 'ohlcv-down'}>
              C <strong>{fmtPrice(last.close)}</strong>
            </span>
            <span>Vol <strong>{fmtVol(last.volume)}</strong></span>
          </span>
        ) : null}
      </div>
      <Chart
        ref={chartRef}
        {...CHART_OPTIONS}
        autoSize
        onCrosshairMove={handleCrosshairMove}
      >
        <CandlestickSeries
          ref={candleRef}
          data={candleData}
          reactive
          upColor="#3fb950"
          downColor="#f85149"
          borderUpColor="#3fb950"
          borderDownColor="#f85149"
          wickUpColor="#3fb950"
          wickDownColor="#f85149"
        />
        <HistogramSeries
          data={volData}
          reactive
          color="#1f6feb"
          priceFormat={{ type: 'volume' }}
          priceScaleId="volume"
        >
          <PriceScale id="volume" scaleMargins={{ top: 0.80, bottom: 0 }} />
        </HistogramSeries>
      </Chart>
    </div>
  )
}
