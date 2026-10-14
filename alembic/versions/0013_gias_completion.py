"""GIAS completion: committee plan approval + plan changes, criteria library, review notes,
working-paper cross-references and sign-off, exit meeting, follow-up procedures

Revision ID: 0013_gias_completion
Revises: 0012_entities_custom_fields
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0013_gias_completion"
down_revision: str | None = "0012_entities_custom_fields"
branch_labels = None
depends_on = None


def _user(name: str, nullable: bool = True, ondelete: str = "SET NULL") -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    # Audit Committee approval of the plan
    op.add_column("assurance_plans", sa.Column("committee_meeting_date", sa.DateTime(), nullable=True))
    op.add_column("assurance_plans", sa.Column("committee_reference", sa.String(100), nullable=True))
    op.add_column("assurance_plans", sa.Column("committee_notes", sa.Text(), nullable=True))
    op.add_column("assurance_plans", sa.Column("committee_recorded_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_plan_committee_user", "assurance_plans", "users", ["committee_recorded_by"], ["id"],
                          ondelete="SET NULL")
    op.add_column("assurance_plans", sa.Column("committee_recorded_at", sa.DateTime(), nullable=True))
    op.create_table(
        "plan_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("plan_engagements.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _user("changed_by"),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_plan_changes_plan_id", "plan_changes", ["plan_id"])

    # Criteria library
    op.create_table(
        "criteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("crit_ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="Policy"),
        sa.Column("reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Active"),
        _user("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('Active','Retired')", name="ck_criteria_status"),
    )
    op.execute("INSERT INTO reference_sequences (prefix, next_value) SELECT 'CR', 0 FROM DUAL "
               "WHERE NOT EXISTS (SELECT 1 FROM reference_sequences WHERE prefix = 'CR')")
    op.add_column("findings", sa.Column("criterion_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_findings_criterion", "findings", "criteria", ["criterion_id"], ["id"],
                          ondelete="SET NULL")

    # Review notes (supervision)
    op.create_table(
        "review_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("target_label", sa.String(255), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Open"),
        sa.Column("response", sa.Text(), nullable=True),
        _user("raised_by"),
        sa.Column("raised_at", sa.DateTime(), nullable=False),
        _user("responded_by"),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        _user("cleared_by"),
        sa.Column("cleared_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('Open','Responded','Cleared')", name="ck_review_notes_status"),
    )
    op.create_index("ix_review_notes_audit_id", "review_notes", ["audit_id"])

    # Working-paper cross-references and reviewer sign-off
    op.add_column("working_papers", sa.Column("wp_ref", sa.String(30), nullable=True))
    op.add_column("working_papers", sa.Column("test_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_wp_test", "working_papers", "control_tests", ["test_id"], ["id"], ondelete="SET NULL")
    op.add_column("working_papers", sa.Column("finding_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_wp_finding", "working_papers", "findings", ["finding_id"], ["id"], ondelete="SET NULL")
    op.add_column("working_papers", sa.Column("reviewed_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_wp_reviewer", "working_papers", "users", ["reviewed_by"], ["id"], ondelete="SET NULL")
    op.add_column("working_papers", sa.Column("reviewed_at", sa.DateTime(), nullable=True))

    # Exit meeting on the report
    op.add_column("audit_reports", sa.Column("exit_meeting_date", sa.DateTime(), nullable=True))
    op.add_column("audit_reports", sa.Column("exit_meeting_attendees", sa.Text(), nullable=True))
    op.add_column("audit_reports", sa.Column("exit_meeting_notes", sa.Text(), nullable=True))

    # Follow-up testing performed by the validating auditor
    op.add_column("capa", sa.Column("validation_procedures", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("capa", "validation_procedures")
    for col in ("exit_meeting_notes", "exit_meeting_attendees", "exit_meeting_date"):
        op.drop_column("audit_reports", col)
    for fk in ("fk_wp_reviewer", "fk_wp_finding", "fk_wp_test"):
        op.drop_constraint(fk, "working_papers", type_="foreignkey")
    for col in ("reviewed_at", "reviewed_by", "finding_id", "test_id", "wp_ref"):
        op.drop_column("working_papers", col)
    op.drop_table("review_notes")
    op.drop_constraint("fk_findings_criterion", "findings", type_="foreignkey")
    op.drop_column("findings", "criterion_id")
    op.execute("DELETE FROM reference_sequences WHERE prefix = 'CR'")
    op.drop_table("criteria")
    op.drop_table("plan_changes")
    op.drop_constraint("fk_plan_committee_user", "assurance_plans", type_="foreignkey")
    for col in ("committee_recorded_at", "committee_recorded_by", "committee_notes", "committee_reference",
                "committee_meeting_date"):
        op.drop_column("assurance_plans", col)
