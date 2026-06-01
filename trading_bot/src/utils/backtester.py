"""
backtester.py — Multi-strategy backtester for NSE equities.

Strategy families: TREND_FOLLOWING, MEAN_REVERSION, MOMENTUM, PRICE_ACTION

For each strategy × timeframe combination, runs the full 20-year history and
returns a StrategyReport with win rates, R:R, WHY-it-works attribution, and
best/worst periods.
"""
from __future__ import annotations
import dataclasses
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
from utils.commission import CommissionCalculator


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
    pnl: float            # gross PnL % (before commission)
    rr_achieved: float    # actual R:R realized
    exit_reason: str      # "TP_HIT" | "SL_HIT" | "END_OF_DATA" | "MAX_HOLD"
    signals_fired: dict   # {"rsi_oversold": True, "ema_cross": True, ...}
    # --- commission fields (populated by _compute_report) ---
    gross_pnl: float = field(default=0.0)       # mirror of pnl before commission
    commission_pct: float = field(default=0.0)  # round-trip cost as % of turnover
    net_pnl: float = field(default=0.0)         # pnl after commission deduction


@dataclass
class WalkForwardWindow:
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_win_rate: float
    test_win_rate: float
    train_pnl: float
    test_pnl: float
    stability_score: float   # test_win_rate / train_win_rate (capped at 1.5)


@dataclass
class WalkForwardReport:
    n_windows: int
    windows: list[WalkForwardWindow]
    avg_stability: float   # mean stability across windows
    is_robust: bool        # True when avg_stability >= 0.50


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
    total_pnl: float              # gross PnL % (sum of gross trade PnLs)
    profitable_months: list[str] = field(default_factory=list)
    loss_months: list[str] = field(default_factory=list)
    why_it_works: dict = field(default_factory=dict)
    best_period: str = ""
    worst_period: str = ""
    trade_records: list[TradeRecord] = field(default_factory=list)
    # --- commission + walk-forward additions ---
    gross_total_pnl: float = field(default=0.0)       # same as total_pnl (kept for clarity)
    net_total_pnl: float = field(default=0.0)         # PnL after all commissions
    total_commission_pct: float = field(default=0.0)  # sum of round-trip costs %
    commission_segment: str = field(default="EQUITY_DELIVERY")
    walk_forward: Optional[WalkForwardReport] = field(default=None)
    
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
    entry_plan: dict
    commission_segment: str = field(default="EQUITY_DELIVERY")
    walk_forward_enabled: bool = field(default=False)


