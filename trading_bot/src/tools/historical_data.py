"""
Historical data manager using yfinance for 20-year multi-exchange data.

Supports:
  - NSE / BSE equity & indices   (via SegmentRegistry → .NS / .BO tickers)
  - NSE F&O futures & options    (underlying index/equity yfinance ticker)
  - MCX commodities              (USD-proxy futures tickers: GC=F, CL=F, etc.)
  - NSE CDS currency pairs       (forex tickers: USDINR=X, EURINR=X, etc.)

All symbol resolution is delegated to SegmentRegistry; this module is
responsible only for fetching, normalising, and caching OHLCV DataFrames.
"""
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf
from loguru import logger

from src.tools.segment_registry import SegmentRegistry, SymbolInfo


class HistoricalDataManager:
    """Fetch and cache historical OHLCV data using yfinance for all exchanges."""

    # --- convenience universe lists ----------------------------------------

    NIFTY50_SYMBOLS = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR",
        "ICICIBANK", "KOTAKBANK", "SBIN", "BHARTIARTL", "ITC",
        "ASIANPAINT", "BAJFINANCE", "HCLTECH", "WIPRO", "AXISBANK",
        "MARUTI", "LT", "ULTRACEMCO", "TITAN", "NESTLEIND",
        "SUNPHARMA", "POWERGRID", "NTPC", "TECHM", "ONGC",
        "BAJAJFINSV", "JSWSTEEL", "TATAMOTORS", "TATASTEEL", "DIVISLAB",
        "DRREDDY", "CIPLA", "EICHERMOT", "BPCL", "COALINDIA",
        "HEROMOTOCO", "BRITANNIA", "GRASIM", "SHREECEM", "HINDALCO",
        "ADANIPORTS", "ADANIENT", "TATACONSUM", "APOLLOHOSP", "BAJAJ-AUTO",
        "M&M", "INDUSINDBK", "SBILIFE", "HDFCLIFE", "UPL",
    ]

    # Kept for backward compatibility — maps to SegmentRegistry internally
    INDEX_SYMBOLS = {"NIFTY50": "^NSEI", "SENSEX": "^BSESN"}

    # Intervals supported by yfinance that we expose
    VALID_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"}

    def __init__(self, data_dir: str = "data/historical"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._registry = SegmentRegistry()
        logger.info(f"HistoricalDataManager initialised: {self.data_dir.absolute()}")

    # ── Symbol resolution ────────────────────────────────────────────────────

    def resolve_symbol_info(
        self,
        symbol: str,
        exchange: str = "NSE",
        instrument: str = "SPOT",
    ) -> SymbolInfo:
        """
        Return full metadata for a symbol via SegmentRegistry.

        Args:
            symbol:     e.g. "RELIANCE", "GOLD", "USDINR", "NIFTY50"
            exchange:   "NSE" | "BSE" | "NFO" | "MCX" | "CDS"
            instrument: "SPOT" | "INTRADAY" | "FUTURES" | "OPTIONS"

        Returns:
            SymbolInfo with yf_ticker, lot_size, currency, commission_segment …
        """
        return self._registry.resolve(symbol, exchange=exchange, instrument=instrument)

    def _resolve_yf_ticker(
        self,
        symbol: str,
        exchange: str = "NSE",
        instrument: str = "SPOT",
    ) -> tuple[str, SymbolInfo]:
        """Return (yf_ticker, SymbolInfo) for fetching via yfinance."""
        info = self._registry.resolve(symbol, exchange=exchange, instrument=instrument)
        if not info.yf_ticker:
            raise ValueError(
                f"{symbol} ({exchange}) has no yfinance proxy. "
                "Use Kite Connect for live/historical data."
            )
        return info.yf_ticker, info

    # ── Legacy helper — kept for any callers that used it directly ───────────

    def _nse_to_yfinance_symbol(self, symbol: str) -> str:
        """Convert NSE symbol to yfinance format (legacy shim)."""
        if symbol.startswith("^"):
            return symbol
        try:
            yf_ticker, _ = self._resolve_yf_ticker(symbol, exchange="NSE")
            return yf_ticker
        except Exception:
            return f"{symbol}.NS"

    # ── Core fetch ──────────────────────────────────────────────────────────

    def fetch_symbol(
        self,
        symbol: str,
        period: str = "20y",
        interval: str = "1d",
        max_retries: int = 3,
        exchange: str = "NSE",
        instrument: str = "SPOT",
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for any symbol on any supported exchange.

        Args:
            symbol:      Exchange symbol (e.g. "RELIANCE", "GOLD", "USDINR")
            period:      yfinance period string ("20y", "5y", "1y", …)
            interval:    yfinance interval ("1d", "1wk", "1h", …)
            max_retries: Network retry count
            exchange:    "NSE" | "BSE" | "NFO" | "MCX" | "CDS"  (default "NSE")
            instrument:  "SPOT" | "INTRADAY" | "FUTURES" | "OPTIONS"

        Returns:
            Normalised DataFrame with columns:
              timestamp, open, high, low, close, volume
            For MCX USD-proxy symbols prices are in USD (add currency metadata).
            Returns None on failure.
        """
        try:
            yf_ticker, info = self._resolve_yf_ticker(symbol, exchange, instrument)
        except ValueError as exc:
            logger.error(str(exc))
            return None

        if info.usd_proxy:
            logger.info(
                f"{symbol} ({exchange}): using USD proxy {yf_ticker}. "
                "Prices returned in USD — apply USDINR rate for INR conversion."
            )

        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(
                    f"Fetching {symbol}/{exchange} ({yf_ticker}) "
                    f"attempt {attempt}/{max_retries}"
                )
                ticker = yf.Ticker(yf_ticker)
                df = ticker.history(period=period, interval=interval)

                if df.empty:
                    logger.warning(f"{symbol}: No data returned from yfinance")
                    return None

                # Normalise column names
                df = df.reset_index()
                df.columns = [col.lower() for col in df.columns]

                if "date" in df.columns:
                    df = df.rename(columns={"date": "timestamp"})
                elif "datetime" in df.columns:
                    df = df.rename(columns={"datetime": "timestamp"})

                required = ["timestamp", "open", "high", "low", "close", "volume"]
                if not all(c in df.columns for c in required):
                    logger.error(
                        f"{symbol}: Missing columns. Got: {df.columns.tolist()}"
                    )
                    return None

                df = df.dropna(subset=["close"])[required]

                logger.info(
                    f"{symbol} ({exchange}): {len(df)} rows "
                    f"({df['timestamp'].min().date()} → "
                    f"{df['timestamp'].max().date()})"
                )
                return df

            except Exception as exc:
                logger.warning(f"{symbol}: Attempt {attempt} failed — {exc}")
                if attempt < max_retries:
                    time.sleep(2)
                else:
                    logger.error(f"{symbol}: All {max_retries} attempts failed")
                    return None

    # ── Bulk fetch helpers ───────────────────────────────────────────────────

    def fetch_nifty50_universe(
        self,
        period: str = "20y",
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        """Fetch all Nifty 50 NSE equity symbols."""
        return self.fetch_bulk(
            self.NIFTY50_SYMBOLS,
            exchange="NSE",
            period=period,
            interval=interval,
        )

    def fetch_indices(
        self,
        period: str = "20y",
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        """Fetch NIFTY50 and SENSEX index data."""
        results: dict[str, pd.DataFrame] = {}
        logger.info("Fetching index data…")
        for name, yf_raw in self.INDEX_SYMBOLS.items():
            # Resolve via registry: NIFTY50→NSE, SENSEX→BSE
            exch = "BSE" if name == "SENSEX" else "NSE"
            df = self.fetch_symbol(name, period=period, interval=interval, exchange=exch)
            if df is not None and len(df) > 0:
                results[name] = df
        return results

    def fetch_bulk(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        instrument: str = "SPOT",
        period: str = "20y",
        interval: str = "1d",
        rate_limit_every: int = 5,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch multiple symbols from any exchange.

        Args:
            symbols:          List of exchange symbols
            exchange:         "NSE" | "BSE" | "NFO" | "MCX" | "CDS"
            instrument:       "SPOT" | "INTRADAY" | "FUTURES" | "OPTIONS"
            period:           yfinance period
            interval:         yfinance interval
            rate_limit_every: Pause 1 s after every N symbols

        Returns:
            {symbol: DataFrame} for every symbol that fetched successfully
        """
        results: dict[str, pd.DataFrame] = {}
        logger.info(f"Bulk fetch: {len(symbols)} symbols from {exchange}")

        for i, symbol in enumerate(symbols):
            df = self.fetch_symbol(
                symbol,
                period=period,
                interval=interval,
                exchange=exchange,
                instrument=instrument,
            )
            if df is not None and len(df) > 0:
                results[symbol] = df

            if (i + 1) % rate_limit_every == 0:
                time.sleep(1)

        logger.info(f"Bulk fetch complete: {len(results)}/{len(symbols)} succeeded")
        return results

    def fetch_mcx_universe(
        self,
        period: str = "20y",
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        """Fetch all MCX commodity contracts that have a yfinance proxy."""
        mcx_symbols = self._registry.list_symbols("MCX")
        return self.fetch_bulk(
            mcx_symbols, exchange="MCX", period=period, interval=interval
        )

    def fetch_cds_universe(
        self,
        period: str = "20y",
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        """Fetch all NSE CDS currency pair contracts."""
        cds_symbols = self._registry.list_symbols("CDS")
        return self.fetch_bulk(
            cds_symbols, exchange="CDS", period=period, interval=interval
        )

    # ── Cache helpers ────────────────────────────────────────────────────────

    def _cache_key(self, symbol: str, exchange: str, interval: str) -> str:
        """Build a unique, filesystem-safe cache filename stem."""
        safe = symbol.replace("&", "_").replace("/", "_").replace("=", "_")
        return f"{safe}_{exchange}_{interval}"

    def save_to_csv(
        self,
        symbol: str,
        df: pd.DataFrame,
        interval: str = "1d",
        exchange: str = "NSE",
    ) -> str:
        """Save DataFrame to CSV cache."""
        filename = f"{self._cache_key(symbol, exchange, interval)}.csv"
        filepath = self.data_dir / filename
        df.to_csv(filepath, index=False)
        logger.debug(f"Saved {len(df)} rows → {filepath}")
        return str(filepath)

    def load_from_csv(
        self,
        symbol: str,
        interval: str = "1d",
        exchange: str = "NSE",
    ) -> Optional[pd.DataFrame]:
        """Load cached CSV; returns None on miss."""
        filename = f"{self._cache_key(symbol, exchange, interval)}.csv"
        filepath = self.data_dir / filename

        # Also try legacy filename format (symbol_interval.csv) for NSE backward compat
        if not filepath.exists() and exchange == "NSE":
            legacy = self.data_dir / f"{symbol}_{interval}.csv"
            if legacy.exists():
                filepath = legacy

        if not filepath.exists():
            logger.debug(f"Cache miss: {filepath.name}")
            return None

        try:
            df = pd.read_csv(filepath)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            logger.debug(f"Cache hit: {filepath.name} — {len(df)} rows")
            return df
        except Exception as exc:
            logger.error(f"Failed to load {filepath}: {exc}")
            return None

    # ── High-level entry point ───────────────────────────────────────────────

    def get_symbol_data(
        self,
        symbol: str,
        period: str = "20y",
        interval: str = "1d",
        use_cache: bool = True,
        exchange: str = "NSE",
        instrument: str = "SPOT",
    ) -> Optional[pd.DataFrame]:
        """
        Primary entry point: return OHLCV data, using CSV cache when available.

        Args:
            symbol:     Exchange symbol
            period:     Data period if fetching fresh
            interval:   Data interval
            use_cache:  Try CSV cache before network fetch
            exchange:   "NSE" | "BSE" | "NFO" | "MCX" | "CDS"
            instrument: "SPOT" | "INTRADAY" | "FUTURES" | "OPTIONS"

        Returns:
            Normalised DataFrame or None on failure
        """
        if use_cache:
            cached = self.load_from_csv(symbol, interval, exchange)
            if cached is not None:
                return cached

        df = self.fetch_symbol(
            symbol,
            period=period,
            interval=interval,
            exchange=exchange,
            instrument=instrument,
        )

        if df is not None and len(df) > 0:
            self.save_to_csv(symbol, df, interval, exchange)

        return df

