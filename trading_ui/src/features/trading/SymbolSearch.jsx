import { useState, useEffect, useRef } from 'react';
import { useMarketStore } from '../../store';
import './SymbolSearch.css';

const DEFAULT_WATCHLIST = ['RELIANCE', 'INFY', 'TCS', 'HDFCBANK'];

export function SymbolSearch() {
  const { selectedSymbol, setSymbol } = useMarketStore();
  const [watchlist, setWatchlist] = useState(DEFAULT_WATCHLIST);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef(null);

  // Search instruments API when query changes
  useEffect(() => {
    if (!query.trim()) { 
      setResults([]); 
      return; 
    }
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await fetch(`/api/symbols?search=${encodeURIComponent(query.trim())}`);
        const data = await res.json();
        setResults(data.symbols || []);
      } catch { 
        setResults([]); 
      } finally { 
        setSearching(false); 
      }
    }, 350);
  }, [query]);

  const handleAddToWatchlist = (e, sym) => {
    e.stopPropagation();
    if (!watchlist.includes(sym)) {
      setWatchlist([...watchlist, sym]);
      localStorage.setItem('trading_watchlist', JSON.stringify([...watchlist, sym]));
    }
    setQuery('');
    setResults([]);
  };

  const handleRemove = (sym) => {
    const updated = watchlist.filter(s => s !== sym);
    setWatchlist(updated);
    localStorage.setItem('trading_watchlist', JSON.stringify(updated));
  };

  return (
    <div className="symbol-search">
      {/* Watchlist items */}
      <div className="watchlist">
        {watchlist.map(sym => (
          <button
            key={sym}
            className={`wl-item ${selectedSymbol === sym ? 'active' : ''}`}
            onClick={() => setSymbol(sym)}
          >
            <span className="wl-dot" />
            <span className="wl-sym">{sym}</span>
            <span
              className="wl-remove"
              title="Remove"
              onClick={(e) => { e.stopPropagation(); handleRemove(sym); }}
            >×</span>
          </button>
        ))}
      </div>

      {/* Search box */}
      <div className="search-box">
        <span className="search-icon">🔍</span>
        <input
          type="text"
          placeholder="Search symbol…"
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
            const inWatchlist = watchlist.includes(s.tradingsymbol);
            return (
              <div key={s.instrument_token} className="result-item">
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
            );
          })}
        </div>
      )}

      {query.trim() && !searching && results.length === 0 && (
        <div className="search-empty">No symbols found</div>
      )}
    </div>
  );
}
