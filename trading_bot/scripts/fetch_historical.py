#!/usr/bin/env python3
"""
Bulk download historical data for Nifty 50 + indices.
Usage: python scripts/fetch_historical.py [--symbols RELIANCE TCS] [--years 20] [--interval 1d]
"""
import argparse
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tools.historical_data import HistoricalDataManager


def main():
    parser = argparse.ArgumentParser(description="Fetch historical market data")
    parser.add_argument("--symbols", nargs="+", help="NSE symbols (default: full Nifty50)")
    parser.add_argument("--years", type=int, default=20, help="Years of history (default: 20)")
    parser.add_argument("--interval", default="1d", choices=["1d", "1wk", "1mo"], help="Data interval")
    parser.add_argument("--indices", action="store_true", help="Also download index data")
    args = parser.parse_args()
    
    mgr = HistoricalDataManager()
    period = f"{args.years}y"
    symbols = args.symbols or HistoricalDataManager.NIFTY50_SYMBOLS
    
    print(f"Downloading {len(symbols)} symbols × {args.years} years ({args.interval})...")
    
    success, failed = 0, []
    for i, sym in enumerate(symbols):
        try:
            df = mgr.get_symbol_data(sym, period=period, interval=args.interval, use_cache=False)
            if df is not None and len(df) > 0:
                print(f"  ✓ {sym}: {len(df)} rows ({df['timestamp'].min().date()} → {df['timestamp'].max().date()})")
                success += 1
            else:
                print(f"  ✗ {sym}: no data")
                failed.append(sym)
        except Exception as e:
            print(f"  ✗ {sym}: {e}")
            failed.append(sym)
        if i % 5 == 4:  # Rate limit: pause every 5 symbols
            time.sleep(1)
    
    if args.indices:
        print("\nDownloading indices...")
        for name, yf_sym in HistoricalDataManager.INDEX_SYMBOLS.items():
            try:
                df = mgr.fetch_symbol(yf_sym, period=period, interval=args.interval)
                if df is not None and len(df) > 0:
                    path = mgr.save_to_csv(name, df, args.interval)
                    print(f"  ✓ {name} ({yf_sym}): {len(df)} rows → {path}")
                else:
                    print(f"  ✗ {name}: no data")
            except Exception as e:
                print(f"  ✗ {name}: {e}")
    
    print(f"\nDone: {success}/{len(symbols)} succeeded. Failed: {failed or 'none'}")


if __name__ == "__main__":
    main()
