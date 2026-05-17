"""
Historical data manager using yfinance for 20-year NSE/BSE data.
Supports Nifty 50 universe, indices, and custom symbols.
"""
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf
from loguru import logger


class HistoricalDataManager:
    """Fetch and cache historical OHLCV data using yfinance."""
    
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
        "M&M", "INDUSINDBK", "SBILIFE", "HDFCLIFE", "UPL"
    ]
    
    INDEX_SYMBOLS = {"NIFTY50": "^NSEI", "SENSEX": "^BSESN"}
    
    def __init__(self, data_dir: str = "data/historical"):
        """Initialize with storage directory."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"HistoricalDataManager initialized: {self.data_dir.absolute()}")
    
    def _nse_to_yfinance_symbol(self, symbol: str) -> str:
        """Convert NSE symbol to yfinance format."""
        # Index symbols (^NSEI, ^BSESN) stay as-is
        if symbol.startswith("^"):
            return symbol
        
        # Handle M&M special case
        if symbol == "M&M":
            return "M%26M.NS"
        
        # NSE stocks get .NS suffix
        return f"{symbol}.NS"
    
    def fetch_symbol(
        self,
        symbol: str,
        period: str = "20y",
        interval: str = "1d",
        max_retries: int = 3
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for a single symbol using yfinance.
        
        Args:
            symbol: NSE symbol (e.g., "RELIANCE") or index (e.g., "^NSEI")
            period: Data period (e.g., "20y", "5y", "1y")
            interval: Data interval ("1d", "1wk", "1mo")
            max_retries: Number of retry attempts for network failures
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            Returns None if fetch fails after all retries
        """
        yf_symbol = self._nse_to_yfinance_symbol(symbol)
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"Fetching {symbol} ({yf_symbol}) - attempt {attempt}/{max_retries}")
                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(period=period, interval=interval)
                
                if df.empty:
                    logger.warning(f"{symbol}: No data returned from yfinance")
                    return None
                
                # Normalize column names
                df = df.reset_index()
                df.columns = [col.lower() for col in df.columns]
                
                # Rename 'date' or 'datetime' to 'timestamp' if needed
                if 'date' in df.columns:
                    df = df.rename(columns={'date': 'timestamp'})
                elif 'datetime' in df.columns:
                    df = df.rename(columns={'datetime': 'timestamp'})
                
                # Ensure we have required columns
                required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                if not all(col in df.columns for col in required_cols):
                    logger.error(f"{symbol}: Missing required columns. Got: {df.columns.tolist()}")
                    return None
                
                # Drop rows with NaN close price
                df = df.dropna(subset=['close'])
                
                # Select only required columns
                df = df[required_cols]
                
                logger.info(f"{symbol}: Fetched {len(df)} rows ({df['timestamp'].min().date()} → {df['timestamp'].max().date()})")
                return df
                
            except Exception as e:
                logger.warning(f"{symbol}: Attempt {attempt} failed - {e}")
                if attempt < max_retries:
                    time.sleep(2)  # Wait 2s before retry
                else:
                    logger.error(f"{symbol}: All {max_retries} attempts failed")
                    return None
    
    def fetch_nifty50_universe(
        self,
        period: str = "20y",
        interval: str = "1d"
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch data for all Nifty 50 stocks.
        
        Returns:
            Dictionary mapping symbol → DataFrame
        """
        results = {}
        logger.info(f"Fetching {len(self.NIFTY50_SYMBOLS)} Nifty 50 symbols...")
        
        for i, symbol in enumerate(self.NIFTY50_SYMBOLS):
            df = self.fetch_symbol(symbol, period=period, interval=interval)
            if df is not None and len(df) > 0:
                results[symbol] = df
            
            # Rate limiting: pause every 5 symbols
            if (i + 1) % 5 == 0:
                time.sleep(1)
        
        logger.info(f"Fetched {len(results)}/{len(self.NIFTY50_SYMBOLS)} symbols successfully")
        return results
    
    def fetch_indices(
        self,
        period: str = "20y",
        interval: str = "1d"
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch Nifty 50 and Sensex index data.
        
        Returns:
            Dictionary mapping index name → DataFrame
        """
        results = {}
        logger.info("Fetching index data...")
        
        for name, yf_symbol in self.INDEX_SYMBOLS.items():
            df = self.fetch_symbol(yf_symbol, period=period, interval=interval)
            if df is not None and len(df) > 0:
                results[name] = df
        
        return results
    
    def save_to_csv(
        self,
        symbol: str,
        df: pd.DataFrame,
        interval: str = "1d"
    ) -> str:
        """
        Save DataFrame to CSV.
        
        Args:
            symbol: Symbol name (for filename)
            df: DataFrame to save
            interval: Data interval (for filename)
        
        Returns:
            Path to saved file
        """
        filename = f"{symbol}_{interval}.csv"
        filepath = self.data_dir / filename
        df.to_csv(filepath, index=False)
        logger.debug(f"Saved {len(df)} rows to {filepath}")
        return str(filepath)
    
    def load_from_csv(
        self,
        symbol: str,
        interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """
        Load cached CSV data.
        
        Args:
            symbol: Symbol name
            interval: Data interval
        
        Returns:
            DataFrame if file exists, None otherwise
        """
        filename = f"{symbol}_{interval}.csv"
        filepath = self.data_dir / filename
        
        if not filepath.exists():
            logger.debug(f"Cache miss: {filepath}")
            return None
        
        try:
            df = pd.read_csv(filepath)
            # Convert timestamp column to datetime
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            logger.debug(f"Cache hit: {filepath} - {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Failed to load {filepath}: {e}")
            return None
    
    def get_symbol_data(
        self,
        symbol: str,
        period: str = "20y",
        interval: str = "1d",
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        High-level method: load from cache or fetch fresh data.
        
        Args:
            symbol: NSE symbol or index
            period: Data period if fetching fresh
            interval: Data interval
            use_cache: If True, try loading from CSV first
        
        Returns:
            DataFrame with OHLCV data
        """
        # Try cache first
        if use_cache:
            cached = self.load_from_csv(symbol, interval)
            if cached is not None:
                return cached
        
        # Fetch fresh data
        df = self.fetch_symbol(symbol, period=period, interval=interval)
        
        # Save to cache if successful
        if df is not None and len(df) > 0:
            self.save_to_csv(symbol, df, interval)
        
        return df
