import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kalshi_agent.auth import build_auth_headers, sign_message


def _keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_signature_verifies():
    key = _keypair()
    message = "1700000000000GET/trade-api/v2/portfolio/balance"
    sig = base64.b64decode(sign_message(key, message))
    key.public_key().verify(
        sig,
        message.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


def test_headers_shape():
    key = _keypair()
    headers = build_auth_headers(
        "my-key-id", key, "get", "/trade-api/v2/markets", timestamp_ms=1700000000000
    )
    assert headers["KALSHI-ACCESS-KEY"] == "my-key-id"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1700000000000"
    # signature must be over "<ts>GET<path>" (method uppercased)
    sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
    key.public_key().verify(
        sig,
        b"1700000000000GET/trade-api/v2/markets",
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
