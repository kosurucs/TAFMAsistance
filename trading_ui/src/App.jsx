import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import SymbolSearch from './components/SymbolSearch.jsx'
import CandleChart from './components/CandleChart.jsx'
import IndicatorPanel from './components/IndicatorPanel.jsx'
import QuoteBar from './components/QuoteBar.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import OrderModal from './components/OrderModal.jsx'
import GTTModal from './components/GTTModal.jsx'
import PortfolioPanel from './components/PortfolioPanel.jsx'
import './App.css'

const API = '/api'
const LS_KEY = 'trading_watchlist'
const DEFAULT_WATCHLIST = ['RELIANCE', 'INFY', 'TCS', 'HDFCBANK']

export default function App() {
  const [authChecking, setAuthChecking] = useState(true)
  const [authRequired, setAuthRequired] = useState(false)
  const [authBusy, setAuthBusy] = useState(false)
  const [authError, setAuthError] = useState('')
  const [loginUrl, setLoginUrl] = useState('')
  const [callbackUrl, setCallbackUrl] = useState('')

  const [watchlist, setWatchlist] = useState([])
  const [selectedSymbol, setSelectedSymbol] = useState(null)
  const [marketData, setMarketData] = useState(null)
  const [quote, setQuote] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [interval, setSelectedInterval] = useState('minute')

  const [activeTab, setActiveTab] = useState('dashboard')  // dashboard | portfolio
  const [showOrderModal, setShowOrderModal] = useState(false)
  const [showGTTModal, setShowGTTModal] = useState(false)
  const [botBusy, setBotBusy] = useState(false)
  const [botResult, setBotResult] = useState(null)

  const fetchAbortRef = useRef(null)

  useEffect(() => {
    let active = true

    const checkAuth = async () => {
      try {
        const r = await axios.get(`${API}/auth/status`)
        const needsLogin = Boolean(r.data?.requires_login)
        if (active) {
          setAuthRequired(needsLogin)
          // Pre-populate login URL from the status response so the UI
          // can open it immediately without a second round-trip.
          if (needsLogin && r.data?.login_url) {
            setLoginUrl(r.data.login_url)
          }
        }
      } catch {
        if (active) setAuthRequired(false)
      } finally {
        if (active) setAuthChecking(false)
      }
    }

    checkAuth()
    return () => { active = false }
  }, [])

  // Auto-open Kite login in a new tab as soon as auth is required and
  // we have the URL (set either from auth/status or from openKiteLogin).
  const autoOpenedRef = useRef(false)
  useEffect(() => {
    if (!authRequired || authChecking || !loginUrl || autoOpenedRef.current) return
    autoOpenedRef.current = true
    window.open(loginUrl, '_blank', 'noopener,noreferrer')
  }, [authRequired, authChecking, loginUrl])

  // Load watchlist: localStorage first, fall back to API
  useEffect(() => {
    if (authChecking || authRequired) return

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
        const apiSymbols = Array.isArray(r.data?.symbols) ? r.data.symbols : []
        const nextSymbols = apiSymbols.length > 0 ? apiSymbols : DEFAULT_WATCHLIST
        setWatchlist(nextSymbols)
        setSelectedSymbol(nextSymbols[0])
      })
      .catch(() => {
        // Keep UI usable even when API is temporarily unavailable at startup.
        setWatchlist(DEFAULT_WATCHLIST)
        setSelectedSymbol(DEFAULT_WATCHLIST[0])
      })
  }, [authChecking, authRequired])

  // Persist watchlist to localStorage on every change
  useEffect(() => {
    if (watchlist.length > 0) localStorage.setItem(LS_KEY, JSON.stringify(watchlist))
  }, [watchlist])

  const addToWatchlist = useCallback((sym) => {
    setWatchlist(prev => prev.includes(sym) ? prev : [...prev, sym])
  }, [])

  const removeFromWatchlist = useCallback((sym) => {
    const next = watchlist.filter(s => s !== sym)

    if (next.length === 0) {
      // Keep one symbol selected so chart + chat never disappear.
      setWatchlist(DEFAULT_WATCHLIST)
      setSelectedSymbol(DEFAULT_WATCHLIST[0])
      return
    }

    setWatchlist(next)

    if (!selectedSymbol || selectedSymbol === sym) {
      setSelectedSymbol(next[0])
    }
  }, [watchlist, selectedSymbol])

  // Self-heal if selection is out of sync with the current watchlist.
  useEffect(() => {
    if (watchlist.length === 0) return
    if (!selectedSymbol || !watchlist.includes(selectedSymbol)) {
      setSelectedSymbol(watchlist[0])
    }
  }, [watchlist, selectedSymbol])

  // Fetch data whenever symbol or interval changes.
  // Uses AbortController so switching symbols quickly never shows stale data.
  const fetchData = useCallback(async (sym, iv) => {
    if (!sym) return

    // Cancel any in-flight request for a previous symbol
    if (fetchAbortRef.current) fetchAbortRef.current.abort()
    const controller = new AbortController()
    fetchAbortRef.current = controller

    setLoading(true)
    setError(null)
    try {
      const [mkt, qt] = await Promise.all([
        axios.get(`${API}/market-data/${sym}?interval=${iv}&days_back=0`, { signal: controller.signal }),
        axios.get(`${API}/quote/${sym}`, { signal: controller.signal }),
      ])
      if (!controller.signal.aborted) {
        setMarketData(mkt.data)
        setQuote(qt.data)
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(e.response?.data?.detail || e.message)
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (authChecking || authRequired) return
    fetchData(selectedSymbol, interval)
    // Cleanup: abort the in-flight request when the effect re-runs
    // (symbol / interval changed) or component unmounts.
    return () => {
      if (fetchAbortRef.current) fetchAbortRef.current.abort()
    }
  }, [authChecking, authRequired, selectedSymbol, interval, fetchData])

  // Auto-refresh every 60 seconds
  useEffect(() => {
    if (authChecking || authRequired) return undefined
    const id = window.setInterval(() => fetchData(selectedSymbol, interval), 60000)
    return () => clearInterval(id)
  }, [authChecking, authRequired, selectedSymbol, interval, fetchData])

  const openKiteLogin = useCallback(async () => {
    setAuthBusy(true)
    setAuthError('')
    try {
      const r = await axios.get(`${API}/auth/login-url`)
      const url = r.data?.login_url
      if (!url) throw new Error('Login URL not returned by server')
      setLoginUrl(url)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (e) {
      setAuthError(e.response?.data?.detail || e.message)
    } finally {
      setAuthBusy(false)
    }
  }, [])

  const submitCallbackUrl = useCallback(async () => {
    const url = callbackUrl.trim()
    if (!url || authBusy) return

    setAuthBusy(true)
    setAuthError('')
    try {
      await axios.post(`${API}/auth/exchange`, { callback_url: url })
      setAuthRequired(false)
      setCallbackUrl('')
    } catch (e) {
      setAuthError(e.response?.data?.detail || e.message)
    } finally {
      setAuthBusy(false)
    }
  }, [authBusy, callbackUrl])

  const runBot = useCallback(async () => {
    if (!selectedSymbol || botBusy) return
    setBotBusy(true)
    setBotResult(null)
    try {
      const r = await axios.post(`${API}/bot/run`, { symbol: selectedSymbol })
      setBotResult(r.data)
    } catch (e) {
      setBotResult({ error: e.response?.data?.detail || e.message })
    } finally {
      setBotBusy(false)
    }
  }, [selectedSymbol, botBusy])

  const handleSymbolSelect = (sym) => {
    if (sym === selectedSymbol) return   // no-op if already selected
    // Abort any in-flight request immediately so the old symbol's response
    // can never overwrite state after we've switched away.
    if (fetchAbortRef.current) fetchAbortRef.current.abort()
    setSelectedSymbol(sym)
    setMarketData(null)  // clear stale indicators / candles
    setQuote(null)       // clear stale quote
    setError(null)
  }

  if (authChecking) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <h2>Checking authentication...</h2>
          <p>Preparing your trading workspace.</p>
        </div>
      </div>
    )
  }

  if (authRequired) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <h1>Kite Login Required</h1>
          <p>
            Launch login, complete Zerodha authentication, then paste the full callback URL
            (contains request_token) to enter the dashboard.
          </p>

          <button className="auth-primary" onClick={openKiteLogin} disabled={authBusy}>
            {authBusy ? 'Opening...' : 'Login'}
          </button>

          {loginUrl && (
            <p className="auth-hint">
              Kite login opened in a new tab.
              If the tab did not open,{' '}
              <a href={loginUrl} target="_blank" rel="noopener noreferrer">click here to login</a>.
            </p>
          )}

          <label htmlFor="callback-url" className="auth-label">Paste callback URL</label>
          <textarea
            id="callback-url"
            className="auth-input"
            rows={3}
            value={callbackUrl}
            onChange={(e) => setCallbackUrl(e.target.value)}
            placeholder="https://localhost:7049/?action=login&type=login&status=success&request_token=..."
          />

          <button
            className="auth-primary"
            onClick={submitCallbackUrl}
            disabled={authBusy || !callbackUrl.trim()}
          >
            {authBusy ? 'Authenticating...' : 'Verify And Enter App'}
          </button>

          {authError && <div className="auth-error">{authError}</div>}
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="logo">
          <span className="logo-icon">📈</span>
          <span className="logo-text">TAFMAsistance</span>
          <span className="logo-sub">AI Trading Bot</span>
        </div>

        {/* ── Top Nav ── */}
        <nav className="top-nav">
          <button
            className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >Dashboard</button>
          <button
            className={`nav-tab ${activeTab === 'portfolio' ? 'active' : ''}`}
            onClick={() => setActiveTab('portfolio')}
          >Portfolio</button>
        </nav>

        {/* ── Right actions ── */}
        <div className="header-right">
          {selectedSymbol && activeTab === 'dashboard' && (
            <>
              <button
                className="hdr-btn order-btn"
                onClick={() => setShowOrderModal(true)}
                title="Place a manual order"
              >+ Order</button>
              <button
                className="hdr-btn gtt-btn"
                onClick={() => setShowGTTModal(true)}
                title="Place a GTT (Good Till Triggered) order"
              >⚡ GTT</button>
              <button
                className={`hdr-btn bot-btn ${botBusy ? 'busy' : ''}`}
                onClick={runBot}
                disabled={botBusy}
                title="Run AI trading agent for this symbol"
              >{botBusy ? '⟳ Running…' : '▶ Run Bot'}</button>
            </>
          )}
          {selectedSymbol && (
            <span className={`live-badge ${loading ? 'loading' : 'live'}`}>
              {loading ? '⟳ Updating…' : '● LIVE'}
            </span>
          )}
        </div>
      </header>

      {/* ── Bot result banner ── */}
      {botResult && activeTab === 'dashboard' && (
        <div className={`bot-result-bar ${botResult.error ? 'err' : botResult.action === 'BUY' ? 'buy' : botResult.action === 'SELL' ? 'sell' : 'hold'}`}>
          {botResult.error
            ? `Bot error: ${botResult.error}`
            : <>
                Bot decision for <strong>{selectedSymbol}</strong>:&nbsp;
                <strong>{botResult.action}</strong>
                {botResult.order_id && <> | Order <code>{botResult.order_id}</code></>}
                {botResult.reasoning && <span className="bot-reason"> — {botResult.reasoning}</span>}
              </>
          }
          <button className="bot-result-close" onClick={() => setBotResult(null)}>✕</button>
        </div>
      )}

      <div className="layout">
        {/* ── Sidebar (always visible) ── */}
        <aside className="sidebar">
          <SymbolSearch
            watchlist={watchlist}
            selected={selectedSymbol}
            onSelect={handleSymbolSelect}
            onAdd={addToWatchlist}
            onRemove={removeFromWatchlist}
          />
          {activeTab === 'dashboard' && selectedSymbol && (
            marketData?.indicators && Object.keys(marketData.indicators).length > 0
              ? <IndicatorPanel indicators={marketData.indicators} />
              : loading
                ? <div className="sidebar-loading">Loading {selectedSymbol}…</div>
                : null
          )}
        </aside>

        {/* ── Main content ── */}
        <main className="main">
          {/* ── PORTFOLIO TAB ── */}
          {activeTab === 'portfolio' && (
            <PortfolioPanel />
          )}

          {/* ── DASHBOARD TAB ── */}
          {activeTab === 'dashboard' && (
            <>
              {error && <div className="error-banner">⚠ {error}</div>}

              {selectedSymbol && (
                <>
                  <QuoteBar symbol={selectedSymbol} quote={quote} />

                  {/* Interval + action toolbar */}
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
                    >⟳ Refresh</button>

                    {/* Inline order + bot shortcuts */}
                    <div className="toolbar-right">
                      <button className="tb-order-btn buy" onClick={() => setShowOrderModal(true)}>
                        ▲ Buy
                      </button>
                      <button className="tb-order-btn sell" onClick={() => setShowOrderModal(true)}>
                        ▼ Sell
                      </button>
                      <button className="tb-order-btn gtt" onClick={() => setShowGTTModal(true)}>
                        ⚡ GTT
                      </button>
                    </div>
                  </div>

                  {/* Chart — always mounted; fed with Kite candle data */}
                  {marketData?.candles
                    ? <CandleChart
                        key={selectedSymbol}
                        symbol={selectedSymbol}
                        candles={marketData.candles}
                        interval={interval}
                      />
                    : !error && (
                        <div className="loading-placeholder">
                          {loading ? `Loading ${selectedSymbol} chart…` : 'No chart data available'}
                        </div>
                      )
                  }
                </>
              )}

              <ChatPanel
                symbol={selectedSymbol}
                indicators={marketData?.indicators || {}}
              />

              {!selectedSymbol && (
                <div className="empty-state">
                  <span>🔍</span>
                  <p>Search or select a stock symbol to view its chart</p>
                </div>
              )}
            </>
          )}
        </main>
      </div>

      {/* ── GTT Modal ── */}
      {showGTTModal && selectedSymbol && (
        <GTTModal
          symbol={selectedSymbol}
          quote={quote}
          onClose={() => setShowGTTModal(false)}
          onSaved={() => setShowGTTModal(false)}
        />
      )}

      {/* ── Order Modal ── */}
      {showOrderModal && (
        <OrderModal
          symbol={selectedSymbol}
          quote={quote}
          onClose={() => setShowOrderModal(false)}
          onFilled={() => {
            // Auto-switch to portfolio after order placed
            setTimeout(() => setActiveTab('portfolio'), 1200)
          }}
        />
      )}
    </div>
  )
}
