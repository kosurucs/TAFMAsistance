import { Link, useLocation } from 'react-router-dom';
import './AppLayout.css';

const NAV_TABS = [
  { label: 'Dashboard', path: '/' },
  { label: 'Portfolio', path: '/portfolio' },
  { label: 'Historical', path: '/historical' },
  { label: 'Backtest', path: '/backtest' },
  { label: 'Simulate', path: '/simulate' },
  { label: 'LLM Studio', path: '/llm-studio' },
];

export function AppLayout({ children }) {
  const { pathname } = useLocation();
  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="app-header__brand">
          <span className="app-header__logo">⚡</span>
          <span className="app-header__title">TAFM Assistant</span>
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
        <div className="app-header__status">
          <span className="status-dot status-dot--live" />
          <span className="app-header__status-text">Live</span>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
