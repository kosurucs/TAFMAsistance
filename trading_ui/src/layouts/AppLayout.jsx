import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useMarketStore } from '../store';
import './AppLayout.css';

const NAV_TABS = [
  { label: 'Dashboard',  path: '/' },
  { label: 'Portfolio',  path: '/portfolio' },
  { label: 'Historical', path: '/historical' },
  { label: 'Backtest',   path: '/backtest' },
  { label: 'Simulate',   path: '/simulate' },
  { label: 'LLM Studio', path: '/llm-studio' },
  { label: 'Algo',       path: '/algo' },
];

const REFRESH_INTERVAL_MS = 15_000;

function isMarketOpen() {
  const now = new Date();
  // IST = UTC+5:30
  const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
  const istMs  = utcMs + 5.5 * 3600000;
  const ist    = new Date(istMs);
  const day    = ist.getDay();       // 0=Sun 6=Sat
  const h      = ist.getHours();
  const m      = ist.getMinutes();
  const mins   = h * 60 + m;
  if (day === 0 || day === 6) return false;
  return mins >= 555 && mins < 930; // 09:15–15:30
}

function ISTClock() {
  const [time, setTime] = useState('');
  useEffect(() => {
    const tick = () => {
      const now  = new Date();
      const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
      const istMs = utcMs + 5.5 * 3600000;
      const ist   = new Date(istMs);
      setTime(ist.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="hdr-clock">{time} IST</span>;
}

function RefreshCountdown() {
  const { lastUpdated, refreshing } = useMarketStore();
  const [secsLeft, setSecsLeft] = useState(REFRESH_INTERVAL_MS / 1000);

  useEffect(() => {
    if (!lastUpdated) return;
    const tick = () => {
      const elapsed = Date.now() - lastUpdated;
      const left = Math.max(0, Math.ceil((REFRESH_INTERVAL_MS - elapsed) / 1000));
      setSecsLeft(left);
    };
    tick();
    const id = setInterval(tick, 500);
    return () => clearInterval(id);
  }, [lastUpdated]);

  if (refreshing) {
    return <span className="hdr-refresh hdr-refresh--syncing">⟳ Syncing…</span>;
  }
  return (
    <span className="hdr-refresh" title="Next auto-refresh">
      ⟳ {secsLeft}s
    </span>
  );
}

export function AppLayout({ children }) {
  const { pathname } = useLocation();
  const open = isMarketOpen();

  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="app-header__brand">
          <span className="app-header__logo">⚡</span>
          <span className="app-header__title">TAFM</span>
          <span className="app-header__subtitle">Assistant</span>
        </div>

        <nav className="app-nav">
          {NAV_TABS.map(t => (
            <Link
              key={t.path}
              to={t.path}
              className={`app-nav__tab ${pathname === t.path ? 'app-nav__tab--active' : ''}`}
            >
              {t.label}
            </Link>
          ))}
        </nav>

        <div className="app-header__right">
          <ISTClock />
          <RefreshCountdown />
          <div className={`market-status ${open ? 'market-status--open' : 'market-status--closed'}`}>
            <span className={`status-dot ${open ? 'status-dot--live' : 'status-dot--closed'}`} />
            <span>{open ? 'Market Open' : 'Market Closed'}</span>
          </div>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
