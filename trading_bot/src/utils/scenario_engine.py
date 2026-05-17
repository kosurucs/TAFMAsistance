"""
scenario_engine.py — Probability-based market scenario scoring.

Five scenarios: BULLISH_BREAKOUT, BEARISH_BREAKDOWN, SIDEWAYS_CONSOLIDATION,
                REVERSAL_UP, REVERSAL_DOWN

Risk Guardian approved constraints:
- SCENARIO_CONFIDENCE_THRESHOLD = 60 is a module constant (never a parameter)
- LLM cannot override a WAIT bias when confidence < threshold
- Enforcement is in risk_validator, not just advisory
"""
from __future__ import annotations
from dataclasses import dataclass, field
from loguru import logger

SCENARIO_CONFIDENCE_THRESHOLD: int = 60  # Non-negotiable — Risk Guardian mandate

# Scenario name constants
BULLISH_BREAKOUT = "BULLISH_BREAKOUT"
BEARISH_BREAKDOWN = "BEARISH_BREAKDOWN"
SIDEWAYS_CONSOLIDATION = "SIDEWAYS_CONSOLIDATION"
REVERSAL_UP = "REVERSAL_UP"
REVERSAL_DOWN = "REVERSAL_DOWN"

# Which scenarios produce which trade actions
SCENARIO_TO_ACTION: dict[str, str] = {
    BULLISH_BREAKOUT: "BUY",
    REVERSAL_UP: "BUY",
    BEARISH_BREAKDOWN: "SELL",
    REVERSAL_DOWN: "SELL",
    SIDEWAYS_CONSOLIDATION: "WAIT",
}


@dataclass
class ScenarioScore:
    name: str
    probability: float   # 0.0 – 100.0
    signals: list[str] = field(default_factory=list)   # human-readable signals that fired


@dataclass
class ScenarioResult:
    scores: list[ScenarioScore]        # all 5, sorted descending
    dominant: ScenarioScore            # highest probability scenario
    confidence: float                  # dominant.probability
    trade_bias: str                    # "BUY" | "SELL" | "WAIT"
    # trade_bias is WAIT if confidence < SCENARIO_CONFIDENCE_THRESHOLD


