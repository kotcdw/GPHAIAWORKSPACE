"""Workplan procedures, testing rounds and test plans, linked evidence requests, Issue Tracker fields on findings

Revision ID: 0029_fieldwork_issues
Revises: 0028_audit_team
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0029_fieldwork_issues"
down_revision: str | None = "0028_audit_team"
branch_labels = None
depends_on = None


def _user_fk(name: str, table: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL",
                                                       name=f"fk_{table}_{name}"), nullable=True)


def upgrade() -> None:
    op.add_column("audits", sa.Column("workflow", sa.String(20), nullable=False, server_default="Internal Control"))
    op.add_column("audits", sa.Column("testing_rounds", sa.Integer(), nullable=False, server_default="1"))

    op.add_column("controls", sa.Column("test_method", sa.String(60), nullable=True))
    op.add_column("controls", sa.Column("total_sample_size", sa.Integer(), nullable=True))
    op.add_column("controls", sa.Column("test_steps", sa.Text(), nullable=True))
    op.add_column("control_tests", sa.Column("round_no", sa.Integer(), nullable=True))
    op.add_column("control_tests", sa.Column("in_scope", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("control_tests", sa.Column("assigned_to", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_control_tests_assigned_to", "control_tests", "users", ["assigned_to"], ["id"],
                          ondelete="SET NULL")
    # Existing operating-effectiveness tests belong to round 1.
    op.execute("UPDATE control_tests SET round_no = 1 WHERE test_type = 'Operating Effectiveness'")

    op.create_table(
        "procedures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("objective_id", sa.Integer(), sa.ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("steps", sa.Text(), nullable=False),
        _user_fk("assigned_to", "procedures"),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="Not Started"),
        sa.Column("results", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=True),
        _user_fk("performed_by", "procedures"),
        sa.Column("performed_at", sa.DateTime(), nullable=True),
        _user_fk("reviewed_by", "procedures"),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=False),
        _user_fk("created_by", "procedures"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_procedures_objective_id", "procedures", ["objective_id"])
    op.create_table(
        "procedure_risks",
        sa.Column("procedure_id", sa.Integer(), sa.ForeignKey("procedures.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("risk_id", sa.Integer(), sa.ForeignKey("risks.id", ondelete="CASCADE"), primary_key=True),
    )

    op.add_column("evidence_requests", sa.Column("target_type", sa.String(20), nullable=True))
    op.add_column("evidence_requests", sa.Column("target_id", sa.Integer(), nullable=True))
    op.add_column("evidence_requests", sa.Column("cc_user_ids", sa.Text(), nullable=True))
    op.add_column("evidence_requests", sa.Column("reminder", sa.String(20), nullable=True))
    op.add_column("evidence_requests", sa.Column("last_reminded_at", sa.DateTime(), nullable=True))

    op.add_column("findings", sa.Column("issue_type", sa.String(60), nullable=True))
    op.add_column("findings", sa.Column("published", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("findings", sa.Column("published_at", sa.DateTime(), nullable=True))
    op.add_column("findings", sa.Column("published_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_findings_published_by", "findings", "users", ["published_by"], ["id"],
                          ondelete="SET NULL")
    op.add_column("findings", sa.Column("procedure_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_findings_procedure_id", "findings", "procedures", ["procedure_id"], ["id"],
                          ondelete="SET NULL")
    op.add_column("findings", sa.Column("review_stage", sa.String(20), nullable=True))
    op.add_column("findings", sa.Column("review_trail", sa.Text(), nullable=True))
    op.add_column("findings", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    # Findings recorded before publication existed stay visible to auditees exactly as before.
    op.execute("UPDATE findings SET published = 1, published_at = created_at")


def downgrade() -> None:
    op.drop_constraint("fk_findings_published_by", "findings", type_="foreignkey")
    op.drop_constraint("fk_findings_procedure_id", "findings", type_="foreignkey")
    for col in ("procedure_id", "reviewed_at", "review_trail", "review_stage", "published_by", "published_at",
                "published",
                "issue_type"):
        op.drop_column("findings", col)
    for col in ("last_reminded_at", "reminder", "cc_user_ids", "target_id", "target_type"):
        op.drop_column("evidence_requests", col)
    op.drop_table("procedure_risks")
    op.drop_table("procedures")
    op.drop_constraint("fk_control_tests_assigned_to", "control_tests", type_="foreignkey")
    for col in ("assigned_to", "in_scope", "round_no"):
        op.drop_column("control_tests", col)
    for col in ("test_steps", "total_sample_size", "test_method"):
        op.drop_column("controls", col)
    op.drop_column("audits", "testing_rounds")
    op.drop_column("audits", "workflow")
