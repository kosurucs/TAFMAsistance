"""
backtester.py — Multi-strategy backtester for NSE equities.

Strategy families: TREND_FOLLOWING, MEAN_REVERSION, MOMENTUM, PRICE_ACTION

For each strategy × timeframe combination, runs the full 20-year history and
returns a StrategyReport with win rates, R:R, WHY-it-works attribution, and
best/worst periods.
"""
from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.technical_analysis import compute_indicators
from utils.rr_calculator import calculate_sl_tp, MIN_RR_RATIO


STRATEGY_FAMILIES = ["TREND_FOLLOWING", "MEAN_REVERSION", "MOMENTUM", "PRICE_ACTION"]
TIMEFRAMES = ["1D", "1W", "1M"]   # Daily, Weekly, Monthly granularity for analysis


@dataclass
class TradeRecord:
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    action: str           # "BUY" or "SELL"
    sl: float
    tp: float
    pnl: float
    rr_achieved: float    # actual R:R realized
    exit_reason: str      # "TP_HIT" | "SL_HIT" | "END_OF_DATA" | "MAX_HOLD"
    signals_fired: dict   # {"rsi_oversold": True, "ema_cross": True, ...}


@dataclass
class StrategyReport:
    strategy_name: str
    timeframe: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    avg_rr: float
    best_rr: float
    worst_rr: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_pnl: float
    profitable_months: list[str] = field(default_factory=list)
    loss_months: list[str] = field(default_factory=list)
    why_it_works: dict = field(default_factory=dict)  # {"volume_driven": 35, "ema_confluence": 42, "rsi_divergence": 23}
    best_period: str = ""
    worst_period: str = ""
    trade_records: list[TradeRecord] = field(default_factory=list)
    
    @property
    def expectancy(self) -> float:
        """Expected R:R per trade = win_rate * avg_win_rr - loss_rate * 1.0"""
        win_rate = self.win_rate_pct / 100
        return win_rate * self.avg_rr - (1 - win_rate)


@dataclass
class BacktestResult:
    symbol: str
    years_analysed: int
    strategy_reports: list[StrategyReport]
    recommended_strategy: str
    recommended_timeframe: str
    recommended_rr: float
    recommended_win_rate: float
    entry_plan: dict   # {"entry_zone": str, "sl_zone": str, "tp_zone": str, "best_rr": float}


