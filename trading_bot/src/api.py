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
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, Field

# Load env from trading_bot/.env
ENV_PATH = Path(__file__).parents[1] / ".env"
load_dotenv(ENV_PATH)

# ── Kite session (reuse across requests) ─────────────────────────────────────
from src.tools.kite_tools import KiteAuthManager, KiteConnect, KiteDataFetcher  # noqa: E402
from src.tools.instruments import InstrumentsCache              # noqa: E402
from src.tools.market_data import MarketData                    # noqa: E402
from src.tools.data_pipeline import DataPipeline                # noqa: E402
from src.utils.technical_analysis import compute_indicators     # noqa: E402

PAPER_TRADING = os.environ.get("PAPER_TRADING", "true").lower() == "true"

_session_lock = threading.Lock()
_auth: KiteAuthManager | None = None
_kite: Any | None = None
_data_fetcher: KiteDataFetcher | None = None
_instruments: InstrumentsCache | None = None
_market: MarketData | None = None
_pipeline: DataPipeline | None = None

app = FastAPI(title="TAFMAsistance Trading API", version="1.0.0")

# Allow the React dev server (localhost:5173) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

EXCHANGE = os.environ.get("EXCHANGE", "NSE")
DEFAULT_CANDLE_LIMIT = int(os.environ.get("UI_CANDLE_LIMIT", "2000"))


