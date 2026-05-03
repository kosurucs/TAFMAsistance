"""
kite_tools.py – Zerodha Kite Connect wrappers.

Provides:
  - KiteAuthManager   : TOTP-based daily login automation
  - KiteDataFetcher   : 1-minute OHLCV data retrieval
  - KiteOrderManager  : Order placement (live + paper-trade mode)
  - KitePortfolio     : Portfolio / position queries
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any

import pyotp
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ── Optional heavy import so the module can be imported in tests without
#    a full kiteconnect installation. ──────────────────────────────────────────
try:
    from kiteconnect import KiteConnect  # type: ignore
except ImportError:  # pragma: no cover
    KiteConnect = None  # type: ignore


class KiteAuthManager:
    """Handles TOTP-based login and access-token management."""

    LOGIN_URL = "https://kite.zerodha.com/api/login"
    TWOFA_URL = "https://kite.zerodha.com/api/twofa"

    def __init__(self) -> None:
        self.api_key: str = os.environ["KITE_API_KEY"]
        self.api_secret: str = os.environ["KITE_API_SECRET"]
        self.totp_secret: str = os.environ["KITE_TOTP_SECRET"]
        self._kite: Any | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_kite_session(self) -> Any:
        """Return an authenticated KiteConnect instance.

        Uses the ``KITE_ACCESS_TOKEN`` env-var if it is already set so that
        repeated calls within the same day skip the TOTP round-trip.
        """
        if KiteConnect is None:
            raise RuntimeError(
                "kiteconnect package is not installed. "
                "Run: pip install kiteconnect"
            )
        if self._kite is not None:
            return self._kite

        access_token = os.environ.get("KITE_ACCESS_TOKEN", "").strip()
        if not access_token:
            access_token = self._login_with_totp()

        kite = KiteConnect(api_key=self.api_key)
        kite.set_access_token(access_token)
        self._kite = kite
        logger.info("KiteConnect session established.")
        return kite

    def invalidate(self) -> None:
        """Force a fresh login on the next call to get_kite_session."""
        self._kite = None
        os.environ.pop("KITE_ACCESS_TOKEN", None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _login_with_totp(self) -> str:
        """Perform interactive TOTP login and return the access token."""
        import requests  # local import – avoids hard dependency at module level

        totp = pyotp.TOTP(self.totp_secret)

        # Step 1 – username/password login to obtain request_token.
        #   In practice the user must supply their Zerodha user-id & password;
        #   for fully automated setups, store them in .env (KITE_USER_ID /
        #   KITE_PASSWORD).  The code below uses a headless flow only when
        #   those variables are set; otherwise it falls back to asking the
        #   user to paste the request_token manually.
        user_id = os.environ.get("KITE_USER_ID", "")
        password = os.environ.get("KITE_PASSWORD", "")

        if user_id and password:
            request_token = self._automated_login(
                requests, user_id, password, totp.now()
            )
        else:
            logger.warning(
                "KITE_USER_ID / KITE_PASSWORD not set. "
                "Please visit the login URL manually and paste the "
                "request_token from the redirect URL."
            )
            kite_tmp = KiteConnect(api_key=self.api_key)
            print(f"\nLogin URL: {kite_tmp.login_url()}\n")
            request_token = input("Paste request_token here: ").strip()

        kite = KiteConnect(api_key=self.api_key)
        data = kite.generate_session(request_token, api_secret=self.api_secret)
        access_token: str = data["access_token"]

        # Persist so the process can reuse it until the env is cleared.
        os.environ["KITE_ACCESS_TOKEN"] = access_token
        logger.info("Login successful; access token acquired.")
        return access_token

    @staticmethod
    def _automated_login(
        requests_module: Any,
        user_id: str,
        password: str,
        totp_code: str,
    ) -> str:
        """Headless login using the Zerodha session API."""
        session = requests_module.Session()

        # Phase 1 – credentials
        resp = session.post(
            KiteAuthManager.LOGIN_URL,
            data={"user_id": user_id, "password": password},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        request_id: str = payload["data"]["request_id"]

        # Phase 2 – TOTP
        resp2 = session.post(
            KiteAuthManager.TWOFA_URL,
            data={
                "user_id": user_id,
                "request_id": request_id,
                "twofa_value": totp_code,
                "twofa_type": "totp",
            },
            timeout=10,
        )
        resp2.raise_for_status()
        redirect_url: str = resp2.url
        # The request_token is embedded in the redirect URL as a query param.
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(redirect_url)
        token = parse_qs(parsed.query).get("request_token", [None])[0]
        if not token:
            raise ValueError(
                f"Could not extract request_token from redirect URL: {redirect_url}"
            )
        return token


class KiteDataFetcher:
    """Fetches 1-minute OHLCV data from Zerodha."""

    def __init__(self, kite: Any) -> None:
        self._kite = kite

    def get_ohlcv(
        self,
        instrument_token: int,
        interval: str = "minute",
        days_back: int = 1,
    ) -> list[dict[str, Any]]:
        """Return OHLCV candles for *instrument_token*.

        Args:
            instrument_token: Zerodha numeric instrument token.
            interval: Kite candle interval (default ``"minute"``).
            days_back: How many calendar days of history to fetch.

        Returns:
            List of candle dicts with keys:
            ``date, open, high, low, close, volume``.
        """
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days_back)

        candles: list[dict[str, Any]] = self._kite.historical_data(
            instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
        )
        logger.debug(
            "Fetched {} candles for token {} ({}).",
            len(candles),
            instrument_token,
            interval,
        )
        return candles

    def get_quote(self, symbols: list[str]) -> dict[str, Any]:
        """Return live quotes for a list of tradingsymbol strings.

        Args:
            symbols: e.g. ``["NSE:RELIANCE", "NSE:INFY"]``

        Returns:
            Quote dict keyed by tradingsymbol.
        """
        return self._kite.quote(symbols)

    def lookup_instrument_token(self, exchange: str, tradingsymbol: str) -> int:
        """Look up the numeric instrument token for a symbol."""
        instruments = self._kite.instruments(exchange)
        for inst in instruments:
            if inst["tradingsymbol"] == tradingsymbol:
                return int(inst["instrument_token"])
        raise KeyError(
            f"Instrument '{tradingsymbol}' not found on exchange '{exchange}'."
        )


class KiteOrderManager:
    """Places and tracks orders (live or paper-trade)."""

    PAPER_TRADING: bool = os.environ.get("PAPER_TRADING", "true").lower() == "true"

    def __init__(self, kite: Any | None = None) -> None:
        self._kite = kite
        self.paper_mode: bool = self.PAPER_TRADING
        self._paper_orders: list[dict[str, Any]] = []

    def place_order(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "MIS",
        price: float | None = None,
        tag: str = "trading_bot",
    ) -> str:
        """Place a buy or sell order.

        In paper-trading mode the order is simulated locally.

        Returns:
            Order-id string (simulated or real).
        """
        order_details: dict[str, Any] = {
            "tradingsymbol": tradingsymbol,
            "exchange": exchange,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "product": product,
            "price": price,
            "tag": tag,
            "timestamp": datetime.now().isoformat(),
        }

        if self.paper_mode:
            order_id = f"PAPER-{int(time.time() * 1000)}"
            order_details["order_id"] = order_id
            order_details["status"] = "COMPLETE"
            self._paper_orders.append(order_details)
            logger.info(
                "[PAPER] {} {} x {} @ {} | id={}",
                transaction_type,
                quantity,
                tradingsymbol,
                price or "MARKET",
                order_id,
            )
            return order_id

        if self._kite is None:
            raise RuntimeError("KiteConnect session is required for live trading.")

        kite_order_type = getattr(self._kite, f"ORDER_TYPE_{order_type}", order_type)
        kite_transaction = getattr(
            self._kite, f"TRANSACTION_TYPE_{transaction_type}", transaction_type
        )
        kite_product = getattr(self._kite, f"PRODUCT_{product}", product)

        # Price must be None for MARKET orders; pass it only for LIMIT/SL orders.
        effective_price = None if order_type == "MARKET" else price

        order_id = self._kite.place_order(
            variety=self._kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=kite_transaction,
            quantity=quantity,
            product=kite_product,
            order_type=kite_order_type,
            price=effective_price,
            tag=tag,
        )
        logger.info(
            "[LIVE] {} {} x {} | id={}",
            transaction_type,
            quantity,
            tradingsymbol,
            order_id,
        )
        return str(order_id)

    def get_paper_orders(self) -> list[dict[str, Any]]:
        """Return all simulated paper-trade orders placed this session."""
        return list(self._paper_orders)


class KitePortfolio:
    """Queries portfolio state from Zerodha."""

    def __init__(self, kite: Any) -> None:
        self._kite = kite

    def get_positions(self) -> dict[str, list[dict[str, Any]]]:
        """Return open positions (day + net)."""
        return self._kite.positions()

    def get_holdings(self) -> list[dict[str, Any]]:
        """Return long-term holdings."""
        return self._kite.holdings()

    def get_margins(self) -> dict[str, Any]:
        """Return available margin / cash balance."""
        return self._kite.margins()

    def get_pnl(self) -> float:
        """Return total unrealised P&L across all open day positions."""
        positions = self.get_positions()
        day_positions: list[dict[str, Any]] = positions.get("day", [])
        return sum(float(p.get("pnl", 0)) for p in day_positions)
