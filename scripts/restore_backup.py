"""Decrypt and restore a database backup.

Usage:
    # Decrypt only (writes the plain .json / .sql next to it - keep it safe!)
    uv run python -m scripts.restore_backup backups/backup_20261013_101500.json.enc --decrypt-only

    # Restore a JSON snapshot into a NEW, EMPTY database:
    #   1. create the empty database and point GPHA_DATABASE_URL at it
    #   2. uv run python -m scripts.restore_backup backups/backup_....json.enc --yes
    #      (applies the migrations itself - do NOT run scripts.init_db first)
    #
    # Restore a mysqldump (.sql.enc) snapshot:
    #   uv run python -m scripts.restore_backup backups/backup_....sql.enc --decrypt-only
    #   mysql -u gpha -p gpha_workspace_restored < backups/backup_....sql

The JSON restore never overwrites live data: it migrates the target schema and
refuses to run unless every table is empty (the reference sequences seeded by
the migrations are replaced). Restored rows keep their original ids, so the
audit log, history and signatures come back exactly as they were.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.config import Config  # noqa: E402
from sqlalchemy import DateTime, delete, func, insert, select, text  # noqa: E402
from sqlalchemy.exc import SAWarning  # noqa: E402
from sqlalchemy.schema import sort_tables  # noqa: E402

import app.main  # noqa: E402,F401 - registers every model on Base.metadata
from alembic import command  # noqa: E402
from app.core.config import BASE_DIR  # noqa: E402
from app.core.crypto import InvalidToken, decrypt  # noqa: E402
from app.core.database import Base, SessionLocal  # noqa: E402

# Tables seeded by the migrations that a restore replaces wholesale.
_REPLACEABLE = {"reference_sequences"}
# The NC <-> CAPA foreign-key cycle is expected; it is handled below.
warnings.filterwarnings("ignore", category=SAWarning, message=".*unresolvable cycles.*")
# Insert order that satisfies foreign keys (the NC<->CAPA cycle is handled by
# inserting the link columns in a second pass).
_DEFERRED_LINKS = {"nonconformances": ["linked_capa_id"], "capa": ["linked_nc_id"]}


def read_backup(path: Path) -> bytes:
    raw = path.read_bytes()
    if path.suffix != ".enc":
        return raw
    try:
        return decrypt(raw)
    except InvalidToken:
        sys.exit("Cannot decrypt: GPHA_ENCRYPTION_KEY / GPHA_SECRET_KEY differ from the ones used for the backup.")


def _coerce(table, row: dict) -> dict:  # noqa: ANN001
    out = {}
    for key, value in row.items():
        column = table.columns.get(key)
        if column is None:
            continue
        if value is not None and isinstance(column.type, DateTime) and isinstance(value, str):
            value = datetime.fromisoformat(value)
        out[key] = value
    return out


def _insert_order() -> list:
    """Tables in FK order, ignoring the NC<->CAPA link columns (set in pass two)."""

    def skip(fk) -> bool:  # noqa: ANN001
        return fk.parent.name in _DEFERRED_LINKS.get(fk.parent.table.name, [])

    return sort_tables(Base.metadata.tables.values(), skip_fn=skip)


def restore_json(payload: dict, *, assume_yes: bool) -> None:
    tables = payload.get("tables", {})
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")
    db = SessionLocal()
    try:
        order = _insert_order()
        for table in order:
            if table.name in _REPLACEABLE:
                continue
            count = db.execute(select(func.count()).select_from(table)).scalar_one()
            if count:
                sys.exit(f"Refusing to restore: {table.name} already has {count} row(s); use an empty database.")
        if not assume_yes:
            answer = input("Restore the snapshot into this (empty) database? [y/N] ")
            if answer.strip().lower() != "y":
                sys.exit("Aborted.")

        # The snapshot is internally consistent, but some tables reference each other (users <-> organizations,
        # NC <-> CAPA ...). On MySQL foreign-key checks are paused for this session while rows go in.
        mysql = db.get_bind().dialect.name == "mysql"
        if mysql:
            db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for name in _REPLACEABLE:
            if name in tables:
                db.execute(delete(Base.metadata.tables[name]))
        for table in order:
            rows = tables.get(table.name) or []
            if not rows:
                continue
            deferred = _DEFERRED_LINKS.get(table.name, [])
            cleaned = []
            for row in rows:
                data = _coerce(table, row)
                for col in deferred:
                    data[col] = None
                cleaned.append(data)
            db.execute(insert(table), cleaned)
            print(f"  {table.name}: {len(cleaned)} row(s)")
        for name, cols in _DEFERRED_LINKS.items():
            table = Base.metadata.tables[name]
            for row in tables.get(name) or []:
                values = {c: row.get(c) for c in cols if row.get(c) is not None}
                if values:
                    db.execute(table.update().where(table.c.id == row["id"]).values(**values))
        if mysql:
            db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        db.commit()
        print("Restore complete. Users must sign in again (sessions are never backed up).")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--decrypt-only", action="store_true", help="write the decrypted file and stop")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args()

    data = read_backup(args.backup)
    if args.decrypt_only:
        target = args.backup.with_suffix("") if args.backup.suffix == ".enc" else args.backup
        if target == args.backup:
            sys.exit("File is not encrypted; nothing to decrypt.")
        target.write_bytes(data)
        print(f"Decrypted to {target} - this file is NOT encrypted; delete it when done.")
        return
    name = args.backup.name.removesuffix(".enc")
    if not name.endswith(".json"):
        sys.exit("Only JSON snapshots can be restored by this script; use --decrypt-only and the mysql client.")
    restore_json(json.loads(data), assume_yes=args.yes)


if __name__ == "__main__":
    main()
