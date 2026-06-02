"""
comprehensive_data.py – Multi-source market data aggregator.

Sources (in order of reliability):
  1. Yahoo Finance (yfinance)  : fundamentals, shareholding, quarterly financials
  2. NSE via yfinance          : ticker suffix ".NS"
  3. BSE via yfinance          : ticker suffix ".BO"
  4. screener.in               : detailed Indian metrics (best-effort HTML scrape)

All methods are safe: they catch every exception and return empty dicts so
callers never get an uncaught error from an external data source.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
import requests
from loguru import logger

try:
    import yfinance as yf  # type: ignore
except ImportError:  # pragma: no cover
    yf = None  # type: ignore

_TICKER_SUFFIX: dict[str, str] = {"NSE": ".NS", "BSE": ".BO"}
_SCREENER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _yahoo_ticker(symbol: str, exchange: str = "NSE") -> str:
    suffix = _TICKER_SUFFIX.get(exchange.upper(), ".NS")
    return f"{symbol}{suffix}"


def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else round(f, 4)
    except Exception:
        return None


class ComprehensiveDataFetcher:
    """Aggregates fundamental and shareholding data from multiple sources."""

    # ── Yahoo Finance helpers ──────────────────────────────────────────────────

    def _yf_info(self, symbol: str, exchange: str) -> dict:
        if yf is None:
            return {}
        try:
            ticker = yf.Ticker(_yahoo_ticker(symbol, exchange))
            info = ticker.info or {}
            return info
        except Exception as exc:
            logger.debug(f"yfinance info({symbol}/{exchange}) failed: {exc}")
            return {}

    # ── Public methods ─────────────────────────────────────────────────────────

    def fetch_fundamentals(self, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
        """Key valuation and company info from Yahoo Finance."""
        info = self._yf_info(symbol, exchange)
        if not info:
            return {}

        return {
            "company_name":     info.get("longName") or info.get("shortName"),
            "sector":           info.get("sector"),
            "industry":         info.get("industry"),
            "description":      (info.get("longBusinessSummary") or "")[:300],
            "pe_ratio":         _safe_float(info.get("trailingPE")),
            "pb_ratio":         _safe_float(info.get("priceToBook")),
            "eps":              _safe_float(info.get("trailingEps")),
            "revenue":          _safe_float(info.get("totalRevenue")),
            "market_cap":       _safe_float(info.get("marketCap")),
            "dividend_yield":   _safe_float(info.get("dividendYield")),
            "debt_to_equity":   _safe_float(info.get("debtToEquity")),
            "roe":              _safe_float(info.get("returnOnEquity")),
            "roa":              _safe_float(info.get("returnOnAssets")),
            "profit_margin":    _safe_float(info.get("profitMargins")),
            "beta":             _safe_float(info.get("beta")),
            "week_52_high":     _safe_float(info.get("fiftyTwoWeekHigh")),
            "week_52_low":      _safe_float(info.get("fiftyTwoWeekLow")),
            "avg_volume":       info.get("averageVolume"),
            "float_shares":     info.get("floatShares"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "analyst_rating":   info.get("recommendationKey"),
            "target_mean_price": _safe_float(info.get("targetMeanPrice")),
        }

    def fetch_shareholding(self, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
        """Promoter, institutional, and public holding breakdown."""
        info = self._yf_info(symbol, exchange)
        result: dict[str, Any] = {
            "promoter_pct":     _safe_float((info.get("heldPercentInsiders") or 0) * 100),
            "institutional_pct": _safe_float((info.get("heldPercentInstitutions") or 0) * 100),
            "public_pct":       None,
            "top_holders":      [],
        }

        # Derive public holding
        promo = result["promoter_pct"] or 0.0
        inst = result["institutional_pct"] or 0.0
        result["public_pct"] = round(max(0.0, 100.0 - promo - inst), 2)

        if yf is None:
            return result
        try:
            ticker = yf.Ticker(_yahoo_ticker(symbol, exchange))
            ih = ticker.institutional_holders
            if ih is not None and not ih.empty:
                for _, row in ih.head(5).iterrows():
                    result["top_holders"].append({
                        "holder": str(row.get("Holder", "")),
                        "pct_out": _safe_float(row.get("% Out")),
                    })
        except Exception as exc:
            logger.debug(f"Institutional holders({symbol}): {exc}")

        return result

    def fetch_financials(self, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
        """Last 4 quarters of revenue and net income."""
        if yf is None:
            return {}
        try:
            ticker = yf.Ticker(_yahoo_ticker(symbol, exchange))
            income = ticker.quarterly_income_stmt

            result: dict[str, Any] = {"quarterly_revenue": [], "quarterly_profit": []}
            if income is None or income.empty:
                return result

            for label, out_key in [("Total Revenue", "quarterly_revenue"), ("Net Income", "quarterly_profit")]:
                if label in income.index:
                    row = income.loc[label]
                    for col, val in zip(row.index[:4], row.values[:4]):
                        if not pd.isna(val):
                            result[out_key].append({
                                "period": str(col.date()) if hasattr(col, "date") else str(col),
                                "value": int(val),
                            })
            return result
        except Exception as exc:
            logger.debug(f"Quarterly financials({symbol}): {exc}")
            return {}

    def fetch_peers(self, symbol: str, exchange: str = "NSE") -> list[dict[str, Any]]:
        """
        Build a basic peer list from Yahoo Finance.
        yfinance does not give a direct 'peers' API; we derive from
        the recommendations table and sector.
        """
        peers: list[dict] = []
        if yf is None:
            return peers
        try:
            ticker = yf.Ticker(_yahoo_ticker(symbol, exchange))
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                # recommendations contain analyst firm data, not peer symbols
                # Return the latest consensus instead
                latest = recs.tail(5)
                buys    = int(latest.get("strongBuy", pd.Series([0])).sum() + latest.get("buy", pd.Series([0])).sum())
                holds   = int(latest.get("hold", pd.Series([0])).sum())
                sells   = int(latest.get("sell", pd.Series([0])).sum() + latest.get("strongSell", pd.Series([0])).sum())
                peers.append({
                    "type": "analyst_consensus",
                    "buys": buys,
                    "holds": holds,
                    "sells": sells,
                })
        except Exception as exc:
            logger.debug(f"Peers/recommendations({symbol}): {exc}")
        return peers

    def fetch_screener_data(self, symbol: str) -> dict[str, str]:
        """
        Scrape key ratios from screener.in (best-effort).
        Returns {} if the page is unavailable or the HTML structure changed.
        """
        url = f"https://www.screener.in/company/{symbol.upper()}/"
        try:
            resp = requests.get(url, headers=_SCREENER_HEADERS, timeout=10)
            if resp.status_code != 200:
                logger.debug(f"screener.in returned {resp.status_code} for {symbol}")
                return {}

            from bs4 import BeautifulSoup  # type: ignore  # noqa: PLC0415
            soup = BeautifulSoup(resp.text, "html.parser")

            result: dict[str, str] = {}
            for li in soup.select("#top-ratios li"):
                name_el = li.select_one(".name")
                val_el  = li.select_one(".value") or li.select_one(".number")
                if name_el and val_el:
                    key = re.sub(r"\s+", "_", name_el.get_text(strip=True).lower())
                    key = re.sub(r"[^a-z0-9_]", "", key)
                    result[key] = val_el.get_text(strip=True)

            return result
        except Exception as exc:
            logger.debug(f"screener.in scrape({symbol}): {exc}")
            return {}

    def fetch_all(
        self,
        symbol: str,
        exchange: str = "NSE",
        include_screener: bool = True,
    ) -> dict[str, Any]:
        """
        Aggregate data from all available sources.

        Returns:
            {
              "fundamentals":  {...},
              "shareholding":  {...},
              "financials":    {...},
              "peers":         [...],
              "screener":      {...},
              "sources_used":  [...],
            }
        """
        sources_used: list[str] = []

        # Primary: NSE via Yahoo Finance
        fundamentals = self.fetch_fundamentals(symbol, exchange)
        if fundamentals:
            sources_used.append(f"yahoo-finance-{exchange.lower()}")

        shareholding = self.fetch_shareholding(symbol, exchange)
        if shareholding.get("top_holders") or shareholding.get("promoter_pct"):
            sources_used.append("yahoo-finance-shareholding")

        financials = self.fetch_financials(symbol, exchange)
        if financials.get("quarterly_revenue"):
            sources_used.append("yahoo-finance-financials")

        peers = self.fetch_peers(symbol, exchange)
        if peers:
            sources_used.append("yahoo-finance-recommendations")

        # Secondary: BSE data fills gaps if primary is NSE
        if exchange.upper() == "NSE":
            bse_fund = self.fetch_fundamentals(symbol, "BSE")
            if bse_fund:
                sources_used.append("yahoo-finance-bse")
                for k, v in bse_fund.items():
                    if v is not None and fundamentals.get(k) is None:
                        fundamentals[k] = v

        # Tertiary: screener.in (best-effort)
        screener: dict[str, str] = {}
        if include_screener:
            screener = self.fetch_screener_data(symbol)
            if screener:
                sources_used.append("screener.in")

        return {
            "fundamentals": fundamentals,
            "shareholding": shareholding,
            "financials":   financials,
            "peers":        peers,
            "screener":     screener,
            "sources_used": sources_used,
        }
