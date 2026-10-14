"""annual planning cycle: stages, cycle events, approved versions, controlled distribution

Revision ID: 0015_plan_cycle
Revises: 0014_roles_programs_evidence
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0015_plan_cycle"
down_revision: str | None = "0014_roles_programs_evidence"
branch_labels = None
depends_on = None


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    op.add_column("assurance_plans", sa.Column("cycle_stage", sa.String(30), nullable=False,
                                               server_default="preparation"))
    op.add_column("assurance_plans", sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"))
    # Plans that existed before the cycle: place them at the matching stage.
    op.execute("UPDATE assurance_plans SET cycle_stage = 'drafting' WHERE status = 'Draft'")
    op.execute("UPDATE assurance_plans SET cycle_stage = 'committee' WHERE status = 'Approved' "
               "AND committee_meeting_date IS NULL")
    op.execute("UPDATE assurance_plans SET cycle_stage = 'distribution', current_version = 1 "
               "WHERE status = 'Approved' AND committee_meeting_date IS NOT NULL")
    op.execute("UPDATE assurance_plans SET cycle_stage = 'execution', current_version = 1 WHERE status = 'Closed'")

    op.create_table(
        "plan_cycle_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("decision", sa.String(40), nullable=True),
        sa.Column("meeting_date", sa.DateTime(), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("attendees", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("data", sa.Text(), nullable=True),
        _user("user_id"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_plan_cycle_events_plan_id", "plan_cycle_events", ["plan_id"])
    op.create_table(
        "plan_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.Text().with_variant(sa.dialects.mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("committee_reference", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=False),
        _user("created_by"),
        sa.UniqueConstraint("plan_id", "version", name="uq_plan_versions_plan_version"),
    )
    op.create_table(
        "plan_distributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        _user("sent_by"),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("plan_id", "version", "user_id", name="uq_plan_distributions"),
    )
    op.create_index("ix_plan_distributions_user_id", "plan_distributions", ["user_id"])


def downgrade() -> None:
    op.drop_table("plan_distributions")
    op.drop_table("plan_versions")
    op.drop_table("plan_cycle_events")
    op.drop_column("assurance_plans", "current_version")
    op.drop_column("assurance_plans", "cycle_stage")
