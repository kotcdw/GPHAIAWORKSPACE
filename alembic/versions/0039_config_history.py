"""Settings change history

``app_config_history`` keeps every change to a setting (Configuration screen): the old and new value, who made it,
when, and the reason given. It is append-only (database triggers refuse UPDATE and DELETE). The person is stored
by id and name without a foreign key, so deleting an account never needs to rewrite the history.

Revision ID: 0039_config_history
Revises: 0038_org_unit_admin
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0039_config_history"
down_revision: str | None = "0038_org_unit_admin"
branch_labels = None
depends_on = None

TABLE = "app_config_history"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, index=True),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("changed_by_name", sa.String(255), nullable=True),
        sa.Column("changed_at", sa.DateTime(), nullable=False, index=True),
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
