"""Symmetric encryption for data at rest (backups and working papers).

Uses Fernet (AES-128-CBC + HMAC-SHA256, from the ``cryptography`` package).
The key comes from ``GPHA_ENCRYPTION_KEY`` (a Fernet key, or any passphrase,
which is stretched with SHA-256); if unset it is derived from the secret key.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

__all__ = ["InvalidToken", "decrypt", "encrypt", "fernet"]


def _derive(material: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(material.encode("ascii"))
        if len(raw) == 32:
            return material.encode("ascii")  # already a valid Fernet key
    except (ValueError, UnicodeEncodeError):
        pass
    return base64.urlsafe_b64encode(hashlib.sha256(material.encode("utf-8")).digest())


@lru_cache(maxsize=1)
def fernet() -> Fernet:
    material = settings.encryption_key or f"gpha-data-key:{settings.secret_key}"
    return Fernet(_derive(material))


def encrypt(data: bytes) -> bytes:
    return fernet().encrypt(data)


def decrypt(token: bytes) -> bytes:
    return fernet().decrypt(token)
