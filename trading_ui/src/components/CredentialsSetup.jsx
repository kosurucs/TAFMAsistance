import { useState } from 'react';
import './CredentialsSetup.css';

export default function CredentialsSetup({ onSubmit, onCancel }) {
  const [formData, setFormData] = useState({
    apiKey: '',
    apiSecret: '',
  });
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    setError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!formData.apiKey.trim()) {
      setError('API Key is required');
      return;
    }

    if (!formData.apiSecret.trim()) {
      setError('API Secret is required');
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit(formData.apiKey.trim(), formData.apiSecret.trim());
    } catch (err) {
      setError(err.message || 'Failed to save credentials');
      setIsSubmitting(false);
    }
  };

  return (
    <div className="credentials-modal-overlay">
      <div className="credentials-modal">
        <div className="credentials-header">
          <h2>Zerodha API Credentials Setup</h2>
          <p className="credentials-subtitle">
            Enter your Zerodha Kite Connect API credentials
          </p>
        </div>

        <form onSubmit={handleSubmit} className="credentials-form">
          <div className="credentials-info">
            <p>To get your API credentials:</p>
            <ol>
              <li>
                Visit{' '}
                <a
                  href="https://kite.trade/"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  kite.trade
                </a>
              </li>
              <li>Login with your Zerodha account</li>
              <li>Create a new app or use an existing one</li>
              <li>Copy the API Key and API Secret</li>
            </ol>
          </div>

          <div className="form-group">
            <label htmlFor="apiKey">API Key *</label>
            <input
              type="text"
              id="apiKey"
              name="apiKey"
              value={formData.apiKey}
              onChange={handleChange}
              placeholder="Enter your Kite API Key"
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="apiSecret">API Secret *</label>
            <input
              type="password"
              id="apiSecret"
              name="apiSecret"
              value={formData.apiSecret}
              onChange={handleChange}
              placeholder="Enter your Kite API Secret"
              disabled={isSubmitting}
              required
            />
          </div>

          {error && <div className="credentials-error">{error}</div>}

          <div className="credentials-actions">
            {onCancel && (
              <button
                type="button"
                className="btn-secondary"
                onClick={onCancel}
                disabled={isSubmitting}
              >
                Cancel
              </button>
            )}
            <button
              type="submit"
              className="btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Saving...' : 'Save & Continue'}
            </button>
          </div>

          <div className="credentials-note">
            <strong>Note:</strong> Your credentials are stored securely in the
            backend .env file and never sent to external servers.
          </div>
        </form>
      </div>
    </div>
  );
}
