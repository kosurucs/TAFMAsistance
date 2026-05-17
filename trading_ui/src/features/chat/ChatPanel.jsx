import { useState, useRef, useEffect, useMemo } from 'react';
import { useMarketStore, useChatStore } from '../../store';
import { sendChatMessage } from '../../services/api';
import { Badge } from '../../design-system';
import './ChatPanel.css';

const QUICK_PROMPTS = [
  'Give a quick trend summary for {symbol}',
  'What are support and resistance for {symbol}?',
  'Is RSI signalling overbought or oversold in {symbol}?',
  'How risky is a fresh entry in {symbol} now?',
];

// Format a JS Date as IST time string
function toIST(date) {
  return date.toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });
}

// Try to parse LLM structured response
function parseStructuredResponse(text) {
  try {
    const json = JSON.parse(text);
    if (json.action || json.confidence !== undefined) {
      return json;
    }
  } catch {
    // Not JSON, return null
  }
  return null;
}

function StructuredMessage({ data }) {
  const actionVariant = 
    data.action === 'BUY' ? 'up' : 
    data.action === 'SELL' ? 'down' : 
    'neutral';
  
  return (
    <div className="chat-structured">
      <div className="chat-structured__header">
        {data.action && <Badge variant={actionVariant}>{data.action}</Badge>}
        {data.confidence !== undefined && (
          <Badge variant="accent">{(data.confidence * 100).toFixed(0)}% confidence</Badge>
        )}
      </div>
      {data.reason && <p className="chat-structured__reason">{data.reason}</p>}
      {data.key_factors && data.key_factors.length > 0 && (
        <div className="chat-structured__factors">
          {data.key_factors.map((f, i) => (
            <Badge key={i} variant="neutral" size="sm">{f}</Badge>
          ))}
        </div>
      )}
      {data.suggested_sl && (
        <p className="chat-structured__levels">
          SL: ₹{data.suggested_sl} | TP: ₹{data.suggested_tp || '—'}
        </p>
      )}
    </div>
  );
}

export function ChatPanel() {
  const { selectedSymbol, indicators } = useMarketStore();
  const { messages, loading, addMessage, clearMessages, setLoading } = useChatStore();
  const [input, setInput] = useState('');
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  const contextReady = Boolean(selectedSymbol) && Boolean(indicators) && Object.keys(indicators).length > 0;
  const promptChips = useMemo(
    () => QUICK_PROMPTS.map((p) => p.replace('{symbol}', selectedSymbol || 'this stock')),
    [selectedSymbol]
  );

  // Initialize with welcome message
  useEffect(() => {
    if (messages.length === 0) {
      addMessage({
        role: 'assistant',
        text: 'Hello! Ask me anything about the selected stock — price levels, indicators, trend analysis, or trading signals.',
        time: new Date(),
      });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [input]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { role: 'user', text, time: new Date() };
    addMessage(userMsg);
    setInput('');
    setLoading(true);

    const { data, error } = await sendChatMessage(text, selectedSymbol, indicators || {});
    
    if (error) {
      addMessage({
        role: 'assistant',
        text: `⚠ Error: ${error}`,
        time: new Date(),
      });
    } else {
      addMessage({
        role: 'assistant',
        text: data.reply || 'No response',
        time: new Date(),
      });
    }
    
    setLoading(false);
  };

  const usePrompt = (text) => {
    setInput(text);
    inputRef.current?.focus();
  };

  const resetChat = () => {
    if (loading) return;
    clearMessages();
    addMessage({
      role: 'assistant',
      text: 'Hello! Ask me anything about the selected stock — price levels, indicators, trend analysis, or trading signals.',
      time: new Date(),
    });
    setInput('');
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-prompts">
        {promptChips.map((prompt) => (
          <button
            key={prompt}
            className="chat-prompt-btn"
            onClick={() => usePrompt(prompt)}
            disabled={loading}
          >
            {prompt}
          </button>
        ))}
      </div>

      <div className="chat-messages">
        {messages.map((msg, i) => {
          const structured = msg.role === 'assistant' ? parseStructuredResponse(msg.text) : null;
          return (
            <div key={i} className={`chat-bubble ${msg.role}`}>
              {structured ? (
                <StructuredMessage data={structured} />
              ) : (
                <div className="bubble-text">{msg.text}</div>
              )}
              <div className="bubble-time">{toIST(msg.time)} IST</div>
            </div>
          );
        })}
        {loading && (
          <div className="chat-bubble assistant">
            <div className="bubble-text typing">
              <span /><span /><span />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          ref={inputRef}
          className="chat-input"
          rows={1}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={selectedSymbol ? `Ask anything about ${selectedSymbol}...` : 'Select a symbol and ask about trend, RSI, levels...'}
          disabled={loading}
        />
        <button className="chat-send" onClick={send} disabled={loading || !input.trim()}>
          ➤
        </button>
      </div>
    </div>
  );
}
