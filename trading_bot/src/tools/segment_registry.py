"""
segment_registry.py — Indian market segment & symbol registry.

Central lookup for symbol → yfinance ticker, exchange, lot size, tick size,
commission segment, and session hours across all Indian market segments:

    NSE Equity     RELIANCE, TCS, HDFCBANK, … (Nifty 50 + Nifty Next 50 + mid-cap)
    BSE Equity     same companies via .BO suffix; handles name differences
    NSE Indices    ^NSEI (Nifty 50), ^NSEBANK (Bank Nifty), ^CNXIT (IT), …
    BSE Indices    ^BSESN (Sensex), ^BSEMD (BSE Midcap), …
    NSE F&O        Index futures & options + stock F&O (SEBI lot sizes Nov-2024)
    MCX Commodity  GOLD, SILVER, CRUDEOIL, NATURALGAS, COPPER, ALUMINIUM, ZINC, LEAD
    NSE CDS        USDINR, EURINR, GBPINR, JPYINR currency futures & options

Data-source strategy:
    - NSE/BSE equity + indices  → yfinance (.NS / .BO / ^xxxx)
    - MCX commodities           → yfinance USD proxy (GC=F, CL=F, …) with note
    - NSE CDS currency          → yfinance forex (USDINR=X, …)
    - NSE F&O (live expiry)     → Kite Connect NFO exchange (requires login)
    - F&O backtesting           → yfinance underlying (NIFTY.NS / stock.NS)
                                  with lot-size-scaled position sizing

Usage:
    reg = SegmentRegistry()

    info = reg.resolve("RELIANCE", exchange="NSE")
    # → SymbolInfo(yf_ticker="RELIANCE.NS", segment="EQUITY",
    #              commission_segment="EQUITY_DELIVERY", lot_size=1)

    info = reg.resolve("NIFTY", exchange="NFO", instrument="FUTURES")
    # → SymbolInfo(yf_ticker="^NSEI", segment="FNO_FUTURES",
    #              commission_segment="FNO_FUTURES", lot_size=75,
    #              notes="yfinance returns index spot; scale by lot_size for F&O PnL")

    info = reg.resolve("GOLD", exchange="MCX")
    # → SymbolInfo(yf_ticker="GC=F", segment="COMMODITY",
    #              commission_segment="MCX_COMMODITY", currency="USD", usd_proxy=True)

    # Auto-detect exchange from symbol name
    info = reg.auto_detect("USDINR")
    # → SymbolInfo(exchange="CDS", …)

    # Get commission segment for use with CommissionCalculator
    seg = reg.get_commission_segment("NIFTY", exchange="NFO", instrument="FUTURES")
    # → "FNO_FUTURES"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger


# ── Symbol info dataclass ──────────────────────────────────────────────────────

@dataclass
class SymbolInfo:
    """
    Fully resolved instrument metadata for a given symbol + exchange.

    Fields:
        symbol              Original user-supplied symbol (uppercased)
        exchange            Canonical exchange: NSE | BSE | NFO | MCX | CDS
        segment             Instrument segment: EQUITY | INDEX | FNO_FUTURES |
                            FNO_OPTIONS | COMMODITY | CURRENCY
        instrument          SPOT | FUTURES | OPTIONS
        yf_ticker           yfinance ticker string (None = Kite-only / unavailable)
        kite_exchange       Kite Connect exchange code for live data (NFO, MCX, CDS)
        lot_size            Contract/lot size. 1 for equity spot.
        tick_size           Minimum price movement in INR (or USD for proxies)
        currency            Price currency: "INR" | "USD"
        usd_proxy           True when MCX data is sourced from USD-denominated futures
        commission_segment  Segment key for CommissionCalculator.calculate()
        notes               Any data-source caveats the caller should display
    """
    symbol: str
    exchange: str
    segment: str
    instrument: str = "SPOT"
    yf_ticker: Optional[str] = None
    kite_exchange: Optional[str] = None
    lot_size: int = 1
    tick_size: float = 0.05
    currency: str = "INR"
    usd_proxy: bool = False
    commission_segment: str = "EQUITY_DELIVERY"
    notes: str = ""

    def is_tradable_via_yfinance(self) -> bool:
        return self.yf_ticker is not None

    def is_index(self) -> bool:
        return self.segment == "INDEX"

    def scaled_turnover(self, price: float, quantity: float = 1.0) -> float:
        """Return INR turnover accounting for lot size: price × quantity × lot_size."""
        return price * quantity * self.lot_size


# ── Registry class ─────────────────────────────────────────────────────────────

class SegmentRegistry:
    """
    Central lookup registry for all Indian market instruments.

    Thread-safe for read-only access (all data is class-level constants).
    """

    # ── NSE / BSE suffix ────────────────────────────────────────────────────────
    _NSE_SUFFIX = ".NS"
    _BSE_SUFFIX = ".BO"

    # ── Special NSE symbols that need URL-encoding or different yfinance names ──
    # Maps NSE canonical name → yfinance ticker
    _NSE_SPECIAL: dict[str, str] = {
        "M&M":       "M%26M.NS",
        "BAJAJ-AUTO": "BAJAJ-AUTO.NS",
        "NIFTY50":   "^NSEI",    # treat as alias for index resolution
        "NIFTY":     "^NSEI",
    }

    # ── BSE symbols — maps NSE common name → BSE yfinance ticker ───────────────
    # Most symbols work as SYMBOL.BO directly.
    # This map only covers exceptions where the BSE name differs.
    _BSE_OVERRIDE: dict[str, str] = {
        "M&M":          "M%26M.BO",
        "BAJAJ-AUTO":   "BAJAJ-AUTO.BO",
        "HDFCLIFE":     "HDFCLIFE.BO",
        "SBILIFE":      "SBILIFE.BO",
        "BAJAJFINSV":   "BAJAJFINSV.BO",
        "ADANIENT":     "ADANIENT.BO",
        "ADANIPORTS":   "ADANIPORTS.BO",
        "TATACONSUM":   "TATACONSUM.BO",
    }

    # ── NSE Index map ──────────────────────────────────────────────────────────
    _NSE_INDEX_MAP: dict[str, str] = {
        "NIFTY50":          "^NSEI",
        "NIFTY":            "^NSEI",
        "BANKNIFTY":        "^NSEBANK",
        "FINNIFTY":         "^CNXFIN",
        "MIDCPNIFTY":       "^NSEMDCP50",
        "NIFTYIT":          "^CNXIT",
        "NIFTYPHARMA":      "^CNXPHARMA",
        "NIFTYAUTO":        "^CNXAUTO",
        "NIFTYFMCG":        "^CNXFMCG",
        "NIFTYMETAL":       "^CNXMETAL",
        "NIFTYREALTY":      "^CNXREALTY",
        "NIFTYINFRA":       "^CNXINFRA",
        "NIFTYNEXT50":      "^NSMIDCP",
        "NIFTY100":         "^CNX100",
        "NIFTY200":         "^CNX200",
        "NIFTY500":         "^CNX500",
        "NIFTYMIDCAP100":   "^NSEMDCP100",
        "NIFTYSMALLCAP100": "^CNXSC",
    }

    # ── BSE Index map ──────────────────────────────────────────────────────────
    _BSE_INDEX_MAP: dict[str, str] = {
        "SENSEX":       "^BSESN",
        "BSE200":       "^BSE200",
        "BSE500":       "^BSE500",
        "BSEMIDCAP":    "^BSEMD",
        "BSESMALLCAP":  "^BSESML",
        "BSEIT":        "^BSEIT",
        "BSEPHARMA":    "^BSEPHRM",
        "BSEFMCG":      "^BSEFMCG",
        "BSEAUTO":      "^BSEAUTO",
        "BSEBANK":      "^BSEBANK",
        "BSEFINANCE":   "^BSEFN",
        "BSEREALTY":    "^BSERT",
    }

    # ── F&O lot sizes — SEBI mandated (effective Nov 2024 revision) ─────────────
    # Source: SEBI circular SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/124 (Oct 2024)
    # For stocks: SEBI quarterly lot-size revision (Jan 2025)
    _FNO_LOT_SIZES: dict[str, int] = {
        # Index derivatives
        "NIFTY":        75,
        "BANKNIFTY":    15,
        "FINNIFTY":     40,
        "MIDCPNIFTY":   75,
        "SENSEX":       10,    # BSE Sensex futures
        # Nifty 50 stock F&O (lot sizes as of Jan 2025)
        "RELIANCE":     250,
        "TCS":          150,
        "HDFCBANK":     550,
        "INFY":         300,
        "HINDUNILVR":   300,
        "ICICIBANK":    700,
        "KOTAKBANK":    400,
        "SBIN":         1500,
        "BHARTIARTL":   514,
        "ITC":          3200,
        "ASIANPAINT":   200,
        "BAJFINANCE":   125,
        "HCLTECH":      350,
        "WIPRO":        1500,
        "AXISBANK":     625,
        "MARUTI":       100,
        "LT":           300,
        "ULTRACEMCO":   100,
        "TITAN":        375,
        "NESTLEIND":    50,
        "SUNPHARMA":    700,
        "POWERGRID":    2700,
        "NTPC":         2700,
        "TECHM":        500,
        "ONGC":         1925,
        "BAJAJFINSV":   125,
        "JSWSTEEL":     600,
        "TATAMOTORS":   1425,
        "TATASTEEL":    4375,
        "DIVISLAB":     150,
        "DRREDDY":      125,
        "CIPLA":        650,
        "EICHERMOT":    100,
        "BPCL":         1800,
        "COALINDIA":    2700,
        "HEROMOTOCO":   150,
        "BRITANNIA":    100,
        "GRASIM":       475,
        "SHREECEM":     25,
        "HINDALCO":     2150,
        "ADANIPORTS":   625,
        "ADANIENT":     250,
        "TATACONSUM":   800,
        "APOLLOHOSP":   125,
        "M&M":          700,
        "INDUSINDBK":   525,
        "SBILIFE":      750,
        "HDFCLIFE":     1100,
        "UPL":          1300,
        # Popular mid-cap F&O stocks
        "PIDILITIND":   200,
        "BERGEPAINT":   1100,
        "HAVELLS":      500,
        "SIEMENS":      100,
        "ABB":          150,
        "BOSCHLTD":     25,
        "MCDOWELL-N":   500,
        "COLPAL":       500,
        "MARICO":       1200,
        "GODREJCP":     500,
        "DABUR":        1250,
        "TRENT":        280,
        "IRCTC":        875,
        "DMART":        125,
        "ZOMATO":       4500,
        "PAYTM":        2000,
        "NYKAA":        3500,
        "POLICYBZR":    700,
        "NAUKRI":       125,
        "BANKBARODA":   3750,
        "PNB":          8000,
        "CANBK":        3000,
        "FEDERALBNK":   5000,
        "IDFCFIRSTB":   6250,
        "MUTHOOTFIN":   500,
        "CHOLAFIN":     625,
        "BAJAJHLDNG":   50,
        "LICHSGFIN":    1000,
        "RECLTD":       2850,
        "PFC":          2700,
        "NHPC":         7500,
        "TATAPOWER":    3375,
        "TORNTPOWER":   450,
        "CESC":         800,
        "SUZLON":       14000,
        "INOXWIND":     2600,
        "VEDL":         2500,
        "NMDC":         5400,
        "SAIL":         7500,
        "JINDALSTEL":   1250,
        "APLAPOLLO":    750,
        "RAMCOCEM":     525,
        "JKCEMENT":     100,
        "AMBUJACEM":    2000,
        "ACCLTD":       400,
        "GMRAIRPORT":   14000,
        "INDIGO":       300,
        "SPICEJET":     7500,
        "OBEROIRLTY":   400,
        "GODREJPROP":   425,
        "DLF":          1650,
        "PHOENIXLTD":   425,
        "PRESTIGE":     800,
    }

    # ── Tick sizes per segment ──────────────────────────────────────────────────
    _TICK_SIZES: dict[str, float] = {
        "NSE_EQUITY":    0.05,
        "BSE_EQUITY":    0.05,
        "NFO_FUTURES":   0.05,
        "NFO_OPTIONS":   0.05,
        "MCX_COMMODITY": 1.00,    # varies — GOLD: 1, CRUDEOIL: 1, COPPER: 0.05
        "CDS_CURRENCY":  0.0025,  # USDINR tick = ₹0.0025
    }

    # ── MCX commodity contract specs ────────────────────────────────────────────
    # yf_ticker: nearest US futures proxy (USD-denominated)
    # lot_size: MCX contract unit
    # unit: contract unit label
    # tick_size: MCX tick in INR
    _MCX_CONTRACTS: dict[str, dict] = {
        "GOLD":       {"yf_ticker": "GC=F",  "lot_size": 1,     "unit": "10g",   "tick_size": 1.0},
        "GOLDM":      {"yf_ticker": "GC=F",  "lot_size": 1,     "unit": "1g",    "tick_size": 1.0},
        "GOLDGUINEA": {"yf_ticker": "GC=F",  "lot_size": 8,     "unit": "8g",    "tick_size": 1.0},
        "GOLDPETAL":  {"yf_ticker": "GC=F",  "lot_size": 1,     "unit": "1g",    "tick_size": 0.5},
        "SILVER":     {"yf_ticker": "SI=F",  "lot_size": 30,    "unit": "kg",    "tick_size": 1.0},
        "SILVERM":    {"yf_ticker": "SI=F",  "lot_size": 5,     "unit": "kg",    "tick_size": 1.0},
        "SILVERMIC":  {"yf_ticker": "SI=F",  "lot_size": 1,     "unit": "kg",    "tick_size": 1.0},
        "CRUDEOIL":   {"yf_ticker": "CL=F",  "lot_size": 100,   "unit": "bbl",   "tick_size": 1.0},
        "CRUDEOILM":  {"yf_ticker": "CL=F",  "lot_size": 10,    "unit": "bbl",   "tick_size": 1.0},
        "NATURALGAS": {"yf_ticker": "NG=F",  "lot_size": 1250,  "unit": "mmBTU", "tick_size": 0.10},
        "NATURALGASM":{"yf_ticker": "NG=F",  "lot_size": 250,   "unit": "mmBTU", "tick_size": 0.10},
        "COPPER":     {"yf_ticker": "HG=F",  "lot_size": 2500,  "unit": "kg",    "tick_size": 0.05},
        "COPPERM":    {"yf_ticker": "HG=F",  "lot_size": 250,   "unit": "kg",    "tick_size": 0.05},
        "ALUMINIUM":  {"yf_ticker": "ALI=F", "lot_size": 5000,  "unit": "kg",    "tick_size": 0.05},
        "ALUMINM":    {"yf_ticker": "ALI=F", "lot_size": 1000,  "unit": "kg",    "tick_size": 0.05},
        "ZINC":       {"yf_ticker": "ZC=F",  "lot_size": 5000,  "unit": "kg",    "tick_size": 0.05},
        "ZINCMINI":   {"yf_ticker": "ZC=F",  "lot_size": 1000,  "unit": "kg",    "tick_size": 0.05},
        "LEAD":       {"yf_ticker": "LE=F",  "lot_size": 5000,  "unit": "kg",    "tick_size": 0.05},
        "LEADMINI":   {"yf_ticker": "LE=F",  "lot_size": 1000,  "unit": "kg",    "tick_size": 0.05},
        "NICKEL":     {"yf_ticker": "NI=F",  "lot_size": 250,   "unit": "kg",    "tick_size": 0.10},
        "NICKELM":    {"yf_ticker": "NI=F",  "lot_size": 100,   "unit": "kg",    "tick_size": 0.10},
        "MENTHAOIL":  {"yf_ticker": None,    "lot_size": 360,   "unit": "kg",    "tick_size": 0.10},
        "CARDAMOM":   {"yf_ticker": None,    "lot_size": 100,   "unit": "kg",    "tick_size": 0.10},
        "CASTOR":     {"yf_ticker": None,    "lot_size": 10,    "unit": "quintals","tick_size":1.0},
    }

    # ── NSE CDS currency futures ────────────────────────────────────────────────
    _CDS_CONTRACTS: dict[str, dict] = {
        "USDINR":  {"yf_ticker": "USDINR=X",  "lot_size": 1000,  "tick_size": 0.0025, "kite_name": "USDINR"},
        "EURINR":  {"yf_ticker": "EURINR=X",  "lot_size": 1000,  "tick_size": 0.0025, "kite_name": "EURINR"},
        "GBPINR":  {"yf_ticker": "GBPINR=X",  "lot_size": 1000,  "tick_size": 0.0025, "kite_name": "GBPINR"},
        "JPYINR":  {"yf_ticker": "JPYINR=X",  "lot_size": 1000,  "tick_size": 0.0025, "kite_name": "JPYINR"},
        "EURUSD":  {"yf_ticker": "EURUSD=X",  "lot_size": 1000,  "tick_size": 0.0001, "kite_name": "EURUSD"},
        "GBPUSD":  {"yf_ticker": "GBPUSD=X",  "lot_size": 1000,  "tick_size": 0.0001, "kite_name": "GBPUSD"},
        "USDJPY":  {"yf_ticker": "USDJPY=X",  "lot_size": 1000,  "tick_size": 0.01,   "kite_name": "USDJPY"},
    }

    # ── Market session hours (IST) ──────────────────────────────────────────────
    _SESSION_HOURS: dict[str, dict] = {
        "NSE":  {"open": "09:15", "close": "15:30", "pre_open": "09:00", "tz": "Asia/Kolkata"},
        "BSE":  {"open": "09:15", "close": "15:30", "pre_open": "09:00", "tz": "Asia/Kolkata"},
        "NFO":  {"open": "09:15", "close": "15:30", "pre_open": "09:00", "tz": "Asia/Kolkata"},
        "MCX":  {"open": "09:00", "close": "23:30", "pre_open": "08:55", "tz": "Asia/Kolkata"},
        "CDS":  {"open": "09:00", "close": "17:00", "pre_open": "08:55", "tz": "Asia/Kolkata"},
    }

    # ── Commission segment mapping ──────────────────────────────────────────────
    # Maps (segment, instrument) → CommissionCalculator segment key
    _COMMISSION_SEGMENT_MAP: dict[tuple[str, str], str] = {
        ("EQUITY",      "SPOT"):    "EQUITY_DELIVERY",
        ("EQUITY",      "INTRADAY"):"EQUITY_INTRADAY",
        ("INDEX",       "SPOT"):    "EQUITY_INTRADAY",   # index = no delivery
        ("FNO_FUTURES", "FUTURES"): "FNO_FUTURES",
        ("FNO_OPTIONS", "OPTIONS"): "FNO_OPTIONS",
        ("COMMODITY",   "FUTURES"): "MCX_COMMODITY",
        ("CURRENCY",    "FUTURES"): "CDS_CURRENCY",
        ("CURRENCY",    "OPTIONS"): "CDS_CURRENCY",
    }

    # ── All recognised NSE equity symbols (Nifty 50 + Nifty Next 50) ──────────
    _NSE_EQUITY_UNIVERSE: set[str] = {
        # Nifty 50
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "HINDUNILVR", "ICICIBANK",
        "KOTAKBANK", "SBIN", "BHARTIARTL", "ITC", "ASIANPAINT", "BAJFINANCE",
        "HCLTECH", "WIPRO", "AXISBANK", "MARUTI", "LT", "ULTRACEMCO", "TITAN",
        "NESTLEIND", "SUNPHARMA", "POWERGRID", "NTPC", "TECHM", "ONGC",
        "BAJAJFINSV", "JSWSTEEL", "TATAMOTORS", "TATASTEEL", "DIVISLAB",
        "DRREDDY", "CIPLA", "EICHERMOT", "BPCL", "COALINDIA", "HEROMOTOCO",
        "BRITANNIA", "GRASIM", "SHREECEM", "HINDALCO", "ADANIPORTS", "ADANIENT",
        "TATACONSUM", "APOLLOHOSP", "BAJAJ-AUTO", "M&M", "INDUSINDBK",
        "SBILIFE", "HDFCLIFE", "UPL",
        # Nifty Next 50
        "ADANIGREEN", "ADANITRANS", "AMBUJACEM", "DMART", "GODREJCP",
        "HAVELLS", "INDHOTEL", "LICI", "LODHA", "MARICO", "MUTHOOTFIN",
        "NMDC", "OFSS", "PIDILITIND", "RECLTD", "SIEMENS", "TATAELXSI",
        "TRENT", "TORNTPHARM", "VEDL", "ZOMATO", "NAUKRI", "PAYTM",
        "BANKBARODA", "CANBK", "PNB", "PFC", "NHPC", "TATAPOWER", "DLF",
        "IRCTC", "IRFC", "SAIL", "JINDALSTEL", "GODREJPROP", "BERGEPAINT",
        "COLPAL", "DABUR", "EMAMILTD", "OBEROIRLTY", "PHOENIXLTD",
        "PRESTIGE", "IDFCFIRSTB", "FEDERALBNK", "CHOLAFIN", "ABB", "BOSCHLTD",
        "DIXON", "LTIM", "MPHASIS",
    }

    # ─────────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────────

    def resolve(
        self,
        symbol: str,
        exchange: str = "NSE",
        instrument: str = "SPOT",
    ) -> SymbolInfo:
        """
        Resolve a symbol to a fully-populated SymbolInfo.

        Args:
            symbol:     User-facing symbol: "RELIANCE", "GOLD", "USDINR",
                        "NIFTY50", "BANKNIFTY", "CRUDEOIL", "SENSEX", …
            exchange:   "NSE" | "BSE" | "NFO" | "MCX" | "CDS"
                        Defaults to "NSE". For F&O pass "NFO".
            instrument: "SPOT" | "FUTURES" | "OPTIONS" | "INTRADAY"
                        Affects commission_segment selection.

        Returns:
            SymbolInfo with all fields populated.

        Raises:
            ValueError if the symbol cannot be resolved for the given exchange.
        """
        sym = symbol.upper().strip()
        exch = exchange.upper().strip()
        inst = instrument.upper().strip()

        if exch == "MCX":
            return self._resolve_mcx(sym, inst)
        if exch == "CDS":
            return self._resolve_cds(sym, inst)
        if exch in ("NFO", "BFO"):
            return self._resolve_fno(sym, inst, exch)
        if exch == "BSE":
            return self._resolve_bse(sym, inst)
        if exch == "NSE":
            return self._resolve_nse(sym, inst)

        raise ValueError(
            f"Unknown exchange '{exchange}'. "
            f"Valid: NSE | BSE | NFO | MCX | CDS"
        )

    def auto_detect(self, symbol: str, instrument: str = "SPOT") -> SymbolInfo:
        """
        Infer the most likely exchange from the symbol and resolve.

        Priority: MCX → CDS → NSE Index → NSE Equity → BSE Equity

        Useful when the caller does not supply an explicit exchange.
        """
        sym = symbol.upper().strip()

        if sym in self._MCX_CONTRACTS:
            return self.resolve(sym, exchange="MCX", instrument=instrument)
        if sym in self._CDS_CONTRACTS:
            return self.resolve(sym, exchange="CDS", instrument=instrument)
        if sym in self._NSE_INDEX_MAP:
            return self.resolve(sym, exchange="NSE", instrument=instrument)
        if sym in self._BSE_INDEX_MAP:
            return self.resolve(sym, exchange="BSE", instrument=instrument)
        # Default to NSE equity
        return self.resolve(sym, exchange="NSE", instrument=instrument)

    def get_commission_segment(
        self,
        symbol: str,
        exchange: str = "NSE",
        instrument: str = "SPOT",
    ) -> str:
        """
        Return the CommissionCalculator segment key for a given instrument.

        Examples:
            get_commission_segment("RELIANCE", "NSE", "SPOT")     → "EQUITY_DELIVERY"
            get_commission_segment("RELIANCE", "NSE", "INTRADAY") → "EQUITY_INTRADAY"
            get_commission_segment("NIFTY", "NFO", "FUTURES")     → "FNO_FUTURES"
            get_commission_segment("GOLD", "MCX", "FUTURES")      → "MCX_COMMODITY"
            get_commission_segment("USDINR", "CDS", "FUTURES")    → "CDS_CURRENCY"
        """
        info = self.resolve(symbol, exchange, instrument)
        return info.commission_segment

    def get_lot_size(self, symbol: str, exchange: str = "NFO") -> int:
        """
        Return the F&O or commodity lot size for a symbol.
        Returns 1 for all equity spot instruments.
        """
        sym = symbol.upper().strip()
        exch = exchange.upper().strip()
        if exch == "MCX":
            return self._MCX_CONTRACTS.get(sym, {}).get("lot_size", 1)
        if exch == "CDS":
            return self._CDS_CONTRACTS.get(sym, {}).get("lot_size", 1000)
        return self._FNO_LOT_SIZES.get(sym, 1)

    def session_hours(self, exchange: str) -> dict:
        """
        Return market session hours for an exchange.

        Returns dict with keys: open, close, pre_open, tz  (all strings, IST)
        """
        exch = exchange.upper().strip()
        if exch not in self._SESSION_HOURS:
            raise ValueError(
                f"Unknown exchange '{exchange}'. "
                f"Valid: {list(self._SESSION_HOURS.keys())}"
            )
        return dict(self._SESSION_HOURS[exch])

    def list_symbols(self, exchange: str) -> list[str]:
        """Return all known symbols for a given exchange (sorted)."""
        exch = exchange.upper().strip()
        if exch == "MCX":
            return sorted(self._MCX_CONTRACTS.keys())
        if exch == "CDS":
            return sorted(self._CDS_CONTRACTS.keys())
        if exch in ("NSE", "NFO"):
            return sorted(
                list(self._NSE_EQUITY_UNIVERSE)
                + list(self._NSE_INDEX_MAP.keys())
            )
        if exch == "BSE":
            return sorted(
                list(self._NSE_EQUITY_UNIVERSE)
                + list(self._BSE_INDEX_MAP.keys())
            )
        raise ValueError(f"Unknown exchange '{exchange}'")

    def list_segments(self) -> list[str]:
        """Return all supported segment identifiers."""
        return [
            "NSE_EQUITY", "BSE_EQUITY", "NSE_INDEX", "BSE_INDEX",
            "NFO_FUTURES", "NFO_OPTIONS",
            "MCX_COMMODITY", "CDS_CURRENCY",
        ]

    def is_index(self, symbol: str) -> bool:
        """Return True if the symbol is a market index."""
        sym = symbol.upper().strip()
        return sym in self._NSE_INDEX_MAP or sym in self._BSE_INDEX_MAP

    def is_fno_eligible(self, symbol: str) -> bool:
        """Return True if the symbol has a known F&O contract."""
        return symbol.upper().strip() in self._FNO_LOT_SIZES

    # ─────────────────────────────────────────────────────────────────────────────
    # Private resolvers
    # ─────────────────────────────────────────────────────────────────────────────

    def _resolve_nse(self, sym: str, inst: str) -> SymbolInfo:
        """Resolve NSE equity or NSE index symbol."""
        # Index check first
        if sym in self._NSE_INDEX_MAP:
            return SymbolInfo(
                symbol=sym,
                exchange="NSE",
                segment="INDEX",
                instrument="SPOT",
                yf_ticker=self._NSE_INDEX_MAP[sym],
                lot_size=1,
                tick_size=0.05,
                currency="INR",
                commission_segment="EQUITY_INTRADAY",
                notes="Index — no delivery; intraday commission rate applied.",
            )

        # Special symbol override (M&M, BAJAJ-AUTO etc.)
        yf_ticker = self._NSE_SPECIAL.get(sym, f"{sym}{self._NSE_SUFFIX}")

        commission_seg = self._COMMISSION_SEGMENT_MAP.get(
            ("EQUITY", inst), "EQUITY_DELIVERY"
        )

        return SymbolInfo(
            symbol=sym,
            exchange="NSE",
            segment="EQUITY",
            instrument=inst,
            yf_ticker=yf_ticker,
            kite_exchange="NSE",
            lot_size=1,
            tick_size=self._TICK_SIZES["NSE_EQUITY"],
            currency="INR",
            commission_segment=commission_seg,
        )

    def _resolve_bse(self, sym: str, inst: str) -> SymbolInfo:
        """Resolve BSE equity or BSE index symbol."""
        if sym in self._BSE_INDEX_MAP:
            return SymbolInfo(
                symbol=sym,
                exchange="BSE",
                segment="INDEX",
                instrument="SPOT",
                yf_ticker=self._BSE_INDEX_MAP[sym],
                lot_size=1,
                tick_size=0.01,
                currency="INR",
                commission_segment="EQUITY_INTRADAY",
                notes="BSE index — intraday commission rate applied.",
            )

        # Use override map if available, else append .BO
        yf_ticker = self._BSE_OVERRIDE.get(sym, f"{sym}{self._BSE_SUFFIX}")

        commission_seg = self._COMMISSION_SEGMENT_MAP.get(
            ("EQUITY", inst), "EQUITY_DELIVERY"
        )

        return SymbolInfo(
            symbol=sym,
            exchange="BSE",
            segment="EQUITY",
            instrument=inst,
            yf_ticker=yf_ticker,
            kite_exchange="BSE",
            lot_size=1,
            tick_size=self._TICK_SIZES["BSE_EQUITY"],
            currency="INR",
            commission_segment=commission_seg,
            notes="BSE equity. Verify yfinance availability for less-liquid scrips.",
        )

    def _resolve_fno(self, sym: str, inst: str, exch: str) -> SymbolInfo:
        """
        Resolve NSE F&O symbol.

        For backtesting we use the underlying equity/index yfinance ticker.
        The lot_size field allows callers to scale position sizing correctly.
        Live expiry-specific Kite tokens are handled by the trading agent.
        """
        lot = self._FNO_LOT_SIZES.get(sym, 1)

        # Determine underlying yfinance ticker
        if sym in self._NSE_INDEX_MAP:
            underlying_yf = self._NSE_INDEX_MAP[sym]
            underlying_type = "INDEX"
        else:
            underlying_yf = self._NSE_SPECIAL.get(sym, f"{sym}{self._NSE_SUFFIX}")
            underlying_type = "STOCK"

        if inst in ("FUTURES", "SPOT"):
            seg = "FNO_FUTURES"
            commission_seg = "FNO_FUTURES"
        else:
            seg = "FNO_OPTIONS"
            commission_seg = "FNO_OPTIONS"

        return SymbolInfo(
            symbol=sym,
            exchange=exch,
            segment=seg,
            instrument=inst if inst != "SPOT" else "FUTURES",
            yf_ticker=underlying_yf,
            kite_exchange=exch,
            lot_size=lot,
            tick_size=self._TICK_SIZES["NFO_FUTURES"],
            currency="INR",
            commission_segment=commission_seg,
            notes=(
                f"Underlying ({underlying_type}) yfinance ticker used for backtesting. "
                f"Lot size {lot}. For live expiry data use Kite NFO."
            ),
        )

    def _resolve_mcx(self, sym: str, inst: str) -> SymbolInfo:
        """Resolve MCX commodity symbol."""
        spec = self._MCX_CONTRACTS.get(sym)
        if spec is None:
            raise ValueError(
                f"Unknown MCX symbol '{sym}'. "
                f"Known: {sorted(self._MCX_CONTRACTS.keys())}"
            )

        yf_ticker = spec["yf_ticker"]
        # A contract is a USD proxy when it has a yfinance ticker (all non-agri).
        # Agri contracts (MENTHAOIL, CARDAMOM, CASTOR) have yf_ticker=None and are INR.
        is_usd_proxy = spec.get("usd_proxy", yf_ticker is not None)

        notes = ""
        if is_usd_proxy and yf_ticker:
            notes = (
                f"USD proxy ({yf_ticker}). Apply USDINR conversion for INR prices. "
                f"MCX contract unit: {spec['unit']}."
            )
        elif yf_ticker is None:
            notes = "No yfinance proxy available. Use Kite MCX for live data."

        return SymbolInfo(
            symbol=sym,
            exchange="MCX",
            segment="COMMODITY",
            instrument=inst if inst != "SPOT" else "FUTURES",
            yf_ticker=yf_ticker,
            kite_exchange="MCX",
            lot_size=spec["lot_size"],
            tick_size=spec.get("tick_size", 1.0),
            currency="USD" if is_usd_proxy else "INR",
            usd_proxy=is_usd_proxy,
            commission_segment="MCX_COMMODITY",
            notes=notes,
        )

    def _resolve_cds(self, sym: str, inst: str) -> SymbolInfo:
        """Resolve NSE CDS currency futures symbol."""
        spec = self._CDS_CONTRACTS.get(sym)
        if spec is None:
            raise ValueError(
                f"Unknown CDS symbol '{sym}'. "
                f"Known: {sorted(self._CDS_CONTRACTS.keys())}"
            )

        return SymbolInfo(
            symbol=sym,
            exchange="CDS",
            segment="CURRENCY",
            instrument=inst if inst != "SPOT" else "FUTURES",
            yf_ticker=spec["yf_ticker"],
            kite_exchange="CDS",
            lot_size=spec["lot_size"],
            tick_size=spec["tick_size"],
            currency="INR",
            commission_segment="CDS_CURRENCY",
            notes="NSE CDS currency futures. yfinance forex pair used for backtesting.",
        )