def _persist_access_token(access_token: str) -> None:
    """Persist the Kite access token to trading_bot/.env for restarts."""
    try:
        text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
        line = f"KITE_ACCESS_TOKEN={access_token}"
        if re.search(r"(?m)^KITE_ACCESS_TOKEN\s*=.*$", text):
            text = re.sub(r"(?m)^KITE_ACCESS_TOKEN\s*=.*$", line, text)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += line + "\n"
        ENV_PATH.write_text(text, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist KITE_ACCESS_TOKEN to .env: {}", exc)


def _is_authenticated() -> bool:
    """Validate the Kite session by probing the API; returns True only when
    the access token is both present and accepted by Zerodha."""
    if PAPER_TRADING:
        return True

    # If a live session is already initialised, verify it is still valid.
    if _kite is not None:
        try:
            _kite.profile()
            return True
        except Exception:
            pass

    # No live session yet – check whether the stored token is still valid.
    access_token = os.environ.get("KITE_ACCESS_TOKEN", "").strip()
    if not access_token or KiteConnect is None:
        return False

    try:
        auth_mgr = KiteAuthManager()
        probe = KiteConnect(api_key=auth_mgr.api_key)
        probe.set_access_token(access_token)
        probe.profile()  # raises TokenException / NetworkException if expired
        return True
    except Exception:
        return False


def _init_kite_session(force: bool = False) -> None:
    """Initialise Kite-dependent singletons lazily."""
    global _auth, _kite, _data_fetcher, _instruments, _market, _pipeline

    if PAPER_TRADING:
        return

    with _session_lock:
        if not force and _kite is not None and _data_fetcher is not None and _instruments is not None and _market is not None and _pipeline is not None:
            return

        _auth = KiteAuthManager()
        _kite = _auth.get_kite_session()
        _data_fetcher = KiteDataFetcher(_kite)
        _instruments = InstrumentsCache(_kite)
        _market = MarketData(_kite)
        _pipeline = DataPipeline(_data_fetcher)


def _require_kite_session() -> None:
    if PAPER_TRADING:
        return

    try:
        _init_kite_session()
    except KeyError as exc:
        missing_key = str(exc).strip("\"'")
        raise HTTPException(
            status_code=400,
            detail=f"Missing environment variable: {missing_key}",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=401,
            detail=(
                "Kite authentication required. Complete login via "
                "/api/auth/login-url and /api/auth/exchange. "
                f"Details: {exc}"
            ),
        ) from exc


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


class AuthExchangeRequest(BaseModel):
    callback_url: str


@app.get("/api/auth/status")
def auth_status() -> dict[str, Any]:
    """Return whether UI must force user login before using market endpoints.

    Also initialises the Kite session when a valid token is found, and
    includes the Kite login URL so the UI can open it without a second
    round-trip when authentication is required.
    """
    if PAPER_TRADING:
        return {
            "paper_trading": True,
            "authenticated": True,
            "requires_login": False,
            "login_url": None,
        }

    authenticated = _is_authenticated()

    # Eagerly initialise the full session when the token is valid but the
    # singletons haven't been created yet (e.g. first request after restart).
    if authenticated and _kite is None:
        try:
            _init_kite_session()
        except Exception:
            authenticated = False

    # Build the Kite login URL upfront so the UI can open it immediately.
    login_url: str | None = None
    if not authenticated and KiteConnect is not None:
        try:
            auth_mgr = KiteAuthManager()
            login_url = KiteConnect(api_key=auth_mgr.api_key).login_url()
        except Exception:
            pass

    return {
        "paper_trading": PAPER_TRADING,
        "authenticated": authenticated,
        "requires_login": not authenticated,
        "login_url": login_url,
    }


@app.get("/api/auth/login-url")
def auth_login_url() -> dict[str, str]:
    """Return Zerodha login URL so UI can open it in a new tab."""
    if PAPER_TRADING:
        raise HTTPException(
            status_code=400,
            detail="PAPER_TRADING=true. Live Kite login is not required.",
        )

    if KiteConnect is None:
        raise HTTPException(status_code=500, detail="kiteconnect package is not installed.")

    try:
        auth = KiteAuthManager()
        return {"login_url": KiteConnect(api_key=auth.api_key).login_url()}
    except KeyError as exc:
        missing_key = str(exc).strip("\"'")
        raise HTTPException(
            status_code=400,
            detail=f"Missing environment variable: {missing_key}",
        ) from exc


@app.post("/api/auth/exchange")
def auth_exchange(body: AuthExchangeRequest) -> dict[str, str]:
    """Exchange request_token from callback URL for access token."""
    if PAPER_TRADING:
        return {"status": "ok", "message": "Paper mode active; authentication skipped."}

    if KiteConnect is None:
        raise HTTPException(status_code=500, detail="kiteconnect package is not installed.")

    callback_url = body.callback_url.strip()
    if not callback_url:
        raise HTTPException(status_code=400, detail="callback_url is required.")

    parsed = urlparse(callback_url)
    params = parse_qs(parsed.query)
    request_token = params.get("request_token", [""])[0].strip()
    status = params.get("status", [""])[0].strip().lower()

    if status and status != "success":
        raise HTTPException(status_code=400, detail="Kite login status is not success.")
    if not request_token:
        raise HTTPException(status_code=400, detail="request_token not found in callback_url.")

    try:
        auth = KiteAuthManager()
        session_data = KiteConnect(api_key=auth.api_key).generate_session(
            request_token,
            api_secret=auth.api_secret,
        )
        access_token = str(session_data.get("access_token", "")).strip()
        if not access_token:
            raise HTTPException(status_code=502, detail="access_token not returned by Kite.")

        os.environ["KITE_ACCESS_TOKEN"] = access_token
        _persist_access_token(access_token)
        _init_kite_session(force=True)

        return {"status": "ok", "message": "Kite authentication successful."}
    except KeyError as exc:
        missing_key = str(exc).strip("\"'")
        raise HTTPException(
            status_code=400,
            detail=f"Missing environment variable: {missing_key}",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to exchange request token: {exc}") from exc


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
    _require_kite_session()
    if _instruments is None:
        raise HTTPException(status_code=503, detail="Kite instruments service is not initialized.")

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
    _require_kite_session()
    if _instruments is None or _pipeline is None:
        raise HTTPException(status_code=503, detail="Kite market services are not initialized.")

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
    _require_kite_session()
    if _market is None:
        raise HTTPException(status_code=503, detail="Kite quote service is not initialized.")

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


# ── Ollama helper ─────────────────────────────────────────────────────────────

import urllib.request as _ureq
import json as _json

_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
_OLLAMA_CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "trading-assistant")

def _ollama_available() -> bool:
    try:
        _ureq.urlopen(f"{_OLLAMA_URL}/api/tags", timeout=1)
        return True
    except Exception:
        return False

def _ollama_chat(system: str, user: str, max_tokens: int = 600) -> str | None:
    """Call Ollama and return the response text, or None on failure."""
    try:
        data = _json.dumps({
            "model": _OLLAMA_CHAT_MODEL,
            "system": system,
            "prompt": user,
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": max_tokens},
        }).encode()
        req = _ureq.Request(
            f"{_OLLAMA_URL}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with _ureq.urlopen(req, timeout=60) as r:
            body = _json.loads(r.read().decode())
            return body.get("response", "").strip()
    except Exception as exc:
        logger.warning("Ollama chat failed: {}", exc)
        return None


# ── Chat endpoint ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    symbol: str | None = None
    indicators: dict[str, object] = Field(default_factory=dict)


_CHAT_SYSTEM = (
    "You are an expert trading and financial markets assistant specialising in Indian markets (NSE/BSE). "
    "You have deep knowledge of technical analysis, price action, options, RSI, EMA, Bollinger Bands, "
    "VWAP, candlestick patterns, intraday strategies, and risk management. "
    "Be concise, specific, and actionable. Always remind users this is not financial advice."
)


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    """Return a trading assistant reply — uses Ollama if available, else rule-based fallback."""
    msg = req.message.strip()
    sym = (req.symbol or "").upper()
    ind = req.indicators
    now_ist = datetime.now(_IST).strftime("%d %b %Y %I:%M:%S %p IST")

    # ── Try Ollama first ──────────────────────────────────────────────────────
    if _ollama_available():
        # Build a context-rich prompt
        ind_lines = ""
        if ind:
            ind_lines = "\n".join(
                f"  {k}: {v}" for k, v in ind.items()
                if v not in (None, "N/A", "")
            )
        context_block = (
            f"Symbol: {sym}\nTime: {now_ist}\nIndicators:\n{ind_lines}"
            if ind_lines else
            f"Symbol: {sym}\nTime: {now_ist}"
        )
        user_prompt = f"{context_block}\n\nUser question: {msg}"
        reply = _ollama_chat(_CHAT_SYSTEM, user_prompt)
        if reply:
            return {"reply": reply, "timestamp_ist": now_ist, "source": "ollama"}

    # ── Rule-based fallback ───────────────────────────────────────────────────
    msg_lower = msg.lower()

    def _ind(key: str, default="N/A"):
        return ind.get(key, default)

    def _fmt_price(val) -> str:
        try:
            return f"₹{float(val):,.2f}"
        except (TypeError, ValueError):
            return str(val)



    # ── Rule-based fallback routing ───────────────────────────────────────────

    # High volume / low risk screener-style question about current symbol
    if any(k in msg_lower for k in ("high volume", "high volum", "volume spike", "unusual volume")):
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

    elif any(k in msg_lower for k in ("low risk", "risk", "safe", "volatile", "volatility")):
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
    elif any(k in msg_lower for k in ("support", "resistance", "level", "price target", "target")):
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
    elif any(k in msg_lower for k in ("rsi", "overbought", "oversold", "momentum")):
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
    elif any(k in msg_lower for k in ("ema", "trend", "moving average", "direction", "bullish", "bearish")):
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
    elif any(k in msg_lower for k in ("bollinger", "bb", "band", "squeeze")):
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
    elif "volume" in msg_lower:
        vol = _ind("volume")
        try:
            reply = f"Volume for **{sym}**: **{int(float(vol)):,}**"
        except (ValueError, TypeError):
            reply = "Volume data is not available."

    # Summary / full overview
    elif any(k in msg_lower for k in ("summary", "analysis", "overview", "all indicator", "check")):
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
    elif any(k in msg_lower for k in ("buy", "sell", "signal", "action", "trade", "entry", "exit")):
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
    elif any(k in msg_lower for k in ("help", "hello", "hi", "what can you", "how", "?")):
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

    # Fallback
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


# ── Manual order placement ────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    transaction_type: str                        # "BUY" | "SELL"
    quantity: int
    variety: str = "regular"                     # regular | amo | co | iceberg | auction
    order_type: str = "MARKET"                   # MARKET | LIMIT | SL | SL-M
    product: str = "MIS"                         # MIS | CNC | NRML | MTF
    price: float | None = None                   # required for LIMIT / SL
    trigger_price: float | None = None           # required for SL / SL-M / CO
    validity: str = "DAY"                        # DAY | IOC | TTL
    validity_ttl: int | None = None              # minutes, only for validity=TTL
    disclosed_quantity: int | None = None        # partial disclosure for equity
    iceberg_legs: int | None = None              # 2–50, only for variety=iceberg
    iceberg_quantity: int | None = None          # quantity per leg for iceberg
    auction_number: str | None = None            # for variety=auction
    market_protection: float | None = None       # 0=off, >0 custom %, -1=auto (MARKET/SL-M only)
    autoslice: bool = False                      # auto-split qty above freeze limit
    tag: str | None = Field(None, max_length=20) # optional user tag (max 20 chars)


class OrderModifyRequest(BaseModel):
    order_type: str | None = None
    quantity: int | None = None
    price: float | None = None
    trigger_price: float | None = None
    disclosed_quantity: int | None = None
    validity: str | None = None
    parent_order_id: str | None = None          # required to modify CO second-leg


VALID_VARIETIES = {"regular", "amo", "co", "iceberg", "auction"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "SL", "SL-M"}
VALID_PRODUCTS = {"MIS", "CNC", "NRML", "MTF"}
VALID_VALIDITY = {"DAY", "IOC", "TTL"}


@app.post("/api/order")
def place_order(body: OrderRequest) -> dict[str, Any]:
    """Place a manual buy/sell order (paper or live).

    Supports all Kite varieties: regular, amo, co, iceberg, auction.
    """
    _require_kite_session()
    symbol = body.symbol.upper()
    tx = body.transaction_type.upper()
    variety = body.variety.lower()
    ot = body.order_type.upper()
    product = body.product.upper()
    validity = body.validity.upper()

    if tx not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="transaction_type must be BUY or SELL.")
    if variety not in VALID_VARIETIES:
        raise HTTPException(status_code=400, detail=f"variety must be one of {sorted(VALID_VARIETIES)}.")
    if ot not in VALID_ORDER_TYPES:
        raise HTTPException(status_code=400, detail=f"order_type must be one of {sorted(VALID_ORDER_TYPES)}.")
    if product not in VALID_PRODUCTS:
        raise HTTPException(status_code=400, detail=f"product must be one of {sorted(VALID_PRODUCTS)}.")
    if validity not in VALID_VALIDITY:
        raise HTTPException(status_code=400, detail=f"validity must be one of {sorted(VALID_VALIDITY)}.")
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be > 0.")
    if ot in ("LIMIT", "SL") and not body.price:
        raise HTTPException(status_code=400, detail=f"price is required for order_type={ot}.")
    if ot in ("SL", "SL-M") and not body.trigger_price:
        raise HTTPException(status_code=400, detail=f"trigger_price is required for order_type={ot}.")
    if variety == "iceberg" and not body.iceberg_legs:
        raise HTTPException(status_code=400, detail="iceberg_legs is required for variety=iceberg.")
    if validity == "TTL" and not body.validity_ttl:
        raise HTTPException(status_code=400, detail="validity_ttl (minutes) is required for validity=TTL.")

    if PAPER_TRADING or _kite is None:
        import time as _time
        order_id = f"PAPER-{int(_time.time() * 1000)}"
        return {
            "order_id": order_id,
            "status": "COMPLETE",
            "paper_trading": True,
            "symbol": symbol,
            "variety": variety,
            "transaction_type": tx,
            "quantity": body.quantity,
            "order_type": ot,
            "product": product,
            "price": body.price,
            "trigger_price": body.trigger_price,
            "validity": validity,
            "tag": body.tag,
        }

    try:
        kw: dict[str, Any] = dict(
            variety=variety,
            exchange=body.exchange.upper(),
            tradingsymbol=symbol,
            transaction_type=tx,
            quantity=body.quantity,
            product=product,
            order_type=ot,
            validity=validity,
            tag=body.tag or "tafm_ui",
        )
        if ot not in ("MARKET", "SL-M"):
            kw["price"] = body.price
        if ot in ("SL", "SL-M"):
            kw["trigger_price"] = body.trigger_price
        if body.disclosed_quantity:
            kw["disclosed_quantity"] = body.disclosed_quantity
        if validity == "TTL" and body.validity_ttl:
            kw["validity_ttl"] = body.validity_ttl
        if variety == "iceberg":
            kw["iceberg_legs"] = body.iceberg_legs
            if body.iceberg_quantity:
                kw["iceberg_quantity"] = body.iceberg_quantity
        if variety == "auction" and body.auction_number:
            kw["auction_number"] = body.auction_number
        if ot in ("MARKET", "SL-M") and body.market_protection is not None:
            kw["market_protection"] = body.market_protection
        if body.autoslice:
            kw["autoslice"] = True

        result = _kite.place_order(**kw)
        # autoslice returns a list; regular returns an order_id
        if isinstance(result, list):
            return {
                "order_ids": [r.get("order_id") for r in result if "order_id" in r],
                "slices": result,
                "status": "OPEN",
                "paper_trading": False,
                "autoslice": True,
            }
        return {
            "order_id": str(result),
            "status": "OPEN",
            "paper_trading": False,
            "symbol": symbol,
            "variety": variety,
            "transaction_type": tx,
            "quantity": body.quantity,
            "order_type": ot,
            "product": product,
            "price": body.price,
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Order placement failed: {exc}") from exc


@app.put("/api/order/{variety}/{order_id}")
def modify_order(variety: str, order_id: str, body: OrderModifyRequest) -> dict[str, Any]:
    """Modify an open or pending order."""
    variety = variety.lower()
    if variety not in VALID_VARIETIES:
        raise HTTPException(status_code=400, detail=f"variety must be one of {sorted(VALID_VARIETIES)}.")

    if PAPER_TRADING or _kite is None:
        return {"order_id": order_id, "paper_trading": True}

    try:
        kw: dict[str, Any] = {"variety": variety, "order_id": order_id}
        if body.order_type:
            kw["order_type"] = body.order_type.upper()
        if body.quantity is not None:
            kw["quantity"] = body.quantity
        if body.price is not None:
            kw["price"] = body.price
        if body.trigger_price is not None:
            kw["trigger_price"] = body.trigger_price
        if body.disclosed_quantity is not None:
            kw["disclosed_quantity"] = body.disclosed_quantity
        if body.validity:
            kw["validity"] = body.validity.upper()
        if body.parent_order_id:
            kw["parent_order_id"] = body.parent_order_id
        _kite.modify_order(**kw)
        return {"order_id": order_id, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Order modify failed: {exc}") from exc


@app.delete("/api/order/{variety}/{order_id}")
def cancel_order(variety: str, order_id: str, parent_order_id: str | None = None) -> dict[str, Any]:
    """Cancel an open or pending order."""
    variety = variety.lower()
    if variety not in VALID_VARIETIES:
        raise HTTPException(status_code=400, detail=f"variety must be one of {sorted(VALID_VARIETIES)}.")

    if PAPER_TRADING or _kite is None:
        return {"order_id": order_id, "paper_trading": True}

    try:
        kw: dict[str, Any] = {"variety": variety, "order_id": order_id}
        if parent_order_id:
            kw["parent_order_id"] = parent_order_id
        _kite.cancel_order(**kw)
        return {"order_id": order_id, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Order cancel failed: {exc}") from exc


@app.get("/api/orders")
def get_orders() -> dict[str, Any]:
    """Return today's orders — all varieties (open + executed + cancelled)."""
    if PAPER_TRADING or _kite is None:
        return {"orders": [], "paper_trading": True}
    try:
        orders = _kite.orders()
        return {"orders": orders, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to fetch orders: {exc}") from exc


@app.get("/api/orders/{order_id}")
def get_order_history(order_id: str) -> dict[str, Any]:
    """Return the full state history of a single order (all status transitions)."""
    if PAPER_TRADING or _kite is None:
        return {"history": [], "paper_trading": True}
    try:
        history = _kite.order_history(order_id=order_id)
        return {"history": history, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to fetch order history for {order_id}: {exc}") from exc


@app.get("/api/trades")
def get_trades() -> dict[str, Any]:
    """Return all executed trades for the day."""
    if PAPER_TRADING or _kite is None:
        return {"trades": [], "paper_trading": True}
    try:
        trades = _kite.trades()
        return {"trades": trades, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to fetch trades: {exc}") from exc


@app.get("/api/orders/{order_id}/trades")
def get_order_trades(order_id: str) -> dict[str, Any]:
    """Return the trades (fills) generated by a specific order."""
    if PAPER_TRADING or _kite is None:
        return {"trades": [], "paper_trading": True}
    try:
        trades = _kite.order_trades(order_id=order_id)
        return {"trades": trades, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to fetch trades for order {order_id}: {exc}") from exc


@app.get("/api/portfolio")
def get_portfolio_summary() -> dict[str, Any]:
    """Combined summary — positions + holdings + margins + day P&L.

    The UI uses this single call to populate all portfolio tabs at once.
    """
    if PAPER_TRADING or _kite is None:
        return {
            "paper_trading": True,
            "positions": {"day": [], "net": []},
            "holdings": [],
            "auctions": [],
            "margins": {},
            "day_pnl": 0.0,
            "holdings_pnl": 0.0,
        }
    try:
        positions = _kite.positions()
        holdings  = _kite.holdings()
        margins   = _kite.margins()
        try:
            auctions = _kite.holdings_auctions()
        except Exception:  # noqa: BLE001
            auctions = []
        day_pnl = sum(float(p.get("pnl", 0)) for p in positions.get("day", []))
        holdings_pnl = sum(float(h.get("pnl", 0)) for h in holdings)
        return {
            "paper_trading": False,
            "positions": positions,
            "holdings": holdings,
            "auctions": auctions,
            "margins": margins,
            "day_pnl": day_pnl,
            "holdings_pnl": holdings_pnl,
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Portfolio fetch failed: {exc}") from exc


@app.get("/api/portfolio/holdings")
def get_holdings() -> dict[str, Any]:
    """GET /portfolio/holdings — long-term equity holdings with P&L."""
    if PAPER_TRADING or _kite is None:
        return {"holdings": [], "paper_trading": True}
    try:
        holdings = _kite.holdings()
        pnl = sum(float(h.get("pnl", 0)) for h in holdings)
        return {"holdings": holdings, "total_pnl": pnl, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Holdings fetch failed: {exc}") from exc


@app.get("/api/portfolio/positions")
def get_positions() -> dict[str, Any]:
    """GET /portfolio/positions — net and day positions."""
    if PAPER_TRADING or _kite is None:
        return {"positions": {"net": [], "day": []}, "paper_trading": True}
    try:
        positions = _kite.positions()
        day_pnl = sum(float(p.get("pnl", 0)) for p in positions.get("day", []))
        return {"positions": positions, "day_pnl": day_pnl, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Positions fetch failed: {exc}") from exc


class PositionConvertRequest(BaseModel):
    tradingsymbol: str
    exchange: str = "NSE"
    transaction_type: str       # BUY | SELL
    position_type: str          # "day" | "overnight"
    quantity: int
    old_product: str            # MIS | NRML | CNC
    new_product: str            # MIS | NRML | CNC


@app.put("/api/portfolio/positions/convert")
def convert_position(body: PositionConvertRequest) -> dict[str, Any]:
    """PUT /portfolio/positions — convert margin product of an open position."""
    tx = body.transaction_type.upper()
    pt = body.position_type.lower()
    if tx not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="transaction_type must be BUY or SELL.")
    if pt not in ("day", "overnight"):
        raise HTTPException(status_code=400, detail="position_type must be 'day' or 'overnight'.")
    if body.old_product.upper() == body.new_product.upper():
        raise HTTPException(status_code=400, detail="old_product and new_product must differ.")
    if body.quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be > 0.")

    if PAPER_TRADING or _kite is None:
        return {"success": True, "paper_trading": True}
    try:
        result = _kite.convert_position(
            tradingsymbol=body.tradingsymbol.upper(),
            exchange=body.exchange.upper(),
            transaction_type=tx,
            position_type=pt,
            quantity=body.quantity,
            old_product=body.old_product.upper(),
            new_product=body.new_product.upper(),
        )
        return {"success": bool(result), "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Position conversion failed: {exc}") from exc


@app.get("/api/portfolio/holdings/auctions")
def get_holdings_auctions() -> dict[str, Any]:
    """GET /portfolio/holdings/auctions — holdings eligible for auction."""
    if PAPER_TRADING or _kite is None:
        return {"auctions": [], "paper_trading": True}
    try:
        auctions = _kite.holdings_auctions()
        return {"auctions": auctions, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Auctions fetch failed: {exc}") from exc


@app.post("/api/bot/run")
def bot_run_symbol(body: dict[str, str]) -> dict[str, Any]:
    """Run one LangGraph cycle for a symbol and return the decision."""
    from src.tools.data_pipeline import DataPipeline as _DP
    symbol = (body.get("symbol") or "").upper()
    exchange = (body.get("exchange") or EXCHANGE).upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required.")

    token: int = 0
    if _data_fetcher is not None:
        try:
            token = _data_fetcher.lookup_instrument_token(exchange, symbol)
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail=f"Instrument '{symbol}' not found on '{exchange}'.",
            )

    pipeline_inst: Any = _DP(_data_fetcher) if _data_fetcher else None
    if pipeline_inst is None:
        # Stub for paper mode
        import numpy as np
        import pandas as pd

        class _StubPL:
            def get_ohlcv_df(self, **_kw: Any) -> Any:
                n = 50
                rng = np.random.default_rng(42)
                prices = 1000.0 + float(abs(hash(symbol)) % 500) + np.cumsum(rng.normal(0, 5, n))
                return pd.DataFrame({"open": prices, "high": prices + 2, "low": prices - 2, "close": prices, "volume": rng.integers(10_000, 100_000, n)})
            def fetch_latest_quote(self, syms: list[str]) -> dict[str, Any]:
                return {s: {"last_price": 1000.0} for s in syms}
        pipeline_inst = _StubPL()

    try:
        from src.agents.trading_agent import TradingState, build_trading_graph
        from src.tools.kite_tools import KiteOrderManager
        from src.utils.risk_manager import RiskManager

        graph = build_trading_graph()
        initial: TradingState = {
            "symbol": symbol,
            "instrument_token": token,
            "exchange": exchange,
            "pipeline": pipeline_inst,
            "order_manager": KiteOrderManager(_kite),
            "portfolio": None,
            "risk_manager": RiskManager(),
            "llm_chain": None,
        }
        result = graph.invoke(initial)
        return {
            "symbol": symbol,
            "action": result.get("action", "HOLD"),
            "reasoning": result.get("reasoning", ""),
            "order_id": result.get("order_id"),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Bot run failed: {exc}") from exc


# ── GTT (Good Till Triggered) orders ─────────────────────────────────────────

class _GTTOrderItem(BaseModel):
    exchange: str = "NSE"
    tradingsymbol: str
    transaction_type: str   # "BUY" | "SELL"
    quantity: int
    order_type: str = "LIMIT"
    product: str = "CNC"
    price: float


class GTTRequest(BaseModel):
    trigger_type: str          # "single" | "two-leg"
    symbol: str
    exchange: str = "NSE"
    trigger_values: list[float]   # 1 value for single, 2 for two-leg
    last_price: float             # current LTP at time of placement
    orders: list[_GTTOrderItem]   # 1 order for single, 2 for two-leg


class GTTModifyRequest(BaseModel):
    trigger_type: str
    symbol: str
    exchange: str = "NSE"
    trigger_values: list[float]
    last_price: float
    orders: list[_GTTOrderItem]


# Resolve forward references (needed when loaded via importlib with
# `from __future__ import annotations` — e.g. via ui_api.py).
_GTTOrderItem.model_rebuild()
GTTRequest.model_rebuild()
GTTModifyRequest.model_rebuild()


def _gtt_paper_stub(trigger_id: int, body: GTTRequest | GTTModifyRequest, status: str = "active") -> dict[str, Any]:
    """Simulate a GTT record in paper-trading mode."""
    return {
        "id": trigger_id,
        "type": body.trigger_type,
        "status": status,
        "paper_trading": True,
        "condition": {
            "exchange": body.exchange,
            "tradingsymbol": body.symbol.upper(),
            "trigger_values": body.trigger_values,
            "last_price": body.last_price,
        },
        "orders": [o.model_dump() for o in body.orders],
    }


# In-process paper GTT store (keyed by id)
_paper_gtts: dict[int, dict[str, Any]] = {}
_paper_gtt_seq: int = 1_000_000


@app.post("/api/gtt")
def place_gtt(body: GTTRequest) -> dict[str, Any]:
    """Place a GTT trigger (single or two-leg / OCO)."""
    global _paper_gtt_seq

    tt = body.trigger_type.lower()
    if tt not in ("single", "two-leg"):
        raise HTTPException(status_code=400, detail="trigger_type must be 'single' or 'two-leg'.")
    if tt == "single" and len(body.trigger_values) != 1:
        raise HTTPException(status_code=400, detail="single GTT requires exactly one trigger_value.")
    if tt == "two-leg" and len(body.trigger_values) != 2:
        raise HTTPException(status_code=400, detail="two-leg GTT requires exactly two trigger_values.")
    if tt == "single" and len(body.orders) != 1:
        raise HTTPException(status_code=400, detail="single GTT requires exactly one order.")
    if tt == "two-leg" and len(body.orders) != 2:
        raise HTTPException(status_code=400, detail="two-leg GTT requires exactly two orders.")

    if PAPER_TRADING or _kite is None:
        _paper_gtt_seq += 1
        rec = _gtt_paper_stub(_paper_gtt_seq, body)
        _paper_gtts[_paper_gtt_seq] = rec
        return {"trigger_id": _paper_gtt_seq, "paper_trading": True}

    try:
        orders_payload = [
            {
                "exchange": o.exchange.upper(),
                "tradingsymbol": o.tradingsymbol.upper(),
                "transaction_type": o.transaction_type.upper(),
                "quantity": o.quantity,
                "order_type": o.order_type.upper(),
                "product": o.product.upper(),
                "price": o.price,
            }
            for o in body.orders
        ]
        trigger_id = _kite.place_gtt(
            trigger_type=tt,
            tradingsymbol=body.symbol.upper(),
            exchange=body.exchange.upper(),
            trigger_values=body.trigger_values,
            last_price=body.last_price,
            orders=orders_payload,
        )
        return {"trigger_id": trigger_id, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"GTT placement failed: {exc}") from exc


@app.get("/api/gtt")
def list_gtts() -> dict[str, Any]:
    """List all GTT triggers (active + recent 7 days)."""
    if PAPER_TRADING or _kite is None:
        return {"gtts": list(_paper_gtts.values()), "paper_trading": True}
    try:
        gtts = _kite.get_gtts()
        return {"gtts": gtts, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to fetch GTTs: {exc}") from exc


@app.get("/api/gtt/{trigger_id}")
def get_gtt(trigger_id: int) -> dict[str, Any]:
    """Get details of a single GTT by ID."""
    if PAPER_TRADING or _kite is None:
        rec = _paper_gtts.get(trigger_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"GTT {trigger_id} not found.")
        return rec
    try:
        return _kite.get_gtt(trigger_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to fetch GTT {trigger_id}: {exc}") from exc


@app.put("/api/gtt/{trigger_id}")
def modify_gtt(trigger_id: int, body: GTTModifyRequest) -> dict[str, Any]:
    """Modify an active GTT."""
    tt = body.trigger_type.lower()
    if tt not in ("single", "two-leg"):
        raise HTTPException(status_code=400, detail="trigger_type must be 'single' or 'two-leg'.")

    if PAPER_TRADING or _kite is None:
        if trigger_id not in _paper_gtts:
            raise HTTPException(status_code=404, detail=f"GTT {trigger_id} not found.")
        rec = _gtt_paper_stub(trigger_id, body)
        _paper_gtts[trigger_id] = rec
        return {"trigger_id": trigger_id, "paper_trading": True}

    try:
        orders_payload = [
            {
                "exchange": o.exchange.upper(),
                "tradingsymbol": o.tradingsymbol.upper(),
                "transaction_type": o.transaction_type.upper(),
                "quantity": o.quantity,
                "order_type": o.order_type.upper(),
                "product": o.product.upper(),
                "price": o.price,
            }
            for o in body.orders
        ]
        _kite.modify_gtt(
            trigger_id=trigger_id,
            trigger_type=tt,
            tradingsymbol=body.symbol.upper(),
            exchange=body.exchange.upper(),
            trigger_values=body.trigger_values,
            last_price=body.last_price,
            orders=orders_payload,
        )
        return {"trigger_id": trigger_id, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"GTT modify failed: {exc}") from exc


@app.delete("/api/gtt/{trigger_id}")
def delete_gtt(trigger_id: int) -> dict[str, Any]:
    """Delete / cancel an active GTT."""
    if PAPER_TRADING or _kite is None:
        _paper_gtts.pop(trigger_id, None)
        return {"trigger_id": trigger_id, "paper_trading": True}
    try:
        _kite.delete_gtt(trigger_id)
        return {"trigger_id": trigger_id, "paper_trading": False}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"GTT delete failed: {exc}") from exc
