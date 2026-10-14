"""plan change requests: requested, reviewed and approved changes to an approved Assurance Plan

Revision ID: 0017_plan_change_requests
Revises: 0016_plan_lifecycle_status
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0017_plan_change_requests"
down_revision: str | None = "0016_plan_lifecycle_status"
branch_labels = None
depends_on = None


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "plan_change_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cr_ref", sa.String(20), nullable=False, unique=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("items", sa.Text(), nullable=False),
        sa.Column("impact", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Submitted"),
        _user("requested_by"),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        _user("reviewer_id"),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        _user("approver_id"),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("new_version", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('Submitted','Endorsed','Returned','Approved','Rejected','Withdrawn')",
                           name="ck_plan_change_requests_status"),
    )
    op.create_index("ix_plan_change_requests_plan_id", "plan_change_requests", ["plan_id"])
    op.execute("INSERT INTO reference_sequences (prefix, next_value) SELECT 'PCR', 0 FROM DUAL "
               "WHERE NOT EXISTS (SELECT 1 FROM reference_sequences WHERE prefix = 'PCR')")


def downgrade() -> None:
    op.execute("DELETE FROM reference_sequences WHERE prefix = 'PCR'")
    op.drop_table("plan_change_requests")
