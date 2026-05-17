#!/usr/bin/env python3
"""
CLI backtest runner with rich table output.
Usage: python scripts/run_backtest.py --symbol RELIANCE --years 5
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args()
    
    import pandas as pd
    from tools.historical_data import HistoricalDataManager
    from utils.backtester import Backtester
    
    print(f"\nFetching {args.years} years of {args.symbol} data...")
    mgr = HistoricalDataManager()
    df = mgr.get_symbol_data(args.symbol, period=f"{args.years}y", interval="1d")
    if df is None:
        print(f"ERROR: No data found for {args.symbol}")
        sys.exit(1)
    
    if "timestamp" in df.columns:
        df = df.set_index(pd.to_datetime(df["timestamp"])).drop(columns=["timestamp"], errors="ignore")
    
    print(f"Running backtest on {len(df)} trading days ({df.index[0].date()} → {df.index[-1].date()})...\n")
    
    bt = Backtester()
    result = bt.run_all_strategies(args.symbol, df)
    
    # Print table
    print(f"{'Strategy':<22} {'TF':<5} {'Trades':>7} {'Win%':>6} {'AvgRR':>7} {'Sharpe':>7} {'MaxDD%':>7} {'Total P&L':>10}")
    print("-" * 80)
    for r in sorted(result.strategy_reports, key=lambda x: x.win_rate_pct * x.avg_rr, reverse=True):
        if r.total_trades == 0: continue
        print(f"{r.strategy_name:<22} {r.timeframe:<5} {r.total_trades:>7} {r.win_rate_pct:>5.1f}% {r.avg_rr:>6.2f}x {r.sharpe_ratio:>7.2f} {r.max_drawdown_pct:>6.1f}% {r.total_pnl:>9.1f}%")
    
    print(f"\n{'='*80}")
    print(f"RECOMMENDATION for {result.symbol}:")
    print(f"  Best Strategy : {result.recommended_strategy} ({result.recommended_timeframe})")
    print(f"  Expected Win% : {result.recommended_win_rate:.1f}%")
    print(f"  Expected R:R  : {result.recommended_rr:.2f}:1")
    print(f"\nEntry Plan:")
    for k, v in result.entry_plan.items():
        print(f"  {k:<22}: {v}")

if __name__ == "__main__":
    main()
