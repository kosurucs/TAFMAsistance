import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, errorMessage: '' }
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      errorMessage: error?.message || 'Unknown runtime error',
    }
  }

  componentDidCatch(error, info) {
    // Keep details in console for debugging while showing a user-friendly fallback.
    console.error('UI crashed:', error)
    console.error(info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          display: 'grid',
          placeItems: 'center',
          background: '#0d1117',
          color: '#c9d1d9',
          padding: '24px',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
        }}>
          <div style={{ maxWidth: '720px', width: '100%', border: '1px solid #30363d', borderRadius: '10px', padding: '18px', background: '#161b22' }}>
            <h2 style={{ marginTop: 0, color: '#f85149' }}>UI runtime error</h2>
            <p style={{ marginBottom: '12px' }}>
              The page hit an unexpected error. Refresh once. If it repeats, share this message.
            </p>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0, color: '#ffa657' }}>
              {this.state.errorMessage}
            </pre>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
