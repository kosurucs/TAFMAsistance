import { useMemo, useState } from 'react'
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

const CHART_W = 1000
const CHART_H = 420
const PRICE_H = 300
const VOLUME_H = 80

const MARGIN = {
  top: 16,
  right: 56,
  bottom: 24,
  left: 12,
}

export default function CandleChart({ symbol, candles }) {
  const [hoverIndex, setHoverIndex] = useState(null)
  const [visibleCount, setVisibleCount] = useState(240)

  const allData = useMemo(() => {
    return Array.isArray(candles) ? candles : []
  }, [candles])

  const data = useMemo(() => {
    if (allData.length <= visibleCount) return allData
    return allData.slice(-visibleCount)
  }, [allData, visibleCount])

  const last = data.length > 0 ? data[data.length - 1] : null
  const active = hoverIndex != null && hoverIndex >= 0 && hoverIndex < data.length ? data[hoverIndex] : last
  const isUp = active && active.close >= active.open
  const lastUp = last && last.close >= last.open

  const geometry = useMemo(() => {
    if (data.length === 0) return null

    const plotLeft = MARGIN.left
    const plotRight = CHART_W - MARGIN.right
    const plotTop = MARGIN.top
    const priceBottom = plotTop + PRICE_H
    const volumeTop = priceBottom + 12
    const volumeBottom = volumeTop + VOLUME_H
    const plotW = plotRight - plotLeft

    let minPrice = Infinity
    let maxPrice = -Infinity
    let maxVol = 0
    for (const c of data) {
      if (c.low < minPrice) minPrice = c.low
      if (c.high > maxPrice) maxPrice = c.high
      if (c.volume > maxVol) maxVol = c.volume
    }

    const pricePad = Math.max((maxPrice - minPrice) * 0.05, 0.5)
    minPrice -= pricePad
    maxPrice += pricePad

    const toY = (p) => {
      if (maxPrice === minPrice) return priceBottom
      return plotTop + ((maxPrice - p) / (maxPrice - minPrice)) * PRICE_H
    }

    const toVolY = (v) => {
      if (maxVol <= 0) return volumeBottom
      return volumeBottom - (v / maxVol) * VOLUME_H
    }

    const step = plotW / Math.max(data.length, 1)
    const bodyW = Math.max(2, Math.min(10, step * 0.68))

    const points = data.map((c, i) => {
      const x = plotLeft + step * i + step / 2
      const openY = toY(c.open)
      const closeY = toY(c.close)
      const highY = toY(c.high)
      const lowY = toY(c.low)
      const top = Math.min(openY, closeY)
      const h = Math.max(1, Math.abs(closeY - openY))
      const up = c.close >= c.open
      return {
        c,
        i,
        x,
        highY,
        lowY,
        bodyY: top,
        bodyH: h,
        bodyW,
        volY: toVolY(c.volume),
        up,
      }
    })

    return {
      plotLeft,
      plotRight,
      plotTop,
      priceBottom,
      volumeTop,
      volumeBottom,
      step,
      minPrice,
      maxPrice,
      points,
    }
  }, [data])

  const onMove = (e) => {
    if (!geometry || data.length === 0) return
    const svg = e.currentTarget
    const rect = svg.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * CHART_W
    const idx = Math.round((x - geometry.plotLeft - geometry.step / 2) / geometry.step)
    if (idx >= 0 && idx < data.length) setHoverIndex(idx)
    else setHoverIndex(null)
  }

  const priceTicks = useMemo(() => {
    if (!geometry) return []
    const ticks = []
    for (let i = 0; i <= 4; i += 1) {
      const ratio = i / 4
      const y = geometry.plotTop + ratio * PRICE_H
      const v = geometry.maxPrice - (geometry.maxPrice - geometry.minPrice) * ratio
      ticks.push({ y, label: fmtPrice(v) })
    }
    return ticks
  }, [geometry])

  const timeTicks = useMemo(() => {
    if (!geometry || data.length === 0) return []
    const count = Math.min(5, data.length)
    const out = []
    for (let i = 0; i < count; i += 1) {
      const idx = Math.round((i * (data.length - 1)) / Math.max(1, count - 1))
      const p = geometry.points[idx]
      if (!p) continue
      out.push({ x: p.x, label: fmtTime(p.c.time).split(', ')[0] })
    }
    return out
  }, [geometry, data])

  const verticalGrid = useMemo(() => {
    if (!geometry || data.length === 0) return []
    const stepCount = 6
    const out = []
    for (let i = 0; i <= stepCount; i += 1) {
      const idx = Math.round((i * (data.length - 1)) / stepCount)
      const p = geometry.points[idx]
      if (p) out.push(p.x)
    }
    return out
  }, [geometry, data])

  const activePoint = hoverIndex != null && geometry?.points[hoverIndex] ? geometry.points[hoverIndex] : null

  const handleZoomIn = () => {
    setVisibleCount((prev) => Math.max(30, Math.floor(prev * 0.75)))
    setHoverIndex(null)
  }

  const handleZoomOut = () => {
    setVisibleCount((prev) => Math.min(allData.length || prev, Math.ceil(prev * 1.35)))
    setHoverIndex(null)
  }

  const handleFit = () => {
    setVisibleCount(Math.max(30, allData.length || 240))
    setHoverIndex(null)
  }

  return (
    <div className="chart-wrapper">
      <div className="chart-title">
        <span>{symbol} — Candlestick</span>
        <div className="chart-tools">
          <button type="button" className="chart-tool-btn" onClick={handleZoomIn} title="Zoom In">+</button>
          <button type="button" className="chart-tool-btn" onClick={handleZoomOut} title="Zoom Out">-</button>
          <button type="button" className="chart-tool-btn fit" onClick={handleFit} title="Fit full data">Fit</button>
        </div>
        {active ? (
          <span className="chart-ohlcv">
            <span className="ohlcv-time">{fmtTime(active.time)}</span>
            <span>O <strong>{fmtPrice(active.open)}</strong></span>
            <span>H <strong className="ohlcv-high">{fmtPrice(active.high)}</strong></span>
            <span>L <strong className="ohlcv-low">{fmtPrice(active.low)}</strong></span>
            <span className={isUp ? 'ohlcv-up' : 'ohlcv-down'}>
              C <strong>{fmtPrice(active.close)}</strong>
            </span>
            <span>Vol <strong>{fmtVol(active.volume)}</strong></span>
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
      <svg
        className="chart-svg"
        viewBox={`0 0 ${CHART_W} ${CHART_H}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${symbol} candlestick chart`}
        onMouseMove={onMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        <rect x="0" y="0" width={CHART_W} height={CHART_H} fill="#161b22" />

        {verticalGrid.map(x => (
          <line key={`vg-${x}`} x1={x} y1={MARGIN.top} x2={x} y2={MARGIN.top + PRICE_H} stroke="#21262d" strokeWidth="1" />
        ))}

        {priceTicks.map(t => (
          <g key={t.y}>
            <line x1={MARGIN.left} y1={t.y} x2={CHART_W - MARGIN.right} y2={t.y} stroke="#21262d" strokeWidth="1" />
            <text x={CHART_W - MARGIN.right + 6} y={t.y + 4} className="chart-axis-label">{t.label}</text>
          </g>
        ))}

        <line
          x1={MARGIN.left}
          y1={MARGIN.top + PRICE_H + 6}
          x2={CHART_W - MARGIN.right}
          y2={MARGIN.top + PRICE_H + 6}
          stroke="#30363d"
          strokeWidth="1"
        />

        {timeTicks.map(t => (
          <text key={`tt-${t.x}`} x={t.x} y={CHART_H - 6} textAnchor="middle" className="chart-axis-label">
            {t.label}
          </text>
        ))}

        {geometry?.points.map(p => (
          <g key={p.c.time}>
            <line
              x1={p.x}
              y1={p.highY}
              x2={p.x}
              y2={p.lowY}
              stroke={p.up ? '#3fb950' : '#f85149'}
              strokeWidth="1"
            />
            <rect
              x={p.x - p.bodyW / 2}
              y={p.bodyY}
              width={p.bodyW}
              height={p.bodyH}
              fill={p.up ? '#3fb950' : '#f85149'}
              stroke={p.up ? '#2ea043' : '#da3633'}
              strokeWidth="0.6"
            />
            <rect
              x={p.x - p.bodyW / 2}
              y={p.volY}
              width={p.bodyW}
              height={Math.max(1, geometry.volumeBottom - p.volY)}
              fill={p.up ? 'rgba(63,185,80,0.45)' : 'rgba(248,81,73,0.45)'}
            />
          </g>
        ))}

        {activePoint && (
          <>
            <line
              x1={activePoint.x}
              y1={geometry.plotTop}
              x2={activePoint.x}
              y2={geometry.volumeBottom}
              stroke="#58a6ff"
              strokeOpacity="0.55"
              strokeWidth="1"
            />
            <line
              x1={geometry.plotLeft}
              y1={activePoint.bodyY + activePoint.bodyH / 2}
              x2={geometry.plotRight}
              y2={activePoint.bodyY + activePoint.bodyH / 2}
              stroke="#58a6ff"
              strokeOpacity="0.35"
              strokeWidth="1"
            />
          </>
        )}
      </svg>
    </div>
  )
}
