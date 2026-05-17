import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import './PortfolioPanel.css'

const API = '/api'

const TABS = ['Positions', 'Holdings', 'Trades', 'Auctions', 'Margins']

function fmt(v, digits = 2) {
  const n = Number(v)
  return isNaN(n) ? '—' : `₹${n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

function pct(v) {
  const n = Number(v)
  return isNaN(n) ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}

function pnlClass(v) {
  const n = Number(v)
  if (isNaN(n) || n === 0) return ''
  return n > 0 ? 'pos' : 'neg'
}

/** Small inline convert-position modal */
function ConvertModal({ position, onClose, onDone }) {
  const products = ['MIS', 'CNC', 'NRML'].filter(p => p !== position.product)
  const [newProd, setNewProd] = useState(products[0])
  const [busy, setBusy] = useState(false)
  const [err, setErr]   = useState('')

  const submit = async () => {
    setBusy(true)
    setErr('')
    try {
      await axios.put(`${API}/portfolio/positions/convert`, {
        tradingsymbol:    position.tradingsymbol,
        exchange:         position.exchange,
        transaction_type: position.quantity >= 0 ? 'BUY' : 'SELL',
        position_type:    'day',
        quantity:         Math.abs(position.quantity),
        old_product:      position.product,
        new_product:      newProd,
      })
      onDone()
    } catch (e) {
      setErr(e.response?.data?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pp-convert-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="pp-convert-modal">
        <div className="pp-convert-title">
          Convert <strong>{position.tradingsymbol}</strong> from <em>{position.product}</em>
        </div>
        <div className="pp-convert-row">
          <span>New product:</span>
          <div className="gtt-btn-group">
            {products.map(p => (
              <button
                key={p}
                className={`gtt-chip ${newProd === p ? 'active' : ''}`}
                onClick={() => setNewProd(p)}
              >{p}</button>
            ))}
          </div>
        </div>
        {err && <div className="pp-convert-err">{err}</div>}
        <div className="pp-convert-footer">
          <button className="gtt-cancel" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="gtt-submit" onClick={submit} disabled={busy}>
            {busy ? 'Converting…' : 'Convert'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function PortfolioPanel({ onClose }) {
  const [tab, setTab]         = useState('Positions')
  const [posView, setPosView] = useState('net')   // net | day
  const [data, setData]       = useState(null)
  const [trades, setTrades]   = useState(null)
  const [busy, setBusy]       = useState(false)
  const [err, setErr]         = useState('')
  const [convertPos, setConvertPos]   = useState(null)

  const load = useCallback(async () => {
    setBusy(true)
    setErr('')
    try {
      const [pf, tr] = await Promise.all([
        axios.get(`${API}/portfolio`),
        axios.get(`${API}/trades`),
      ])
      setData(pf.data)
      setTrades(tr.data?.trades ?? [])
    } catch (e) {
      setErr(e.response?.data?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const positions = data?.positions?.[posView] ?? []
  const holdings  = data?.holdings ?? []
  const auctions  = data?.auctions ?? []
  const margins   = data?.margins ?? {}
  const dayPnl    = data?.day_pnl ?? 0
  const holdPnl   = data?.holdings_pnl ?? 0

  return (
    <div className="pp-panel">
      {/* ── Panel header ── */}
      <div className="pp-header">
        <span className="pp-title">Portfolio</span>
        <span className={`pp-pnl ${pnlClass(dayPnl)}`} title="Intraday P&L">
          Day {fmt(dayPnl)}
        </span>
        <span className={`pp-pnl ${pnlClass(holdPnl)}`} title="Holdings P&L">
          Hold {fmt(holdPnl)}
        </span>
        {data?.paper_trading && <span className="pp-paper">PAPER</span>}
        <button className="pp-refresh" onClick={load} disabled={busy} title="Refresh">⟳</button>
        {onClose && <button className="pp-close" onClick={onClose}>✕</button>}
      </div>

      {/* ── Tabs ── */}
      <div className="pp-tabs">
        {TABS.map(t => (
          <button
            key={t}
            className={`pp-tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >{t}</button>
        ))}
      </div>

      {err && <div className="pp-err">{err}</div>}
      {busy && !data && <div className="pp-loading">Loading…</div>}

      {/* ── Positions ── */}
      {tab === 'Positions' && (
        <div className="pp-table-wrap">
          {/* net / day toggle */}
          <div className="pp-pos-toggle">
            <button className={`pp-pos-btn ${posView === 'net' ? 'active' : ''}`} onClick={() => setPosView('net')}>Net</button>
            <button className={`pp-pos-btn ${posView === 'day' ? 'active' : ''}`} onClick={() => setPosView('day')}>Day</button>
          </div>
          {positions.length === 0
            ? <div className="pp-empty">No {posView} positions</div>
            : (
              <table className="pp-table">
                <thead>
                  <tr>
                    <th>Symbol</th><th>Exch</th><th>Qty</th><th>Avg</th><th>LTP</th>
                    <th>P&amp;L</th><th>M2M</th><th>Product</th><th>Convert</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p, i) => (
                    <tr key={i}>
                      <td className="sym">{p.tradingsymbol}</td>
                      <td style={{ fontSize: 11, color: '#8b949e' }}>{p.exchange}</td>
                      <td className={p.quantity > 0 ? 'pos' : p.quantity < 0 ? 'neg' : ''}>
                        {p.quantity}
                      </td>
                      <td>{fmt(p.average_price)}</td>
                      <td>{fmt(p.last_price)}</td>
                      <td className={pnlClass(p.pnl)}>{fmt(p.pnl)}</td>
                      <td className={pnlClass(p.m2m)}>{fmt(p.m2m)}</td>
                      <td><span className="chip">{p.product}</span></td>
                      <td>
                        {p.quantity !== 0 && (
                          <button
                            className="pp-gtt-btn"
                            title="Convert margin product"
                            onClick={() => setConvertPos(p)}
                          >⇄</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      )}

      {/* ── Holdings ── */}
      {tab === 'Holdings' && (
        <div className="pp-table-wrap">
          {holdings.length === 0
            ? <div className="pp-empty">No holdings</div>
            : (
              <table className="pp-table">
                <thead>
                  <tr>
                    <th>Symbol</th><th>Qty</th><th>T1</th><th>Avg Cost</th><th>LTP</th>
                    <th>Current Val</th><th>P&amp;L</th><th>Day Chg</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h, i) => (
                    <tr key={i}>
                      <td className="sym">{h.tradingsymbol}
                        {h.t1_quantity > 0 && <span className="pp-t1-badge" title="T+1 delivery pending"> T1</span>}
                      </td>
                      <td>{h.quantity}</td>
                      <td style={{ fontSize: 11, color: '#8b949e' }}>{h.t1_quantity || '—'}</td>
                      <td>{fmt(h.average_price)}</td>
                      <td>{fmt(h.last_price)}</td>
                      <td>{fmt(h.last_price * (h.quantity + (h.t1_quantity ?? 0)), 0)}</td>
                      <td className={pnlClass(h.pnl)}>
                        {fmt(h.pnl)}
                      </td>
                      <td className={pnlClass(h.day_change)}>
                        {h.day_change != null
                          ? <>{fmt(h.day_change)} <span style={{ fontSize: 10 }}>({pct(h.day_change_percentage)})</span></>
                          : '—'
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      )}

      {/* ── Trades ── */}
      {tab === 'Trades' && (
        <div className="pp-table-wrap">
          {!trades || trades.length === 0
            ? <div className="pp-empty">No trades today</div>
            : (
              <table className="pp-table">
                <thead>
                  <tr>
                    <th>Symbol</th><th>Side</th><th>Qty</th><th>Avg Price</th>
                    <th>Product</th><th>Fill Time</th><th>Trade ID</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t, i) => (
                    <tr key={i}>
                      <td className="sym">{t.tradingsymbol}</td>
                      <td className={t.transaction_type === 'BUY' ? 'pos' : 'neg'}>{t.transaction_type}</td>
                      <td>{t.quantity ?? t.filled}</td>
                      <td>{fmt(t.average_price)}</td>
                      <td>{t.product}</td>
                      <td style={{ fontSize: 11 }}>{t.fill_timestamp ?? t.exchange_timestamp ?? '—'}</td>
                      <td style={{ fontSize: 11 }}>{t.trade_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      )}

      {/* ── Auctions ── */}
      {tab === 'Auctions' && (
        <div className="pp-table-wrap">
          {auctions.length === 0
            ? <div className="pp-empty">No holdings auctions currently open</div>
            : (
              <table className="pp-table">
                <thead>
                  <tr>
                    <th>Symbol</th><th>Exchange</th><th>Qty</th><th>Avg Cost</th>
                    <th>LTP</th><th>P&amp;L</th><th>Auction #</th>
                  </tr>
                </thead>
                <tbody>
                  {auctions.map((a, i) => (
                    <tr key={i}>
                      <td className="sym">{a.tradingsymbol}</td>
                      <td style={{ fontSize: 11, color: '#8b949e' }}>{a.exchange}</td>
                      <td>{a.quantity}</td>
                      <td>{fmt(a.average_price)}</td>
                      <td>{fmt(a.last_price)}</td>
                      <td className={pnlClass(a.pnl)}>{fmt(a.pnl)}</td>
                      <td style={{ fontSize: 11 }}>{a.auction_number}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      )}

      {/* ── Margins ── */}
      {tab === 'Margins' && (
        <div className="pp-margins">
          {Object.keys(margins).length === 0
            ? <div className="pp-empty">No margin data</div>
            : Object.entries(margins).map(([seg, m]) => (
              <div key={seg} className="pp-margin-seg">
                <div className="pp-margin-seg-name">{seg.toUpperCase()}</div>
                <div className="pp-margin-row">
                  <span>Available</span>
                  <span className="pos">{fmt(m.available?.live_balance ?? m.net)}</span>
                </div>
                <div className="pp-margin-row">
                  <span>Adhoc margin</span>
                  <span>{fmt(m.available?.adhoc_margin ?? 0)}</span>
                </div>
                <div className="pp-margin-row">
                  <span>Used (debits)</span>
                  <span>{fmt(m.utilised?.debits ?? 0)}</span>
                </div>
                <div className="pp-margin-row">
                  <span>Span</span>
                  <span>{fmt(m.utilised?.span ?? 0)}</span>
                </div>
                <div className="pp-margin-row">
                  <span>Exposure</span>
                  <span>{fmt(m.utilised?.exposure ?? 0)}</span>
                </div>
                <div className="pp-margin-row">
                  <span>Option premium</span>
                  <span>{fmt(m.utilised?.option_premium ?? 0)}</span>
                </div>
                <div className="pp-margin-row">
                  <span>Net</span>
                  <span className={pnlClass(m.net)}><strong>{fmt(m.net)}</strong></span>
                </div>
              </div>
            ))
          }
        </div>
      )}

      {/* Position convert modal */}
      {convertPos && (
        <ConvertModal
          position={convertPos}
          onClose={() => setConvertPos(null)}
          onDone={() => { setConvertPos(null); load() }}
        />
      )}
    </div>
  )
}

