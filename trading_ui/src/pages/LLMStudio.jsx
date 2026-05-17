import { AppLayout } from '../layouts/AppLayout';
import { Card, Badge } from '../design-system';
import { ChatPanel } from '../features/chat/ChatPanel';
import './LLMStudio.css';

export default function LLMStudio() {
  return (
    <AppLayout>
      <div className="llm-studio">
        <Card title="Model Status" className="llm-studio__status">
          <div className="llm-studio__status-grid">
            <div><span className="status-label">Model</span><Badge variant="accent">Mistral 7B</Badge></div>
            <div><span className="status-label">Mode</span><Badge variant="neutral">Ollama Local</Badge></div>
            <div><span className="status-label">Output</span><Badge variant="up">JSON Structured</Badge></div>
          </div>
        </Card>
        <Card title="AI Trading Assistant" className="llm-studio__chat">
          <ChatPanel />
        </Card>
      </div>
    </AppLayout>
  );
}
