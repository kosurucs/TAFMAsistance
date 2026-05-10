import { useEffect, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'
import './CandleChart.css'

const MIN_HEIGHT = 200
const MAX_HEIGHT = 1200
const MIN_WIDTH = 320

const CHART_OPTS = {
  layout: {
    background: { color: '#0d1117' },
    textColor: '#c9d1d9',
  },
  grid: {
    vertLines: { color: '#21262d' },
    horzLines: { color: '#21262d' },
  },
  crosshair: { mode: 1 },
  rightPriceScale: { borderColor: '#30363d' },
  timeScale: {
    borderColor: '#30363d',
    timeVisible: true,
    secondsVisible: false,
  },
}

export default function CandleChart({ symbol, candles, interval }) {
  const hostRef = useRef(null)
  const wrapperRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const volSeriesRef = useRef(null)
  const [canvasHeight, setCanvasHeight] = useState(520)
  const [wrapperWidth, setWrapperWidth] = useState(null)

  // Create chart once on mount; destroy on unmount.
  useEffect(() => {
    const el = hostRef.current
    if (!el) return

    const chart = createChart(el, {
      ...CHART_OPTS,
      width: el.clientWidth,
      height: canvasHeight,
    })
    chartRef.current = chart

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#3fb950',
      downColor: '#f85149',
      borderUpColor: '#3fb950',
      borderDownColor: '#f85149',
      wickUpColor: '#3fb950',
      wickDownColor: '#f85149',
    })
    candleSeriesRef.current = candleSeries

    const volSeries = chart.addHistogramSeries({
      color: '#388bfd44',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
    volSeriesRef.current = volSeries

    // Fit on window resize
    const ro = new ResizeObserver(() => {
      if (chartRef.current) {
        chartRef.current.applyOptions({ width: el.clientWidth })
      }
    })
    ro.observe(el)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volSeriesRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Update height when user drags handle.
  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.applyOptions({ height: canvasHeight })
    }
  }, [canvasHeight])

  // Feed new candle data whenever symbol / candles change.
  useEffect(() => {
    if (!candleSeriesRef.current || !volSeriesRef.current) return
    if (!candles || candles.length === 0) {
      candleSeriesRef.current.setData([])
      volSeriesRef.current.setData([])
      return
    }

    const ohlc = candles.map(c => ({
      time: c.time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))
    const vol = candles.map(c => ({
      time: c.time,
      value: c.volume,
      color: c.close >= c.open ? '#3fb95044' : '#f8514944',
    }))

    candleSeriesRef.current.setData(ohlc)
    volSeriesRef.current.setData(vol)
    chartRef.current.timeScale().fitContent()
  }, [candles])

  const startDrag = (e, type) => {
    e.preventDefault()
    const wrapper = wrapperRef.current
    if (!wrapper) return

    const startY = e.clientY
    const startX = e.clientX
    const startH = hostRef.current.getBoundingClientRect().height
    const startW = wrapper.getBoundingClientRect().width

    const onMouseMove = (ev) => {
      if (type === 'bottom' || type === 'corner') {
        const newH = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, startH + (ev.clientY - startY)))
        setCanvasHeight(Math.round(newH))
      }
      if (type === 'right' || type === 'corner') {
        const newW = Math.max(MIN_WIDTH, startW + (ev.clientX - startX))
        setWrapperWidth(Math.round(newW))
      }
    }

    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  return (
    <div
      ref={wrapperRef}
      className="chart-wrapper"
      style={wrapperWidth ? { width: wrapperWidth } : undefined}
    >
      <div className="chart-title">
        <span>{symbol} — Candlestick Chart ({interval})</span>
        <div className="chart-title-right">
          <span className="chart-size-hint">{canvasHeight}px{wrapperWidth ? ` × ${wrapperWidth}px` : ''}</span>
          <span className="chart-note">Data source: Zerodha Kite</span>
        </div>
      </div>
      <div
        ref={hostRef}
        className="chart-canvas"
        role="img"
        aria-label={`${symbol} candlestick chart`}
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
  )
}
