"""Evidence storage: encrypted at rest, SHA-256 integrity hash, path-traversal safe."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.crypto import InvalidToken, decrypt, encrypt


def safe_name(name: str | None) -> str:
    return Path(name or "upload.bin").name.replace("\x00", "")[:200] or "upload.bin"


def store_encrypted(data: bytes, folder: str, filename: str) -> tuple[str, str]:
    """Encrypt and save ``data`` under the upload directory; returns (relative path, sha256)."""
    target = Path(settings.upload_dir) / folder
    target.mkdir(parents=True, exist_ok=True)
    stored = target / f"{uuid.uuid4().hex}_{safe_name(filename)}.enc"
    stored.write_bytes(encrypt(data))
    return str(stored.relative_to(Path(settings.upload_dir))), hashlib.sha256(data).hexdigest()


def read_verified(relative_path: str, sha256: str | None, encrypted: bool = True) -> bytes:
    """Read a stored file, decrypting it and checking its integrity hash."""
    root = Path(settings.upload_dir).resolve()
    absolute = (root / relative_path).resolve()
    if root not in absolute.parents or not absolute.exists():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="File is no longer available")
    raw = absolute.read_bytes()
    if not encrypted:
        return raw
    try:
        data = decrypt(raw)
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="File cannot be decrypted (encryption key changed?)") from exc
    if sha256 and hashlib.sha256(data).hexdigest() != sha256:
        raise HTTPException(status_code=500, detail="File integrity check failed")
    return data
