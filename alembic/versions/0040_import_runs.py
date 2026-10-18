"""Bulk import history

``import_runs`` records every import that was carried out and every upload that was rejected (with its first
problems), so administrators can see what came in, from whom, and what failed. Append-only.

Revision ID: 0040_import_runs
Revises: 0039_config_history
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0040_import_runs"
down_revision: str | None = "0039_config_history"
branch_labels = None
depends_on = None

TABLE = "import_runs"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False, index=True),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("outcome", sa.String(10), nullable=False, index=True),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Text(), nullable=True),
        sa.Column("context", sa.String(120), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True, index=True),
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
