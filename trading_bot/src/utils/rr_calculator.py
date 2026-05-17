"""
rr_calculator.py — Dynamic Risk:Reward calculator.

Risk Guardian approved. Mandatory constraints:
- MIN_RR_RATIO is a module constant (2.0) — not overridable at call site.
- SL = 1.5 × ATR from entry. TP = 3.0 × ATR from entry.
- R:R ratio must be ≥ 2.0 or the trade is WAIT.
"""
from __future__ import annotations
from dataclasses import dataclass
from loguru import logger

MIN_RR_RATIO: float = 2.0        # Non-negotiable: min reward/risk
ATR_SL_MULTIPLIER: float = 1.5   # SL = entry ± 1.5 × ATR
ATR_TP_MULTIPLIER: float = 3.0   # TP = entry ± 3.0 × ATR  (gives 1:2 R:R)
MAX_SL_PCT: float = 0.03         # SL must not exceed 3% loss from entry


@dataclass
class RRResult:
    sl: float
    tp: float
    risk: float          # absolute distance from entry to SL
    reward: float        # absolute distance from entry to TP
    rr_ratio: float      # reward / risk
    acceptable: bool     # True if rr_ratio >= MIN_RR_RATIO and SL within MAX_SL_PCT


def calculate_sl_tp(action: str, entry_price: float, atr: float) -> RRResult:
    """
    Calculate SL and TP based on ATR.
    action: "BUY" or "SELL"
    entry_price: price at which the trade will be entered
    atr: Average True Range (14-period)
    """
    if atr <= 0:
        logger.warning(f"Invalid ATR={atr}, using 0.5% of entry as fallback")
        atr = entry_price * 0.005

    if action == "BUY":
        sl = entry_price - ATR_SL_MULTIPLIER * atr
        tp = entry_price + ATR_TP_MULTIPLIER * atr
    elif action == "SELL":
        sl = entry_price + ATR_SL_MULTIPLIER * atr
        tp = entry_price - ATR_TP_MULTIPLIER * atr
    else:
        raise ValueError(f"action must be BUY or SELL, got: {action!r}")

    risk = abs(entry_price - sl)
    reward = abs(tp - entry_price)
    rr_ratio = reward / risk if risk > 0 else 0.0

    # Check SL is within 3% of entry
    sl_pct = risk / entry_price
    acceptable = (rr_ratio >= MIN_RR_RATIO) and (sl_pct <= MAX_SL_PCT)

    if not acceptable:
        if rr_ratio < MIN_RR_RATIO:
            logger.warning(f"R:R {rr_ratio:.2f} below minimum {MIN_RR_RATIO} — trade will be WAIT")
        if sl_pct > MAX_SL_PCT:
            logger.warning(f"SL {sl_pct:.2%} exceeds MAX_SL_PCT {MAX_SL_PCT:.0%} — trade will be WAIT")

    return RRResult(
        sl=round(sl, 2),
        tp=round(tp, 2),
        risk=round(risk, 2),
        reward=round(reward, 2),
        rr_ratio=round(rr_ratio, 3),
        acceptable=acceptable,
    )
