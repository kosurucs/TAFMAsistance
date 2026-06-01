import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import './design-system/theme.css';
import Dashboard from './pages/Dashboard';
import Portfolio from './pages/Portfolio';
import Backtest from './pages/Backtest';
import Simulate from './pages/Simulate';
import LLMStudio from './pages/LLMStudio';
import HistoricalData from './pages/HistoricalData';
import Login from './pages/Login';
import useAuthStore from './store/authStore';

// Protected route wrapper that checks authentication
function ProtectedRoute({ children }) {
  const { authenticated, requiresLogin, loading } = useAuthStore();
  const location = useLocation();

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: 'var(--color-bg-base)',
      }}>
        <div style={{
          width: '48px',
          height: '48px',
          border: '4px solid var(--color-border-subtle)',
          borderTopColor: 'var(--color-primary)',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
        }}></div>
      </div>
    );
  }

  if (requiresLogin && !authenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

// App content with auth initialization
function AppContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const { checkAuthStatus, authenticated, loading } = useAuthStore();

  useEffect(() => {
    // Check authentication status on app startup
    checkAuthStatus().catch((error) => {
      console.error('Failed to check auth status:', error);
      // If we're not on the login page, redirect there
      if (location.pathname !== '/login') {
        navigate('/login');
      }
    });
  }, []);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/portfolio" element={<ProtectedRoute><Portfolio /></ProtectedRoute>} />
      <Route path="/historical" element={<ProtectedRoute><HistoricalData /></ProtectedRoute>} />
      <Route path="/backtest" element={<ProtectedRoute><Backtest /></ProtectedRoute>} />
      <Route path="/simulate" element={<ProtectedRoute><Simulate /></ProtectedRoute>} />
      <Route path="/llm-studio" element={<ProtectedRoute><LLMStudio /></ProtectedRoute>} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}

