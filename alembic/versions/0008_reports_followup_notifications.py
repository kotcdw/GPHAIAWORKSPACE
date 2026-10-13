"""audit reports, follow-up validation, notifications, review levels, MFA

Revision ID: 0008_reports_followup
Revises: 0007_form_drafts
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0008_reports_followup"
down_revision: str | None = "0007_form_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users: review level (Manager / CAE) and optional TOTP MFA ----------
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("review_level", sa.String(20), nullable=True))
        batch.add_column(sa.Column("mfa_secret", sa.String(255), nullable=True))
        batch.add_column(sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default="0"))

    # --- CAPA follow-up: implementation evidence, auditor validation, escalation
    with op.batch_alter_table("capa") as batch:
        batch.add_column(sa.Column("implementation_evidence", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("implemented_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
        )
        batch.add_column(sa.Column("implemented_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("validation_result", sa.String(20), nullable=True))
        batch.add_column(sa.Column("validation_comment", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("validated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
        )
        batch.add_column(sa.Column("validated_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("reopen_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_escalated_at", sa.DateTime(), nullable=True))

    # --- in-app notifications ------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link_type", sa.String(50), nullable=True),
        sa.Column("link_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("emailed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "is_read"])

    # --- audit reports ---------------------------------------------------------
    op.create_table(
        "audit_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="RESTRICT"), nullable=False, unique=True
        ),
        sa.Column("report_ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="Draft"),
        sa.Column("overall_rating", sa.String(30), nullable=True),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("background", sa.Text(), nullable=False),
        sa.Column("scope_objectives", sa.Text(), nullable=False),
        sa.Column("methodology", sa.Text(), nullable=False),
        sa.Column("overall_opinion", sa.Text(), nullable=False),
        sa.Column("distribution_list", sa.Text(), nullable=False),
        sa.Column("management_comments", sa.Text(), nullable=False),
        sa.Column("issued_snapshot", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("manager_reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("manager_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("cae_approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cae_approved_at", sa.DateTime(), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('Draft','Management Review','Manager Review','CAE Approval','Issued')",
            name="ck_audit_reports_status",
        ),
        sa.CheckConstraint(
            "overall_rating IS NULL OR overall_rating IN ('Satisfactory','Needs Improvement','Unsatisfactory')",
            name="ck_audit_reports_rating",
        ),
    )
    op.execute("INSERT INTO reference_sequences (prefix, next_value) VALUES ('RPT', 0)")


def downgrade() -> None:
    op.execute("DELETE FROM reference_sequences WHERE prefix = 'RPT'")
    op.drop_table("audit_reports")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_table("notifications")
    with op.batch_alter_table("capa") as batch:
        for col in (
            "last_escalated_at",
            "escalation_level",
            "reopen_count",
            "validated_at",
            "validated_by",
            "validation_comment",
            "validation_result",
            "implemented_at",
            "implemented_by",
            "implementation_evidence",
        ):
            batch.drop_column(col)
    with op.batch_alter_table("users") as batch:
        batch.drop_column("mfa_enabled")
        batch.drop_column("mfa_secret")
        batch.drop_column("review_level")
