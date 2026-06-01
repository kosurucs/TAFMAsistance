import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import useAuthStore from '../store/authStore';
import '../design-system/theme.css';
import './Login.css';

const POLL_INTERVAL_MS  = 3000;   // poll auth every 3s while waiting for Kite
const REDIRECT_DELAY_MS = 2500;   // countdown before pushing to /

// ─── small sub-components ────────────────────────────────────
function BrandHeader() {
  return (
    <div className="lp-brand">
      <span className="lp-logo">⚡</span>
      <div>
        <div className="lp-title">TAFM Assistant</div>
        <div className="lp-tagline">AI Trading Analysis · Analysis-Only Mode</div>
      </div>
    </div>
  );
}

function FeatureList() {
  const items = [
    'Real-time market data & live quotes',
    'Technical indicators (RSI, MACD, EMA, ATR…)',
    'AI-powered trade recommendations (read-only)',
    'Backtesting & strategy analysis',
    'Portfolio monitoring (no order placement)',
  ];
  return (
    <ul className="lp-features">
      {items.map(f => <li key={f}><span className="lp-check">✓</span>{f}</li>)}
    </ul>
  );
}

// ─── phases: 'idle' | 'fetching_url' | 'waiting_kite' | 'exchanging' | 'success' | 'error'
export default function Login() {
  const navigate        = useNavigate();
  const [searchParams]  = useSearchParams();
  const {
    authenticated, paperTrading, tokenExpired, loginUrl,
    checkAuthStatus, getLoginUrl, exchangeToken,
  } = useAuthStore();

  const [phase,       setPhase]       = useState('idle');
  const [errorMsg,    setErrorMsg]    = useState(null);
  const [countdown,   setCountdown]   = useState(3);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [manualToken, setManualToken] = useState('');

  const pollRef = useRef(null);
  const cdRef   = useRef(null);

  const stopPolling   = () => { clearInterval(pollRef.current); pollRef.current = null; };
  const stopCountdown = () => { clearInterval(cdRef.current);   cdRef.current   = null; };
  useEffect(() => () => { stopPolling(); stopCountdown(); }, []);

  // Begin countdown → navigate
  const beginRedirect = useCallback(() => {
    stopPolling();
    setPhase('success');
    let secs = Math.ceil(REDIRECT_DELAY_MS / 1000);
    setCountdown(secs);
    cdRef.current = setInterval(() => {
      secs -= 1;
      setCountdown(secs);
      if (secs <= 0) { stopCountdown(); navigate('/'); }
    }, 1000);
  }, [navigate]);

  // React to authenticated state change → start redirect
  useEffect(() => {
    if (authenticated && phase !== 'idle' && phase !== 'success') {
      beginRedirect();
    }
  }, [authenticated, phase, beginRedirect]);

  // On mount: handle Zerodha callback OR normal auth-check
  useEffect(() => {
    const requestToken   = searchParams.get('request_token');
    const callbackStatus = searchParams.get('status');

    // --- Zerodha just redirected back with a token ---
    if (requestToken && (!callbackStatus || callbackStatus === 'success')) {
      window.history.replaceState({}, '', '/login');
      setPhase('exchanging');
      exchangeToken(requestToken)
        .catch(err => {
          setPhase('error');
          setErrorMsg(err.message || 'Authentication failed. Please try again.');
        });
      return;
    }

    if (callbackStatus && callbackStatus !== 'success') {
      setErrorMsg('Login was cancelled or failed.');
      window.history.replaceState({}, '', '/login');
    }

    // --- Normal page load: check if already authenticated ---
    checkAuthStatus()
      .then(s => { if (s.authenticated) navigate('/'); })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Open Zerodha in a new tab + start polling
  const handleKiteLogin = () => {
    setErrorMsg(null);
    const openAndPoll = (url) => {
      window.open(url, '_blank', 'noopener,noreferrer');
      setPhase('waiting_kite');
      stopPolling();
      pollRef.current = setInterval(() => {
        checkAuthStatus().catch(() => {});
      }, POLL_INTERVAL_MS);
    };

    if (loginUrl) { openAndPoll(loginUrl); return; }

    setPhase('fetching_url');
    getLoginUrl()
      .then(url => { setPhase('idle'); openAndPoll(url); })
      .catch(err => { setPhase('error'); setErrorMsg(err.message || 'Could not fetch Kite login URL.'); });
  };

  const handleCancelWait = () => { stopPolling(); setPhase('idle'); };

  const handleSkip = () => navigate('/');

  const handleManualExchange = async () => {
    const val = manualToken.trim();
    if (!val) return;
    setErrorMsg(null);
    setPhase('exchanging');
    try {
      await exchangeToken(val);
    } catch (err) {
      setPhase('error');
      setErrorMsg(err.message || 'Token exchange failed.');
    }
  };

  // ─── Processing overlay (fetching URL or exchanging token) ───
  if (phase === 'fetching_url' || phase === 'exchanging') {
    return (
      <div className="lp-bg">
        <div className="lp-card lp-card--center">
          <div className="lp-spinner" />
          <p className="lp-processing-msg">
            {phase === 'fetching_url' ? 'Connecting to Kite…' : 'Exchanging token…'}
          </p>
        </div>
      </div>
    );
  }

  // ─── Success state ────────────────────────────────────────────
  if (phase === 'success') {
    return (
      <div className="lp-bg">
        <div className="lp-card lp-card--center">
          <div className="lp-success-icon">✓</div>
          <h2 className="lp-success-title">Authenticated!</h2>
          <p className="lp-processing-msg">Redirecting to dashboard in {countdown}s…</p>
        </div>
      </div>
    );
  }

  // ─── Paper trading: skip immediately ─────────────────────────
  if (paperTrading) {
    return (
      <div className="lp-bg">
        <div className="lp-card">
          <BrandHeader />
          <div className="lp-paper-notice">
            <strong>Paper Trading Mode</strong> — no Zerodha account required.
          </div>
          <button className="lp-btn lp-btn--primary" onClick={handleSkip}>
            Continue to Dashboard
          </button>
        </div>
      </div>
    );
  }

  // ─── Main login page ──────────────────────────────────────────
  return (
    <div className="lp-bg">
      <div className="lp-card">
        <BrandHeader />

        <FeatureList />

        {/* Token expired banner */}
        {tokenExpired && (
          <div className="lp-notice lp-notice--warning">
            <strong>Session expired</strong> — your 24-hour Kite token has expired. Please log in again.
          </div>
        )}

        {/* Error banner */}
        {errorMsg && (
          <div className="lp-notice lp-notice--error">
            <span>⚠ {errorMsg}</span>
            <button className="lp-notice-dismiss" onClick={() => setErrorMsg(null)} aria-label="Dismiss">×</button>
          </div>
        )}

        {/* Waiting for Kite tab */}
        {phase === 'waiting_kite' && (
          <div className="lp-waiting">
            <span className="lp-waiting-dot" />
            <span>Kite is open in another tab — complete login &amp; 2FA there…</span>
            <button className="lp-waiting-cancel" onClick={handleCancelWait}>Cancel</button>
          </div>
        )}

        {/* ── Primary CTA ─────────────────────────────────── */}
        <div className="lp-actions">
          <button
            className="lp-btn lp-btn--primary"
            onClick={handleKiteLogin}
          >
            <span className="lp-btn-icon">🔐</span>
            {phase === 'waiting_kite' ? 'Re-open Kite Login' : 'Login with Kite (Zerodha)'}
          </button>

          <div className="lp-or-sep"><span>or</span></div>

          <button className="lp-btn lp-btn--ghost" onClick={handleSkip}>
            Skip — Continue without Login
          </button>
        </div>

        {/* ── Advanced: manual token ───────────────────────── */}
        <div className="lp-advanced">
          <button
            className="lp-advanced-toggle"
            onClick={() => setShowAdvanced(v => !v)}
          >
            {showAdvanced ? '▲' : '▼'} Advanced — paste request_token manually
          </button>
          {showAdvanced && (
            <div className="lp-advanced-body">
              <textarea
                className="lp-manual-input"
                value={manualToken}
                onChange={e => setManualToken(e.target.value)}
                placeholder="Paste full callback URL or just the request_token value"
                rows={2}
              />
              <button
                className="lp-btn lp-btn--outline lp-btn--sm"
                onClick={handleManualExchange}
                disabled={!manualToken.trim()}
              >
                Exchange Token
              </button>
            </div>
          )}
        </div>

        <p className="lp-footnote">
          Kite opens in a new tab. After completing 2FA, this page auto-detects the token
          and redirects you — no copy-paste needed.
        </p>
      </div>
    </div>
  );
}

