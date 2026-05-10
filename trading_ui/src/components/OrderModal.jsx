import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import './OrderModal.css'

const API = '/api'

const ORDER_TYPES = ['MARKET', 'LIMIT', 'SL', 'SL-M']
const PRODUCTS    = ['MIS', 'CNC', 'NRML', 'MTF']
const VARIETIES   = ['regular', 'amo', 'co', 'iceberg']
const VALIDITIES  = ['DAY', 'IOC', 'TTL']

export default function OrderModal({ symbol, quote, onClose, onFilled }) {
  const ltp = quote?.last_price ?? quote?.ltp ?? null

  const [side, setSide]           = useState('BUY')   // BUY | SELL
  const [orderType, setOT]        = useState('MARKET')
  const [product, setProduct]     = useState('MIS')
  const [variety, setVariety]     = useState('regular')
  const [validity, setValidity]   = useState('DAY')
  const [qty, setQty]             = useState(1)
  const [price, setPrice]         = useState(ltp ? String(ltp) : '')
  const [trigger, setTrigger]     = useState('')
  const [validityTtl, setTtl]     = useState(5)     // minutes, for TTL validity
  const [icebergLegs, setILegs]   = useState(2)     // for iceberg variety
  const [tag, setTag]             = useState('')
  const [busy, setBusy]           = useState(false)
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState('')

  // Reset price when order type flips to MARKET
  useEffect(() => {
    if (orderType === 'MARKET') setPrice('')
  }, [orderType])

  const needsPrice   = orderType === 'LIMIT' || orderType === 'SL'
  const needsTrigger = orderType === 'SL' || orderType === 'SL-M'
  const isIceberg    = variety === 'iceberg'
  const isTtl        = validity === 'TTL'

  const submit = useCallback(async () => {
    if (!symbol) return
    if (qty <= 0) { setError('Quantity must be ≥ 1'); return }
    if (needsPrice && !price) { setError('Price is required for this order type'); return }
    if (needsTrigger && !trigger) { setError('Trigger price is required'); return }
    if (isIceberg && (!icebergLegs || icebergLegs < 2)) { setError('Iceberg legs must be 2–50'); return }
    if (isTtl && (!validityTtl || validityTtl < 1)) { setError('TTL must be ≥ 1 minute'); return }
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const payload = {
        symbol,
        transaction_type: side,
        quantity: Number(qty),
        variety,
        order_type: orderType,
        product,
        validity,
        price: needsPrice ? Number(price) : null,
        trigger_price: needsTrigger ? Number(trigger) : null,
        validity_ttl: isTtl ? Number(validityTtl) : null,
        iceberg_legs: isIceberg ? Number(icebergLegs) : null,
        tag: tag.trim() || null,
      }
      const r = await axios.post(`${API}/order`, payload)
      setResult(r.data)
      onFilled?.(r.data)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }, [symbol, side, orderType, product, variety, validity, qty, price, trigger, validityTtl, icebergLegs, tag, needsPrice, needsTrigger, isIceberg, isTtl, onFilled])

  // Close on Escape
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div className="om-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="om-modal">
        {/* ── Header ── */}
        <div className="om-header">
          <span className="om-title">Place Order — <strong>{symbol}</strong></span>
          {ltp && <span className="om-ltp">LTP ₹{Number(ltp).toFixed(2)}</span>}
          <button className="om-close" onClick={onClose}>✕</button>
        </div>

        {/* ── BUY / SELL toggle ── */}
        <div className="om-side-row">
          <button
            className={`om-side-btn buy ${side === 'BUY' ? 'active' : ''}`}
            onClick={() => setSide('BUY')}
          >BUY</button>
          <button
            className={`om-side-btn sell ${side === 'SELL' ? 'active' : ''}`}
            onClick={() => setSide('SELL')}
          >SELL</button>
        </div>

        {/* ── Form ── */}
        <div className="om-form">
          {/* Variety */}
          <div className="om-row">
            <label>Variety</label>
            <div className="om-btn-group">
              {VARIETIES.map(v => (
                <button
                  key={v}
                  className={`om-chip ${variety === v ? 'active' : ''}`}
                  onClick={() => setVariety(v)}
                >{v === 'amo' ? 'AMO' : v === 'co' ? 'CO' : v.charAt(0).toUpperCase() + v.slice(1)}</button>
              ))}
            </div>
          </div>

          {/* Order Type */}
          <div className="om-row">
            <label>Order Type</label>
            <div className="om-btn-group">
              {ORDER_TYPES.map(t => (
                <button
                  key={t}
                  className={`om-chip ${orderType === t ? 'active' : ''}`}
                  onClick={() => setOT(t)}
                >{t}</button>
              ))}
            </div>
          </div>

          {/* Product */}
          <div className="om-row">
            <label>Product</label>
            <div className="om-btn-group">
              {PRODUCTS.map(p => (
                <button
                  key={p}
                  className={`om-chip ${product === p ? 'active' : ''}`}
                  onClick={() => setProduct(p)}
                >{p}</button>
              ))}
            </div>
          </div>

          {/* Validity */}
          <div className="om-row">
            <label>Validity</label>
            <div className="om-btn-group">
              {VALIDITIES.map(v => (
                <button
                  key={v}
                  className={`om-chip ${validity === v ? 'active' : ''}`}
                  onClick={() => setValidity(v)}
                >{v}</button>
              ))}
            </div>
          </div>

          {/* TTL minutes */}
          {isTtl && (
            <div className="om-row">
              <label>TTL (minutes)</label>
              <input
                type="number" min="1" step="1" className="om-input"
                value={validityTtl}
                onChange={(e) => setTtl(e.target.value)}
              />
            </div>
          )}

          {/* Quantity */}
          <div className="om-row">
            <label>Quantity</label>
            <input
              type="number" min="1" step="1" className="om-input"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
            />
          </div>

          {/* Iceberg legs */}
          {isIceberg && (
            <div className="om-row">
              <label>Iceberg Legs</label>
              <input
                type="number" min="2" max="50" step="1" className="om-input"
                value={icebergLegs}
                onChange={(e) => setILegs(e.target.value)}
                placeholder="2 – 50"
              />
            </div>
          )}

          {needsPrice && (
            <div className="om-row">
              <label>Price (₹)</label>
              <input
                type="number" min="0" step="0.05" className="om-input"
                value={price}
                placeholder="Enter limit price"
                onChange={(e) => setPrice(e.target.value)}
              />
            </div>
          )}

          {needsTrigger && (
            <div className="om-row">
              <label>Trigger Price (₹)</label>
              <input
                type="number" min="0" step="0.05" className="om-input"
                value={trigger}
                placeholder="Enter trigger price"
                onChange={(e) => setTrigger(e.target.value)}
              />
            </div>
          )}

          {/* Optional tag */}
          <div className="om-row">
            <label>Tag <span className="om-optional">(optional)</span></label>
            <input
              type="text" maxLength={20} className="om-input"
              value={tag}
              placeholder="Max 20 chars"
              onChange={(e) => setTag(e.target.value)}
            />
          </div>
        </div>

        {/* ── Result / Error ── */}
        {result && (
          <div className="om-success">
            Order placed!&nbsp;
            <strong>{result.paper_trading ? '[PAPER]' : '[LIVE]'}</strong>&nbsp;
            {result.order_id
              ? <>ID: <code>{result.order_id}</code>&nbsp;| Status: <strong>{result.status}</strong></>
              : <>Autoslice: <strong>{result.order_ids?.length} slices</strong></>
            }
          </div>
        )}
        {error && <div className="om-error">{error}</div>}

        {/* ── Footer ── */}
        <div className="om-footer">
          <button className="om-cancel" onClick={onClose} disabled={busy}>Cancel</button>
          <button
            className={`om-submit ${side === 'BUY' ? 'buy' : 'sell'}`}
            onClick={submit}
            disabled={busy}
          >
            {busy ? 'Placing…' : `${side} ${qty} × ${symbol}`}
          </button>
        </div>
      </div>
    </div>
  )
}

