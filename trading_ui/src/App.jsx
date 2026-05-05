import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import SymbolSearch from './components/SymbolSearch.jsx'
import CandleChart from './components/CandleChart.jsx'
import IndicatorPanel from './components/IndicatorPanel.jsx'
import QuoteBar from './components/QuoteBar.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import './App.css'

const API = '/api'
const LS_KEY = 'trading_watchlist'

export default function App() {
  const [watchlist, setWatchlist] = useState([])
  const [selectedSymbol, setSelectedSymbol] = useState(null)
  const [marketData, setMarketData] = useState(null)
  const [quote, setQuote] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [interval, setSelectedInterval] = useState('minute')

  // Load watchlist: localStorage first, fall back to API
  useEffect(() => {
    const saved = localStorage.getItem(LS_KEY)
    if (saved) {
      try {
        const syms = JSON.parse(saved)
        if (Array.isArray(syms) && syms.length > 0) {
          setWatchlist(syms)
          setSelectedSymbol(syms[0])
          return
        }
      } catch {}
    }
    axios.get(`${API}/watchlist`)
      .then(r => {
        setWatchlist(r.data.symbols)
        if (r.data.symbols.length > 0) setSelectedSymbol(r.data.symbols[0])
      })
      .catch(() => {})
  }, [])

  // Persist watchlist to localStorage on every change
  useEffect(() => {
    if (watchlist.length > 0) localStorage.setItem(LS_KEY, JSON.stringify(watchlist))
  }, [watchlist])

  const addToWatchlist = useCallback((sym) => {
    setWatchlist(prev => prev.includes(sym) ? prev : [...prev, sym])
  }, [])

  const removeFromWatchlist = useCallback((sym) => {
    setWatchlist(prev => {
      const next = prev.filter(s => s !== sym)
      if (next.length === 0) localStorage.removeItem(LS_KEY)
      return next
    })
    setSelectedSymbol(prev => prev === sym ? null : prev)
  }, [])

  // Fetch data whenever symbol or interval changes
  const fetchData = useCallback(async (sym, iv) => {
    if (!sym) return
    setLoading(true)
    setError(null)
    try {
      const [mkt, qt] = await Promise.all([
        axios.get(`${API}/market-data/${sym}?interval=${iv}&days_back=0`),
        axios.get(`${API}/quote/${sym}`),
      ])
      setMarketData(mkt.data)
      setQuote(qt.data)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData(selectedSymbol, interval)
  }, [selectedSymbol, interval, fetchData])

  // Auto-refresh every 60 seconds
  useEffect(() => {
    const id = window.setInterval(() => fetchData(selectedSymbol, interval), 60000)
    return () => clearInterval(id)
  }, [selectedSymbol, interval, fetchData])

  const handleSymbolSelect = (sym) => {
    setSelectedSymbol(sym)
    setMarketData(null)
    setQuote(null)
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="logo">
          <span className="logo-icon">📈</span>
          <span className="logo-text">TAFMAsistance</span>
          <span className="logo-sub">AI Trading Bot</span>
        </div>
        <div className="header-right">
          {selectedSymbol && (
            <span className={`live-badge ${loading ? 'loading' : 'live'}`}>
              {loading ? '⟳ Updating…' : '● LIVE'}
            </span>
          )}
        </div>
      </header>

      <div className="layout">
        {/* Sidebar */}
        <aside className="sidebar">
          <SymbolSearch
            watchlist={watchlist}
            selected={selectedSymbol}
            onSelect={handleSymbolSelect}
            onAdd={addToWatchlist}
            onRemove={removeFromWatchlist}
          />
          {/* Indicators */}
          {marketData?.indicators && Object.keys(marketData.indicators).length > 0 && (
            <IndicatorPanel indicators={marketData.indicators} />
          )}
        </aside>

        {/* Main content */}
        <main className="main">
          {error && (
            <div className="error-banner">⚠ {error}</div>
          )}

          {selectedSymbol && (
            <>
              {/* Quote bar */}
              <QuoteBar symbol={selectedSymbol} quote={quote} />

              {/* Interval selector */}
              <div className="toolbar">
                <span className="toolbar-label">Interval:</span>
                {['minute', '3minute', '5minute', '15minute', '30minute', '60minute', 'day', 'week', 'month'].map(iv => (
                  <button
                    key={iv}
                    className={`iv-btn ${interval === iv ? 'active' : ''}`}
                    onClick={() => setSelectedInterval(iv)}
                  >
                    {iv === 'minute' ? '1m' :
                     iv === '3minute' ? '3m' :
                     iv === '5minute' ? '5m' :
                     iv === '15minute' ? '15m' :
                     iv === '30minute' ? '30m' :
                     iv === '60minute' ? '1h' :
                     iv === 'day' ? '1D' :
                     iv === 'week' ? '1W' : '1M'}
                  </button>
                ))}
                <button
                  className="refresh-btn"
                  onClick={() => fetchData(selectedSymbol, interval)}
                  disabled={loading}
                >
                  ⟳ Refresh
                </button>
              </div>

              {/* Chart */}
              {marketData ? (
                <CandleChart
                  symbol={selectedSymbol}
                  candles={marketData.candles}
                />
              ) : (
                !error && <div className="loading-placeholder">Loading chart…</div>
              )}

              {/* AI Chat */}
              <ChatPanel
                symbol={selectedSymbol}
                indicators={marketData?.indicators || {}}
              />
            </>
          )}

          {!selectedSymbol && (
            <div className="empty-state">
              <span>🔍</span>
              <p>Search or select a stock symbol to view its chart</p>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
