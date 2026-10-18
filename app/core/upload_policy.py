"""One upload policy for every attachment: allowed types, size limit and a check that the content matches the type.

The administrator settings (Configuration > Data & attachments) apply within the server limits in ``.env``: the
size can only be lowered and the types only narrowed. Programs and scripts are never accepted.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import HTTPException, status

from app.core.appconfig import cfg
from app.core.config import settings

NEVER = {".exe", ".dll", ".bat", ".cmd", ".com", ".msi", ".ps1", ".vbs", ".js", ".jar", ".sh", ".scr", ".hta",
         ".html", ".htm", ".svg", ".php", ".py", ".lnk", ".iso"}
_CHUNK = 1024 * 1024

# Leading bytes ("magic numbers") each type must start with. Office 2007+ and OpenDocument files are zip archives;
# older Office files and Outlook messages are OLE compound files.
_ZIP = (b"PK\x03\x04", b"PK\x05\x06")
_OLE = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)
SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF",), ".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"), ".bmp": (b"BM",),
    ".tif": (b"II*\x00", b"MM\x00*"), ".tiff": (b"II*\x00", b"MM\x00*"),
    ".docx": _ZIP, ".xlsx": _ZIP, ".xlsm": _ZIP, ".pptx": _ZIP, ".odt": _ZIP, ".ods": _ZIP, ".zip": _ZIP,
    ".doc": _OLE, ".xls": _OLE, ".ppt": _OLE, ".msg": _OLE, ".rtf": (b"{\\rtf",), ".wav": (b"RIFF",),
    ".mp3": (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
}
TEXT_TYPES = {".txt", ".csv", ".eml"}
FTYP_TYPES = {".mp4", ".m4a"}  # ISO media: "ftyp" at byte 4


def max_bytes() -> int:
    return min(int(cfg("attachment_max_mb")), settings.max_upload_mb) * 1024 * 1024


def max_mb() -> int:
    return min(int(cfg("attachment_max_mb")), settings.max_upload_mb)


def allowed() -> set[str]:
    chosen = {e.strip().lower() for e in (cfg("attachment_file_types") or [])}
    return (chosen & settings.allowed_extensions) - NEVER


def safe_name(name: str | None) -> str:
    return Path(name or "upload.bin").name.replace("\x00", "")[:200] or "upload.bin"


def check_name(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed():
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"File type '{suffix or 'none'}' is not allowed. Allowed: "
                                   f"{', '.join(sorted(allowed()))}")
    return suffix


def content_matches(data: bytes, suffix: str) -> bool:
    head = data[:16]
    if suffix in SIGNATURES:
        return head.startswith(SIGNATURES[suffix])
    if suffix in FTYP_TYPES:
        return data[4:8] == b"ftyp"
    if suffix in TEXT_TYPES:
        return b"\x00" not in data[:8192]
    return True  # a type without a known signature: the extension check applies


def check_content(data: bytes, filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    if cfg("attachment_check_content") and not content_matches(data, suffix):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"The file's content does not match its {suffix} type; it may be damaged or "
                                   f"renamed")


async def read_upload(file) -> tuple[bytes, str, str]:  # noqa: ANN001
    """Read an upload under the policy. Returns (data, sha256, safe original name)."""
    original = safe_name(file.filename)
    check_name(original)
    limit = max_bytes()
    digest, chunks, size = hashlib.sha256(), [], 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                detail=f"File exceeds the {max_mb()} MB limit")
        digest.update(chunk)
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty")
    data = b"".join(chunks)
    check_content(data, original)
    return data, digest.hexdigest(), original
