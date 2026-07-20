"""Kalshi API request signing.

Every authenticated request carries three headers:

  KALSHI-ACCESS-KEY        the API key ID (UUID)
  KALSHI-ACCESS-TIMESTAMP  current time in epoch milliseconds
  KALSHI-ACCESS-SIGNATURE  base64 RSA-PSS/SHA-256 signature of
                           "<timestamp><METHOD><path>" where path includes the
                           /trade-api/v2 prefix and excludes the query string
"""

from __future__ import annotations

import base64
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def load_private_key(path: str, password: bytes | None = None) -> rsa.RSAPrivateKey:
    with open(path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=password)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError("Kalshi API keys must be RSA private keys")
    return key


def sign_message(private_key: rsa.RSAPrivateKey, message: str) -> str:
    signature = private_key.sign(
        message.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def build_auth_headers(
    api_key_id: str,
    private_key: rsa.RSAPrivateKey,
    method: str,
    path: str,
    timestamp_ms: int | None = None,
) -> dict[str, str]:
    """Build the three auth headers for a request.

    `path` must include the /trade-api/v2 prefix and must not include a query string.
    """
    ts = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
    message = f"{ts}{method.upper()}{path}"
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": sign_message(private_key, message),
    }
