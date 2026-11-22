import { useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card, Badge } from '../design-system';
import { ChatPanel } from '../features/chat/ChatPanel';
import { ResearchPanel } from '../features/research/ResearchPanel';
import { getTrainingStats, getChatStatus } from '../services/api';
import { useEffect } from 'react';
import './LLMStudio.css';

export default function LLMStudio() {
  const [tab, setTab] = useState('research');
  const [stats, setStats] = useState(null);
  const [chatStatus, setChatStatus] = useState(null);

  useEffect(() => {
    getTrainingStats().then(({ data }) => { if (data) setStats(data); });
    getChatStatus().then(({ data }) => { if (data) setChatStatus(data); });
  }, []);

  const ollamaConnected = Boolean(chatStatus?.ollama_connected);
  const activeModel = chatStatus?.active_model || 'N/A';
  const modeLabel = ollamaConnected ? 'Local Ollama' : 'Rule-based Fallback';
  const outputVariant = ollamaConnected ? 'up' : 'neutral';
  const outputLabel = ollamaConnected ? 'LLM Active' : 'Fallback Active';

  return (
    <AppLayout>
      <div className="llm-studio">
        {/* Status bar */}
        <Card title="Model Status" className="llm-studio__status">
          <div className="llm-studio__status-grid">
            <div>
              <span className="status-label">Model</span>
              <Badge variant={ollamaConnected ? 'accent' : 'neutral'}>{activeModel}</Badge>
            </div>
            <div>
              <span className="status-label">Mode</span>
              <Badge variant="neutral">{modeLabel}</Badge>
            </div>
            <div>
              <span className="status-label">Output</span>
              <Badge variant={outputVariant}>{outputLabel}</Badge>
            </div>
            {stats && (
              <div>
                <span className="status-label">Training Examples</span>
                <Badge variant="neutral">{stats.training_examples}</Badge>
              </div>
            )}
            {stats && (
              <div>
                <span className="status-label">Cached Instruments</span>
                <Badge variant="neutral">{stats.cached_symbols}</Badge>
              </div>
            )}
          </div>
        </Card>

        {/* Tabs */}
        <div className="llm-studio__tabs">
          <button
            className={`llm-studio__tab${tab === 'research' ? ' llm-studio__tab--active' : ''}`}
            onClick={() => setTab('research')}
          >
            Research Analyser
          </button>
          <button
            className={`llm-studio__tab${tab === 'chat' ? ' llm-studio__tab--active' : ''}`}
            onClick={() => setTab('chat')}
          >
            AI Chat
          </button>
        </div>

        {/* Tab content */}
        {tab === 'research' && (
          <Card title="Comprehensive Instrument Analysis" className="llm-studio__panel">
            <p className="llm-studio__hint">
              Enter any NSE/BSE symbol (e.g. <strong>TATACAPITAL</strong>) to fetch live technicals,
              Yahoo Finance fundamentals, shareholding, quarterly financials, and screener.in data
              — then get a local-LLM BUY/SELL/WAIT decision.  Every analysis is cached and
              automatically added to the LLM training dataset.
            </p>
            <ResearchPanel />
          </Card>
        )}

        {tab === 'chat' && (
          <Card title="AI Trading Assistant" className="llm-studio__panel llm-studio__chat">
            <p className="llm-studio__hint">
              Command prompt mode enabled. Try commands like <strong>/summary RELIANCE</strong>, <strong>/levels TCS</strong>, or <strong>/signal INFY</strong>.
            </p>
            <ChatPanel />
          </Card>
        )}
      </div>
    </AppLayout>
  );
}
