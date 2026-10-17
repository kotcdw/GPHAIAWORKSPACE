"""Structured audit trail; follow-up timeline, evidence files, extensions and risk acceptance

- ``audit_logs``: ``username`` (snapshot), ``category``, ``outcome``, ``entity_type``, ``entity_id``,
  ``user_agent`` - so sign-ins, failures, exports and record changes can be filtered and reported.
- ``capa``: ``original_due_date``, ``extension_count``, risk acceptance (who, when, why).
- ``capa_events``: append-only follow-up timeline (progress notes, evidence, validations, extensions,
  escalations, reopenings, closure) - nothing is overwritten.
- ``capa_files``: encrypted evidence files attached to a remediation action.

Revision ID: 0035_audit_trail_followup
Revises: 0034_drop_workspace_prefs
Create Date: 2026-10-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0035_audit_trail_followup"
down_revision: str | None = "0034_drop_workspace_prefs"
branch_labels = None
depends_on = None


def _append_only(table: str) -> None:
    dialect = op.get_bind().dialect.name
    for verb in ("UPDATE", "DELETE"):
        name = f"{table}_no_{verb.lower()}"
        message = f"{table} is append-only: {verb} not permitted"
        if dialect == "mysql":
            op.execute(f"CREATE TRIGGER {name} BEFORE {verb} ON {table} FOR EACH ROW "
                       f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{message}'")
        else:
            op.execute(f"CREATE TRIGGER {name} BEFORE {verb} ON {table} BEGIN SELECT RAISE(ABORT, '{message}'); END;")


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("username", sa.String(64), nullable=True))
    op.add_column("audit_logs", sa.Column("category", sa.String(20), nullable=True))
    op.add_column("audit_logs", sa.Column("outcome", sa.String(10), nullable=True))
    op.add_column("audit_logs", sa.Column("entity_type", sa.String(50), nullable=True))
    op.add_column("audit_logs", sa.Column("entity_id", sa.Integer(), nullable=True))
    op.add_column("audit_logs", sa.Column("user_agent", sa.String(255), nullable=True))
    op.create_index("ix_audit_logs_category", "audit_logs", ["category"])
    op.create_index("ix_audit_logs_outcome", "audit_logs", ["outcome"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])

    op.add_column("capa", sa.Column("original_due_date", sa.DateTime(), nullable=True))
    op.add_column("capa", sa.Column("extension_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("capa", sa.Column("risk_accepted_by", sa.Integer(), nullable=True))
    op.add_column("capa", sa.Column("risk_accepted_at", sa.DateTime(), nullable=True))
    op.add_column("capa", sa.Column("risk_acceptance", sa.Text(), nullable=True))
    op.execute("UPDATE capa SET original_due_date = due_date WHERE original_due_date IS NULL")

    op.create_table(
        "capa_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capa_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("old_due_date", sa.DateTime(), nullable=True),
        sa.Column("new_due_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
    )
    op.create_index("ix_capa_events_capa_id", "capa_events", ["capa_id"])
    _append_only("capa_events")

    op.create_table(
        "capa_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capa_id", sa.Integer(), sa.ForeignKey("capa.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_name", sa.String(200), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_by", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_capa_files_capa_id", "capa_files", ["capa_id"])


def downgrade() -> None:
    op.drop_table("capa_files")
    op.execute("DROP TRIGGER IF EXISTS capa_events_no_update")
    op.execute("DROP TRIGGER IF EXISTS capa_events_no_delete")
    op.drop_table("capa_events")
    with op.batch_alter_table("capa") as batch:
        for name in ("risk_acceptance", "risk_accepted_at", "risk_accepted_by", "extension_count",
                     "original_due_date"):
            batch.drop_column(name)
    op.drop_index("ix_audit_logs_entity", "audit_logs")
    op.drop_index("ix_audit_logs_outcome", "audit_logs")
    op.drop_index("ix_audit_logs_category", "audit_logs")
    with op.batch_alter_table("audit_logs") as batch:
        for name in ("user_agent", "entity_id", "entity_type", "outcome", "category", "username"):
            batch.drop_column(name)
