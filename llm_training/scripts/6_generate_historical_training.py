"""
Step 6 – Generate historical OHLCV-based training examples.

Fetches historical daily data from yfinance for NSE symbols, computes technical
indicators for each trading day using a rolling window, scores scenarios,
and creates labeled Q&A pairs based on future price movement.

Usage:
    python llm_training/scripts/6_generate_historical_training.py
    python llm_training/scripts/6_generate_historical_training.py --symbols RELIANCE TCS --years 1

Output: llm_training/data/processed/historical_train.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf
from loguru import logger

# Add trading_bot/src to path so we can import utils
ROOT = Path(__file__).parents[2]
TRADING_BOT_SRC = ROOT / "trading_bot" / "src"
sys.path.insert(0, str(TRADING_BOT_SRC))

from utils.technical_analysis import compute_indicators
from utils.scenario_engine import ScenarioEngine

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "WIPRO.NS", "AXISBANK.NS"
]

WINDOW_SIZE = 60        # days of lookback for indicators
MIN_WINDOW_DATA = 30    # minimum valid trading days in window
FUTURE_DAYS = 5         # days ahead to label outcome
BUY_THRESHOLD = 1.5     # % avg return threshold for BUY
SELL_THRESHOLD = -1.5   # % avg return threshold for SELL
MAX_DD_THRESHOLD = 1.0  # % max drawdown threshold

OUTPUT_FILE = ROOT / "llm_training" / "data" / "processed" / "historical_train.jsonl"


# ── Labeling logic ────────────────────────────────────────────────────────────

def compute_future_label(df: pd.DataFrame, idx: int) -> tuple[str, dict]:
    """
    Look ahead FUTURE_DAYS from index idx and label as BUY/SELL/WAIT.
    
    Returns:
        (label, stats) where stats = {"avg_return": float, "max_dd": float}
    """
    if idx + FUTURE_DAYS >= len(df):
        return "WAIT", {"avg_return": 0.0, "max_dd": 0.0}
    
    current_close = df.iloc[idx]["close"]
    future_slice = df.iloc[idx+1 : idx+1+FUTURE_DAYS]
    
    if len(future_slice) < FUTURE_DAYS or current_close <= 0:
        return "WAIT", {"avg_return": 0.0, "max_dd": 0.0}
    
    returns = (future_slice["close"] - current_close) / current_close * 100
    avg_return = returns.mean()
    
    # Max drawdown during the period
    min_price = future_slice["close"].min()
    max_dd = (min_price - current_close) / current_close * 100
    
    # Label logic
    if avg_return > BUY_THRESHOLD and max_dd > -MAX_DD_THRESHOLD:
        label = "BUY"
    elif avg_return < SELL_THRESHOLD and max_dd > -MAX_DD_THRESHOLD:
        label = "SELL"
    else:
        label = "WAIT"
    
    return label, {"avg_return": avg_return, "max_dd": max_dd}


def format_indicator_input(symbol: str, indicators: dict, scenario_name: str, confidence: float) -> str:
    """Format indicator snapshot as input text for training."""
    rsi = indicators.get("rsi", 50)
    ema9 = indicators.get("ema_fast", 0)
    ema21 = indicators.get("ema_slow", 0)
    ema50 = indicators.get("ema_50", 0)
    bb_upper = indicators.get("bb_upper", 0)
    bb_lower = indicators.get("bb_lower", 0)
    macd = indicators.get("macd", 0)
    macd_sig = indicators.get("macd_signal", 0)
    atr = indicators.get("atr", 0)
    volume = indicators.get("volume", 0)
    close = indicators.get("close", 0)
    
    macd_cross = "Bullish" if macd > macd_sig else "Bearish"
    ema_trend = "Bullish" if ema9 > ema21 else "Bearish"
    
    return (
        f"Symbol: {symbol} | Timeframe: 1D | "
        f"Close: ₹{close:.2f} | RSI: {rsi:.1f} | "
        f"EMA9: {ema9:.0f} {'above' if ema9 > ema21 else 'below'} EMA21: {ema21:.0f} | "
        f"EMA50: {ema50:.0f} | "
        f"BB: Upper={bb_upper:.0f}, Lower={bb_lower:.0f} | "
        f"MACD: {macd_cross} crossover | ATR: {atr:.2f} | "
        f"Volume: {volume:,} | "
        f"Dominant Scenario: {scenario_name} ({confidence:.0f}%)"
    )


def build_output_json(
    action: str,
    reason: str,
    confidence: float,
    close: float,
    atr: float
) -> str:
    """Build the output JSON string for training."""
    if action == "BUY":
        sl = close - 1.5 * atr
        tp = close + 3.0 * atr
    elif action == "SELL":
        sl = close + 1.5 * atr
        tp = close - 3.0 * atr
    else:
        sl = close
        tp = close
    
    output_dict = {
        "action": action,
        "reason": reason,
        "confidence": int(confidence),
        "suggested_sl": round(sl, 2),
        "suggested_tp": round(tp, 2),
    }
    return json.dumps(output_dict)


def generate_reason(
    action: str,
    indicators: dict,
    scenario_name: str,
    confidence: float
) -> str:
    """Generate a concise reason string based on indicators and scenario."""
    rsi = indicators.get("rsi", 50)
    ema9 = indicators.get("ema_fast", 0)
    ema21 = indicators.get("ema_slow", 0)
    macd = indicators.get("macd", 0)
    macd_sig = indicators.get("macd_signal", 0)
    close = indicators.get("close", 0)
    bb_upper = indicators.get("bb_upper", 0)
    bb_lower = indicators.get("bb_lower", 0)
    
    parts = []
    
    if action == "BUY":
        if rsi < 40:
            parts.append(f"RSI oversold at {rsi:.0f}")
        if close > 0 and bb_lower > 0 and close < bb_lower * 1.02:
            parts.append("price near lower BB")
        if macd > macd_sig:
            parts.append("MACD bullish crossover")
        if ema9 > ema21:
            parts.append("EMA9 crossed above EMA21")
    elif action == "SELL":
        if rsi > 60:
            parts.append(f"RSI overbought at {rsi:.0f}")
        if close > 0 and bb_upper > 0 and close > bb_upper * 0.98:
            parts.append("price near upper BB")
        if macd < macd_sig:
            parts.append("MACD bearish crossover")
        if ema9 < ema21:
            parts.append("EMA9 crossed below EMA21")
    else:
        parts.append("insufficient directional conviction")
    
    if not parts:
        parts.append("market structure indicates" + (" upside" if action == "BUY" else " downside" if action == "SELL" else " consolidation"))
    
    reason = ", ".join(parts[:3])  # max 3 parts
    reason += f". {scenario_name} scenario at {confidence:.0f}% confidence."
    
    return reason.capitalize()


# ── Main generator ────────────────────────────────────────────────────────────

def generate_historical_examples(
    symbols: list[str],
    years: int,
    output_path: Path
) -> int:
    """
    Generate training examples from historical data.
    
    Returns:
        Number of examples generated.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    engine = ScenarioEngine()
    examples_count = 0
    
    with output_path.open("w", encoding="utf-8") as f:
        for symbol in symbols:
            logger.info(f"Processing {symbol}...")
            
            # Fetch data
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=f"{years}y", interval="1d")
            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
                continue
            
            if df.empty or len(df) < WINDOW_SIZE + FUTURE_DAYS + 10:
                logger.warning(f"{symbol}: insufficient data ({len(df)} rows)")
                continue
            
            # Normalize column names
            df.columns = [c.lower() for c in df.columns]
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            
            # Ensure we have required columns
            required = ["close", "high", "low", "open", "volume"]
            if not all(c in df.columns for c in required):
                logger.warning(f"{symbol}: missing required columns")
                continue
            
            symbol_clean = symbol.replace(".NS", "")
            
            # Iterate through rolling windows
            for i in range(WINDOW_SIZE, len(df) - FUTURE_DAYS):
                window_df = df.iloc[i - WINDOW_SIZE : i].copy()
                
                # Skip if window has insufficient data
                if len(window_df) < MIN_WINDOW_DATA:
                    continue
                
                # Compute indicators
                try:
                    indicators = compute_indicators(window_df)
                except Exception as e:
                    logger.debug(f"{symbol} row {i}: indicator computation failed: {e}")
                    continue
                
                # Skip if ATR is invalid
                atr = indicators.get("atr", 0)
                if atr <= 0 or pd.isna(atr):
                    continue
                
                close = indicators.get("close", 0)
                if close <= 0:
                    continue
                
                # Score scenarios
                try:
                    scenario_result = engine.score_scenarios(indicators)
                except Exception as e:
                    logger.debug(f"{symbol} row {i}: scenario scoring failed: {e}")
                    continue
                
                dominant = scenario_result.dominant
                scenario_name = dominant.name
                scenario_confidence = dominant.probability
                
                # Compute future label
                future_label, stats = compute_future_label(df, i)
                
                # Match confidence: if scenario matches label direction, use scenario confidence
                # Otherwise use a lower confidence (50)
                scenario_bias = scenario_result.trade_bias
                if scenario_bias == future_label:
                    confidence = scenario_confidence
                else:
                    confidence = 50.0
                
                # Build Alpaca format example
                instruction = f"Based on this technical analysis for {symbol_clean}, what trade action should you take and why?"
                input_text = format_indicator_input(symbol_clean, indicators, scenario_name, scenario_confidence)
                reason = generate_reason(future_label, indicators, scenario_name, confidence)
                output_json = build_output_json(future_label, reason, confidence, close, atr)
                
                # Validate output JSON
                try:
                    json.loads(output_json)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON generated for {symbol} row {i}")
                    continue
                
                example = {
                    "instruction": instruction,
                    "input": input_text,
                    "output": output_json,
                }
                
                f.write(json.dumps(example, ensure_ascii=False) + "\n")
                examples_count += 1
                
                if examples_count % 1000 == 0:
                    logger.info(f"Generated {examples_count} examples...")
    
    logger.info(f"Total examples generated: {examples_count}")
    return examples_count


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate historical training data")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help="List of yfinance symbols (e.g. RELIANCE.NS TCS.NS)"
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Years of historical data to fetch"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help="Output JSONL file path"
    )
    
    args = parser.parse_args()
    
    logger.info(f"Generating historical training data for {len(args.symbols)} symbols, {args.years} years")
    logger.info(f"Output: {args.output}")
    
    count = generate_historical_examples(args.symbols, args.years, args.output)
    
    if count > 0:
        logger.success(f"✓ Generated {count} training examples → {args.output}")
    else:
        logger.warning("No examples generated. Check symbol list and data availability.")


if __name__ == "__main__":
    main()
