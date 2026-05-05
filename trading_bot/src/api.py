"""
api.py – FastAPI server exposing trading bot data to the React UI.

Endpoints
---------
GET /api/symbols          – list all NSE instruments (name + token)
GET /api/watchlist        – symbols currently in the .env WATCHLIST
GET /api/market-data/{symbol}  – OHLCV candles + indicators for a symbol
GET /api/quote/{symbol}   – latest LTP / bid / ask
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# Load env from trading_bot/.env
load_dotenv(Path(__file__).parents[1] / ".env")

# ── Kite session (reuse across requests) ─────────────────────────────────────
from src.tools.kite_tools import KiteAuthManager, KiteDataFetcher  # noqa: E402
from src.tools.instruments import InstrumentsCache              # noqa: E402
from src.tools.market_data import MarketData                    # noqa: E402
from src.tools.data_pipeline import DataPipeline                # noqa: E402
from src.utils.technical_analysis import compute_indicators     # noqa: E402

_auth = KiteAuthManager()
_kite = _auth.get_kite_session()
_data_fetcher = KiteDataFetcher(_kite)
_instruments = InstrumentsCache(_kite)
_market = MarketData(_kite)
_pipeline = DataPipeline(_data_fetcher)

app = FastAPI(title="TAFMAsistance Trading API", version="1.0.0")

# Allow the React dev server (localhost:5173) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EXCHANGE = os.environ.get("EXCHANGE", "NSE")
DEFAULT_CANDLE_LIMIT = int(os.environ.get("UI_CANDLE_LIMIT", "2000"))


def _resolve_days_back(interval: str, days_back: int) -> int:
    """Resolve requested lookback window.

    Convention:
      - days_back > 0: explicit lookback from caller.
      - days_back <= 0: fetch the fullest practical history.

    Note: Kite imposes tighter limits for intraday intervals. We keep a
    conservative cap there to avoid frequent broker-side errors.
    """
    if days_back > 0:
        return days_back

    intraday_intervals = {
        "minute",
        "3minute",
        "5minute",
        "10minute",
        "15minute",
        "30minute",
        "60minute",
    }
    if interval in intraday_intervals:
        return 60

    # Day interval: ~5 years
    if interval == "day":
        return 1825

    # Week/month intervals: 10 years
    return 3650


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/watchlist")
def get_watchlist() -> dict[str, Any]:
    """Return the symbols configured in WATCHLIST env var."""
    raw = os.environ.get("WATCHLIST", "RELIANCE,INFY,TCS,HDFCBANK")
    symbols = [s.strip() for s in raw.split(",") if s.strip()]
    return {"symbols": symbols, "exchange": EXCHANGE}


@app.get("/api/symbols")
def get_symbols(search: str = "") -> dict[str, Any]:
    """Return all NSE instruments, optionally filtered by search string."""
    try:
        df = _instruments.get_all_instruments(EXCHANGE)
        base_df = df
        # Keep only EQ segment for clean dropdown
        if "segment" in df.columns:
            eq_df = df[df["segment"].astype(str).str.upper() == f"{EXCHANGE}-EQ"]
            if not eq_df.empty:
                df = eq_df
        elif "instrument_type" in df.columns:
            eq_df = df[df["instrument_type"].astype(str).str.upper() == "EQ"]
            if not eq_df.empty:
                df = eq_df

        # Safety fallback: never return an empty universe because of schema drift.
        if df.empty:
            df = base_df

        if search:
            query = search.strip().lower()

            symbol_series = df["tradingsymbol"].fillna("").astype(str)
            name_series = df["name"].fillna("").astype(str)

            symbol_lower = symbol_series.str.lower()
            name_lower = name_series.str.lower()

            # Match by symbol/name contains plus a lightweight subsequence match
            # so short inputs like "hd" can still find symbols like "HDFCBANK".
            contains_mask = symbol_lower.str.contains(query, regex=False, na=False) | name_lower.str.contains(query, regex=False, na=False)

            def _is_subsequence(text: str, pattern: str) -> bool:
                if not pattern:
                    return True
                i = 0
                for ch in text:
                    if i < len(pattern) and ch == pattern[i]:
                        i += 1
                        if i == len(pattern):
                            return True
                return False

            subseq_mask = symbol_lower.apply(lambda x: _is_subsequence(x, query))
            df = df[contains_mask | subseq_mask]

            # Rank results: exact prefix in symbol -> symbol contains -> name contains -> rest
            ranked = df.copy()
            ranked["_rank"] = 3
            ranked.loc[symbol_lower.loc[ranked.index].str.contains(query, regex=False, na=False), "_rank"] = 1
            ranked.loc[symbol_lower.loc[ranked.index].str.startswith(query, na=False), "_rank"] = 0
            ranked.loc[name_lower.loc[ranked.index].str.contains(query, regex=False, na=False), "_rank"] = ranked["_rank"].where(ranked["_rank"] < 2, 2)
            df = ranked.sort_values(["_rank", "tradingsymbol"]).drop(columns=["_rank"])

        results = (
            df[["tradingsymbol", "name", "instrument_token"]]
            .fillna("")
            .head(500)
            .to_dict(orient="records")
        )
        return {"symbols": results, "total": len(results)}
    except Exception as exc:
        logger.error("get_symbols failed: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/market-data/{symbol}")
def get_market_data(symbol: str, days_back: int = 0, interval: str = "minute", limit: int = DEFAULT_CANDLE_LIMIT) -> dict[str, Any]:
    """Return OHLCV candles + computed indicators for *symbol*."""
    try:
        token = _instruments.get_instrument_token(EXCHANGE, symbol)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found on {EXCHANGE}")
    except Exception as exc:
        logger.error("Token lookup failed for {} on {}: {}", symbol, EXCHANGE, exc)
        raise HTTPException(status_code=503, detail=f"Token lookup temporarily unavailable: {exc}")

    try:
        resolved_days_back = _resolve_days_back(interval, days_back)
        df = _pipeline.get_ohlcv_df(
            instrument_token=token,
            tradingsymbol=symbol,
            interval=interval,
            days_back=resolved_days_back,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch OHLCV: {exc}")

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No OHLCV data for '{symbol}'")

    # Keep payload bounded for the UI even when a deep history window is fetched.
    if limit <= 0:
        limit = DEFAULT_CANDLE_LIMIT
    if len(df) > limit:
        df = df.tail(limit)

    # Convert DataFrame to list of candle dicts for the frontend
    df_out = df.reset_index()
    time_col = df_out.columns[0]  # first col is datetime index
    candles = []
    for _, row in df_out.iterrows():
        dt = row[time_col]
        # Kite may return timezone-naive datetimes that are implicitly IST.
        # Localise to IST before converting to a UTC Unix timestamp so the
        # frontend (which uses Asia/Kolkata localization) shows correct times.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_IST)
        candles.append({
            "time": int(dt.timestamp()),
            "open":  round(float(row["open"]),  2),
            "high":  round(float(row["high"]),  2),
            "low":   round(float(row["low"]),   2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        })

    # Compute indicators
    try:
        indicators = compute_indicators(df)
    except Exception as exc:
        logger.warning("Indicator computation failed for {}: {}", symbol, exc)
        indicators = {}

    return {
        "symbol": symbol,
        "exchange": EXCHANGE,
        "interval": interval,
        "candles": candles,
        "indicators": indicators,
    }


@app.get("/api/quote/{symbol}")
def get_quote(symbol: str) -> dict[str, Any]:
    """Return latest LTP and depth for *symbol*."""
    try:
        quote = _market.get_quote([f"{EXCHANGE}:{symbol}"])
        data = quote.get(f"{EXCHANGE}:{symbol}", {})
        return {
            "symbol": symbol,
            "ltp": data.get("last_price", 0),
            "open": data.get("ohlc", {}).get("open", 0),
            "high": data.get("ohlc", {}).get("high", 0),
            "low":  data.get("ohlc", {}).get("low",  0),
            "close": data.get("ohlc", {}).get("close", 0),
            "volume": data.get("volume", 0),
            "change": data.get("net_change", 0),
            "change_pct": data.get("oi_day_change_percentage", 0),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ── Chat endpoint ─────────────────────────────────────────────────────────────

from pydantic import BaseModel  # noqa: E402


class ChatRequest(BaseModel):
    message: str
    symbol: str | None = None
    indicators: dict[str, Any] = {}


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    """Return a plain-text trading assistant reply for the given message."""
    msg = req.message.strip().lower()
    sym = (req.symbol or "").upper()
    ind = req.indicators

    now_ist = datetime.now(_IST).strftime("%d %b %Y %I:%M:%S %p IST")

    def _ind(key: str, default="N/A"):
        return ind.get(key, default)

    def _fmt_price(val) -> str:
        try:
            return f"₹{float(val):,.2f}"
        except (TypeError, ValueError):
            return str(val)

    # ── Route to the best matching handler ────────────────────────────────────

    # High volume / low risk screener-style question about current symbol
    if any(k in msg for k in ("high volume", "high volum", "volume spike", "unusual volume")):
        vol = _ind("volume")
        try:
            vol_f = int(float(vol))
            if vol_f > 500_000:
                assessment = f"**high** ({vol_f:,}) — significant market interest."
            elif vol_f > 100_000:
                assessment = f"**moderate** ({vol_f:,}) — decent liquidity."
            else:
                assessment = f"**low** ({vol_f:,}) — limited activity."
            reply = f"Volume for **{sym}**: {assessment}"
        except (ValueError, TypeError):
            reply = "Volume data is not available for this symbol."

    elif any(k in msg for k in ("low risk", "risk", "safe", "volatile", "volatility")):
        bb_upper = _ind("bb_upper")
        bb_lower = _ind("bb_lower")
        close = _ind("close")
        rsi = _ind("rsi")
        parts = []
        try:
            width = float(bb_upper) - float(bb_lower)
            pct = (width / float(close)) * 100
            if pct < 3:
                parts.append(f"BB width is **narrow** ({pct:.1f}% of price) — low volatility, low risk environment.")
            elif pct < 7:
                parts.append(f"BB width is **moderate** ({pct:.1f}% of price) — normal volatility.")
            else:
                parts.append(f"BB width is **wide** ({pct:.1f}% of price) — high volatility, elevated risk.")
        except (ValueError, TypeError):
            pass
        try:
            rsi_f = float(rsi)
            if rsi_f >= 70:
                parts.append(f"RSI ({rsi_f:.1f}) is overbought — entering now carries reversal risk.")
            elif rsi_f <= 30:
                parts.append(f"RSI ({rsi_f:.1f}) is oversold — downside may be limited.")
            else:
                parts.append(f"RSI ({rsi_f:.1f}) is neutral — no extreme risk from momentum.")
        except (ValueError, TypeError):
            pass
        reply = (
            "\n".join(parts) + "\n\n⚠ This is not financial advice."
            if parts else
            "Not enough data to assess risk. Please load market data first."
        )

    # Support / resistance / price levels
    elif any(k in msg for k in ("support", "resistance", "level", "price target", "target")):
        bb_upper = _ind("bb_upper")
        bb_mid = _ind("bb_middle")
        bb_lower = _ind("bb_lower")
        ema9 = _ind("ema_fast")
        ema21 = _ind("ema_slow")
        close = _ind("close")
        lines = [f"📍 **Key price levels for {sym}** ({now_ist})", ""]
        if bb_lower != "N/A":
            lines.append(f"• **Support (BB Lower)**: {_fmt_price(bb_lower)}")
        if ema21 != "N/A":
            lines.append(f"• **Support (EMA 21)**: {_fmt_price(ema21)}")
        if ema9 != "N/A":
            lines.append(f"• **Support/Pivot (EMA 9)**: {_fmt_price(ema9)}")
        if bb_mid != "N/A":
            lines.append(f"• **Mid pivot (BB Mid)**: {_fmt_price(bb_mid)}")
        if bb_upper != "N/A":
            lines.append(f"• **Resistance (BB Upper)**: {_fmt_price(bb_upper)}")
        if close != "N/A":
            lines.append(f"\n• **Current price**: {_fmt_price(close)}")
        reply = "\n".join(lines) if len(lines) > 2 else "Price level data is not available."

    # RSI analysis
    elif any(k in msg for k in ("rsi", "overbought", "oversold", "momentum")):
        rsi = _ind("rsi")
        if rsi != "N/A":
            try:
                rsi_f = float(rsi)
                if rsi_f >= 70:
                    state = f"**overbought** ({rsi_f:.1f}). Consider taking profits or waiting for a pullback."
                elif rsi_f <= 30:
                    state = f"**oversold** ({rsi_f:.1f}). A potential reversal or bounce may be near."
                else:
                    state = f"**neutral** ({rsi_f:.1f}). No extreme momentum signal right now."
                reply = f"RSI for **{sym}** is {state}"
            except ValueError:
                reply = f"RSI value: {rsi}"
        else:
            reply = "RSI data is not available for this symbol."

    # EMA / trend / direction
    elif any(k in msg for k in ("ema", "trend", "moving average", "direction", "bullish", "bearish")):
        ema9 = _ind("ema_fast")
        ema21 = _ind("ema_slow")
        close = _ind("close")
        trend = _ind("trend", "")
        parts = []
        if ema9 != "N/A" and ema21 != "N/A":
            try:
                if float(ema9) > float(ema21):
                    parts.append(f"EMA 9 ({_fmt_price(ema9)}) is **above** EMA 21 ({_fmt_price(ema21)}) — bullish cross.")
                else:
                    parts.append(f"EMA 9 ({_fmt_price(ema9)}) is **below** EMA 21 ({_fmt_price(ema21)}) — bearish cross.")
            except ValueError:
                pass
        if trend:
            parts.append(f"Overall trend: **{trend}**")
        if close != "N/A":
            parts.append(f"Last close: {_fmt_price(close)}")
        reply = "\n".join(parts) if parts else "EMA data is not available."

    # Bollinger Bands
    elif any(k in msg for k in ("bollinger", "bb", "band", "squeeze")):
        bb_upper = _ind("bb_upper")
        bb_mid = _ind("bb_middle")
        bb_lower = _ind("bb_lower")
        bb_signal = _ind("bb_signal", "")
        close = _ind("close")
        if bb_upper != "N/A" and bb_lower != "N/A":
            try:
                width = float(bb_upper) - float(bb_lower)
                reply = (
                    f"Bollinger Bands for **{sym}**:\n"
                    f"  Upper: {_fmt_price(bb_upper)}  |  Middle: {_fmt_price(bb_mid)}  |  Lower: {_fmt_price(bb_lower)}\n"
                    f"  Band width: ₹{width:.2f}  |  Signal: **{bb_signal or 'N/A'}**\n"
                    f"  Last close: {_fmt_price(close)}"
                )
            except ValueError:
                reply = f"BB Upper: {bb_upper}, Middle: {bb_mid}, Lower: {bb_lower}"
        else:
            reply = "Bollinger Band data is not available."

    # Volume (plain)
    elif "volume" in msg:
        vol = _ind("volume")
        try:
            reply = f"Volume for **{sym}**: **{int(float(vol)):,}**"
        except (ValueError, TypeError):
            reply = "Volume data is not available."

    # Summary / full overview
    elif any(k in msg for k in ("summary", "analysis", "overview", "all indicator", "check")):
        if not ind:
            reply = "No indicator data is currently loaded. Select a symbol and interval first."
        else:
            trend = str(_ind("trend", "")).upper()
            rsi = _ind("rsi", "N/A")
            close = _ind("close", "N/A")
            ema9 = _ind("ema_fast", "N/A")
            ema21 = _ind("ema_slow", "N/A")
            bb_signal = _ind("bb_signal", "N/A")
            vol = _ind("volume", "N/A")
            lines = [f"📊 **Market Summary — {sym}** ({now_ist})", ""]
            lines.append(f"• Close: {_fmt_price(close)}")
            lines.append(f"• Trend: **{trend}**")
            lines.append(f"• RSI (14): **{rsi}**")
            lines.append(f"• EMA 9: {_fmt_price(ema9)}  |  EMA 21: {_fmt_price(ema21)}")
            lines.append(f"• BB Signal: **{bb_signal}**")
            try:
                lines.append(f"• Volume: **{int(float(vol)):,}**")
            except (ValueError, TypeError):
                lines.append(f"• Volume: {vol}")
            reply = "\n".join(lines)

    # Buy / sell / signal / action
    elif any(k in msg for k in ("buy", "sell", "signal", "action", "trade", "entry", "exit")):
        trend = str(_ind("trend", "")).upper()
        rsi = _ind("rsi", "N/A")
        bb_signal = str(_ind("bb_signal", "")).upper()
        ema9 = _ind("ema_fast", "N/A")
        ema21 = _ind("ema_slow", "N/A")
        advice = []
        if trend == "BULLISH":
            advice.append("✅ Trend is **BULLISH** — price momentum is upward.")
        elif trend == "BEARISH":
            advice.append("🔴 Trend is **BEARISH** — price momentum is downward.")
        try:
            rsi_f = float(rsi)
            if rsi_f >= 70:
                advice.append(f"⚠ RSI ({rsi_f:.1f}) is overbought — avoid chasing, wait for pullback.")
            elif rsi_f <= 30:
                advice.append(f"💡 RSI ({rsi_f:.1f}) is oversold — potential long opportunity.")
            else:
                advice.append(f"RSI ({rsi_f:.1f}) is neutral.")
        except (ValueError, TypeError):
            pass
        try:
            if float(ema9) > float(ema21):
                advice.append(f"EMA cross is **bullish** (EMA9 > EMA21).")
            else:
                advice.append(f"EMA cross is **bearish** (EMA9 < EMA21).")
        except (ValueError, TypeError):
            pass
        if bb_signal:
            advice.append(f"BB Signal: **{bb_signal}**")
        if advice:
            reply = "\n".join(advice) + "\n\n⚠ This is not financial advice. Always apply your own risk management."
        else:
            reply = "Not enough indicator data to generate a signal. Please load market data first."

    # Help / greeting
    elif any(k in msg for k in ("help", "hello", "hi", "what can you", "how", "?")):
        reply = (
            f"Hello! I'm analysing **{sym or 'your selected stock'}**. You can ask me:\n\n"
            "• **RSI** — overbought/oversold momentum\n"
            "• **EMA / Trend** — moving average crossovers and direction\n"
            "• **Bollinger Bands** — volatility and squeeze\n"
            "• **Support / Resistance** — key price levels\n"
            "• **Volume** — current traded volume\n"
            "• **Risk / Volatility** — how risky the setup looks\n"
            "• **Summary** — full indicator overview\n"
            "• **Buy/Sell** — combined signal from all indicators\n\n"
            f"Current time: {now_ist}"
        )

    # Fallback — attempt a best-effort response using available data
    else:
        if ind:
            trend = str(_ind("trend", "")).upper()
            rsi = _ind("rsi", "N/A")
            close = _ind("close", "N/A")
            reply = (
                f"I'm not sure exactly what you're asking, but here's a quick read on **{sym}**:\n"
                f"• Close: {_fmt_price(close)}  |  Trend: **{trend}**  |  RSI: **{rsi}**\n\n"
                "Try: *summary*, *RSI*, *EMA*, *support/resistance*, *volume*, *risk*, or *buy/sell signal*."
            )
        else:
            reply = (
                "Please select a symbol and load market data first, then ask about:\n"
                "RSI, EMA, Bollinger Bands, support/resistance, volume, risk, or buy/sell signal."
            )

    return {"reply": reply, "timestamp_ist": now_ist}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
