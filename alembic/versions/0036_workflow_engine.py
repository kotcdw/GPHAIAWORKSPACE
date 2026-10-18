"""Workflow engine: definitions, transition log, work items (My work) and SLA policies

- ``workflow_definitions``: versioned workflows per record type (the shipped defaults live in code until an
  administrator saves a customised version).
- ``workflow_transitions``: every status change of a tracked record, append-only.
- ``work_items``: the inbox - who must act next on which record, with a working-day due date and SLA state.
- ``sla_policies``: time allowed per kind of task (prepare 5, review 3, client response 10, validation 10 working
  days by default).

Revision ID: 0036_workflow_engine
Revises: 0035_audit_trail_followup
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0036_workflow_engine"
down_revision: str | None = "0035_audit_trail_followup"
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
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_type", sa.String(40), nullable=False),
        sa.Column("audit_type", sa.String(100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_workflow_definitions_record_type", "workflow_definitions", ["record_type"])

    op.create_table(
        "workflow_transitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_type", sa.String(40), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("audit_id", sa.Integer(), nullable=True),
        sa.Column("from_state", sa.String(40), nullable=True),
        sa.Column("to_state", sa.String(40), nullable=False),
        sa.Column("action", sa.String(60), nullable=True),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="app"),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_workflow_transitions_record", "workflow_transitions", ["record_type", "record_id"])
    op.create_index("ix_workflow_transitions_audit_id", "workflow_transitions", ["audit_id"])
    op.create_index("ix_workflow_transitions_created_at", "workflow_transitions", ["created_at"])
    _append_only("workflow_transitions")

    op.create_table(
        "work_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("record_type", sa.String(40), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("audit_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="open"),
        sa.Column("sla_key", sa.String(40), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("due_from_record", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sla_state", sa.String(10), nullable=False, server_default="ok"),
        sa.Column("warned_at", sa.DateTime(), nullable=True),
        sa.Column("breached_at", sa.DateTime(), nullable=True),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_work_items_assignee_status", "work_items", ["assignee_id", "status"])
    op.create_index("ix_work_items_record", "work_items", ["record_type", "record_id"])
    op.create_index("ix_work_items_audit_id", "work_items", ["audit_id"])

    op.create_table(
        "sla_policies",
        sa.Column("key", sa.String(40), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("working_days", sa.Integer(), nullable=False),
        sa.Column("warn_before_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("escalate_on_breach", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    for verb in ("update", "delete"):
        op.execute(f"DROP TRIGGER IF EXISTS workflow_transitions_no_{verb}")
    op.drop_table("sla_policies")
    op.drop_table("work_items")
    op.drop_table("workflow_transitions")
    op.drop_table("workflow_definitions")
