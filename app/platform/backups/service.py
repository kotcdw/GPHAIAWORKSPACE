"""Backup service: snapshot the database (and the attachments) to a timestamped backup set.

Prefers ``mysqldump`` when the database is MySQL and the client tool is on
PATH (a native, restorable SQL dump). Otherwise falls back to a portable JSON
export of every table produced through SQLAlchemy, which works for any backend
and needs no external tools.

Every snapshot is encrypted at rest (``.enc`` suffix, see ``app.core.crypto``)
and the plaintext is never left on disk. Login sessions are excluded from JSON
dumps. Restore with ``uv run python -m scripts.restore_backup``.

A backup set shares one stamp:

* ``backup_<stamp>.json.enc`` / ``.sql.enc`` - the encrypted database snapshot;
* ``backup_<stamp>.files.tar.gz`` - the attachments (each file is already encrypted at rest);
* ``backup_<stamp>.manifest.json`` - SHA-256 of both, row counts, file count and schema revision
  (no data, no secrets), used by :func:`verify_backup`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.crypto import InvalidToken, decrypt, encrypt
from app.core.database import Base


@dataclass
class BackupInfo:
    filename: str  # the database snapshot
    path: str
    size_bytes: int
    created_at: str
    stamp: str = ""
    method: str = ""  # mysqldump | json
    files_name: str | None = None  # the attachments archive, when the set has one
    files_bytes: int = 0
    file_count: int = 0
    has_manifest: bool = False


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
        # The command and all arguments are fixed or derived from the configured database URL.
        # Shell execution is disabled.
        subprocess.run(cmd, check=True, capture_output=True, timeout=300, env=env)  # nosec B603 - fixed argv, no shell
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


STAMP = re.compile(r"^backup_(\d{8}_\d{6})")
SQL_HEADS, SQL_TAIL = (b"-- MySQL dump", b"-- MariaDB dump"), b"-- Dump completed"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_counts(db: DBSession) -> dict[str, int]:
    out = {}
    for table in Base.metadata.tables.values():
        if table.name not in EXCLUDED_TABLES:
            out[table.name] = db.execute(select(func.count()).select_from(table)).scalar_one()
    return out


def _schema_revision(db: DBSession) -> str | None:
    try:
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001 - no migration table (tests on create_all)
        db.rollback()
        return None


def _archive_attachments(dest: Path) -> int:
    """Pack the upload directory (files stay encrypted as stored). Returns the number of files."""
    root = Path(settings.upload_dir)
    count = 0
    with tarfile.open(dest, "w:gz") as tar:
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and not path.is_symlink():
                    tar.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
                    count += 1
    return count


def include_attachments() -> bool:
    from app.core.appconfig import cfg

    return bool(cfg("backup_include_attachments"))


def retention() -> int:
    from app.core.appconfig import cfg

    return int(cfg("backup_retention"))


def interval_hours() -> int:
    """Hours between scheduled backups (0 = paused). The server setting 0 switches the schedule off entirely."""
    from app.core.appconfig import cfg

    if settings.backup_interval_hours <= 0:
        return 0
    return int(cfg("backup_interval_hours"))


def create_backup(db: DBSession) -> BackupInfo:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    root = backup_root()
    while any(root.glob(f"backup_{stamp}.*")):  # two backups in the same second: wait for the next one
        time.sleep(0.25)
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    counts = _row_counts(db)
    sql_dest = root / f"backup_{stamp}.sql"
    if _try_mysqldump(sql_dest):
        plain, method = sql_dest, "mysqldump"
    else:
        plain, method = root / f"backup_{stamp}.json", "json"
        _json_dump(db, plain)
    dest = plain.with_name(plain.name + ".enc")
    try:
        dest.write_bytes(encrypt(plain.read_bytes()))
    finally:
        plain.unlink(missing_ok=True)
    manifest = {
        "stamp": stamp, "created_at": datetime.now(UTC).isoformat(), "method": method,
        "schema_revision": _schema_revision(db), "database": {"file": dest.name, "bytes": dest.stat().st_size,
                                                               "sha256": _sha256(dest), "row_counts": counts},
        "attachments": None,
    }
    if include_attachments():
        files = root / f"backup_{stamp}.files.tar.gz"
        try:
            count = _archive_attachments(files)
        except Exception:
            files.unlink(missing_ok=True)
            dest.unlink(missing_ok=True)
            raise
        manifest["attachments"] = {"file": files.name, "bytes": files.stat().st_size, "sha256": _sha256(files),
                                   "count": count}
    (root / f"backup_{stamp}.manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    purge_old_backups()
    return _set_info(stamp)


def _manifest(stamp: str) -> dict | None:
    path = backup_root() / f"backup_{stamp}.manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _set_files(stamp: str) -> list[Path]:
    return [p for p in backup_root().glob(f"backup_{stamp}.*") if p.is_file()]


def _set_info(stamp: str) -> BackupInfo | None:
    files = _set_files(stamp)
    names = [f"backup_{stamp}.{ext}" for ext in ("json.enc", "sql.enc", "json", "sql")]
    db_file = next((p for name in names for p in files if p.name == name), None)
    if db_file is None:
        return None
    archive = next((p for p in files if p.name.endswith(".files.tar.gz")), None)
    manifest = _manifest(stamp) or {}
    stat = db_file.stat()
    return BackupInfo(
        filename=db_file.name, path=str(db_file), size_bytes=stat.st_size,
        created_at=manifest.get("created_at") or datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
        stamp=stamp, method=manifest.get("method") or ("mysqldump" if ".sql" in db_file.name else "json"),
        files_name=archive.name if archive else None, files_bytes=archive.stat().st_size if archive else 0,
        file_count=(manifest.get("attachments") or {}).get("count", 0) if archive else 0,
        has_manifest=bool(manifest),
    )


def _stamps() -> list[str]:
    found = {m.group(1) for p in backup_root().glob("backup_*") if (m := STAMP.match(p.name))}
    return sorted(found, reverse=True)


def stamp_of(name: str) -> str | None:
    """The set a file name (or a bare stamp) belongs to; None when it is not a backup name."""
    if re.fullmatch(r"\d{8}_\d{6}", name):
        return name
    match = STAMP.match(name)
    return match.group(1) if match else None


def list_backups() -> list[BackupInfo]:
    return [info for stamp in _stamps() if (info := _set_info(stamp)) is not None]


def delete_set(stamp: str) -> list[str]:
    removed = []
    for path in _set_files(stamp):
        path.unlink(missing_ok=True)
        removed.append(path.name)
    return removed


def purge_old_backups() -> list[str]:
    removed: list[str] = []
    for stamp in _stamps()[max(retention(), 1):]:
        removed.extend(delete_set(stamp))
    return removed


# ------------------------------------------------------------------ verification


def verify_backup(stamp: str) -> dict:
    """Check that a backup set can be used for a restore: the files are intact (SHA-256 against the manifest), the
    database snapshot decrypts with the current key and is complete, and the attachments archive opens with every
    file listed. Reads only; never restores. Returns ``{"ok": bool, "checks": [{"name", "ok", "detail"}]}``."""
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"name": name, "ok": ok, "detail": detail})
        return ok

    info = _set_info(stamp)
    if info is None:
        add("Database snapshot present", False, "The database file is missing")
        return {"ok": False, "checks": checks}
    manifest = _manifest(stamp)
    db_path = Path(info.path)
    if manifest:
        want = manifest["database"]["sha256"]
        add("Database file intact", _sha256(db_path) == want, "" if _sha256(db_path) == want else "Checksum differs")
    else:
        add("Manifest present", False, "Older backup without a manifest: integrity cannot be confirmed")
    raw = db_path.read_bytes()
    plain = None
    if db_path.suffix == ".enc":
        try:
            plain = decrypt(raw)
            add("Decrypts with the current key", True)
        except InvalidToken:
            add("Decrypts with the current key", False, "The encryption key differs from the one used for this backup")
    else:
        plain = raw
    if plain is not None:
        if ".json" in db_path.name:
            try:
                tables = json.loads(plain).get("tables") or {}
                counts = {k: len(v) for k, v in tables.items()}
                expected = (manifest or {}).get("database", {}).get("row_counts")
                if expected is not None:
                    diff = [t for t, n in expected.items() if counts.get(t) != n]
                    add("All tables and rows present", not diff,
                        f"{sum(counts.values())} rows in {len(counts)} tables" if not diff
                        else f"Different row counts: {', '.join(diff[:5])}")
                else:
                    add("Snapshot readable", bool(tables), f"{sum(counts.values())} rows in {len(counts)} tables")
            except ValueError:
                add("Snapshot readable", False, "The snapshot is not valid JSON")
        else:
            complete = any(h in plain[:400] for h in SQL_HEADS) and SQL_TAIL in plain[-400:]
            add("Snapshot complete", complete, "" if complete else "The SQL dump is truncated")
            expected = (manifest or {}).get("database", {}).get("row_counts")
            if complete and expected is not None:
                missing = [t for t in expected if f"CREATE TABLE `{t}`".encode() not in plain]
                add("All tables present", not missing,
                    f"{len(expected)} tables" if not missing else f"Missing: {', '.join(missing[:5])}")
    expected_files = (manifest or {}).get("attachments")
    if expected_files:
        archive = backup_root() / expected_files["file"]
        if not archive.exists():
            add("Attachments archive present", False, "The attachments archive is missing")
        else:
            digest = _sha256(archive)
            add("Attachments archive intact", digest == expected_files["sha256"],
                "" if digest == expected_files["sha256"] else "Checksum differs")
            try:
                with tarfile.open(archive, "r:gz") as tar:
                    members = [m for m in tar.getmembers() if m.isfile()]
                    unsafe = [m.name for m in members if m.name.startswith("/") or ".." in Path(m.name).parts]
                add("All attachments listed", len(members) == expected_files["count"] and not unsafe,
                    f"{len(members)} file{'' if len(members) == 1 else 's'}" if not unsafe
                    else "Unsafe paths in the archive")
            except (tarfile.TarError, OSError, EOFError):
                add("All attachments listed", False, "The archive cannot be opened")
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def record_check(db: DBSession, stamp: str, result: dict, *, kind: str = "check", user=None) -> None:  # noqa: ANN001
    from app.platform.backups.models import BackupCheck

    db.add(BackupCheck(backup=stamp, kind=kind, outcome="passed" if result["ok"] else "failed",
                       details=json.dumps(result["checks"])[:60000],
                       user_id=getattr(user, "id", None), user_name=getattr(user, "full_name", None)))
