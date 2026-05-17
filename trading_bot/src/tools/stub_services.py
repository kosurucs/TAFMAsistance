"""
stub_services.py – Stub implementations for paper-trading mode.

Provides mock implementations of Kite services that use historical CSV data
instead of live market data from Zerodha.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from src.tools.historical_data import HistoricalDataManager


class StubDataFetcher:
    """Mock data fetcher that returns historical data from CSV files."""
    
    def __init__(self):
        self._historical = HistoricalDataManager()
        logger.info("StubDataFetcher initialized with historical data")
    
    def fetch_ohlcv(self, instrument_token: int, tradingsymbol: str, interval: str, from_date: Any, to_date: Any) -> list[dict]:
        """Fetch historical OHLCV data from CSV files."""
        try:
            # Map interval to historical data manager format
            interval_map = {"minute": "1h", "day": "1d", "hour": "1h"}
            hist_interval = interval_map.get(interval, "1d")
            
            df = self._historical.get_symbol_data(tradingsymbol, interval=hist_interval)
            if df is None or df.empty:
                return []
            
            # Convert DataFrame to Kite-like dict format
            records = []
            for idx, row in df.iterrows():
                records.append({
                    "date": idx,
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": int(row.get("volume", 0)),
                })
            return records
        except Exception as e:
            logger.warning(f"Error fetching historical data for {tradingsymbol}: {e}")
            return []
    
    def fetch_latest_quote(self, symbols: list[str]) -> dict[str, Any]:
        """Fetch latest quote from historical data."""
        result = {}
        for symbol in symbols:
            try:
                df = self._historical.get_symbol_data(symbol, interval="1d")
                if df is not None and not df.empty:
                    last_row = df.iloc[-1]
                    result[symbol] = {
                        "last_price": float(last_row.get("close", 0)),
                        "ohlc": {
                            "open": float(last_row.get("open", 0)),
                            "high": float(last_row.get("high", 0)),
                            "low": float(last_row.get("low", 0)),
                            "close": float(last_row.get("close", 0)),
                        },
                        "volume": int(last_row.get("volume", 0)),
                    }
            except Exception as e:
                logger.warning(f"Error fetching quote for {symbol}: {e}")
        return result
    
    def lookup_instrument_token(self, exchange: str, tradingsymbol: str) -> int:
        """Return dummy token for paper trading."""
        return 0


class StubMarketData:
    """Stub MarketData that returns data from historical CSV files."""
    
    def __init__(self):
        self._historical = HistoricalDataManager()
        logger.info("StubMarketData initialized with historical data")
    
    def get_quote(self, symbols: list[str]) -> dict[str, Any]:
        """Return latest quote from historical data with simulated market depth."""
        result = {}
        for symbol_str in symbols:
            # Remove exchange prefix (e.g., "NSE:RELIANCE" -> "RELIANCE")
            symbol = symbol_str.split(":")[-1]
            try:
                df = self._historical.get_symbol_data(symbol, interval="1d")
                if df is not None and not df.empty:
                    last_row = df.iloc[-1]
                    last_price = float(last_row.get("close", 0))
                    
                    # Simulate market depth (5 levels each side)
                    # Buy orders below last_price, sell orders above
                    tick_size = 0.05  # ₹0.05 tick size
                    buy_depth = []
                    sell_depth = []
                    
                    for i in range(5):
                        buy_price = round(last_price - (i + 1) * tick_size, 2)
                        sell_price = round(last_price + (i + 1) * tick_size, 2)
                        
                        # Simulate decreasing quantity at each level
                        buy_qty = int(1000 * (5 - i))
                        sell_qty = int(1000 * (5 - i))
                        
                        buy_depth.append({"price": buy_price, "quantity": buy_qty, "orders": i + 1})
                        sell_depth.append({"price": sell_price, "quantity": sell_qty, "orders": i + 1})
                    
                    result[symbol_str] = {
                        "instrument_token": 0,
                        "last_price": last_price,
                        "ohlc": {
                            "open": float(last_row.get("open", 0)),
                            "high": float(last_row.get("high", 0)),
                            "low": float(last_row.get("low", 0)),
                            "close": float(last_row.get("close", 0)),
                        },
                        "volume": int(last_row.get("volume", 0)),
                        "net_change": 0.0,
                        "oi_day_change_percentage": 0.0,
                        "depth": {
                            "buy": buy_depth,
                            "sell": sell_depth,
                        },
                    }
            except Exception as e:
                logger.warning(f"Error fetching quote for {symbol}: {e}")
        return result


class StubDataPipeline:
    """Stub DataPipeline that returns historical CSV data."""
    
    def __init__(self):
        self._historical = HistoricalDataManager()
        logger.info("StubDataPipeline initialized with historical data")
    
    def get_ohlcv_df(self, instrument_token: int, tradingsymbol: str, interval: str = "minute", days_back: int = 1, use_cache: bool = False):
        """Return historical OHLCV data from CSV files."""
        # Map interval to historical data manager format
        interval_map = {"minute": "1h", "day": "1d", "hour": "1h"}
        hist_interval = interval_map.get(interval, "1d")
        
        df = self._historical.get_symbol_data(tradingsymbol, interval=hist_interval)
        
        if df is None or df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        
        # Match the format of real DataPipeline: index named "date", not "timestamp"
        if 'timestamp' in df.columns:
            df = df.rename(columns={'timestamp': 'date'})
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        elif df.index.name != 'date':
            # If timestamp is already the index, rename it
            df.index.name = 'date'
            df.index = pd.to_datetime(df.index)
        
        # Keep only OHLCV columns (matching real DataPipeline format)
        cols = ['open', 'high', 'low', 'close', 'volume']
        existing_cols = [c for c in cols if c in df.columns]
        df = df[existing_cols]
        
        return df
