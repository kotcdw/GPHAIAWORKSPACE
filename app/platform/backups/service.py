"""Backup service: snapshot the database to a timestamped, encrypted file.

Prefers ``mysqldump`` when the database is MySQL and the client tool is on
PATH (a native, restorable SQL dump). Otherwise falls back to a portable JSON
export of every table produced through SQLAlchemy, which works for any backend
and needs no external tools.

Every snapshot is encrypted at rest (``.enc`` suffix, see ``app.core.crypto``)
and the plaintext is never left on disk. Login sessions are excluded from JSON
dumps. Restore with ``uv run python -m scripts.restore_backup``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.crypto import encrypt
from app.core.database import Base


@dataclass
class BackupInfo:
    filename: str
    path: str
    size_bytes: int
    created_at: str


# Ephemeral/secret tables that must never be written into a backup.
EXCLUDED_TABLES = frozenset({"sessions"})


def backup_root() -> Path:
    root = Path(settings.backup_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe(value):  # noqa: ANN001, ANN202
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


def _try_mysqldump(dest: Path) -> bool:
    url = settings.database_url or ""
    if not url.startswith("mysql") or shutil.which("mysqldump") is None:
        return False
    parsed = make_url(url)
    cmd = [
        "mysqldump",
        "-h",
        parsed.host or settings.mysql_host,
        "-P",
        str(parsed.port or settings.mysql_port),
        "-u",
        parsed.username or settings.mysql_user,
        "--single-transaction",
        "--routines",
        "--triggers",
        "--ignore-table",
        f"{parsed.database}.sessions",
        "--result-file",
        str(dest),
        parsed.database or settings.mysql_database,
    ]
    # The password goes through the environment, never the command line
    # (where any local user could read it from the process list).
    env = {**os.environ, "MYSQL_PWD": parsed.password or settings.mysql_password}
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300, env=env)
        return dest.exists() and dest.stat().st_size > 0
    except (subprocess.SubprocessError, OSError):
        dest.unlink(missing_ok=True)
        return False


def _json_dump(db: DBSession, dest: Path) -> None:
    payload: dict[str, list[dict]] = {"created_at": datetime.now(UTC).isoformat(), "tables": {}}
    # Dump order is irrelevant; iterating tables directly avoids SQLAlchemy's
    # unresolvable-cycle warning from the mutual NC<->CAPA foreign keys.
    for table in Base.metadata.tables.values():
        if table.name in EXCLUDED_TABLES:
            continue
        rows = []
        for row in db.execute(select(table)).mappings():
            rows.append({k: _safe(v) for k, v in row.items()})
        payload["tables"][table.name] = rows
    dest.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def create_backup(db: DBSession) -> BackupInfo:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    root = backup_root()
    sql_dest = root / f"backup_{stamp}.sql"
    if _try_mysqldump(sql_dest):
        plain = sql_dest
    else:
        plain = root / f"backup_{stamp}.json"
        _json_dump(db, plain)
    dest = plain.with_name(plain.name + ".enc")
    try:
        dest.write_bytes(encrypt(plain.read_bytes()))
    finally:
        plain.unlink(missing_ok=True)
    purge_old_backups()
    stat = dest.stat()
    return BackupInfo(
        filename=dest.name,
        path=str(dest),
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    )


def list_backups() -> list[BackupInfo]:
    root = backup_root()
    files = sorted(root.glob("backup_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        BackupInfo(
            filename=p.name,
            path=str(p),
            size_bytes=p.stat().st_size,
            created_at=datetime.fromtimestamp(p.stat().st_mtime, tz=UTC).isoformat(),
        )
        for p in files
    ]


def purge_old_backups() -> list[str]:
    root = backup_root()
    files = sorted(root.glob("backup_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed: list[str] = []
    for old in files[settings.backup_retention :]:
        old.unlink(missing_ok=True)
        removed.append(old.name)
    return removed