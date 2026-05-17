"""
exit_monitor.py — Continuous position monitoring and exit logic.

Monitors open positions for:
1. Price hitting SL or TP
2. Volume deterioration (illiquidity risk)
3. Market-correlated risk (Nifty drop + high beta)
4. Trailing stop activation (lock in 1:1 after price moves favorably)
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from loguru import logger


@dataclass
class ExitSignal:
    should_exit: bool
    reason: str
    urgency: str            # "IMMEDIATE" | "MONITOR" | "NONE"
    adjusted_sl: float | None = None   # New SL if trailing stop triggered


class ExitMonitor:
    """
    Monitors a single open position and returns exit recommendations.
    
    Rules:
    1. IMMEDIATE exit if current_price <= sl (stop-loss hit)
    2. IMMEDIATE exit if current_price >= tp (take-profit hit)
    3. IMMEDIATE exit if volume < 0.5 * avg_volume (illiquidity — can't exit cleanly)
    4. IMMEDIATE exit if nifty_change_pct < -1.5 AND beta > 1.2 (market crash risk)
    5. TRAILING STOP: if price > entry + 2*atr → raise SL to entry + atr (lock in 1:1)
    6. MONITOR (not exit) if RSI overbought > 75 on a BUY position (weakening momentum)
    """
    
    def should_exit(
        self,
        action: str,              # "BUY" or "SELL" (original trade direction)
        entry_price: float,
        current_price: float,
        sl: float,
        tp: float,
        atr: float,
        volume: float = 0,
        avg_volume: float = 0,
        nifty_change_pct: float = 0,
        beta: float = 1.0,
        rsi: float = 50,
    ) -> ExitSignal:
        """
        Evaluate exit conditions for an open position.
        Returns ExitSignal with exit recommendation.
        """
        # 1. SL hit
        if action == "BUY" and current_price <= sl:
            return ExitSignal(True, f"Stop-loss hit: {current_price:.2f} ≤ SL {sl:.2f}", "IMMEDIATE")
        if action == "SELL" and current_price >= sl:
            return ExitSignal(True, f"Stop-loss hit: {current_price:.2f} ≥ SL {sl:.2f}", "IMMEDIATE")
        
        # 2. TP hit
        if action == "BUY" and current_price >= tp:
            return ExitSignal(True, f"Take-profit hit: {current_price:.2f} ≥ TP {tp:.2f}", "IMMEDIATE")
        if action == "SELL" and current_price <= tp:
            return ExitSignal(True, f"Take-profit hit: {current_price:.2f} ≤ TP {tp:.2f}", "IMMEDIATE")
        
        # 3. Illiquidity risk
        if avg_volume > 0 and volume < 0.5 * avg_volume:
            return ExitSignal(True, f"Volume crisis: {volume:.0f} < 50% of avg {avg_volume:.0f}", "IMMEDIATE")
        
        # 4. Market crash risk
        if nifty_change_pct < -1.5 and beta > 1.2:
            return ExitSignal(
                True,
                f"Market crash risk: Nifty {nifty_change_pct:.1f}% with beta {beta:.1f}",
                "IMMEDIATE"
            )
        
        # 5. Trailing stop (lock in 1:1 when 2:1 target halfway achieved)
        if atr > 0:
            if action == "BUY":
                trail_trigger = entry_price + 2 * atr
                new_sl = entry_price + atr  # lock in 1:1 profit
                if current_price > trail_trigger and new_sl > sl:
                    logger.info(f"Trailing stop activated: raising SL from {sl:.2f} to {new_sl:.2f}")
                    return ExitSignal(False, f"Trailing stop: SL raised to {new_sl:.2f}", "MONITOR", adjusted_sl=new_sl)
            elif action == "SELL":
                trail_trigger = entry_price - 2 * atr
                new_sl = entry_price - atr
                if current_price < trail_trigger and new_sl < sl:
                    logger.info(f"Trailing stop activated: lowering SL from {sl:.2f} to {new_sl:.2f}")
                    return ExitSignal(False, f"Trailing stop: SL lowered to {new_sl:.2f}", "MONITOR", adjusted_sl=new_sl)
        
        # 6. Weakening momentum (advisory only)
        if action == "BUY" and rsi > 75:
            return ExitSignal(False, f"RSI overbought at {rsi:.0f} — consider partial exit", "MONITOR")
        if action == "SELL" and rsi < 25:
            return ExitSignal(False, f"RSI oversold at {rsi:.0f} — consider covering short", "MONITOR")
        
        return ExitSignal(False, "Position within normal parameters", "NONE")
    
    def check_all_positions(
        self,
        positions: list[dict],
        indicators_by_symbol: dict[str, dict],
        nifty_change_pct: float = 0.0,
    ) -> list[dict]:
        """
        Check multiple positions at once.
        Returns list of dicts: {symbol, action, exit_signal, original_position}
        """
        results = []
        for pos in positions:
            symbol = pos.get("symbol", "")
            indicators = indicators_by_symbol.get(symbol, {})
            
            signal = self.should_exit(
                action=pos.get("action", "BUY"),
                entry_price=float(pos.get("entry_price", 0)),
                current_price=float(pos.get("current_price", 0)),
                sl=float(pos.get("sl", 0)),
                tp=float(pos.get("tp", 0)),
                atr=float(indicators.get("atr", 0)),
                volume=float(indicators.get("volume", 0)),
                avg_volume=float(indicators.get("avg_volume_20", 0)),
                nifty_change_pct=nifty_change_pct,
                beta=float(pos.get("beta", 1.0)),
                rsi=float(indicators.get("rsi", 50)),
            )
            
            if signal.should_exit or signal.urgency != "NONE":
                logger.info(f"Exit signal for {symbol}: [{signal.urgency}] {signal.reason}")
            
            results.append({
                "symbol": symbol,
                "action": pos.get("action"),
                "exit_signal": signal,
                "position": pos,
            })
        
        return results
