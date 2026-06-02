import { create } from 'zustand';
import { api } from '../services/api';

const useAuthStore = create((set, get) => ({
  // Auth state
  authenticated: false,
  requiresLogin: false,
  requiresCredentials: false,
  hasCredentials: false,
  tokenExpired: false,
  loginUrl: null,
  loading: true,
  error: null,
  paperTrading: false,

  // Check authentication status
  checkAuthStatus: async () => {
    try {
      set({ loading: true, error: null });
      const response = await api.get('/api/auth/status');
      const data = response.data;
      
      set({
        authenticated: data.authenticated,
        requiresLogin: data.requires_login,
        requiresCredentials: data.requires_credentials || false,
        hasCredentials: data.has_credentials,
        tokenExpired: data.token_expired || false,
        loginUrl: data.login_url,
        paperTrading: data.paper_trading,
        loading: false,
      });

      return data;
    } catch (error) {
      console.error('Failed to check auth status:', error);
      set({
        authenticated: false,
        requiresLogin: false,
        requiresCredentials: true,
        hasCredentials: false,
        error: error.response?.data?.detail || 'Failed to check authentication status',
        loading: false,
      });
      throw error;
    }
  },

  // Save API credentials
  saveCredentials: async (apiKey, apiSecret) => {
    try {
      set({ loading: true, error: null });
      const response = await api.post('/api/auth/save-credentials', {
        api_key: apiKey,
        api_secret: apiSecret,
      });

      // Reload auth status after saving credentials
      await get().checkAuthStatus();

      return response.data;
    } catch (error) {
      console.error('Failed to save credentials:', error);
      set({
        error: error.response?.data?.detail || 'Failed to save credentials',
        loading: false,
      });
      throw error;
    }
  },

  // Get login URL
  getLoginUrl: async () => {
    try {
      const response = await api.get('/api/auth/login-url');
      const loginUrl = response.data.login_url;
      set({ loginUrl });
      return loginUrl;
    } catch (error) {
      console.error('Failed to get login URL:', error);
      set({ error: error.response?.data?.detail || 'Failed to get login URL' });
      throw error;
    }
  },

  // Exchange callback for access token
  exchangeToken: async (callbackOrToken) => {
    try {
      set({ loading: true, error: null });
      const value = (callbackOrToken || '').trim();
      const payload = value.includes('request_token=') || value.startsWith('http')
        ? { callback_url: value }
        : { request_token: value };

      const response = await api.post('/api/auth/exchange', payload);

      // Check auth status after successful exchange
      await get().checkAuthStatus();

      // Test connection in background — don't block navigation on this
      get().testConnection().catch((e) => console.warn('Connection test (non-fatal):', e));

      return response.data;
    } catch (error) {
      console.error('Failed to exchange token:', error);
      set({
        error: error.response?.data?.detail || 'Failed to authenticate',
        loading: false,
      });
      throw error;
    }
  },

  // Allow guest / paper-trading access without Kite login
  setGuestMode: () => {
    set({
      authenticated: false,
      requiresLogin: false,
      loading: false,
      error: null,
    });
  },

  // Test connection with actual API calls
  testConnection: async () => {
    try {
      const response = await api.post('/api/auth/test-connection', {});
      return response.data;
    } catch (error) {
      console.error('Connection test failed:', error);
      throw new Error(error.response?.data?.detail || 'Connection test failed');
    }
  },

  // Reset auth state
  reset: () => {
    set({
      authenticated: false,
      requiresLogin: false,
      requiresCredentials: false,
      hasCredentials: false,
      tokenExpired: false,
      loginUrl: null,
      loading: false,
      error: null,
      paperTrading: false,
    });
  },
}));

export default useAuthStore;