class Backtester:
    """Multi-strategy backtester."""
    
    MAX_HOLD_DAYS = 20     # Maximum holding period before force-exit
    INITIAL_CAPITAL = 100_000.0
    
    def run_all_strategies(
        self,
        symbol: str,
        df: pd.DataFrame,
        initial_capital: float = INITIAL_CAPITAL,
        strategy_filter: list | None = None,
        custom_params: dict | None = None,
        commission_segment: str = "EQUITY_DELIVERY",
        lot_size: int = 1,
        walk_forward: bool = False,
    ) -> BacktestResult:
        """
        Run strategy families on the provided OHLCV dataframe.

        Args:
            symbol:             Exchange symbol for logging/plan.
            df:                 OHLCV DataFrame with datetime index.
            initial_capital:    Notional capital for sizing (default 100 000 INR).
            strategy_filter:    Limit to specific strategy names (None = all).
            custom_params:      Parameter dict for the CUSTOM strategy.
            commission_segment: CommissionCalculator segment key
                                (e.g. "EQUITY_DELIVERY", "FNO_FUTURES").
            lot_size:           Contract lot size for turnover scaling.
            walk_forward:       If True, run anchored walk-forward validation
                                on the winning strategy.

        Returns:
            BacktestResult with StrategyReports (net PnL after commission)
            and an optional WalkForwardReport on the best strategy.
        """
        reports = []
        families = strategy_filter if strategy_filter else STRATEGY_FAMILIES

        for strategy in families:
            for timeframe in TIMEFRAMES:
                logger.info(f"Backtesting {strategy} on {symbol} ({timeframe})…")
                try:
                    df_tf = self._resample(df, timeframe)
                    if len(df_tf) < 60:
                        continue

                    trades = self._run_strategy(
                        strategy, df_tf, symbol, custom_params=custom_params
                    )
                    if trades:
                        report = self._compute_report(
                            strategy, timeframe, trades, df_tf,
                            commission_segment=commission_segment,
                            lot_size=lot_size,
                        )
                        reports.append(report)
                except Exception as exc:
                    logger.warning(f"Strategy {strategy} {timeframe} failed: {exc}")

        if not reports:
            return BacktestResult(
                symbol=symbol, years_analysed=0, strategy_reports=[],
                recommended_strategy="N/A", recommended_timeframe="N/A",
                recommended_rr=0.0, recommended_win_rate=0.0, entry_plan={},
                commission_segment=commission_segment,
                walk_forward_enabled=walk_forward,
            )

        best = self._get_best_strategy(reports)

        # Optionally run anchored walk-forward on the winning strategy
        if walk_forward:
            try:
                wf_validator = WalkForwardValidator()
                wf_report = wf_validator.validate(
                    strategy=best.strategy_name,
                    df=df,
                    symbol=symbol,
                    backtester=self,
                    commission_segment=commission_segment,
                    lot_size=lot_size,
                    custom_params=custom_params,
                )
                best = dataclasses.replace(best, walk_forward=wf_report)
                # Update the report in the list too
                reports = [
                    dataclasses.replace(r, walk_forward=wf_report)
                    if r.strategy_name == best.strategy_name and r.timeframe == best.timeframe
                    else r
                    for r in reports
                ]
                logger.info(
                    f"Walk-forward: avg_stability={wf_report.avg_stability:.2f} "
                    f"robust={wf_report.is_robust}"
                )
            except Exception as exc:
                logger.warning(f"Walk-forward validation failed: {exc}")

        return BacktestResult(
            symbol=symbol,
            years_analysed=int((df.index[-1] - df.index[0]).days / 365),
            strategy_reports=reports,
            recommended_strategy=best.strategy_name,
            recommended_timeframe=best.timeframe,
            recommended_rr=best.avg_rr,
            recommended_win_rate=best.win_rate_pct,
            entry_plan=self._generate_entry_plan(symbol, df, best),
            commission_segment=commission_segment,
            walk_forward_enabled=walk_forward,
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
        self, strategy: str, df: pd.DataFrame, symbol: str, custom_params: dict | None = None
    ) -> list[TradeRecord]:
        """Run a single strategy and return list of trade records."""
        if strategy == "CUSTOM":
            return self._strategy_custom(df, symbol, custom_params or {})
        method_map = {
            "TREND_FOLLOWING": self._strategy_trend_following,
            "MEAN_REVERSION": self._strategy_mean_reversion,
            "MOMENTUM": self._strategy_momentum,
            "PRICE_ACTION": self._strategy_price_action,
        }
        if strategy not in method_map:
            logger.warning(f"Unknown strategy '{strategy}' — skipping")
            return []
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
    
    def _strategy_custom(self, df: pd.DataFrame, symbol: str, params: dict) -> list[TradeRecord]:
        """
        Custom strategy: EMA fast/slow crossover with configurable RSI confirmation,
        ATR-based SL/TP multipliers, and optional volume filter.

        params keys (with defaults):
          ema_fast        int   9
          ema_slow        int   21
          rsi_oversold    int   30   (RSI threshold for BUY confirmation)
          rsi_overbought  int   70   (RSI threshold for SELL confirmation)
          atr_mult_sl     float 1.5
          atr_mult_tp     float 3.0
          volume_confirm  bool  True
        """
        ema_fast = int(params.get("ema_fast", 9))
        ema_slow = int(params.get("ema_slow", 21))
        rsi_oversold = int(params.get("rsi_oversold", 30))
        rsi_overbought = int(params.get("rsi_overbought", 70))
        atr_mult_sl = float(params.get("atr_mult_sl", 1.5))
        atr_mult_tp = float(params.get("atr_mult_tp", 3.0))
        volume_confirm = bool(params.get("volume_confirm", True))

        trades: list[TradeRecord] = []
        in_trade = False
        entry_i = 0
        entry_price = 0.0
        action = ""
        sl = tp = 0.0
        signals_fired: dict = {}

        closes = df["close"].values
        ema_f = pd.Series(closes).ewm(span=ema_fast, adjust=False).mean().values
        ema_s = pd.Series(closes).ewm(span=ema_slow, adjust=False).mean().values
        volumes = df["volume"].values

        start = max(ema_slow + 10, 40)
        for i in range(start, len(df)):
            close = float(closes[i])
            vol = float(volumes[i])
            avg_vol = float(np.mean(volumes[max(0, i - 20):i])) if i > 20 else vol
            vol_ok = (vol > 1.2 * avg_vol) if volume_confirm else True

            ind = self._compute_indicators_for_row(df, i)
            rsi = ind.get("rsi", 50) if ind else 50
            atr = ind.get("atr", close * 0.015) if ind else close * 0.015

            # Custom SL/TP using user-defined ATR multipliers
            def _calc_exit(direction: str):
                if direction == "BUY":
                    return close - atr_mult_sl * atr, close + atr_mult_tp * atr
                return close + atr_mult_sl * atr, close - atr_mult_tp * atr

            if not in_trade:
                cross_up = ema_f[i] > ema_s[i] and ema_f[i - 1] <= ema_s[i - 1]
                cross_dn = ema_f[i] < ema_s[i] and ema_f[i - 1] >= ema_s[i - 1]

                if cross_up and rsi < rsi_overbought and vol_ok:
                    sl_val, tp_val = _calc_exit("BUY")
                    rr = (tp_val - close) / (close - sl_val) if (close - sl_val) > 0 else 0
                    if rr >= MIN_RR_RATIO:
                        in_trade = True; entry_i = i; entry_price = close; action = "BUY"
                        sl, tp = sl_val, tp_val
                        signals_fired = {
                            f"ema{ema_fast}_cross_up": True,
                            "rsi_confirmation": True,
                            "volume_ok": vol_ok,
                        }

                elif cross_dn and rsi > rsi_oversold and vol_ok:
                    sl_val, tp_val = _calc_exit("SELL")
                    rr = (close - tp_val) / (sl_val - close) if (sl_val - close) > 0 else 0
                    if rr >= MIN_RR_RATIO:
                        in_trade = True; entry_i = i; entry_price = close; action = "SELL"
                        sl, tp = sl_val, tp_val
                        signals_fired = {
                            f"ema{ema_fast}_cross_dn": True,
                            "rsi_confirmation": True,
                            "volume_ok": vol_ok,
                        }
            else:
                exit_reason = None
                exit_price = close
                if action == "BUY":
                    if close >= tp: exit_reason = "TP_HIT"
                    elif close <= sl: exit_reason = "SL_HIT"
                else:
                    if close <= tp: exit_reason = "TP_HIT"
                    elif close >= sl: exit_reason = "SL_HIT"
                if i - entry_i >= self.MAX_HOLD_DAYS:
                    exit_reason = "MAX_HOLD"
                if exit_reason:
                    risk = abs(entry_price - sl)
                    reward = abs(exit_price - entry_price)
                    pnl_pct = (
                        (exit_price - entry_price) / entry_price if action == "BUY"
                        else (entry_price - exit_price) / entry_price
                    )
                    trades.append(TradeRecord(
                        entry_date=str(df.index[entry_i]),
                        exit_date=str(df.index[i]),
                        entry_price=round(entry_price, 2),
                        exit_price=round(exit_price, 2),
                        action=action,
                        sl=round(sl, 2),
                        tp=round(tp, 2),
                        pnl=round(pnl_pct * 100, 2),
                        rr_achieved=round(reward / risk if risk > 0 else 0, 3),
                        exit_reason=exit_reason,
                        signals_fired=dict(signals_fired),
                    ))
                    in_trade = False
        return trades

    def _compute_report(
        self,
        strategy: str,
        timeframe: str,
        trades: list[TradeRecord],
        df: pd.DataFrame,
        commission_segment: str = "EQUITY_DELIVERY",
        lot_size: int = 1,
    ) -> StrategyReport:
        """Compute StrategyReport from trade list, including commission deduction."""
        if not trades:
            return StrategyReport(
                strategy_name=strategy, timeframe=timeframe,
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate_pct=0.0, avg_rr=0.0, best_rr=0.0, worst_rr=0.0,
                max_drawdown_pct=0.0, sharpe_ratio=0.0, total_pnl=0.0,
                gross_total_pnl=0.0, net_total_pnl=0.0,
                total_commission_pct=0.0, commission_segment=commission_segment,
            )

        # ── Commission per trade ──────────────────────────────────────────────
        calculator = CommissionCalculator()
        # Use 5% of INITIAL_CAPITAL as notional position size (max-risk rule)
        position_size_inr = max(
            self.INITIAL_CAPITAL * 0.05,
            # lot-aware: at least 1 lot
            trades[0].entry_price * lot_size if trades else 5_000.0,
        )
        cost_frac = calculator.effective_cost_pct(commission_segment, position_size_inr)
        # effective_cost_pct already returns a percentage (e.g. 0.323 = 0.323%)
        cost_pct = cost_frac  # percentage points per round trip — do NOT multiply by 100

        # Enrich trades with net commission fields
        trades = [
            dataclasses.replace(
                t,
                gross_pnl=t.pnl,
                commission_pct=round(cost_pct, 4),
                net_pnl=round(t.pnl - cost_pct, 4),
            )
            for t in trades
        ]

        # Use net_pnl for win/loss classification
        winning = [t for t in trades if t.net_pnl > 0]
        losing = [t for t in trades if t.net_pnl <= 0]
        pnls = [t.net_pnl for t in trades]   # net for metrics
        gross_pnls = [t.gross_pnl for t in trades]
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
        
        gross_total = round(sum(gross_pnls), 2)
        net_total = round(sum(pnls), 2)
        total_comm = round(cost_pct * len(trades), 4)

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
            total_pnl=gross_total,           # kept as gross for backward compat
            gross_total_pnl=gross_total,
            net_total_pnl=net_total,
            total_commission_pct=total_comm,
            commission_segment=commission_segment,
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
            "gross_total_pnl": best_report.gross_total_pnl,
            "net_total_pnl": best_report.net_total_pnl,
            "commission_drag_pct": best_report.total_commission_pct,
            "best_timeframe": best_report.timeframe,
            "strategy": best_report.strategy_name,
        }


