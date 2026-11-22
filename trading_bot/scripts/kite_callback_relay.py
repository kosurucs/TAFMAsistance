"""Lightweight HTTPS relay for Zerodha callback URL.

Kite redirects to https://127.0.0.1:7049 with request_token. This relay
forwards that callback to the React login route so the UI can exchange token
and navigate to home automatically.
"""

from __future__ import annotations

import ipaddress
import os
import ssl
import subprocess
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from loguru import logger


def _build_ssl_context() -> ssl.SSLContext:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    cert_dir = Path(__file__).parents[1] / "data" / "certs"
    cert_path = cert_dir / "kite_callback.crt.pem"
    key_path = cert_dir / "kite_callback.key.pem"

    if not cert_path.exists() or not key_path.exists():
        cert_dir.mkdir(parents=True, exist_ok=True)
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
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]),
                critical=False,
            )
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))

    if os.name == "nt":
        result = subprocess.run(
            ["certutil.exe", "-user", "-addstore", "Root", str(cert_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            logger.info("Kite callback certificate trusted in current-user Root store")
        else:
            logger.warning("Could not trust Kite callback certificate: {}", result.stderr.strip())

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    return ctx


def main() -> None:
    frontend_base = os.environ.get("UI_BASE_URL", "http://localhost:5173").rstrip("/")

    class CallbackRelayHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            token = params.get("request_token", [""])[0].strip()
            status = params.get("status", [""])[0].strip().lower()

            if status == "success" and token:
                target = f"{frontend_base}/login?status=success&request_token={token}"
            else:
                target = f"{frontend_base}/login?status=failed"

            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # Suppress BaseHTTPRequestHandler stdout noise.
            return

    server = HTTPServer(("127.0.0.1", 7049), CallbackRelayHandler)
    server.socket = _build_ssl_context().wrap_socket(server.socket, server_side=True)

    logger.info("Kite callback relay running on https://127.0.0.1:7049")
    logger.info("Forwarding successful callbacks to {}/login", frontend_base)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        logger.info("Kite callback relay stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
