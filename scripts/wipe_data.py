"""Wipe the workspace's records, keeping users, roles and settings (run on the server).

    uv run python -m scripts.wipe_data             (shows what will be wiped, asks you to type WIPE)
    uv run python -m scripts.wipe_data --dry-run   (only shows the row counts)

Kept: user accounts, profiles and groups; role permissions and Access by module; Configuration and the other
settings (SLA limits, workflows, custom fields, automation rules, audit type terms, saved views); the methodology
libraries (topical requirements, frameworks, regulations, criteria, factors, audit programmes); the audit trail
(activity log and record history) and the backup checks.

Wiped: everything else - org structure, universe, plans, audits, fieldwork, findings, actions, reports, GRC,
analytics, notifications, comments, tasks, timesheets - and the stored attachments.

A full encrypted backup (database and attachments) is taken first; if it fails nothing is wiped. Restore it with
``uv run python -m scripts.restore_backup``. Numbering (AUD-0001, ...) starts again.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import Table, func, select, text, update  # noqa: E402
from sqlalchemy.orm import Session as DBSession  # noqa: E402

import app.main  # noqa: E402, F401  (registers every model with SQLAlchemy)
from app.core.database import Base  # noqa: E402

KEEP = frozenset({
    # Users and roles
    "users", "auditor_profiles", "auditor_prior_roles", "user_groups", "user_group_members", "user_invitations",
    "role_permissions", "role_module_access", "sessions", "saved_views",
    # Settings
    "app_config", "app_config_history", "custom_fields", "sla_policies", "workflow_definitions", "automation_rules",
    "audit_type_terms",
    # Methodology libraries
    "topical_requirements", "topical_requirement_items", "frameworks", "library_controls", "requirements",
    "regulations", "criteria", "assessment_factors", "audit_programs",
    # Audit trail and operations
    "audit_logs", "record_history", "backup_checks",
})


def wiped_tables() -> list[Table]:
    """Tables to empty, children first."""
    return [t for t in reversed(Base.metadata.sorted_tables) if t.name not in KEEP]


def row_counts(db: DBSession, tables: list[Table]) -> dict[str, int]:
    return {t.name: db.execute(select(func.count()).select_from(t)).scalar() or 0 for t in tables}


def _detach_kept(db: DBSession, wiped: set[str]) -> None:
    """Rows we keep that point at wiped rows: clear an optional link; drop a row that cannot live without it."""
    for t in Base.metadata.sorted_tables:
        if t.name not in KEEP:
            continue
        for fk in t.foreign_keys:
            if fk.column.table.name not in wiped:
                continue
            col = fk.parent
            if col.nullable:
                db.execute(update(t).where(col.is_not(None)).values({col.name: None}))
            else:
                db.execute(t.delete())


def wipe(db: DBSession) -> int:
    """Empty every wiped table; returns the number of rows removed. The caller commits."""
    tables = wiped_tables()
    removed = sum(row_counts(db, tables).values())
    _detach_kept(db, {t.name for t in tables})
    dialect = db.get_bind().dialect.name
    if dialect == "mysql":
        db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    try:
        for t in tables:
            db.execute(t.delete())
    finally:
        if dialect == "mysql":
            db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    if dialect == "mysql":
        for t in tables:
            db.execute(text(f"ALTER TABLE `{t.name}` AUTO_INCREMENT = 1"))
    return removed


def clear_attachments() -> int:
    from app.core.config import settings

    root = Path(settings.upload_dir)
    n = 0
    if root.is_dir():
        for child in root.iterdir():
            n += sum(1 for p in child.rglob("*") if p.is_file()) if child.is_dir() else 1
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    return n


def main() -> None:
    from app.core.audit import log_action
    from app.core.database import SessionLocal
    from app.core.dbcheck import ensure_schema
    from app.platform.backups.service import create_backup

    parser = argparse.ArgumentParser(description="Wipe the workspace's records, keeping users, roles and settings.")
    parser.add_argument("--dry-run", action="store_true", help="only show what would be wiped")
    args = parser.parse_args()

    status = ensure_schema()
    if not status.ok:
        print(f"The database is not reachable: {status.error}")
        sys.exit(2)
    db = SessionLocal()
    try:
        counts = {k: v for k, v in row_counts(db, wiped_tables()).items() if v}
        total = sum(counts.values())
        print("Records to wipe:")
        for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {name:<34} {n:>8}")
        print(f"  {'TOTAL':<34} {total:>8}")
        print("Kept: users, roles, settings, methodology libraries and the audit trail.")
        if args.dry_run:
            return
        if input("\nThis cannot be undone except from the backup. Type WIPE to continue: ").strip() != "WIPE":
            print("Cancelled. Nothing was changed.")
            sys.exit(1)
        print("Taking a full backup first...")
        try:
            info = create_backup(db)
        except Exception as exc:  # noqa: BLE001 - never wipe without a backup
            print(f"Backup failed, nothing was wiped: {exc}")
            sys.exit(3)
        print(f"Backup saved: {info.filename}" + (f" (+ {info.files_name})" if info.files_name else ""))
        removed = wipe(db)
        log_action(db, user_id=None, action=f"DATA_WIPE_CLI rows={removed} backup={info.stamp}")
        db.commit()
        files = clear_attachments() if info.files_name else 0
        print(f"Done: {removed} records wiped" + (f", {files} attachments removed" if files else "") + ".")
        if not info.files_name:
            print("Attachments were left in place because the backup does not include them.")
        print("Restart the app (close its window, then Start-GPHA.cmd) so it starts from the wiped data.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
