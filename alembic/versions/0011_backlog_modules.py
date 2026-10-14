"""planning memos, auditor capacity and time sheets, QAIP, saved views

Revision ID: 0011_backlog_modules
Revises: 0010_remediation_refs
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0011_backlog_modules"
down_revision: str | None = "0010_remediation_refs"
branch_labels = None
depends_on = None


def _user_fk(name: str, nullable: bool = True, ondelete: str = "SET NULL") -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "planning_memos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False,
                  unique=True),
        sa.Column("background", sa.Text(), nullable=False),
        sa.Column("objectives", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("key_risks", sa.Text(), nullable=False),
        sa.Column("approach", sa.Text(), nullable=False),
        sa.Column("team", sa.Text(), nullable=False),
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.Column("budget_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="Draft"),
        sa.Column("review_comment", sa.Text(), nullable=False),
        _user_fk("prepared_by"),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        _user_fk("approved_by"),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('Draft','Submitted','Approved','Returned')", name="ck_memo_status"),
    )
    op.create_table(
        "auditor_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("grade", sa.String(100), nullable=False, server_default=""),
        sa.Column("skills", sa.Text(), nullable=False),
        sa.Column("certifications", sa.Text(), nullable=False),
        sa.Column("annual_hours", sa.Integer(), nullable=False, server_default="1600"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "time_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk("user_id", nullable=False, ondelete="CASCADE"),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(30), nullable=False, server_default="Audit"),
        sa.Column("entry_date", sa.DateTime(), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("hours > 0 AND hours <= 24", name="ck_time_hours"),
    )
    op.create_index("ix_time_entries_user_id", "time_entries", ["user_id"])
    op.create_index("ix_time_entries_audit_id", "time_entries", ["audit_id"])
    op.create_table(
        "quality_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False,
                  unique=True),
        sa.Column("answers", sa.Text(), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        _user_fk("reviewer_id"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "audit_surveys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        _user_fk("respondent_id"),
        sa.Column("scores", sa.Text(), nullable=False),
        sa.Column("average", sa.Float(), nullable=False, server_default="0"),
        sa.Column("comments", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("audit_id", "respondent_id", name="uq_survey_audit_respondent"),
    )
    op.create_index("ix_audit_surveys_audit_id", "audit_surveys", ["audit_id"])
    op.create_table(
        "saved_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        _user_fk("user_id", nullable=False, ondelete="CASCADE"),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("params", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "module", "name", name="uq_saved_view"),
    )
    op.create_index("ix_saved_views_user_id", "saved_views", ["user_id"])


def downgrade() -> None:
    for table in ("saved_views", "audit_surveys", "quality_reviews", "time_entries", "auditor_profiles",
                  "planning_memos"):
        op.drop_table(table)
