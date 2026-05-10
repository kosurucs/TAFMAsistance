import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import './GTTModal.css'

const API = '/api'
const PRODUCTS = ['CNC', 'MIS', 'NRML']

/**
 * GTTModal – Place a GTT (single or two-leg / OCO).
 *
 * Props:
 *   symbol    – pre-filled instrument symbol
 *   quote     – live quote object ({ ltp, last_price, … })
 *   editGtt   – existing GTT object to pre-fill for editing (optional)
 *   onClose   – called when modal should close
 *   onSaved   – called after successful place/modify
 */
export default function GTTModal({ symbol, quote, editGtt, onClose, onSaved }) {
  const ltp = quote?.last_price ?? quote?.ltp ?? ''

  const isEdit = Boolean(editGtt)

  // ── Trigger type: single | two-leg ──────────────────────────────────────────
  const [type, setType] = useState(editGtt?.type ?? 'single')

  // ── Shared fields ───────────────────────────────────────────────────────────
  const [lastPrice, setLastPrice] = useState(
    editGtt?.condition?.last_price ?? (ltp ? String(ltp) : '')
  )

  // ── Single trigger ──────────────────────────────────────────────────────────
  const [triggerVal, setTriggerVal] = useState(
    editGtt?.condition?.trigger_values?.[0] ?? ''
  )
  const [side, setSide]       = useState(editGtt?.orders?.[0]?.transaction_type ?? 'BUY')
  const [qty, setQty]         = useState(editGtt?.orders?.[0]?.quantity ?? 1)
  const [limitPrice, setLimit] = useState(editGtt?.orders?.[0]?.price ?? '')
  const [product, setProduct] = useState(editGtt?.orders?.[0]?.product ?? 'CNC')

  // ── Two-leg (OCO) ───────────────────────────────────────────────────────────
  // Leg 0 = stop-loss (lower trigger), Leg 1 = target (upper trigger)
  const [slTrigger, setSlTrigger] = useState(editGtt?.condition?.trigger_values?.[0] ?? '')
  const [slPrice, setSlPrice]     = useState(editGtt?.orders?.[0]?.price ?? '')
  const [slQty, setSlQty]         = useState(editGtt?.orders?.[0]?.quantity ?? 1)
  const [slProduct, setSlProduct] = useState(editGtt?.orders?.[0]?.product ?? 'CNC')

  const [tgtTrigger, setTgtTrigger] = useState(editGtt?.condition?.trigger_values?.[1] ?? '')
  const [tgtPrice, setTgtPrice]     = useState(editGtt?.orders?.[1]?.price ?? '')
  const [tgtQty, setTgtQty]         = useState(editGtt?.orders?.[1]?.quantity ?? 1)
  const [tgtProduct, setTgtProduct] = useState(editGtt?.orders?.[1]?.product ?? 'CNC')

  // ── State ───────────────────────────────────────────────────────────────────
  const [busy, setBusy]     = useState(false)
  const [error, setError]   = useState('')
  const [success, setSuccess] = useState('')

  // Close on Escape
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const validate = useCallback(() => {
    if (!symbol) return 'No symbol selected.'
    if (!lastPrice || isNaN(Number(lastPrice))) return 'Last price is required.'
    if (type === 'single') {
      if (!triggerVal || isNaN(Number(triggerVal))) return 'Trigger price is required.'
      if (!limitPrice || isNaN(Number(limitPrice))) return 'Limit price is required.'
      if (Number(qty) < 1) return 'Quantity must be ≥ 1.'
    } else {
      if (!slTrigger || isNaN(Number(slTrigger))) return 'Stop-loss trigger is required.'
      if (!slPrice   || isNaN(Number(slPrice)))   return 'Stop-loss limit price is required.'
      if (!tgtTrigger || isNaN(Number(tgtTrigger))) return 'Target trigger is required.'
      if (!tgtPrice   || isNaN(Number(tgtPrice)))   return 'Target limit price is required.'
      if (Number(slQty) < 1 || Number(tgtQty) < 1) return 'Quantity must be ≥ 1.'
    }
    return null
  }, [symbol, lastPrice, type, triggerVal, limitPrice, qty, slTrigger, slPrice, tgtTrigger, tgtPrice, slQty, tgtQty])

  const buildPayload = useCallback(() => {
    if (type === 'single') {
      return {
        trigger_type: 'single',
        symbol: symbol.toUpperCase(),
        exchange: 'NSE',
        trigger_values: [Number(triggerVal)],
        last_price: Number(lastPrice),
        orders: [{
          exchange: 'NSE',
          tradingsymbol: symbol.toUpperCase(),
          transaction_type: side,
          quantity: Number(qty),
          order_type: 'LIMIT',
          product,
          price: Number(limitPrice),
        }],
      }
    }
    // two-leg: leg-0 = stop-loss (SELL below), leg-1 = target (SELL above)
    return {
      trigger_type: 'two-leg',
      symbol: symbol.toUpperCase(),
      exchange: 'NSE',
      trigger_values: [Number(slTrigger), Number(tgtTrigger)],
      last_price: Number(lastPrice),
      orders: [
        {
          exchange: 'NSE',
          tradingsymbol: symbol.toUpperCase(),
          transaction_type: 'SELL',
          quantity: Number(slQty),
          order_type: 'LIMIT',
          product: slProduct,
          price: Number(slPrice),
        },
        {
          exchange: 'NSE',
          tradingsymbol: symbol.toUpperCase(),
          transaction_type: 'SELL',
          quantity: Number(tgtQty),
          order_type: 'LIMIT',
          product: tgtProduct,
          price: Number(tgtPrice),
        },
      ],
    }
  }, [type, symbol, lastPrice, triggerVal, limitPrice, qty, product, side, slTrigger, slPrice, slQty, slProduct, tgtTrigger, tgtPrice, tgtQty, tgtProduct])

  const submit = useCallback(async () => {
    const err = validate()
    if (err) { setError(err); return }
    setBusy(true)
    setError('')
    setSuccess('')
    try {
      const payload = buildPayload()
      let r
      if (isEdit) {
        r = await axios.put(`${API}/gtt/${editGtt.id}`, payload)
      } else {
        r = await axios.post(`${API}/gtt`, payload)
      }
      setSuccess(
        isEdit
          ? `GTT #${r.data.trigger_id} updated.`
          : `GTT placed! Trigger ID: ${r.data.trigger_id}${r.data.paper_trading ? ' [PAPER]' : ''}`
      )
      onSaved?.(r.data)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }, [validate, buildPayload, isEdit, editGtt, onSaved])

  return (
    <div className="gtt-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="gtt-modal">

        {/* ── Header ── */}
        <div className="gtt-header">
          <span className="gtt-title">
            {isEdit ? 'Edit GTT' : 'New GTT'} — <strong>{symbol}</strong>
          </span>
          {ltp && <span className="gtt-ltp">LTP ₹{Number(ltp).toFixed(2)}</span>}
          <button className="gtt-close" onClick={onClose}>✕</button>
        </div>

        {/* ── Type toggle ── */}
        {!isEdit && (
          <div className="gtt-type-row">
            <button
              className={`gtt-type-btn ${type === 'single' ? 'active' : ''}`}
              onClick={() => setType('single')}
            >Single</button>
            <button
              className={`gtt-type-btn ${type === 'two-leg' ? 'active' : ''}`}
              onClick={() => setType('two-leg')}
            >Two-Leg (OCO)</button>
          </div>
        )}

        <div className="gtt-body">
          {/* ── Last price (always) ── */}
          <div className="gtt-row">
            <label>Last Price (₹)</label>
            <input
              type="number" min="0" step="0.05" className="gtt-input"
              value={lastPrice} onChange={(e) => setLastPrice(e.target.value)}
              placeholder="Current LTP"
            />
          </div>

          {/* ── SINGLE leg ── */}
          {type === 'single' && (
            <>
              <div className="gtt-section-title">Trigger &amp; Order</div>

              <div className="gtt-row">
                <label>Side</label>
                <div className="gtt-btn-group">
                  {['BUY', 'SELL'].map(s => (
                    <button
                      key={s}
                      className={`gtt-chip side-${s.toLowerCase()} ${side === s ? 'active' : ''}`}
                      onClick={() => setSide(s)}
                    >{s}</button>
                  ))}
                </div>
              </div>

              <div className="gtt-row">
                <label>Trigger Price (₹)</label>
                <input
                  type="number" min="0" step="0.05" className="gtt-input"
                  value={triggerVal} onChange={(e) => setTriggerVal(e.target.value)}
                  placeholder="Price that fires the order"
                />
              </div>

              <div className="gtt-row">
                <label>Limit Price (₹)</label>
                <input
                  type="number" min="0" step="0.05" className="gtt-input"
                  value={limitPrice} onChange={(e) => setLimit(e.target.value)}
                  placeholder="LIMIT execution price"
                />
              </div>

              <div className="gtt-row">
                <label>Quantity</label>
                <input
                  type="number" min="1" step="1" className="gtt-input"
                  value={qty} onChange={(e) => setQty(e.target.value)}
                />
              </div>

              <div className="gtt-row">
                <label>Product</label>
                <div className="gtt-btn-group">
                  {PRODUCTS.map(p => (
                    <button
                      key={p}
                      className={`gtt-chip ${product === p ? 'active' : ''}`}
                      onClick={() => setProduct(p)}
                    >{p}</button>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* ── TWO-LEG (OCO) ── */}
          {type === 'two-leg' && (
            <>
              {/* Stop-loss leg */}
              <div className="gtt-section-title">Leg 1 — Stop-Loss (SELL if price drops)</div>

              <div className="gtt-row">
                <label>SL Trigger (₹)</label>
                <input
                  type="number" min="0" step="0.05" className="gtt-input"
                  value={slTrigger} onChange={(e) => setSlTrigger(e.target.value)}
                  placeholder="Lower trigger price"
                />
              </div>
              <div className="gtt-row">
                <label>SL Limit (₹)</label>
                <input
                  type="number" min="0" step="0.05" className="gtt-input"
                  value={slPrice} onChange={(e) => setSlPrice(e.target.value)}
                  placeholder="SL LIMIT execution price"
                />
              </div>
              <div className="gtt-row">
                <label>Quantity</label>
                <input
                  type="number" min="1" step="1" className="gtt-input"
                  value={slQty} onChange={(e) => setSlQty(e.target.value)}
                />
              </div>
              <div className="gtt-row">
                <label>Product</label>
                <div className="gtt-btn-group">
                  {PRODUCTS.map(p => (
                    <button
                      key={p}
                      className={`gtt-chip ${slProduct === p ? 'active' : ''}`}
                      onClick={() => setSlProduct(p)}
                    >{p}</button>
                  ))}
                </div>
              </div>

              {/* Target leg */}
              <div className="gtt-section-title gtt-section-title-2">Leg 2 — Target (SELL if price rises)</div>

              <div className="gtt-row">
                <label>Target Trigger (₹)</label>
                <input
                  type="number" min="0" step="0.05" className="gtt-input"
                  value={tgtTrigger} onChange={(e) => setTgtTrigger(e.target.value)}
                  placeholder="Upper trigger price"
                />
              </div>
              <div className="gtt-row">
                <label>Target Limit (₹)</label>
                <input
                  type="number" min="0" step="0.05" className="gtt-input"
                  value={tgtPrice} onChange={(e) => setTgtPrice(e.target.value)}
                  placeholder="Target LIMIT execution price"
                />
              </div>
              <div className="gtt-row">
                <label>Quantity</label>
                <input
                  type="number" min="1" step="1" className="gtt-input"
                  value={tgtQty} onChange={(e) => setTgtQty(e.target.value)}
                />
              </div>
              <div className="gtt-row">
                <label>Product</label>
                <div className="gtt-btn-group">
                  {PRODUCTS.map(p => (
                    <button
                      key={p}
                      className={`gtt-chip ${tgtProduct === p ? 'active' : ''}`}
                      onClick={() => setTgtProduct(p)}
                    >{p}</button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* ── Feedback ── */}
        {success && <div className="gtt-success">{success}</div>}
        {error   && <div className="gtt-error">{error}</div>}

        {/* ── GTT info note ── */}
        <p className="gtt-note">
          GTT orders are valid for 1 year. A LIMIT order is placed automatically when the trigger price is hit.
          {type === 'two-leg' && ' One cancel other: whichever leg triggers first cancels the other.'}
        </p>

        {/* ── Footer ── */}
        <div className="gtt-footer">
          <button className="gtt-cancel" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="gtt-submit" onClick={submit} disabled={busy}>
            {busy ? 'Saving…' : isEdit ? 'Update GTT' : 'Place GTT'}
          </button>
        </div>
      </div>
    </div>
  )
}
