import { useState } from 'react';
import { AppLayout } from '../layouts/AppLayout';
import { Card, Badge } from '../design-system';
import { ChatPanel } from '../features/chat/ChatPanel';
import { ResearchPanel } from '../features/research/ResearchPanel';
import { getTrainingStats } from '../services/api';
import { useEffect } from 'react';
import './LLMStudio.css';

export default function LLMStudio() {
  const [tab, setTab] = useState('research');
  const [stats, setStats] = useState(null);

  useEffect(() => {
    getTrainingStats().then(({ data }) => { if (data) setStats(data); });
  }, []);

  return (
    <AppLayout>
      <div className="llm-studio">
        {/* Status bar */}
        <Card title="Model Status" className="llm-studio__status">
          <div className="llm-studio__status-grid">
            <div>
              <span className="status-label">Model</span>
              <Badge variant="accent">Local GPT-2 124M</Badge>
            </div>
            <div>
              <span className="status-label">Mode</span>
              <Badge variant="neutral">rasbt/llms-from-scratch</Badge>
            </div>
            <div>
              <span className="status-label">Output</span>
              <Badge variant="up">JSON Structured</Badge>
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
            <ChatPanel />
          </Card>
        )}
      </div>
    </AppLayout>
  );
}