# ── Walk-forward validator ────────────────────────────────────────────────────

class WalkForwardValidator:
    """
    Anchored walk-forward validation.

    Splits the full history into 3 expanding train windows + fixed test windows:
      Window 1: train [  0% – 60%], test [60% – 73%]
      Window 2: train [  0% – 73%], test [73% – 87%]
      Window 3: train [  0% – 87%], test [87% – 100%]

    Stability score = test_win_rate / train_win_rate (capped at 1.5).
    is_robust = True when avg_stability >= 0.50.
    """

    _WINDOWS: list[tuple[float, float, float, float]] = [
        (0.00, 0.60, 0.60, 0.73),
        (0.00, 0.73, 0.73, 0.87),
        (0.00, 0.87, 0.87, 1.00),
    ]
    _MIN_TRAIN_BARS = 60
    _MIN_TEST_BARS = 20

    def validate(
        self,
        strategy: str,
        df: pd.DataFrame,
        symbol: str,
        backtester: "Backtester",
        commission_segment: str = "EQUITY_DELIVERY",
        lot_size: int = 1,
        custom_params: dict | None = None,
    ) -> WalkForwardReport:
        """
        Run anchored walk-forward on a single strategy.

        Args:
            strategy:           Strategy name (e.g. "TREND_FOLLOWING").
            df:                 Full OHLCV DataFrame with datetime index.
            symbol:             Symbol name (for logging).
            backtester:         Backtester instance to reuse strategy methods.
            commission_segment: CommissionCalculator segment key.
            lot_size:           Contract lot size.
            custom_params:      Params for CUSTOM strategy.

        Returns:
            WalkForwardReport with per-window metrics and is_robust flag.
        """
        n = len(df)
        windows: list[WalkForwardWindow] = []

        for wid, (tr_s, tr_e, te_s, te_e) in enumerate(self._WINDOWS, 1):
            train_df = df.iloc[int(tr_s * n): int(tr_e * n)]
            test_df  = df.iloc[int(te_s * n): int(te_e * n)]

            if len(train_df) < self._MIN_TRAIN_BARS or len(test_df) < self._MIN_TEST_BARS:
                logger.debug(
                    f"WF window {wid}: too short "
                    f"(train={len(train_df)}, test={len(test_df)}) — skipped"
                )
                continue

            train_trades = backtester._run_strategy(
                strategy, train_df, symbol, custom_params=custom_params
            )
            test_trades = backtester._run_strategy(
                strategy, test_df, symbol, custom_params=custom_params
            )

            if not train_trades:
                logger.debug(f"WF window {wid}: no train trades — skipped")
                continue

            train_report = backtester._compute_report(
                strategy, "1D", train_trades, train_df, commission_segment, lot_size
            )
            test_report = backtester._compute_report(
                strategy, "1D", test_trades or [], test_df, commission_segment, lot_size
            ) if test_trades else None

            test_wr = test_report.win_rate_pct if test_report else 0.0
            test_pnl = test_report.net_total_pnl if test_report else 0.0
            stability = (
                min(test_wr / train_report.win_rate_pct, 1.5)
                if train_report.win_rate_pct > 0 else 0.0
            )

            windows.append(
                WalkForwardWindow(
                    window_id=wid,
                    train_start=str(train_df.index[0].date()),
                    train_end=str(train_df.index[-1].date()),
                    test_start=str(test_df.index[0].date()),
                    test_end=str(test_df.index[-1].date()),
                    train_win_rate=train_report.win_rate_pct,
                    test_win_rate=test_wr,
                    train_pnl=train_report.net_total_pnl,
                    test_pnl=test_pnl,
                    stability_score=round(stability, 3),
                )
            )

            logger.debug(
                f"WF window {wid}: train_wr={train_report.win_rate_pct:.1f}% "
                f"test_wr={test_wr:.1f}% stability={stability:.2f}"
            )

        avg_stability = (
            float(np.mean([w.stability_score for w in windows])) if windows else 0.0
        )
        return WalkForwardReport(
            n_windows=len(windows),
            windows=windows,
            avg_stability=round(avg_stability, 3),
            is_robust=avg_stability >= 0.50,
        )
