"""Prove that backups can actually be restored: take a fresh encrypted snapshot, restore it into an empty
test database and compare every table's row count with the live database.

    uv run python -m scripts.verify_backup                         (restores into <live database>_restore_test)
    uv run python -m scripts.verify_backup --target-db my_test_db  (choose the empty test database)

The test database uses the same server and account as the live one. It is created when the account is
allowed to (CREATE privilege); otherwise ask the DBA to create an empty database with that name. Live data
is only read, never changed. Run this before go-live and then every quarter; keep the printed result as
evidence for the business-continuity file.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, func, inspect, select, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

import app.main  # noqa: E402,F401 - registers every model
from app.core.config import BASE_DIR, settings  # noqa: E402
from app.core.crypto import decrypt, encrypt  # noqa: E402
from app.core.database import Base, SessionLocal  # noqa: E402
from app.platform.backups.service import EXCLUDED_TABLES, _json_dump, backup_root  # noqa: E402


def _counts(engine) -> dict[str, int]:  # noqa: ANN001
    names = set(inspect(engine).get_table_names())
    out = {}
    with engine.connect() as conn:
        for table in Base.metadata.tables.values():
            if table.name in EXCLUDED_TABLES or table.name not in names:
                continue
            out[table.name] = conn.execute(select(func.count()).select_from(table)).scalar_one()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target-db", help="empty database to restore into (default: <live>_restore_test)")
    args = parser.parse_args()

    live_url = make_url(settings.database_url)
    if not live_url.drivername.startswith("mysql"):
        print("This check is for MySQL installations.")
        return 2
    target_name = args.target_db or f"{live_url.database}_restore_test"
    if target_name == live_url.database:
        print("The target must be a different, empty database.")
        return 2
    target_url = live_url.set(database=target_name)

    # 1. Fresh snapshot, encrypted exactly like a scheduled backup, then read back with the current key.
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    plain = backup_root() / f"verify_{stamp}.json"
    db = SessionLocal()
    try:
        _json_dump(db, plain)
    finally:
        db.close()
    enc = plain.with_name(plain.name + ".enc")
    enc.write_bytes(encrypt(plain.read_bytes()))
    plain.unlink(missing_ok=True)
    decrypt(enc.read_bytes())  # raises if the encryption key cannot read it
    print(f"[1/3] Snapshot written and decrypted with the current key: {enc.name}")

    # 2. Restore into the empty test database (created when the account may).
    server = create_engine(live_url.set(database=""), future=True)
    try:
        with server.begin() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{target_name}` CHARACTER SET utf8mb4"))
    except Exception as exc:  # noqa: BLE001
        print(f"      Could not create {target_name} ({exc.__class__.__name__}); it must already exist and be empty.")
    finally:
        server.dispose()
    env = {**os.environ, "GPHA_DATABASE_URL": target_url.render_as_string(hide_password=False)}
    result = subprocess.run([sys.executable, "-m", "scripts.restore_backup", str(enc), "--yes"], cwd=BASE_DIR,
                            env=env, capture_output=True, text=True)
    if result.returncode != 0:
        # Show only the error lines (never the row data, which can include password hashes).
        lines = [ln for ln in (result.stdout + result.stderr).splitlines()
                 if "Error" in ln or "Refusing" in ln or "Cannot" in ln][-3:]
        print("[2/3] Restore FAILED:\n      " + "\n      ".join(ln[:300] for ln in lines))
        return 1
    print(f"[2/3] Restored into {target_name}")

    # 3. Compare every table.
    live_engine = create_engine(live_url, future=True)
    test_engine = create_engine(target_url, future=True)
    try:
        live, restored = _counts(live_engine), _counts(test_engine)
    finally:
        live_engine.dispose()
        test_engine.dispose()
    bad = [(t, n, restored.get(t)) for t, n in live.items() if restored.get(t) != n]
    total = sum(live.values())
    if bad:
        print("[3/3] MISMATCH (rows may have been added while the check ran - run it again at a quiet time):")
        for t, n, r in bad:
            print(f"      {t}: live {n}, restored {r}")
        return 1
    print(f"[3/3] All {len(live)} tables match ({total} rows). Backup and restore verified "
          f"{datetime.now():%d %b %Y %H:%M}.")
    print(f"      You can now drop the test database {target_name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
