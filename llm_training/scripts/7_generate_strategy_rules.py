"""
Step 7 – Generate rule-based strategy Q&A training examples.

Creates synthetic training examples encoding trading strategy knowledge for:
- TREND_FOLLOWING
- MEAN_REVERSION
- MOMENTUM
- PRICE_ACTION

Each strategy has multiple parameter variations and market conditions.

Usage:
    python llm_training/scripts/7_generate_strategy_rules.py
    python llm_training/scripts/7_generate_strategy_rules.py --examples-per-strategy 3000

Output: llm_training/data/processed/strategy_rules.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from loguru import logger

# ── Constants ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parents[2]
OUTPUT_FILE = ROOT / "llm_training" / "data" / "processed" / "strategy_rules.jsonl"

SYMBOLS = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC", "WIPRO", "AXISBANK"]
TIMEFRAMES = ["1D", "1h", "15min"]

RANDOM_SEED = 42


# ── Strategy generators ───────────────────────────────────────────────────────

def generate_trend_following_examples(n: int, rng: random.Random) -> list[dict]:
    """Generate TREND_FOLLOWING strategy examples (EMA crossovers, momentum)."""
    examples = []
    
    for _ in range(n):
        symbol = rng.choice(SYMBOLS)
        tf = rng.choice(TIMEFRAMES)
        close = rng.randint(1000, 3000)
        
        # Bullish trend scenarios
        if rng.random() < 0.5:
            rsi = rng.randint(55, 75)
            ema9 = close + rng.randint(5, 30)
            ema21 = close - rng.randint(10, 50)
            volume_mult = round(rng.uniform(1.5, 3.0), 1)
            atr = rng.randint(20, 60)
            
            mtf_bullish = rng.randint(2, 3)
            conf = rng.randint(65, 85)
            
            scenario = rng.choice(["BULLISH_BREAKOUT", "MOMENTUM_BULLISH"])
            
            input_text = (
                f"Symbol: {symbol} | Timeframe: {tf} | "
                f"RSI: {rsi} | EMA9: {ema9} above EMA21: {ema21} | "
                f"MACD: Bullish crossover | BB: Price near middle band | "
                f"ATR: {atr} | Volume: {volume_mult}x average | "
                f"MTF Bias: BULLISH ({mtf_bullish}/3 timeframes) | "
                f"Dominant Scenario: {scenario} ({conf}%)"
            )
            
            sl = close - 1.5 * atr
            tp = close + 3.0 * atr
            
            reason = (
                f"Strong bullish momentum with RSI at {rsi} and EMA9 crossing above EMA21. "
                f"Volume spike at {volume_mult}x confirms breakout. "
                f"{scenario} scenario at {conf}% confidence. Trend-following setup."
            )
            
            output = {
                "action": "BUY",
                "reason": reason,
                "confidence": conf,
                "suggested_sl": round(sl, 2),
                "suggested_tp": round(tp, 2),
            }
        else:
            # Bearish trend scenarios
            rsi = rng.randint(25, 45)
            ema9 = close - rng.randint(5, 30)
            ema21 = close + rng.randint(10, 50)
            volume_mult = round(rng.uniform(1.5, 3.0), 1)
            atr = rng.randint(20, 60)
            
            mtf_bearish = rng.randint(2, 3)
            conf = rng.randint(65, 85)
            
            scenario = rng.choice(["BEARISH_BREAKDOWN", "MOMENTUM_BEARISH"])
            
            input_text = (
                f"Symbol: {symbol} | Timeframe: {tf} | "
                f"RSI: {rsi} | EMA9: {ema9} below EMA21: {ema21} | "
                f"MACD: Bearish crossover | BB: Price near middle band | "
                f"ATR: {atr} | Volume: {volume_mult}x average | "
                f"MTF Bias: BEARISH ({mtf_bearish}/3 timeframes) | "
                f"Dominant Scenario: {scenario} ({conf}%)"
            )
            
            sl = close + 1.5 * atr
            tp = close - 3.0 * atr
            
            reason = (
                f"Strong bearish momentum with RSI at {rsi} and EMA9 crossing below EMA21. "
                f"Volume spike at {volume_mult}x confirms breakdown. "
                f"{scenario} scenario at {conf}% confidence. Trend-following setup."
            )
            
            output = {
                "action": "SELL",
                "reason": reason,
                "confidence": conf,
                "suggested_sl": round(sl, 2),
                "suggested_tp": round(tp, 2),
            }
        
        examples.append({
            "instruction": "What trading action do you recommend and why?",
            "input": input_text,
            "output": json.dumps(output),
        })
    
    return examples


def generate_mean_reversion_examples(n: int, rng: random.Random) -> list[dict]:
    """Generate MEAN_REVERSION strategy examples (RSI extremes, BB bounces)."""
    examples = []
    
    for _ in range(n):
        symbol = rng.choice(SYMBOLS)
        tf = rng.choice(TIMEFRAMES)
        close = rng.randint(1000, 3000)
        
        # Oversold reversal scenarios
        if rng.random() < 0.5:
            rsi = rng.randint(20, 35)
            atr = rng.randint(20, 60)
            bb_lower = close - rng.randint(30, 80)
            bb_upper = close + rng.randint(100, 200)
            ema9 = close - rng.randint(10, 40)
            ema21 = close + rng.randint(5, 30)
            
            mtf_bullish = rng.randint(2, 3)
            conf = rng.randint(65, 80)
            
            input_text = (
                f"Symbol: {symbol} | Timeframe: {tf} | "
                f"RSI: {rsi:.1f} | EMA9: {ema9} below EMA21: {ema21} | "
                f"MACD: Bearish crossover | BB: Price at lower band (Lower={bb_lower}, Upper={bb_upper}) | "
                f"ATR: {atr} | Volume: 1.8x average | "
                f"MTF Bias: BULLISH ({mtf_bullish}/3 timeframes) | "
                f"Dominant Scenario: REVERSAL_UP ({conf}%)"
            )
            
            sl = close - 1.5 * atr
            tp = close + 3.0 * atr
            
            reason = (
                f"RSI deeply oversold at {rsi:.1f} with price at lower Bollinger Band. "
                f"MTF bias confirms bullish across {mtf_bullish}/3 timeframes. "
                f"REVERSAL_UP scenario at {conf}% > 60% confidence threshold. Mean reversion setup."
            )
            
            output = {
                "action": "BUY",
                "reason": reason,
                "confidence": conf,
                "suggested_sl": round(sl, 2),
                "suggested_tp": round(tp, 2),
            }
        else:
            # Overbought reversal scenarios
            rsi = rng.randint(70, 85)
            atr = rng.randint(20, 60)
            bb_lower = close - rng.randint(100, 200)
            bb_upper = close + rng.randint(30, 80)
            ema9 = close + rng.randint(10, 40)
            ema21 = close - rng.randint(5, 30)
            
            mtf_bearish = rng.randint(2, 3)
            conf = rng.randint(65, 80)
            
            input_text = (
                f"Symbol: {symbol} | Timeframe: {tf} | "
                f"RSI: {rsi:.1f} | EMA9: {ema9} above EMA21: {ema21} | "
                f"MACD: Bullish crossover | BB: Price at upper band (Lower={bb_lower}, Upper={bb_upper}) | "
                f"ATR: {atr} | Volume: 1.8x average | "
                f"MTF Bias: BEARISH ({mtf_bearish}/3 timeframes) | "
                f"Dominant Scenario: REVERSAL_DOWN ({conf}%)"
            )
            
            sl = close + 1.5 * atr
            tp = close - 3.0 * atr
            
            reason = (
                f"RSI overbought at {rsi:.1f} with price at upper Bollinger Band. "
                f"MTF bias confirms bearish across {mtf_bearish}/3 timeframes. "
                f"REVERSAL_DOWN scenario at {conf}% > 60% confidence threshold. Mean reversion setup."
            )
            
            output = {
                "action": "SELL",
                "reason": reason,
                "confidence": conf,
                "suggested_sl": round(sl, 2),
                "suggested_tp": round(tp, 2),
            }
        
        examples.append({
            "instruction": "What trading action do you recommend and why?",
            "input": input_text,
            "output": json.dumps(output),
        })
    
    return examples


def generate_momentum_examples(n: int, rng: random.Random) -> list[dict]:
    """Generate MOMENTUM strategy examples (strong trending, breakouts)."""
    examples = []
    
    for _ in range(n):
        symbol = rng.choice(SYMBOLS)
        tf = rng.choice(TIMEFRAMES)
        close = rng.randint(1000, 3000)
        
        # Strong bullish momentum
        if rng.random() < 0.5:
            rsi = rng.randint(60, 75)
            atr = rng.randint(30, 70)
            ema9 = close + rng.randint(20, 60)
            ema21 = close - rng.randint(30, 80)
            ema50 = close - rng.randint(50, 120)
            volume_mult = round(rng.uniform(2.0, 4.0), 1)
            
            conf = rng.randint(70, 90)
            
            input_text = (
                f"Symbol: {symbol} | Timeframe: {tf} | "
                f"RSI: {rsi} | EMA9: {ema9} above EMA21: {ema21} above EMA50: {ema50} | "
                f"MACD: Strong bullish divergence | BB: Price breaking upper band | "
                f"ATR: {atr} | Volume: {volume_mult}x average (breakout volume) | "
                f"MTF Bias: BULLISH (3/3 timeframes) | "
                f"Dominant Scenario: BULLISH_BREAKOUT ({conf}%)"
            )
            
            sl = close - 1.5 * atr
            tp = close + 3.0 * atr
            
            reason = (
                f"Strong breakout momentum with all EMAs aligned bullish (EMA9 > EMA21 > EMA50). "
                f"Explosive volume at {volume_mult}x confirms genuine breakout. "
                f"RSI at {rsi} shows strength without overbought extremes. "
                f"BULLISH_BREAKOUT at {conf}% confidence."
            )
            
            output = {
                "action": "BUY",
                "reason": reason,
                "confidence": conf,
                "suggested_sl": round(sl, 2),
                "suggested_tp": round(tp, 2),
            }
        else:
            # Strong bearish momentum
            rsi = rng.randint(25, 40)
            atr = rng.randint(30, 70)
            ema9 = close - rng.randint(20, 60)
            ema21 = close + rng.randint(30, 80)
            ema50 = close + rng.randint(50, 120)
            volume_mult = round(rng.uniform(2.0, 4.0), 1)
            
            conf = rng.randint(70, 90)
            
            input_text = (
                f"Symbol: {symbol} | Timeframe: {tf} | "
                f"RSI: {rsi} | EMA9: {ema9} below EMA21: {ema21} below EMA50: {ema50} | "
                f"MACD: Strong bearish divergence | BB: Price breaking lower band | "
                f"ATR: {atr} | Volume: {volume_mult}x average (breakdown volume) | "
                f"MTF Bias: BEARISH (3/3 timeframes) | "
                f"Dominant Scenario: BEARISH_BREAKDOWN ({conf}%)"
            )
            
            sl = close + 1.5 * atr
            tp = close - 3.0 * atr
            
            reason = (
                f"Strong breakdown momentum with all EMAs aligned bearish (EMA9 < EMA21 < EMA50). "
                f"Explosive volume at {volume_mult}x confirms genuine breakdown. "
                f"RSI at {rsi} shows weakness without oversold bounce yet. "
                f"BEARISH_BREAKDOWN at {conf}% confidence."
            )
            
            output = {
                "action": "SELL",
                "reason": reason,
                "confidence": conf,
                "suggested_sl": round(sl, 2),
                "suggested_tp": round(tp, 2),
            }
        
        examples.append({
            "instruction": "What trading action do you recommend and why?",
            "input": input_text,
            "output": json.dumps(output),
        })
    
    return examples


def generate_price_action_examples(n: int, rng: random.Random) -> list[dict]:
    """Generate PRICE_ACTION strategy examples (patterns, S/R levels)."""
    examples = []
    
    patterns_bullish = [
        "bullish engulfing", "morning star", "hammer", "piercing pattern",
        "three white soldiers", "rising window"
    ]
    patterns_bearish = [
        "bearish engulfing", "evening star", "shooting star", "dark cloud cover",
        "three black crows", "falling window"
    ]
    
    for _ in range(n):
        symbol = rng.choice(SYMBOLS)
        tf = rng.choice(TIMEFRAMES)
        close = rng.randint(1000, 3000)
        
        # Bullish price action
        if rng.random() < 0.5:
            pattern = rng.choice(patterns_bullish)
            rsi = rng.randint(40, 60)
            atr = rng.randint(25, 55)
            support = close - rng.randint(50, 100)
            resistance = close + rng.randint(80, 150)
            ema9 = close + rng.randint(-10, 20)
            ema21 = close - rng.randint(5, 30)
            
            conf = rng.randint(62, 78)
            
            input_text = (
                f"Symbol: {symbol} | Timeframe: {tf} | "
                f"Candle Pattern: {pattern.title()} at support ₹{support} | "
                f"Close: ₹{close} | Resistance: ₹{resistance} | "
                f"RSI: {rsi} | EMA9: {ema9} crossing EMA21: {ema21} | "
                f"MACD: Early bullish signal | ATR: {atr} | "
                f"Volume: Above average | "
                f"Dominant Scenario: REVERSAL_UP ({conf}%)"
            )
            
            sl = close - 1.5 * atr
            tp = close + 3.0 * atr
            
            reason = (
                f"{pattern.capitalize()} candle pattern formed at key support level ₹{support}. "
                f"Price action suggests rejection of lower prices with EMA9 crossing above EMA21. "
                f"REVERSAL_UP scenario at {conf}% confidence. Price action reversal setup."
            )
            
            output = {
                "action": "BUY",
                "reason": reason,
                "confidence": conf,
                "suggested_sl": round(sl, 2),
                "suggested_tp": round(tp, 2),
            }
        else:
            # Bearish price action
            pattern = rng.choice(patterns_bearish)
            rsi = rng.randint(40, 60)
            atr = rng.randint(25, 55)
            support = close - rng.randint(80, 150)
            resistance = close + rng.randint(50, 100)
            ema9 = close - rng.randint(-10, 20)
            ema21 = close + rng.randint(5, 30)
            
            conf = rng.randint(62, 78)
            
            input_text = (
                f"Symbol: {symbol} | Timeframe: {tf} | "
                f"Candle Pattern: {pattern.title()} at resistance ₹{resistance} | "
                f"Close: ₹{close} | Support: ₹{support} | "
                f"RSI: {rsi} | EMA9: {ema9} crossing EMA21: {ema21} | "
                f"MACD: Early bearish signal | ATR: {atr} | "
                f"Volume: Above average | "
                f"Dominant Scenario: REVERSAL_DOWN ({conf}%)"
            )
            
            sl = close + 1.5 * atr
            tp = close - 3.0 * atr
            
            reason = (
                f"{pattern.capitalize()} candle pattern formed at key resistance level ₹{resistance}. "
                f"Price action suggests rejection of higher prices with EMA9 crossing below EMA21. "
                f"REVERSAL_DOWN scenario at {conf}% confidence. Price action reversal setup."
            )
            
            output = {
                "action": "SELL",
                "reason": reason,
                "confidence": conf,
                "suggested_sl": round(sl, 2),
                "suggested_tp": round(tp, 2),
            }
        
        examples.append({
            "instruction": "What trading action do you recommend and why?",
            "input": input_text,
            "output": json.dumps(output),
        })
    
    # Add NEGATIVE examples (good setup but context wrong → WAIT)
    negative_count = n // 10
    for _ in range(negative_count):
        symbol = rng.choice(SYMBOLS)
        tf = rng.choice(TIMEFRAMES)
        close = rng.randint(1000, 3000)
        pattern = rng.choice(patterns_bullish + patterns_bearish)
        rsi = rng.randint(45, 55)
        atr = rng.randint(25, 55)
        ema9 = close + rng.randint(-5, 5)
        ema21 = close + rng.randint(-5, 5)
        
        # Low confidence
        conf = rng.randint(45, 58)
        
        input_text = (
            f"Symbol: {symbol} | Timeframe: {tf} | "
            f"Candle Pattern: {pattern.title()} | "
            f"Close: ₹{close} | RSI: {rsi} | EMA9: {ema9} near EMA21: {ema21} | "
            f"MACD: Neutral | ATR: {atr} | Volume: Average | "
            f"Dominant Scenario: SIDEWAYS_CONSOLIDATION ({conf}%)"
        )
        
        reason = (
            f"Pattern signal present but insufficient directional conviction. "
            f"SIDEWAYS_CONSOLIDATION at {conf}% < 60% confidence threshold. "
            f"EMAs flat, volume average. Await clearer setup."
        )
        
        output = {
            "action": "WAIT",
            "reason": reason,
            "confidence": conf,
            "suggested_sl": round(close, 2),
            "suggested_tp": round(close, 2),
        }
        
        examples.append({
            "instruction": "What trading action do you recommend and why?",
            "input": input_text,
            "output": json.dumps(output),
        })
    
    return examples


# ── Main generator ────────────────────────────────────────────────────────────

def generate_strategy_examples(examples_per_strategy: int, output_path: Path) -> int:
    """Generate all strategy examples and write to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(RANDOM_SEED)
    
    logger.info("Generating TREND_FOLLOWING examples...")
    trend_examples = generate_trend_following_examples(examples_per_strategy, rng)
    
    logger.info("Generating MEAN_REVERSION examples...")
    reversion_examples = generate_mean_reversion_examples(examples_per_strategy, rng)
    
    logger.info("Generating MOMENTUM examples...")
    momentum_examples = generate_momentum_examples(examples_per_strategy, rng)
    
    logger.info("Generating PRICE_ACTION examples...")
    price_action_examples = generate_price_action_examples(examples_per_strategy, rng)
    
    all_examples = trend_examples + reversion_examples + momentum_examples + price_action_examples
    rng.shuffle(all_examples)
    
    # Validate all JSON outputs
    valid_examples = []
    for ex in all_examples:
        try:
            json.loads(ex["output"])
            valid_examples.append(ex)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON output, skipping: {ex['output'][:100]}")
    
    with output_path.open("w", encoding="utf-8") as f:
        for ex in valid_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    
    logger.info(f"Total examples generated: {len(valid_examples)}")
    return len(valid_examples)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate strategy rule training data")
    parser.add_argument(
        "--examples-per-strategy",
        type=int,
        default=2500,
        help="Number of examples per strategy family"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help="Output JSONL file path"
    )
    
    args = parser.parse_args()
    
    logger.info(f"Generating {args.examples_per_strategy} examples per strategy")
    logger.info(f"Output: {args.output}")
    
    count = generate_strategy_examples(args.examples_per_strategy, args.output)
    
    if count > 0:
        logger.success(f"✓ Generated {count} strategy rule examples → {args.output}")
    else:
        logger.error("Failed to generate examples")


if __name__ == "__main__":
    main()