class Backtester:
    """Multi-strategy backtester."""
    
    MAX_HOLD_DAYS = 20     # Maximum holding period before force-exit
    INITIAL_CAPITAL = 100_000.0
    
    def run_all_strategies(
        self,
        symbol: str,
        df: pd.DataFrame,
        initial_capital: float = INITIAL_CAPITAL,
    ) -> BacktestResult:
        """
        Run all 4 strategy families on the provided OHLCV dataframe.
        Returns BacktestResult with all StrategyReport objects.
        """
        reports = []
        
        for strategy in STRATEGY_FAMILIES:
            for timeframe in TIMEFRAMES:
                logger.info(f"Backtesting {strategy} on {symbol} ({timeframe})...")
                try:
                    # Resample df to timeframe
                    df_tf = self._resample(df, timeframe)
                    if len(df_tf) < 60:
                        continue  # Not enough data
                    
                    trades = self._run_strategy(strategy, df_tf, symbol)
                    if trades:
                        report = self._compute_report(strategy, timeframe, trades, df_tf)
                        reports.append(report)
                except Exception as e:
                    logger.warning(f"Strategy {strategy} {timeframe} failed: {e}")
        
        if not reports:
            # Return empty result if no reports generated
            return BacktestResult(
                symbol=symbol, years_analysed=0, strategy_reports=[],
                recommended_strategy="N/A", recommended_timeframe="N/A",
                recommended_rr=0.0, recommended_win_rate=0.0, entry_plan={}
            )
        
        best = self._get_best_strategy(reports)
        
        return BacktestResult(
            symbol=symbol,
            years_analysed=int((df.index[-1] - df.index[0]).days / 365),
            strategy_reports=reports,
            recommended_strategy=best.strategy_name,
            recommended_timeframe=best.timeframe,
            recommended_rr=best.avg_rr,
            recommended_win_rate=best.win_rate_pct,
            entry_plan=self._generate_entry_plan(symbol, df, best),
        )
    
    def _resample(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Resample daily OHLCV to weekly or monthly."""
        if timeframe == "1D":
            return df.copy()
        
        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.get("timestamp", df.index))
        
        freq_map = {"1W": "W-FRI", "1M": "ME"}
        freq = freq_map.get(timeframe, "D")
        
        resampled = df.resample(freq).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()
        return resampled
    
    def _run_strategy(
        self, strategy: str, df: pd.DataFrame, symbol: str
    ) -> list[TradeRecord]:
        """Run a single strategy and return list of trade records."""
        method_map = {
            "TREND_FOLLOWING": self._strategy_trend_following,
            "MEAN_REVERSION": self._strategy_mean_reversion,
            "MOMENTUM": self._strategy_momentum,
            "PRICE_ACTION": self._strategy_price_action,
        }
        return method_map[strategy](df, symbol)
    
    def _compute_indicators_for_row(self, df: pd.DataFrame, i: int, window: int = 60) -> dict:
        """Compute indicators on a rolling window ending at row i."""
        start = max(0, i - window)
        window_df = df.iloc[start:i+1].copy()
        if len(window_df) < 20:
            return {}
        try:
            return compute_indicators(window_df)
        except Exception:
            return {}
    
    def _strategy_trend_following(self, df: pd.DataFrame, symbol: str) -> list[TradeRecord]:
        """
        Trend following: Enter BUY when EMA9 crosses above EMA21 AND volume > 1.2x avg.
        Enter SELL when EMA9 crosses below EMA21 AND volume > 1.2x avg.
        Exit: TP (3×ATR) or SL (1.5×ATR) or max hold.
        """
        trades = []
        in_trade = False
        entry_i = 0
        entry_price = 0.0
        action = ""
        sl = tp = 0.0
        signals_fired = {}
        
        # Precompute EMA using pandas (faster than rolling compute_indicators)
        closes = df["close"].values
        ema9 = pd.Series(closes).ewm(span=9, adjust=False).mean().values
        ema21 = pd.Series(closes).ewm(span=21, adjust=False).mean().values
        volumes = df["volume"].values
        
        for i in range(40, len(df)):
            row = df.iloc[i]
            close = float(row["close"])
            vol = float(volumes[i])
            avg_vol = float(np.mean(volumes[max(0,i-20):i])) if i > 20 else vol
            
            if not in_trade:
                # Entry: EMA9 crosses above EMA21 with volume
                if ema9[i] > ema21[i] and ema9[i-1] <= ema21[i-1] and vol > 1.2 * avg_vol:
                    ind = self._compute_indicators_for_row(df, i)
                    atr = ind.get("atr", close * 0.015)
                    try:
                        rr_result = calculate_sl_tp("BUY", close, atr)
                        if rr_result.acceptable:
                            in_trade = True
                            entry_i = i
                            entry_price = close
                            action = "BUY"
                            sl, tp = rr_result.sl, rr_result.tp
                            signals_fired = {"ema_cross_bullish": True, "volume_confirmation": vol > 1.2 * avg_vol}
                    except Exception:
                        pass
                
                # Entry: EMA9 crosses below EMA21 with volume
                elif ema9[i] < ema21[i] and ema9[i-1] >= ema21[i-1] and vol > 1.2 * avg_vol:
                    ind = self._compute_indicators_for_row(df, i)
                    atr = ind.get("atr", close * 0.015)
                    try:
                        rr_result = calculate_sl_tp("SELL", close, atr)
                        if rr_result.acceptable:
                            in_trade = True
                            entry_i = i
                            entry_price = close
                            action = "SELL"
                            sl, tp = rr_result.sl, rr_result.tp
                            signals_fired = {"ema_cross_bearish": True, "volume_confirmation": True}
                    except Exception:
                        pass
            
            else:  # In trade — check exit
                exit_reason = None
                exit_price = close
                
                if action == "BUY":
                    if close >= tp:
                        exit_reason = "TP_HIT"
                    elif close <= sl:
                        exit_reason = "SL_HIT"
                elif action == "SELL":
                    if close <= tp:
                        exit_reason = "TP_HIT"
                    elif close >= sl:
                        exit_reason = "SL_HIT"
                
                if i - entry_i >= self.MAX_HOLD_DAYS:
                    exit_reason = "MAX_HOLD"
                
                if exit_reason:
                    pnl_pct = (exit_price - entry_price) / entry_price if action == "BUY" else (entry_price - exit_price) / entry_price
                    risk = abs(entry_price - sl)
                    reward = abs(exit_price - entry_price)
                    rr_achieved = reward / risk if risk > 0 else 0.0
                    
                    trades.append(TradeRecord(
                        entry_date=str(df.index[entry_i]),
                        exit_date=str(df.index[i]),
                        entry_price=round(entry_price, 2),
                        exit_price=round(exit_price, 2),
                        action=action,
                        sl=round(sl, 2),
                        tp=round(tp, 2),
                        pnl=round(pnl_pct * 100, 2),
                        rr_achieved=round(rr_achieved, 3),
                        exit_reason=exit_reason,
                        signals_fired=dict(signals_fired),
                    ))
                    in_trade = False
        
        return trades
    
    def _strategy_mean_reversion(self, df: pd.DataFrame, symbol: str) -> list[TradeRecord]:
        """
        Mean reversion: Enter BUY when RSI < 30 AND price near lower BB.
        Enter SELL when RSI > 70 AND price near upper BB.
        """
        trades = []
        in_trade = False
        entry_i = 0
        entry_price = action = ""
        sl = tp = 0.0
        signals_fired = {}
        
        closes = df["close"].values
        
        for i in range(40, len(df)):
            ind = self._compute_indicators_for_row(df, i)
            if not ind:
                continue
            
            rsi = ind.get("rsi", 50)
            close = float(closes[i])
            bb_lower = ind.get("bb_lower", close * 0.97)
            bb_upper = ind.get("bb_upper", close * 1.03)
            atr = ind.get("atr", close * 0.015)
            
            if not in_trade:
                # Oversold BUY
                if rsi < 30 and close <= bb_lower * 1.01:
                    try:
                        rr_result = calculate_sl_tp("BUY", close, atr)
                        if rr_result.acceptable:
                            in_trade = True; entry_i = i; entry_price = close; action = "BUY"
                            sl, tp = rr_result.sl, rr_result.tp
                            signals_fired = {"rsi_oversold": True, "bb_lower_touch": True}
                    except Exception:
                        pass
                # Overbought SELL
                elif rsi > 70 and close >= bb_upper * 0.99:
                    try:
                        rr_result = calculate_sl_tp("SELL", close, atr)
                        if rr_result.acceptable:
                            in_trade = True; entry_i = i; entry_price = close; action = "SELL"
                            sl, tp = rr_result.sl, rr_result.tp
                            signals_fired = {"rsi_overbought": True, "bb_upper_touch": True}
                    except Exception:
                        pass
            else:
                exit_reason = None; exit_price = close
                if action == "BUY":
                    if close >= tp: exit_reason = "TP_HIT"
                    elif close <= sl: exit_reason = "SL_HIT"
                elif action == "SELL":
                    if close <= tp: exit_reason = "TP_HIT"
                    elif close >= sl: exit_reason = "SL_HIT"
                if i - entry_i >= self.MAX_HOLD_DAYS: exit_reason = "MAX_HOLD"
                
                if exit_reason:
                    risk = abs(entry_price - sl)
                    reward = abs(exit_price - entry_price)
                    pnl_pct = (exit_price - entry_price) / entry_price if action == "BUY" else (entry_price - exit_price) / entry_price
                    trades.append(TradeRecord(
                        entry_date=str(df.index[entry_i]), exit_date=str(df.index[i]),
                        entry_price=round(entry_price, 2), exit_price=round(exit_price, 2),
                        action=action, sl=round(sl, 2), tp=round(tp, 2),
                        pnl=round(pnl_pct * 100, 2), rr_achieved=round(reward/risk if risk>0 else 0, 3),
                        exit_reason=exit_reason, signals_fired=dict(signals_fired),
                    ))
                    in_trade = False
        return trades
    
    def _strategy_momentum(self, df: pd.DataFrame, symbol: str) -> list[TradeRecord]:
        """
        Momentum: Enter BUY when RSI 50-70 range AND MACD bullish AND price > EMA200.
        """
        trades = []
        in_trade = False
        entry_i = 0
        entry_price = action = ""
        sl = tp = 0.0
        signals_fired = {}
        closes = df["close"].values
        
        for i in range(60, len(df)):
            ind = self._compute_indicators_for_row(df, i)
            if not ind: continue
            rsi = ind.get("rsi", 50)
            macd = ind.get("macd", 0)
            macd_signal = ind.get("macd_signal", 0)
            ema200 = ind.get("ema_200", 0)
            close = float(closes[i])
            atr = ind.get("atr", close * 0.015)
            
            if not in_trade:
                if 50 < rsi < 70 and macd > macd_signal and close > ema200 > 0:
                    try:
                        rr_result = calculate_sl_tp("BUY", close, atr)
                        if rr_result.acceptable:
                            in_trade = True; entry_i = i; entry_price = close; action = "BUY"
                            sl, tp = rr_result.sl, rr_result.tp
                            signals_fired = {"rsi_momentum": True, "macd_bullish": True, "above_ema200": True}
                    except Exception:
                        pass
                elif 30 < rsi < 50 and macd < macd_signal and (ema200 == 0 or close < ema200):
                    try:
                        rr_result = calculate_sl_tp("SELL", close, atr)
                        if rr_result.acceptable:
                            in_trade = True; entry_i = i; entry_price = close; action = "SELL"
                            sl, tp = rr_result.sl, rr_result.tp
                            signals_fired = {"rsi_momentum_bearish": True, "macd_bearish": True}
                    except Exception:
                        pass
            else:
                exit_reason = None; exit_price = close
                if action == "BUY":
                    if close >= tp: exit_reason = "TP_HIT"
                    elif close <= sl: exit_reason = "SL_HIT"
                elif action == "SELL":
                    if close <= tp: exit_reason = "TP_HIT"
                    elif close >= sl: exit_reason = "SL_HIT"
                if i - entry_i >= self.MAX_HOLD_DAYS: exit_reason = "MAX_HOLD"
                if exit_reason:
                    risk = abs(entry_price - sl)
                    reward = abs(exit_price - entry_price)
                    pnl_pct = (exit_price - entry_price) / entry_price if action == "BUY" else (entry_price - exit_price) / entry_price
                    trades.append(TradeRecord(
                        entry_date=str(df.index[entry_i]), exit_date=str(df.index[i]),
                        entry_price=round(entry_price, 2), exit_price=round(exit_price, 2),
                        action=action, sl=round(sl, 2), tp=round(tp, 2),
                        pnl=round(pnl_pct * 100, 2), rr_achieved=round(reward/risk if risk>0 else 0, 3),
                        exit_reason=exit_reason, signals_fired=dict(signals_fired),
                    ))
                    in_trade = False
        return trades
    
    def _strategy_price_action(self, df: pd.DataFrame, symbol: str) -> list[TradeRecord]:
        """
        Price action: Detect hammer/inverted-hammer candle patterns at key EMAs.
        Hammer: lower shadow >= 2x body, close near high.
        """
        trades = []
        in_trade = False
        entry_i = 0
        entry_price = action = ""
        sl = tp = 0.0
        signals_fired = {}
        
        for i in range(40, len(df)):
            row = df.iloc[i]
            open_ = float(row["open"]); high = float(row["high"])
            low = float(row["low"]); close = float(row["close"])
            body = abs(close - open_)
            lower_shadow = min(open_, close) - low
            upper_shadow = high - max(open_, close)
            
            ind = self._compute_indicators_for_row(df, i)
            if not ind: continue
            ema21 = ind.get("ema_slow", 0)
            atr = ind.get("atr", close * 0.015)
            
            if not in_trade:
                # Hammer at support (near EMA21)
                is_hammer = body > 0 and lower_shadow >= 2 * body and close > open_ and abs(close - ema21) < atr
                if is_hammer:
                    try:
                        rr_result = calculate_sl_tp("BUY", close, atr)
                        if rr_result.acceptable:
                            in_trade = True; entry_i = i; entry_price = close; action = "BUY"
                            sl, tp = rr_result.sl, rr_result.tp
                            signals_fired = {"hammer_candle": True, "near_ema21": True}
                    except Exception:
                        pass
                # Shooting star at resistance
                is_shooting_star = body > 0 and upper_shadow >= 2 * body and close < open_ and abs(close - ema21) < atr
                if is_shooting_star:
                    try:
                        rr_result = calculate_sl_tp("SELL", close, atr)
                        if rr_result.acceptable:
                            in_trade = True; entry_i = i; entry_price = close; action = "SELL"
                            sl, tp = rr_result.sl, rr_result.tp
                            signals_fired = {"shooting_star": True, "near_ema21": True}
                    except Exception:
                        pass
            else:
                exit_reason = None; exit_price = close
                if action == "BUY":
                    if close >= tp: exit_reason = "TP_HIT"
                    elif close <= sl: exit_reason = "SL_HIT"
                elif action == "SELL":
                    if close <= tp: exit_reason = "TP_HIT"
                    elif close >= sl: exit_reason = "SL_HIT"
                if i - entry_i >= self.MAX_HOLD_DAYS: exit_reason = "MAX_HOLD"
                if exit_reason:
                    risk = abs(entry_price - sl)
                    reward = abs(exit_price - entry_price)
                    pnl_pct = (exit_price - entry_price) / entry_price if action == "BUY" else (entry_price - exit_price) / entry_price
                    trades.append(TradeRecord(
                        entry_date=str(df.index[entry_i]), exit_date=str(df.index[i]),
                        entry_price=round(entry_price, 2), exit_price=round(exit_price, 2),
                        action=action, sl=round(sl, 2), tp=round(tp, 2),
                        pnl=round(pnl_pct * 100, 2), rr_achieved=round(reward/risk if risk>0 else 0, 3),
                        exit_reason=exit_reason, signals_fired=dict(signals_fired),
                    ))
                    in_trade = False
        return trades
    
    def _compute_report(
        self, strategy: str, timeframe: str, trades: list[TradeRecord], df: pd.DataFrame
    ) -> StrategyReport:
        """Compute StrategyReport from trade list."""
        if not trades:
            return StrategyReport(
                strategy_name=strategy, timeframe=timeframe,
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate_pct=0.0, avg_rr=0.0, best_rr=0.0, worst_rr=0.0,
                max_drawdown_pct=0.0, sharpe_ratio=0.0, total_pnl=0.0,
            )
        
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]
        pnls = [t.pnl for t in trades]
        rrs = [t.rr_achieved for t in trades]
        
        # Drawdown
        cumulative = np.cumsum(pnls)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (peak - cumulative)
        max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
        
        # Sharpe (annualised)
        if len(pnls) > 1:
            mean_pnl = np.mean(pnls)
            std_pnl = np.std(pnls)
            sharpe = (mean_pnl / std_pnl) * np.sqrt(252) if std_pnl > 0 else 0.0
        else:
            sharpe = 0.0
        
        # Monthly P&L breakdown
        monthly_pnl: dict[str, float] = {}
        for t in trades:
            month = t.entry_date[:7]  # "YYYY-MM"
            monthly_pnl[month] = monthly_pnl.get(month, 0) + t.pnl
        profitable_months = [m for m, p in monthly_pnl.items() if p > 0]
        loss_months = [m for m, p in monthly_pnl.items() if p <= 0]
        
        # WHY it works — count which signals appear in winning trades
        signal_counts: dict[str, int] = {}
        for t in winning:
            for sig in t.signals_fired:
                signal_counts[sig] = signal_counts.get(sig, 0) + 1
        total_winning = len(winning) or 1
        why_it_works = {sig: round(count / total_winning * 100) for sig, count in signal_counts.items()}
        
        # Best/worst period
        best_month = max(monthly_pnl, key=lambda m: monthly_pnl[m]) if monthly_pnl else "N/A"
        worst_month = min(monthly_pnl, key=lambda m: monthly_pnl[m]) if monthly_pnl else "N/A"
        
        return StrategyReport(
            strategy_name=strategy,
            timeframe=timeframe,
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate_pct=round(len(winning) / len(trades) * 100, 1),
            avg_rr=round(float(np.mean(rrs)), 3),
            best_rr=round(float(np.max(rrs)), 3),
            worst_rr=round(float(np.min(rrs)), 3),
            max_drawdown_pct=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 3),
            total_pnl=round(sum(pnls), 2),
            profitable_months=profitable_months,
            loss_months=loss_months,
            why_it_works=why_it_works,
            best_period=f"{best_month} ({monthly_pnl.get(best_month, 0):.1f}% P&L)",
            worst_period=f"{worst_month} ({monthly_pnl.get(worst_month, 0):.1f}% P&L)",
            trade_records=trades,
        )
    
    def _get_best_strategy(self, reports: list[StrategyReport]) -> StrategyReport:
        """Pick best strategy by (win_rate × avg_rr) — composite score."""
        return max(reports, key=lambda r: r.win_rate_pct * r.avg_rr if r.total_trades > 5 else 0)
    
    def _generate_entry_plan(
        self, symbol: str, df: pd.DataFrame, best_report: StrategyReport
    ) -> dict:
        """Generate forward-looking entry plan from best report statistics."""
        last_close = float(df["close"].iloc[-1])
        avg_atr = last_close * 0.015  # ~1.5% approximate ATR
        
        return {
            "entry_zone": f"₹{last_close:.2f} (current price)",
            "sl_zone": f"₹{last_close - 1.5 * avg_atr:.2f} (1.5×ATR below)",
            "tp_zone": f"₹{last_close + 3.0 * avg_atr:.2f} (3.0×ATR above)",
            "best_rr": best_report.avg_rr,
            "expected_win_rate": best_report.win_rate_pct,
            "best_timeframe": best_report.timeframe,
            "strategy": best_report.strategy_name,
        }
