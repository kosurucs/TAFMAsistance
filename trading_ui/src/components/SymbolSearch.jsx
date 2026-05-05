import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import './SymbolSearch.css'

export default function SymbolSearch({ watchlist, selected, onSelect, onAdd, onRemove }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const debounceRef = useRef(null)

  // Search instruments API when query changes
  useEffect(() => {
    if (!query.trim()) { setResults([]); return }
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const r = await axios.get(`/api/symbols?search=${encodeURIComponent(query.trim())}`)
        setResults(r.data.symbols || [])
      } catch { setResults([]) }
      finally { setSearching(false) }
    }, 350)
  }, [query])

  const handleAddToWatchlist = (e, sym) => {
    e.stopPropagation()
    onAdd(sym)
    setQuery('')
    setResults([])
  }

  return (
    <div className="symbol-search">
      <div className="section-title">Watchlist</div>

      {/* Watchlist items */}
      <div className="watchlist">
        {watchlist.length === 0 && (
          <div className="wl-empty">Search and add symbols below</div>
        )}
        {watchlist.map(sym => (
          <button
            key={sym}
            className={`wl-item ${selected === sym ? 'active' : ''}`}
            onClick={() => onSelect(sym)}
          >
            <span className="wl-dot" />
            <span className="wl-sym">{sym}</span>
            <span
              className="wl-remove"
              title="Remove"
              onClick={(e) => { e.stopPropagation(); onRemove(sym) }}
            >×</span>
          </button>
        ))}
      </div>

      {/* Search box */}
      <div className="section-title" style={{ marginTop: 16 }}>Search Symbol</div>
      <div className="search-box">
        <span className="search-icon">🔍</span>
        <input
          type="text"
          placeholder="e.g. RELIANCE, HDFC…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="search-input"
        />
        {searching && <span className="search-spinner">⟳</span>}
      </div>

      {/* Search results */}
      {results.length > 0 && (
        <div className="search-results">
          {results.map(s => {
            const inWatchlist = watchlist.includes(s.tradingsymbol)
            return (
              <div
                key={s.instrument_token}
                className="result-item"
              >
                <div className="result-info">
                  <span className="result-symbol">{s.tradingsymbol}</span>
                  <span className="result-name">{s.name}</span>
                </div>
                <button
                  className={`add-btn ${inWatchlist ? 'added' : ''}`}
                  title={inWatchlist ? 'Already in watchlist' : 'Add to watchlist'}
                  disabled={inWatchlist}
                  onClick={(e) => handleAddToWatchlist(e, s.tradingsymbol)}
                >
                  {inWatchlist ? '✓' : '+'}
                </button>
              </div>
            )
          })}
        </div>
      )}

      {query.trim() && !searching && results.length === 0 && (
        <div className="no-results">No symbols found</div>
      )}
    </div>
  )
}
