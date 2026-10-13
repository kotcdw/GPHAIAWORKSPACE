"""Time-based one-time passwords (RFC 6238), standard library only.

Works with Microsoft Authenticator, Google Authenticator and similar apps:
6 digits, 30-second steps, HMAC-SHA1.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from app.core.crypto import decrypt, encrypt

DIGITS = 6
STEP = 30


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def code_at(secret: str, timestamp: float) -> str:
    counter = int(timestamp // STEP)
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def verify(secret: str, code: str | None, *, window: int = 1, now: float | None = None) -> bool:
    """Accept the current code and one step either side (clock drift)."""
    if not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != DIGITS:
        return False
    now = time.time() if now is None else now
    return any(
        hmac.compare_digest(code_at(secret, now + i * STEP), code) for i in range(-window, window + 1)
    )


def provisioning_uri(secret: str, account: str, issuer: str = "GPHA Internal Audit") -> str:
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}"
        f"&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}"
    )


def seal(secret: str) -> str:
    """Encrypt a secret for storage."""
    return encrypt(secret.encode("ascii")).decode("ascii")


def unseal(token: str) -> str:
    return decrypt(token.encode("ascii")).decode("ascii")
