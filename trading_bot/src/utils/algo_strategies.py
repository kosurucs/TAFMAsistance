"""
algo_strategies.py – Pre-coded algorithmic trading strategies.

Four strategies:
  1. BullishBreakout   – RSI momentum + EMA alignment + MACD + volume scenario
  2. BearishBreakdown  – Mirror of BullishBreakout for short side
  3. MeanReversionBuy  – RSI/stochastic oversold + price near BB lower
  4. MomentumFollower  – Full EMA stack alignment + scenario confidence

Each strategy.evaluate() returns an AlgoSignal or None.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

_IST = ZoneInfo("Asia/Kolkata")

# ─── Signal dataclass ─────────────────────────────────────────────────────────

@dataclass
class AlgoSignal:
    id: str
    symbol: str
    strategy: str
    action: str             # BUY | SELL
    reason: str
    confidence: float       # 0-100
    entry_price: float
    suggested_sl: float
    suggested_tp: float
    rr_ratio: float
    checklist: dict         # {item_name: bool}
    checklist_pass: bool    # True only when ALL items are True
    timestamp: str          # IST ISO string
    indicators: dict = field(default_factory=dict)
    scenario: str = ""
    scenario_confidence: float = 0.0


def _now_ist() -> str:
    return datetime.now(_IST).isoformat()


def _make_signal(
    symbol: str,
    strategy: str,
    action: str,
    reason: str,
    confidence: float,
    indicators: dict,
    scenario: str,
    scenario_confidence: float,
) -> AlgoSignal:
    """Build an AlgoSignal with R:R computed from ATR."""
    from src.utils.rr_calculator import calculate_sl_tp  # avoid circular
    entry = indicators.get("close", 0.0)
    atr   = indicators.get("atr", 0.0)

    try:
        rr = calculate_sl_tp(action, entry, atr)
        sl, tp, rr_ratio = rr.sl, rr.tp, rr.rr_ratio
    except Exception:
        sl, tp, rr_ratio = 0.0, 0.0, 0.0

    return AlgoSignal(
        id=str(uuid.uuid4())[:8],
        symbol=symbol,
        strategy=strategy,
        action=action,
        reason=reason,
        confidence=confidence,
        entry_price=round(entry, 2),
        suggested_sl=round(sl, 2),
        suggested_tp=round(tp, 2),
        rr_ratio=round(rr_ratio, 2),
        checklist={},           # filled by engine
        checklist_pass=False,   # filled by engine
        timestamp=_now_ist(),
        indicators=indicators,
        scenario=scenario,
        scenario_confidence=scenario_confidence,
    )


# ─── Strategy base ────────────────────────────────────────────────────────────

class BaseStrategy:
    name: str = "base"
    description: str = ""
    enabled: bool = True

    def evaluate(
        self,
        symbol: str,
        indicators: dict,
        scenario: str,
        scenario_confidence: float,
    ) -> Optional[AlgoSignal]:
        raise NotImplementedError


# ─── Strategy 1: Bullish Breakout ─────────────────────────────────────────────

class BullishBreakoutStrategy(BaseStrategy):
    name = "BullishBreakout"
    description = (
        "Buys when RSI ∈ [55, 75], price above EMA50, MACD bullish, "
        "and BULLISH_BREAKOUT scenario ≥ 60%."
    )

    def evaluate(self, symbol, indicators, scenario, scenario_confidence):
        if not self.enabled:
            return None

        rsi       = indicators.get("rsi", 0)
        close     = indicators.get("close", 0)
        ema_50    = indicators.get("ema_50", 0)
        macd_lbl  = indicators.get("macd_label", "")
        trend     = indicators.get("trend", "")

        # Conditions
        rsi_ok       = 55 <= rsi <= 75
        price_ok     = close > ema_50 > 0
        macd_ok      = macd_lbl in ("BUY", "BULLISH")
        trend_ok     = trend == "BULLISH"
        scenario_ok  = scenario == "BULLISH_BREAKOUT" and scenario_confidence >= 60

        if not all([rsi_ok, price_ok, macd_ok, trend_ok, scenario_ok]):
            return None

        confidence = min(95, 60 + scenario_confidence * 0.4)
        reason = (
            f"RSI={rsi:.1f} in momentum zone, price above EMA50, "
            f"MACD bullish, BULLISH_BREAKOUT @{scenario_confidence:.0f}%"
        )
        return _make_signal(symbol, self.name, "BUY", reason, confidence,
                            indicators, scenario, scenario_confidence)


# ─── Strategy 2: Bearish Breakdown ───────────────────────────────────────────

class BearishBreakdownStrategy(BaseStrategy):
    name = "BearishBreakdown"
    description = (
        "Sells when RSI ∈ [25, 45], price below EMA50, MACD bearish, "
        "and BEARISH_BREAKDOWN scenario ≥ 60%."
    )

    def evaluate(self, symbol, indicators, scenario, scenario_confidence):
        if not self.enabled:
            return None

        rsi       = indicators.get("rsi", 0)
        close     = indicators.get("close", 0)
        ema_50    = indicators.get("ema_50", 0)
        macd_lbl  = indicators.get("macd_label", "")
        trend     = indicators.get("trend", "")

        rsi_ok       = 25 <= rsi <= 45
        price_ok     = ema_50 > 0 and close < ema_50
        macd_ok      = macd_lbl in ("SELL", "BEARISH")
        trend_ok     = trend == "BEARISH"
        scenario_ok  = scenario == "BEARISH_BREAKDOWN" and scenario_confidence >= 60

        if not all([rsi_ok, price_ok, macd_ok, trend_ok, scenario_ok]):
            return None

        confidence = min(95, 60 + scenario_confidence * 0.4)
        reason = (
            f"RSI={rsi:.1f} in breakdown zone, price below EMA50, "
            f"MACD bearish, BEARISH_BREAKDOWN @{scenario_confidence:.0f}%"
        )
        return _make_signal(symbol, self.name, "SELL", reason, confidence,
                            indicators, scenario, scenario_confidence)


# ─── Strategy 3: Mean Reversion Buy ──────────────────────────────────────────

class MeanReversionBuyStrategy(BaseStrategy):
    name = "MeanReversionBuy"
    description = (
        "Buys when RSI < 30 AND stochastic < 25 AND price near BB lower band "
        "(oversold bounce setup)."
    )

    def evaluate(self, symbol, indicators, scenario, scenario_confidence):
        if not self.enabled:
            return None

        rsi      = indicators.get("rsi", 50)
        stoch_k  = indicators.get("stoch_k", 50)
        close    = indicators.get("close", 0)
        bb_lower = indicators.get("bb_lower", 0)

        rsi_ok    = rsi < 30
        stoch_ok  = stoch_k < 25
        # price within 1.5% above bb_lower
        bb_ok     = bb_lower > 0 and close <= bb_lower * 1.015
        scene_ok  = scenario in ("REVERSAL_UP", "SIDEWAYS_CONSOLIDATION") or scenario_confidence < 60

        if not all([rsi_ok, stoch_ok, bb_ok]):
            return None

        confidence = min(85, 55 + (30 - rsi) * 1.2)
        reason = (
            f"RSI={rsi:.1f} oversold, Stoch={stoch_k:.1f} < 25, "
            f"price near BB lower — mean-reversion bounce entry"
        )
        return _make_signal(symbol, self.name, "BUY", reason, confidence,
                            indicators, scenario, scenario_confidence)


# ─── Strategy 4: Momentum Follower ───────────────────────────────────────────

class MomentumFollowerStrategy(BaseStrategy):
    name = "MomentumFollower"
    description = (
        "Follows full EMA stack alignment (EMA9>EMA21>EMA50 for BUY, reverse for SELL) "
        "with scenario confidence ≥ 65%."
    )

    def evaluate(self, symbol, indicators, scenario, scenario_confidence):
        if not self.enabled:
            return None

        ema9  = indicators.get("ema_fast", 0)
        ema21 = indicators.get("ema_slow", 0)
        ema50 = indicators.get("ema_50",   0)
        rsi   = indicators.get("rsi", 50)

        if not (ema9 > 0 and ema21 > 0 and ema50 > 0):
            return None

        bull_stack = ema9 > ema21 > ema50
        bear_stack = ema9 < ema21 < ema50

        if scenario_confidence < 65:
            return None

        if bull_stack and rsi >= 45 and scenario in ("BULLISH_BREAKOUT", "REVERSAL_UP"):
            confidence = min(90, 60 + scenario_confidence * 0.35)
            reason = (
                f"Full bullish EMA stack (EMA9>{ema21:.0f}>EMA50), "
                f"RSI={rsi:.1f}, {scenario} @{scenario_confidence:.0f}%"
            )
            return _make_signal(symbol, self.name, "BUY", reason, confidence,
                                indicators, scenario, scenario_confidence)

        if bear_stack and rsi <= 55 and scenario in ("BEARISH_BREAKDOWN", "REVERSAL_DOWN"):
            confidence = min(90, 60 + scenario_confidence * 0.35)
            reason = (
                f"Full bearish EMA stack (EMA9<{ema21:.0f}<EMA50), "
                f"RSI={rsi:.1f}, {scenario} @{scenario_confidence:.0f}%"
            )
            return _make_signal(symbol, self.name, "SELL", reason, confidence,
                                indicators, scenario, scenario_confidence)

        return None


# ─── Registry ─────────────────────────────────────────────────────────────────

STRATEGY_REGISTRY: list[BaseStrategy] = [
    BullishBreakoutStrategy(),
    BearishBreakdownStrategy(),
    MeanReversionBuyStrategy(),
    MomentumFollowerStrategy(),
]


def get_strategy(name: str) -> Optional[BaseStrategy]:
    for s in STRATEGY_REGISTRY:
        if s.name == name:
            return s
    return None


def evaluate_all(
    symbol: str,
    indicators: dict,
    scenario: str,
    scenario_confidence: float,
) -> list[AlgoSignal]:
    """Run all enabled strategies and return any signals produced."""
    signals = []
    for strategy in STRATEGY_REGISTRY:
        try:
            sig = strategy.evaluate(symbol, indicators, scenario, scenario_confidence)
            if sig is not None:
                signals.append(sig)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                f"Strategy {strategy.name} raised: {exc}"
            )
    return signals
