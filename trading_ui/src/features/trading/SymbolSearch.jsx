import { useState, useEffect, useRef, useCallback } from 'react';
import { useMarketStore } from '../../store';
import './SymbolSearch.css';

const STORAGE_KEY     = 'tafm_watchlist';
const DEFAULT_SYMBOLS = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK'];
const DEBOUNCE_MS     = 320;

function loadWatchlist() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return DEFAULT_SYMBOLS;
}

export function SymbolSearch() {
  const { selectedSymbol, setSymbol } = useMarketStore();

  const [watchlist,  setWatchlist]  = useState(loadWatchlist);
  const [query,      setQuery]      = useState('');
  const [results,    setResults]    = useState([]);
  const [searching,  setSearching]  = useState(false);
  const [open,       setOpen]       = useState(false);

  const inputRef    = useRef(null);
  const dropdownRef = useRef(null);
  const debounceRef = useRef(null);

  // Persist watchlist to localStorage
  const saveWatchlist = useCallback((list) => {
    setWatchlist(list);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const onDown = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
        setQuery('');
        setResults([]);
      }
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  // Debounced symbol search
  useEffect(() => {
    clearTimeout(debounceRef.current);
    if (!query.trim()) { setResults([]); return; }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res  = await fetch(`/api/symbols?search=${encodeURIComponent(query.trim())}`);
        const data = await res.json();
        setResults(data.symbols || []);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, DEBOUNCE_MS);
  }, [query]);

  const handleOpenSearch = () => {
    setOpen(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const handleAddSymbol = (sym) => {
    if (!watchlist.includes(sym)) saveWatchlist([...watchlist, sym]);
    setSymbol(sym);
    setOpen(false);
    setQuery('');
    setResults([]);
  };

  const handleRemove = (e, sym) => {
    e.stopPropagation();
    const updated = watchlist.filter(s => s !== sym);
    saveWatchlist(updated.length ? updated : DEFAULT_SYMBOLS);
    if (selectedSymbol === sym && updated.length > 0) setSymbol(updated[0]);
  };

  return (
    <div className="wl-bar" ref={dropdownRef}>
      {/* ── Watchlist pills with | separators ────────────── */}
      <div className="wl-symbols">
        {watchlist.map((sym, idx) => (
          <span key={sym} className="wl-sym-group">
            {idx > 0 && <span className="wl-pipe">|</span>}
            <button
              className={`wl-pill ${selectedSymbol === sym ? 'wl-pill--active' : ''}`}
              onClick={() => setSymbol(sym)}
              title={sym}
            >
              <span className={`wl-dot ${selectedSymbol === sym ? 'wl-dot--active' : ''}`} />
              {sym}
              <span
                className="wl-remove"
                role="button"
                aria-label={`Remove ${sym}`}
                onClick={(e) => handleRemove(e, sym)}
              >×</span>
            </button>
          </span>
        ))}
      </div>

      {/* ── Search trigger / input ────────────────────────── */}
      <div className="wl-search-wrap">
        {!open ? (
          <button className="wl-add-btn" onClick={handleOpenSearch} title="Add symbol">
            <span className="wl-add-icon">+</span>
            <span>Add</span>
          </button>
        ) : (
          <div className="wl-search-box">
            <span className="wl-search-icon">⌕</span>
            <input
              ref={inputRef}
              type="text"
              className="wl-search-input"
              placeholder="Search symbol…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Escape' && setOpen(false)}
            />
            {searching && <span className="wl-search-spin">⟳</span>}
          </div>
        )}

        {/* Results dropdown */}
        {open && (results.length > 0 || (query.trim() && !searching)) && (
          <div className="wl-results">
            {results.length === 0 ? (
              <div className="wl-results-empty">No results for "{query}"</div>
            ) : (
              results.map(s => {
                const inList = watchlist.includes(s.tradingsymbol);
                return (
                  <button
                    key={s.instrument_token}
                    className={`wl-result-item ${inList ? 'wl-result-item--added' : ''}`}
                    onClick={() => !inList && handleAddSymbol(s.tradingsymbol)}
                    disabled={inList}
                  >
                    <span className="wl-result-sym">{s.tradingsymbol}</span>
                    <span className="wl-result-name">{s.name}</span>
                    <span className="wl-result-badge">{inList ? '✓' : '+'}</span>
                  </button>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}

