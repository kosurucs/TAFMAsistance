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
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_IST = ZoneInfo('Asia/Kolkata')
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
        self.totp_secret: str = os.environ.get("KITE_TOTP_SECRET", "")
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

        user_id = os.environ.get("KITE_USER_ID", "")
        password = os.environ.get("KITE_PASSWORD", "")

        if user_id and password and self.totp_secret:
            totp = pyotp.TOTP(self.totp_secret)
            request_token = self._automated_login(
                requests, user_id, password, totp.now()
            )
        else:
            # Open browser to Kite login; capture redirect on localhost:7049
            request_token = self._browser_callback_login()

        kite = KiteConnect(api_key=self.api_key)
        data = kite.generate_session(request_token, api_secret=self.api_secret)
        access_token: str = data["access_token"]

        # Persist so the process can reuse it until the env is cleared.
        os.environ["KITE_ACCESS_TOKEN"] = access_token
        logger.info("Login successful; access token acquired.")
        return access_token

    def _browser_callback_login(self) -> str:
        """Open the Kite login URL in a browser and capture the request_token
        automatically via a temporary local HTTPS server on port 7049.

        A self-signed certificate is generated in-memory so the redirect from
        Zerodha (https://localhost:7049/...) is received without any manual
        copy-paste.  The browser will show a certificate warning — click
        "Advanced → Proceed" once to allow it.
        """
        import ipaddress
        import ssl
        import tempfile
        import threading
        import webbrowser
        from datetime import datetime, timezone
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import parse_qs, urlparse

        # ── generate a self-signed cert valid for localhost ───────────────────
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import NameOID

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
            ])
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.now(timezone.utc))
                .not_valid_after(datetime(2030, 1, 1, tzinfo=timezone.utc))
                .add_extension(
                    x509.SubjectAlternativeName([
                        x509.DNSName("localhost"),
                        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    ]),
                    critical=False,
                )
                .sign(key, hashes.SHA256())
            )
            cert_pem = cert.public_bytes(serialization.Encoding.PEM)
            key_pem = key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
            tmp_cert = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
            tmp_key = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
            tmp_cert.write(cert_pem); tmp_cert.flush()
            tmp_key.write(key_pem);  tmp_key.flush()
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(tmp_cert.name, tmp_key.name)
            use_ssl = True
        except ImportError:
            logger.warning(
                "cryptography package not installed – falling back to plain HTTP. "
                "Change redirect URL in Kite portal to http://localhost:7049 or "
                "run: pip install cryptography"
            )
            ssl_ctx = None
            use_ssl = False

        request_token_holder: list[str] = []
        server_ready = threading.Event()
        token_received = threading.Event()

        class _CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                token = params.get("request_token", [None])[0]
                status = params.get("status", [""])[0]

                frontend_base = os.environ.get("UI_BASE_URL", "http://localhost:5173").rstrip("/")

                if status == "success" and token:
                    request_token_holder.append(token)
                    redirect_url = f"{frontend_base}/login?status=success&request_token={token}"
                    self.send_response(302)
                    self.send_header("Location", redirect_url)
                else:
                    redirect_url = f"{frontend_base}/login?status=failed"
                    self.send_response(302)
                    self.send_header("Location", redirect_url)

                self.end_headers()
                token_received.set()

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                pass  # suppress default HTTP server logs

        httpd = HTTPServer(("localhost", 7049), _CallbackHandler)
        if use_ssl and ssl_ctx:
            httpd.socket = ssl_ctx.wrap_socket(httpd.socket, server_side=True)
        httpd.timeout = 1

        def _serve() -> None:
            server_ready.set()
            while not token_received.is_set():
                httpd.handle_request()
            httpd.server_close()

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()
        server_ready.wait()

        kite_tmp = KiteConnect(api_key=self.api_key)
        login_url = kite_tmp.login_url()
        scheme = "https" if use_ssl else "http"
        logger.info("Opening browser for Kite login: {}", login_url)
        logger.info("Callback server listening on {}://localhost:7049", scheme)
        webbrowser.open(login_url)
        print(f"\nIf the browser did not open, visit:\n  {login_url}\n")
        if use_ssl:
            print(
                "NOTE: Your browser may warn about an untrusted certificate.\n"
                "Click 'Advanced' → 'Proceed to localhost' to allow it.\n"
            )

        logger.info("Waiting for Kite redirect to {}://localhost:7049 ...", scheme)
        token_received.wait(timeout=300)

        if not request_token_holder:
            raise RuntimeError(
                "Timed out waiting for Kite login redirect. "
                "Please run again and complete login within 5 minutes."
            )

        token = request_token_holder[0]
        logger.info("request_token captured from redirect.")
        return token

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
        to_date = datetime.now(_IST)
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

    def get_ohlcv_range(
        self,
        instrument_token: int,
        start_dt: datetime,
        end_dt: datetime,
        interval: str = "minute",
    ) -> list[dict[str, Any]]:
        """Return OHLCV candles for a fixed datetime range.

        Args:
            instrument_token: Zerodha numeric instrument token.
            start_dt: Range start datetime (timezone-aware preferred).
            end_dt: Range end datetime (must be after start).
            interval: Kite candle interval.

        Returns:
            List of candle dicts with keys:
            ``date, open, high, low, close, volume``.
        """
        try:
            candles: list[dict[str, Any]] = self._kite.historical_data(
                instrument_token,
                from_date=start_dt,
                to_date=end_dt,
                interval=interval,
            )
        except Exception as exc:  # noqa: BLE001
            max_days = self._extract_max_days(str(exc))
            span_days = (end_dt - start_dt).total_seconds() / 86400.0
            if max_days is not None and span_days > max_days:
                logger.warning(
                    "Range {} days exceeds {} days for interval '{}'; chunking fetch.",
                    f"{span_days:.1f}",
                    max_days,
                    interval,
                )
                candles = self._get_ohlcv_range_chunked(
                    instrument_token=instrument_token,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    interval=interval,
                    max_days=max_days,
                )
            else:
                raise

        logger.debug(
            "Fetched {} candles for token {} ({}) in explicit range.",
            len(candles),
            instrument_token,
            interval,
        )
        return candles

    @staticmethod
    def _extract_max_days(error_text: str) -> int | None:
        """Extract max-day limit from Kite error text, if present."""
        m = re.search(r"max\s+limit\s*:\s*(\d+)\s*days", error_text, flags=re.IGNORECASE)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:  # noqa: BLE001
            return None

    def _get_ohlcv_range_chunked(
        self,
        instrument_token: int,
        start_dt: datetime,
        end_dt: datetime,
        interval: str,
        max_days: int,
    ) -> list[dict[str, Any]]:
        """Fetch OHLCV in multiple bounded windows when Kite enforces max days."""
        all_candles: list[dict[str, Any]] = []
        cursor = start_dt

        while cursor < end_dt:
            chunk_end = min(cursor + timedelta(days=max_days), end_dt)
            part: list[dict[str, Any]] = self._kite.historical_data(
                instrument_token,
                from_date=cursor,
                to_date=chunk_end,
                interval=interval,
            )
            all_candles.extend(part)

            # Move by one second to avoid re-requesting the same boundary candle.
            cursor = chunk_end + timedelta(seconds=1)

        return all_candles

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

    def get_day_pnl(self) -> float:
        """Return total unrealised P&L across all open day positions."""
        positions = self.get_positions()
        day_positions: list[dict[str, Any]] = positions.get("day", [])
        return sum(float(p.get("pnl", 0)) for p in day_positions)
