"""Backup checks

``backup_checks`` records every verification of a backup set (automatic after each backup, or on request) and
every full restore test run with ``scripts.verify_backup``. Append-only.

Revision ID: 0041_backup_checks
Revises: 0040_import_runs
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0041_backup_checks"
down_revision: str | None = "0040_import_runs"
branch_labels = None
depends_on = None

TABLE = "backup_checks"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("backup", sa.String(80), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_name", sa.String(255), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False, index=True),
    )
    dialect = op.get_bind().dialect.name
    for verb in ("UPDATE", "DELETE"):
        name = f"{TABLE}_no_{verb.lower()}"
        message = f"{TABLE} is append-only: {verb} not permitted"
        if dialect == "mysql":
            op.execute(f"CREATE TRIGGER {name} BEFORE {verb} ON {TABLE} FOR EACH ROW "
                       f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{message}'")
        else:
            op.execute(f"CREATE TRIGGER {name} BEFORE {verb} ON {TABLE} BEGIN SELECT RAISE(ABORT, '{message}'); END;")


def downgrade() -> None:
    for verb in ("update", "delete"):
        op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_{verb}")
    op.drop_table(TABLE)
