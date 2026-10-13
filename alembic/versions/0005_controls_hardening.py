"""controls hardening: auditee assignments, login lockout, evidence integrity

- ``audit_auditees``: which Auditee accounts may see an audit.
- ``users.failed_login_count`` / ``users.locked_until``: brute-force lockout.
- ``working_papers``: soft delete (``is_deleted``/``deleted_by``/``deleted_at``),
  ``encrypted`` flag and ``sha256`` integrity hash.
- Append-only triggers on ``record_history`` and ``approval_cycles`` (the same
  protection ``audit_logs`` already has).

Revision ID: 0005_controls_hardening
Revises: 0004_user_profile_fields
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0005_controls_hardening"
down_revision: str | None = "0004_user_profile_fields"
branch_labels = None
depends_on = None

_PROTECTED = ("record_history", "approval_cycles")


def _create_append_only_triggers(table: str) -> None:
    dialect = op.get_bind().dialect.name
    for verb in ("UPDATE", "DELETE"):
        name = f"{table}_no_{verb.lower()}"
        message = f"{table} is append-only: {verb} not permitted"
        if dialect == "mysql":
            op.execute(
                f"CREATE TRIGGER {name} BEFORE {verb} ON {table} FOR EACH ROW "
                f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{message}'"
            )
        else:
            op.execute(
                f"CREATE TRIGGER {name} BEFORE {verb} ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{message}'); END;"
            )


def upgrade() -> None:
    op.create_table(
        "audit_auditees",
        sa.Column("audit_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("audit_id", "user_id"),
        sa.ForeignKeyConstraint(["audit_id"], ["audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_auditees_user_id", "audit_auditees", ["user_id"], unique=False)

    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(), nullable=True))

    op.add_column("working_papers", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("working_papers", sa.Column("deleted_by", sa.Integer(), nullable=True))
    op.add_column("working_papers", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("working_papers", sa.Column("encrypted", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("working_papers", sa.Column("sha256", sa.String(length=64), nullable=True))

    for table in _PROTECTED:
        _create_append_only_triggers(table)


def downgrade() -> None:
    for table in _PROTECTED:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")

    with op.batch_alter_table("working_papers") as batch:
        for name in ("sha256", "encrypted", "deleted_at", "deleted_by", "is_deleted"):
            batch.drop_column(name)
    with op.batch_alter_table("users") as batch:
        batch.drop_column("locked_until")
        batch.drop_column("failed_login_count")

    op.drop_index("ix_audit_auditees_user_id", table_name="audit_auditees")
    op.drop_table("audit_auditees")