class ScenarioEngine:
    def score_scenarios(
        self,
        indicators: dict,
        mtf_indicators: dict | None = None,
    ) -> ScenarioResult:
        """
        Score all 5 scenarios using current indicators + optional MTF confluence.
        Returns ScenarioResult with ranked list and dominant scenario.
        """
        scores: dict[str, float] = {
            BULLISH_BREAKOUT: 0.0,
            BEARISH_BREAKDOWN: 0.0,
            SIDEWAYS_CONSOLIDATION: 0.0,
            REVERSAL_UP: 0.0,
            REVERSAL_DOWN: 0.0,
        }
        signals: dict[str, list[str]] = {k: [] for k in scores}

        rsi = indicators.get("rsi", 50.0) or 50.0
        macd = indicators.get("macd", 0.0) or 0.0
        macd_signal = indicators.get("macd_signal", 0.0) or 0.0
        close = indicators.get("close", 0.0) or 0.0
        ema200 = indicators.get("ema_200", close) or close
        ema9 = indicators.get("ema_fast", close) or close
        ema21 = indicators.get("ema_slow", close) or close
        bb_upper = indicators.get("bb_upper", 0.0) or 0.0
        bb_lower = indicators.get("bb_lower", 0.0) or 0.0
        bb_mid = indicators.get("bb_middle", 0.0) or 0.0
        volume = indicators.get("volume", 0.0) or 0.0
        avg_volume = indicators.get("avg_volume_20", volume) or volume

        # RSI signals
        if rsi > 60:
            scores[BULLISH_BREAKOUT] += 20
            signals[BULLISH_BREAKOUT].append(f"RSI={rsi:.0f} (above 60)")
        if rsi < 40:
            scores[REVERSAL_UP] += 20
            signals[REVERSAL_UP].append(f"RSI={rsi:.0f} (below 40)")
        if rsi > 70:
            scores[REVERSAL_DOWN] += 15
            signals[REVERSAL_DOWN].append(f"RSI={rsi:.0f} (overbought >70)")
        if rsi < 30:
            scores[REVERSAL_UP] += 15
            signals[REVERSAL_UP].append(f"RSI={rsi:.0f} (oversold <30)")

        # MACD signals
        if macd > macd_signal:
            scores[BULLISH_BREAKOUT] += 15
            signals[BULLISH_BREAKOUT].append("MACD bullish crossover")
        elif macd < macd_signal:
            scores[BEARISH_BREAKDOWN] += 15
            signals[BEARISH_BREAKDOWN].append("MACD bearish crossover")

        # EMA trend vs EMA200
        if close > 0 and ema200 > 0:
            if close > ema200:
                scores[BULLISH_BREAKOUT] += 10
                signals[BULLISH_BREAKOUT].append("Price above EMA200")
            else:
                scores[BEARISH_BREAKDOWN] += 10
                signals[BEARISH_BREAKDOWN].append("Price below EMA200")

        # EMA fast/slow crossover
        if ema9 > ema21:
            scores[BULLISH_BREAKOUT] += 10
            signals[BULLISH_BREAKOUT].append("EMA9 > EMA21 (bullish cross)")
        elif ema9 < ema21:
            scores[BEARISH_BREAKDOWN] += 10
            signals[BEARISH_BREAKDOWN].append("EMA9 < EMA21 (bearish cross)")

        # Volume confirmation
        if avg_volume > 0 and volume > 1.5 * avg_volume:
            # Apply volume boost to whichever direction has higher score
            if scores[BULLISH_BREAKOUT] >= scores[BEARISH_BREAKDOWN]:
                scores[BULLISH_BREAKOUT] += 20
                signals[BULLISH_BREAKOUT].append(f"Volume spike ({volume/avg_volume:.1f}x avg)")
            else:
                scores[BEARISH_BREAKDOWN] += 20
                signals[BEARISH_BREAKDOWN].append(f"Volume spike ({volume/avg_volume:.1f}x avg)")

        # Bollinger Band squeeze → Sideways
        if bb_upper > 0 and bb_lower > 0 and bb_mid > 0:
            bb_width_pct = (bb_upper - bb_lower) / bb_mid * 100
            if bb_width_pct < 2.0:
                scores[SIDEWAYS_CONSOLIDATION] += 20
                signals[SIDEWAYS_CONSOLIDATION].append(f"BB squeeze ({bb_width_pct:.1f}% width)")

        # MTF confluence
        if mtf_indicators:
            conf = mtf_indicators.get("confluence", {})
            bias = conf.get("bias", "NEUTRAL")
            if bias == "BULLISH":
                scores[BULLISH_BREAKOUT] += 20
                scores[REVERSAL_UP] += 20
                signals[BULLISH_BREAKOUT].append("MTF bias BULLISH")
                signals[REVERSAL_UP].append("MTF bias BULLISH")
            elif bias == "BEARISH":
                scores[BEARISH_BREAKDOWN] += 20
                scores[REVERSAL_DOWN] += 20
                signals[BEARISH_BREAKDOWN].append("MTF bias BEARISH")
                signals[REVERSAL_DOWN].append("MTF bias BEARISH")

        # Normalise: cap each score at 100, then express dominant as %
        total = sum(scores.values())
        if total > 0:
            norm = {k: (v / total) * 100 for k, v in scores.items()}
        else:
            # Flat distribution if no signals fired
            norm = {k: 20.0 for k in scores}

        scenario_list = [
            ScenarioScore(name=k, probability=round(norm[k], 1), signals=signals[k])
            for k in scores
        ]
        scenario_list.sort(key=lambda s: s.probability, reverse=True)
        dominant = scenario_list[0]

        # Gate check: WAIT if confidence below threshold
        if dominant.probability < SCENARIO_CONFIDENCE_THRESHOLD:
            trade_bias = "WAIT"
            logger.info(
                f"Scenario gate: dominant={dominant.name} @ {dominant.probability:.1f}% "
                f"< {SCENARIO_CONFIDENCE_THRESHOLD}% threshold → WAIT"
            )
        else:
            trade_bias = SCENARIO_TO_ACTION.get(dominant.name, "WAIT")
            logger.info(
                f"Scenario gate: dominant={dominant.name} @ {dominant.probability:.1f}% "
                f"→ {trade_bias}"
            )

        return ScenarioResult(
            scores=scenario_list,
            dominant=dominant,
            confidence=dominant.probability,
            trade_bias=trade_bias,
        )
