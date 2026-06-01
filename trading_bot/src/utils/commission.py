"""
commission.py — Indian market commission & tax calculator.

Covers all six Indian market segments with accurate statutory rates (FY 2024-25):
    EQUITY_INTRADAY    NSE/BSE intraday equity
    EQUITY_DELIVERY    NSE/BSE CNC delivery equity
    FNO_FUTURES        NSE F&O futures segment
    FNO_OPTIONS        NSE F&O options segment (on premium value)
    MCX_COMMODITY      MCX commodity futures (CTT-applicable non-agri)
    CDS_CURRENCY       NSE currency derivatives

Statutory rates sources:
    STT   — Finance Act 2024 (Budget 2024 revisions effective Oct 2024)
    CTT   — Finance Act 2013
    SEBI  — SEBI circular SEBI/HO/MRD/MRD-POD-2/P/CIR/2023/170
    GST   — 18% on brokerage + exchange fees (CGST 9% + SGST 9%)
    Stamp — Indian Stamp Act 2019, Schedule I (uniform nationwide rates)

Usage:
    calc = CommissionCalculator()

    # Single trade leg
    cost = calc.calculate("EQUITY_INTRADAY", turnover=100_000, trade_type="SELL")
    print(cost.total)          # total INR cost for this leg
    print(cost.as_pct(100_000))  # as % of turnover

    # Full round-trip (buy + sell)
    total = calc.round_trip_cost("EQUITY_DELIVERY", turnover=500_000)

    # F&O options (pass premium value as turnover)
    cost = calc.calculate("FNO_OPTIONS", turnover=premium * lot_size, trade_type="SELL")

    # With custom broker rates
    calc_custom = CommissionCalculator(broker_preset="icici")
    cost = calc_custom.calculate("EQUITY_INTRADAY", turnover=100_000, trade_type="BUY")
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from loguru import logger


# ── Segment type alias ─────────────────────────────────────────────────────────
Segment = Literal[
    "EQUITY_INTRADAY",
    "EQUITY_DELIVERY",
    "FNO_FUTURES",
    "FNO_OPTIONS",
    "MCX_COMMODITY",
    "CDS_CURRENCY",
]

TradeSide = Literal["BUY", "SELL"]
BrokerPreset = Literal["zerodha", "groww", "icici", "custom"]


# ── Broker brokerage rate table ────────────────────────────────────────────────
# Each entry: (flat_per_order_inr, pct_of_turnover, max_per_order_inr)
# Effective brokerage = min(flat_per_order, pct_rate * turnover)
# Set flat_per_order=None to always use pct model (ICICI delivery)
_BROKER_RATES: dict[str, dict[str, tuple]] = {
    # (flat_inr, pct_rate, cap_inr)
    "zerodha": {
        "EQUITY_INTRADAY": (20.0, 0.0003, 20.0),   # ₹20 or 0.03%, whichever lower
        "EQUITY_DELIVERY": (0.0,  0.0000, 0.0),     # zero brokerage delivery
        "FNO_FUTURES":     (20.0, 0.0003, 20.0),
        "FNO_OPTIONS":     (20.0, 0.0003, 20.0),
        "MCX_COMMODITY":   (20.0, 0.0003, 20.0),
        "CDS_CURRENCY":    (20.0, 0.0003, 20.0),
    },
    "groww": {
        "EQUITY_INTRADAY": (20.0, 0.0005, 20.0),
        "EQUITY_DELIVERY": (0.0,  0.0000, 0.0),
        "FNO_FUTURES":     (20.0, 0.0005, 20.0),
        "FNO_OPTIONS":     (20.0, 0.0005, 20.0),
        "MCX_COMMODITY":   (20.0, 0.0005, 20.0),
        "CDS_CURRENCY":    (20.0, 0.0005, 20.0),
    },
    "icici": {
        # ICICI Direct: 0.55% intraday, 0.55% delivery, ₹35 F&O per lot
        "EQUITY_INTRADAY": (None, 0.0055, None),    # pct-only model
        "EQUITY_DELIVERY": (None, 0.0055, None),
        "FNO_FUTURES":     (35.0, 0.0000, 35.0),    # flat per lot (approx per order)
        "FNO_OPTIONS":     (35.0, 0.0000, 35.0),
        "MCX_COMMODITY":   (35.0, 0.0000, 35.0),
        "CDS_CURRENCY":    (35.0, 0.0000, 35.0),
    },
}


# ── Statutory rate tables ──────────────────────────────────────────────────────

# Securities Transaction Tax (STT) rates — Finance Act 2024
# Format: {"BUY": rate, "SELL": rate}  (rate as decimal, 0.001 = 0.1%)
_STT_RATES: dict[str, dict[str, float]] = {
    "EQUITY_INTRADAY": {"BUY": 0.0,      "SELL": 0.00025},   # 0.025% on sell
    "EQUITY_DELIVERY": {"BUY": 0.001,    "SELL": 0.001},     # 0.1% both sides
    "FNO_FUTURES":     {"BUY": 0.0,      "SELL": 0.000125},  # 0.0125% on sell (eq futures)
    "FNO_OPTIONS":     {"BUY": 0.0,      "SELL": 0.000625},  # 0.0625% on sell (on premium)
    "MCX_COMMODITY":   {"BUY": 0.0,      "SELL": 0.0},       # STT not applicable on MCX
    "CDS_CURRENCY":    {"BUY": 0.0,      "SELL": 0.0},       # STT not applicable on CDS
}

# Commodity Transaction Tax (CTT) — MCX non-agricultural futures only
# 0.01% on sell side
_CTT_RATES: dict[str, dict[str, float]] = {
    "MCX_COMMODITY": {"BUY": 0.0, "SELL": 0.0001},
}

# NSE/BSE Exchange transaction charges (% of turnover)
# Source: NSE circulars 2024
_EXCHANGE_FEES: dict[str, float] = {
    "EQUITY_INTRADAY": 0.0000335,   # NSE 0.00335% (use NSE as default)
    "EQUITY_DELIVERY": 0.0000335,
    "FNO_FUTURES":     0.00002,     # 0.002%
    "FNO_OPTIONS":     0.0005,      # 0.05% on premium
    "MCX_COMMODITY":   0.000026,    # 0.0026% (varies by commodity, use average)
    "CDS_CURRENCY":    0.0000035,   # 0.00035%
}

# SEBI regulatory fee: ₹10 per crore = 0.000001 of turnover
_SEBI_FEE_RATE: float = 0.000001   # 0.0001% on all segments

# GST rate on (brokerage + exchange_fee + sebi_fee)
_GST_RATE: float = 0.18

# Indian Stamp Act 2019 — uniform nationwide rates (% of turnover, BUY side only)
_STAMP_DUTY: dict[str, float] = {
    "EQUITY_INTRADAY": 0.00003,    # ₹300 per crore
    "EQUITY_DELIVERY": 0.00015,    # ₹1500 per crore
    "FNO_FUTURES":     0.00002,    # ₹200 per crore
    "FNO_OPTIONS":     0.00003,    # ₹300 per crore (on premium)
    "MCX_COMMODITY":   0.00002,    # ₹200 per crore
    "CDS_CURRENCY":    0.00001,    # ₹100 per crore
}

# Slippage model — estimated market impact as % of turnover
# Based on NSE average bid-ask spread data (liquid large-cap midpoint)
_DEFAULT_SLIPPAGE: dict[str, float] = {
    "EQUITY_INTRADAY": 0.0003,   # 0.03% — liquid large-cap assumption
    "EQUITY_DELIVERY": 0.0005,   # 0.05% — slightly wider (less aggressive fill)
    "FNO_FUTURES":     0.0002,   # 0.02% — very tight on index futures
    "FNO_OPTIONS":     0.001,    # 0.10% — wider spread on options premium
    "MCX_COMMODITY":   0.0003,   # 0.03%
    "CDS_CURRENCY":    0.0002,   # 0.02%
}

# Valid segment names
_VALID_SEGMENTS: set[str] = set(_STT_RATES.keys())


# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass
class CommissionBreakdown:
    """
    Per-trade-leg cost breakdown in INR.

    All values are the monetary cost for ONE side (either BUY or SELL).
    For round-trip cost, use CommissionCalculator.round_trip_cost().
    """
    segment: str = ""
    trade_type: str = "BUY"
    turnover: float = 0.0           # price × quantity
    brokerage: float = 0.0          # broker charge
    stt: float = 0.0                # Securities Transaction Tax
    ctt: float = 0.0                # Commodity Transaction Tax (MCX only)
    exchange_fee: float = 0.0       # NSE/BSE/MCX transaction charges
    sebi_fee: float = 0.0           # SEBI regulatory fee
    gst: float = 0.0                # 18% GST on (brokerage + exchange_fee + sebi_fee)
    stamp_duty: float = 0.0         # Stamp duty (BUY side only)
    slippage: float = 0.0           # Estimated market impact
    total: float = 0.0              # Sum of all above

    def as_pct(self, base: float | None = None) -> float:
        """Return total cost as percentage of turnover (or supplied base)."""
        denom = base if base is not None else self.turnover
        if denom <= 0:
            return 0.0
        return round(self.total / denom * 100, 4)

    def to_dict(self) -> dict:
        return {
            "segment": self.segment,
            "trade_type": self.trade_type,
            "turnover": round(self.turnover, 2),
            "brokerage": round(self.brokerage, 4),
            "stt": round(self.stt, 4),
            "ctt": round(self.ctt, 4),
            "exchange_fee": round(self.exchange_fee, 4),
            "sebi_fee": round(self.sebi_fee, 4),
            "gst": round(self.gst, 4),
            "stamp_duty": round(self.stamp_duty, 4),
            "slippage": round(self.slippage, 4),
            "total": round(self.total, 4),
            "total_pct": self.as_pct(),
        }


@dataclass
class RoundTripCost:
    """Combined cost for a full buy + sell round-trip trade."""
    segment: str
    turnover: float
    buy_leg: CommissionBreakdown = field(default_factory=CommissionBreakdown)
    sell_leg: CommissionBreakdown = field(default_factory=CommissionBreakdown)
    total: float = 0.0

    def as_pct(self) -> float:
        """Round-trip cost as % of single-leg turnover."""
        if self.turnover <= 0:
            return 0.0
        return round(self.total / self.turnover * 100, 4)

    def to_dict(self) -> dict:
        return {
            "segment": self.segment,
            "turnover": round(self.turnover, 2),
            "buy_leg": self.buy_leg.to_dict(),
            "sell_leg": self.sell_leg.to_dict(),
            "total": round(self.total, 4),
            "total_pct": self.as_pct(),
        }


# ── Calculator ─────────────────────────────────────────────────────────────────

class CommissionCalculator:
    """
    Calculate realistic all-in trade cost for Indian market segments.

    Rates are based on statutory charges effective FY 2024-25 and apply
    to NSE/BSE equity, NSE F&O, MCX commodity, and NSE CDS segments.

    Args:
        broker_preset: Default broker rate schedule. Options:
                       "zerodha" (default) | "groww" | "icici"
        slippage_override: Override default slippage % per segment.
                           Dict format: {"EQUITY_INTRADAY": 0.0005, ...}
    """

    def __init__(
        self,
        broker_preset: BrokerPreset = "zerodha",
        slippage_override: dict[str, float] | None = None,
    ):
        if broker_preset not in _BROKER_RATES:
            raise ValueError(
                f"Unknown broker_preset '{broker_preset}'. "
                f"Valid options: {list(_BROKER_RATES.keys())}"
            )
        self.broker_preset = broker_preset
        self._slippage = dict(_DEFAULT_SLIPPAGE)
        if slippage_override:
            self._slippage.update(slippage_override)

    # ── Public API ──────────────────────────────────────────────────────────────

    def calculate(
        self,
        segment: str,
        turnover: float,
        trade_type: TradeSide = "BUY",
        include_slippage: bool = True,
    ) -> CommissionBreakdown:
        """
        Calculate all statutory costs for a single trade leg.

        Args:
            segment:          "EQUITY_INTRADAY" | "EQUITY_DELIVERY" |
                              "FNO_FUTURES" | "FNO_OPTIONS" |
                              "MCX_COMMODITY" | "CDS_CURRENCY"
            turnover:         price × quantity in INR.
                              For options: premium × lot_size.
            trade_type:       "BUY" or "SELL"
            include_slippage: Add estimated market impact slippage. Default True.

        Returns:
            CommissionBreakdown with per-component costs and total.
        """
        segment = segment.upper()
        trade_type = trade_type.upper()

        if segment not in _VALID_SEGMENTS:
            raise ValueError(
                f"Unknown segment '{segment}'. "
                f"Valid: {sorted(_VALID_SEGMENTS)}"
            )
        if trade_type not in ("BUY", "SELL"):
            raise ValueError(f"trade_type must be 'BUY' or 'SELL', got '{trade_type}'")
        if turnover < 0:
            raise ValueError(f"turnover must be >= 0, got {turnover}")

        brokerage   = self._calc_brokerage(segment, turnover)
        stt         = self._calc_stt(segment, turnover, trade_type)
        ctt         = self._calc_ctt(segment, turnover, trade_type)
        exchange_fee = turnover * _EXCHANGE_FEES[segment]
        sebi_fee    = turnover * _SEBI_FEE_RATE
        gst         = (brokerage + exchange_fee + sebi_fee) * _GST_RATE
        stamp_duty  = self._calc_stamp_duty(segment, turnover, trade_type)
        slippage    = (turnover * self._slippage[segment]) if include_slippage else 0.0

        total = brokerage + stt + ctt + exchange_fee + sebi_fee + gst + stamp_duty + slippage

        bd = CommissionBreakdown(
            segment=segment,
            trade_type=trade_type,
            turnover=turnover,
            brokerage=round(brokerage, 4),
            stt=round(stt, 4),
            ctt=round(ctt, 4),
            exchange_fee=round(exchange_fee, 4),
            sebi_fee=round(sebi_fee, 4),
            gst=round(gst, 4),
            stamp_duty=round(stamp_duty, 4),
            slippage=round(slippage, 4),
            total=round(total, 4),
        )
        logger.debug(
            "Commission [{} {}] turnover={:.0f} → total={:.2f} ({:.4f}%)",
            segment, trade_type, turnover, total, bd.as_pct(),
        )
        return bd

    def round_trip_cost(
        self,
        segment: str,
        turnover: float,
        include_slippage: bool = True,
    ) -> RoundTripCost:
        """
        Calculate combined cost for a full BUY + SELL round-trip.

        Both legs are computed at the same turnover value (symmetric assumption).
        For asymmetric entries/exits, call calculate() twice and sum manually.

        Returns:
            RoundTripCost with buy_leg, sell_leg, and combined total.
        """
        buy  = self.calculate(segment, turnover, "BUY",  include_slippage)
        sell = self.calculate(segment, turnover, "SELL", include_slippage)
        return RoundTripCost(
            segment=segment.upper(),
            turnover=turnover,
            buy_leg=buy,
            sell_leg=sell,
            total=round(buy.total + sell.total, 4),
        )

    def effective_cost_pct(
        self,
        segment: str,
        turnover: float = 100_000.0,
        include_slippage: bool = True,
    ) -> float:
        """
        Return round-trip cost as % of one-side turnover.

        Useful for quick comparison across segments.
        Example: effective_cost_pct("EQUITY_INTRADAY") → 0.085 (≈ 0.085%)
        """
        rt = self.round_trip_cost(segment, turnover, include_slippage)
        return rt.as_pct()

    def apply_to_pnl(
        self,
        pnl_inr: float,
        segment: str,
        entry_turnover: float,
        exit_turnover: float | None = None,
        include_slippage: bool = True,
    ) -> tuple[float, RoundTripCost]:
        """
        Subtract realistic commission from a gross PnL figure.

        Args:
            pnl_inr:          Gross PnL in INR (before costs).
            segment:          Market segment.
            entry_turnover:   Entry price × quantity.
            exit_turnover:    Exit price × quantity. Defaults to entry_turnover.
            include_slippage: Include market impact slippage.

        Returns:
            Tuple of (net_pnl_inr, RoundTripCost breakdown).
        """
        exit_tv = exit_turnover if exit_turnover is not None else entry_turnover
        buy  = self.calculate(segment, entry_turnover, "BUY",  include_slippage)
        sell = self.calculate(segment, exit_tv,        "SELL", include_slippage)
        total_cost = buy.total + sell.total
        net_pnl = pnl_inr - total_cost
        rt = RoundTripCost(
            segment=segment.upper(),
            turnover=entry_turnover,
            buy_leg=buy,
            sell_leg=sell,
            total=round(total_cost, 4),
        )
        return round(net_pnl, 4), rt

    # ── Private helpers ─────────────────────────────────────────────────────────

    def _calc_brokerage(self, segment: str, turnover: float) -> float:
        """Compute brokerage using broker preset rate table."""
        rates = _BROKER_RATES[self.broker_preset][segment]
        flat_inr, pct_rate, cap_inr = rates

        if flat_inr is None:
            # Pure percentage model (e.g. ICICI delivery)
            return turnover * pct_rate

        pct_charge = turnover * pct_rate
        # cap_inr acts as both the flat amount and the ceiling
        if cap_inr is not None and cap_inr > 0:
            return min(pct_charge, cap_inr)
        return pct_charge

    def _calc_stt(self, segment: str, turnover: float, trade_type: str) -> float:
        """Compute STT for a given segment and trade side."""
        rate = _STT_RATES[segment][trade_type]
        return turnover * rate

    def _calc_ctt(self, segment: str, turnover: float, trade_type: str) -> float:
        """Compute CTT (MCX only). Returns 0 for all other segments."""
        if segment not in _CTT_RATES:
            return 0.0
        rate = _CTT_RATES[segment][trade_type]
        return turnover * rate

    def _calc_stamp_duty(self, segment: str, turnover: float, trade_type: str) -> float:
        """
        Stamp duty applies on BUY side only per Indian Stamp Act 2019.
        Stamp duty on SELL is zero for all segments.
        """
        if trade_type != "BUY":
            return 0.0
        return turnover * _STAMP_DUTY[segment]

    # ── Convenience summary ─────────────────────────────────────────────────────

    def summary_table(self) -> list[dict]:
        """
        Return a summary of round-trip effective cost % for all segments
        at a standard ₹1 lakh turnover. Useful for UI display.
        """
        rows = []
        for seg in sorted(_VALID_SEGMENTS):
            try:
                rt = self.round_trip_cost(seg, 100_000.0, include_slippage=True)
                rows.append({
                    "segment": seg,
                    "broker": self.broker_preset,
                    "turnover": 100_000,
                    "round_trip_cost_inr": round(rt.total, 2),
                    "round_trip_cost_pct": rt.as_pct(),
                    "brokerage_pct":    round((rt.buy_leg.brokerage + rt.sell_leg.brokerage) / 100_000 * 100, 4),
                    "stt_pct":          round((rt.buy_leg.stt + rt.sell_leg.stt) / 100_000 * 100, 4),
                    "gst_pct":          round((rt.buy_leg.gst + rt.sell_leg.gst) / 100_000 * 100, 4),
                    "slippage_pct":     round((rt.buy_leg.slippage + rt.sell_leg.slippage) / 100_000 * 100, 4),
                })
            except Exception as exc:
                logger.warning("summary_table: {} failed: {}", seg, exc)
        return rows
