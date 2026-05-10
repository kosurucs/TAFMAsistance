import { useState, useRef, useEffect, useMemo } from 'react'
import axios from 'axios'
import './ChatPanel.css'

const API = '/api'
const QUICK_PROMPTS = [
  'Give a quick trend summary for {symbol}',
  'What are support and resistance for {symbol}?',
  'Is RSI signalling overbought or oversold in {symbol}?',
  'How risky is a fresh entry in {symbol} now?',
]

// Format a JS Date as IST time string, e.g. "09:15:32 AM"
function toIST(date) {
  return date.toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
}

export default function ChatPanel({ symbol, indicators }) {
  const initialMessages = useMemo(() => ([
    {
      role: 'assistant',
      text: 'Hello! Ask me anything about the selected stock — price levels, indicators, trend analysis, or trading signals.',
      time: new Date(),
    },
  ]), [])

  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  const contextReady = Boolean(symbol) && Boolean(indicators) && Object.keys(indicators).length > 0
  const promptChips = useMemo(
    () => QUICK_PROMPTS.map((p) => p.replace('{symbol}', symbol || 'this stock')),
    [symbol]
  )

  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [input])

  // Scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg = { role: 'user', text, time: new Date() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await axios.post(`${API}/chat`, {
        message: text,
        symbol: symbol || null,
        indicators: indicators || {},
      })
      setMessages(prev => [
        ...prev,
        { role: 'assistant', text: res.data.reply, time: new Date() },
      ])
    } catch (e) {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          text: `⚠ Error: ${e.response?.data?.detail || e.message}`,
          time: new Date(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const usePrompt = (text) => {
    setInput(text)
    inputRef.current?.focus()
  }

  const resetChat = () => {
    if (loading) return
    setMessages(initialMessages)
    setInput('')
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <span className="chat-title">AI Trading Assistant</span>
        {symbol && <span className="chat-symbol">{symbol}</span>}
        <span className={`chat-context ${contextReady ? 'ready' : 'waiting'}`}>
          {contextReady ? 'Context Ready' : 'Waiting For Market Data'}
        </span>
        <button className="chat-reset" onClick={resetChat} disabled={loading}>
          New Chat
        </button>
      </div>

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
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble ${msg.role}`}>
            <div className="bubble-text">{msg.text}</div>
            <div className="bubble-time">{toIST(msg.time)} IST</div>
          </div>
        ))}
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
          placeholder={symbol ? `Ask anything about ${symbol}...` : 'Select a symbol and ask about trend, RSI, levels...'}
          disabled={loading}
        />
        <button className="chat-send" onClick={send} disabled={loading || !input.trim()}>
          ➤
        </button>
      </div>
    </div>
  )
}
