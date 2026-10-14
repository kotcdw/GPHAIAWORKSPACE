"""AMS compliance: follow-up reporting, Audit Committee register, charter, EQA, declarations, CPD,
report distribution, automation rules and custom fields on audits / findings / actions

Revision ID: 0022_ams_compliance
Revises: 0021_ai_requests
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0022_ams_compliance"
down_revision: str | None = "0021_ai_requests"
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.Integer(), primary_key=True)


def _user(name: str, nullable: bool = True, cascade: bool = False) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE" if cascade else "SET NULL"),
                     nullable=nullable)


def upgrade() -> None:
    # --- actions / recommendations
    with op.batch_alter_table("capa") as t:
        t.add_column(sa.Column("implementation_status", sa.String(30), nullable=False,
                               server_default="Not Implemented"))
        t.add_column(sa.Column("timeframe", sa.String(60), nullable=True))
        t.add_column(sa.Column("source_body", sa.String(100), nullable=True))
        t.add_column(sa.Column("source_reference", sa.String(120), nullable=True))
        t.add_column(sa.Column("source_year", sa.Integer(), nullable=True))
        t.add_column(sa.Column("followup_comment", sa.Text(), nullable=True))
        t.add_column(sa.Column("progress_note", sa.Text(), nullable=True))
        t.add_column(sa.Column("withdrawal_reason", sa.Text(), nullable=True))
        t.add_column(_user("withdrawal_proposed_by"))
        t.add_column(sa.Column("withdrawal_proposed_at", sa.DateTime(), nullable=True))
        t.add_column(sa.Column("external_closure_ref", sa.String(120), nullable=True))
        t.add_column(sa.Column("custom_fields", sa.Text(), nullable=True))
    op.execute("UPDATE capa SET custom_fields='{}' WHERE custom_fields IS NULL")
    op.execute("UPDATE capa SET implementation_status='Fully Implemented' WHERE status='Closed'")
    op.execute("UPDATE capa SET implementation_status='Partially Implemented' "
               "WHERE status IN ('Review') OR implemented_at IS NOT NULL AND status <> 'Closed'")
    op.execute("UPDATE capa SET source_body='Internal Audit' WHERE source_type='finding'")
    for table in ("audits", "findings"):
        op.add_column(table, sa.Column("custom_fields", sa.Text(), nullable=True))
        op.execute(f"UPDATE {table} SET custom_fields='{{}}'")
    # --- report response deadline + distribution register
    op.add_column("audit_reports", sa.Column("draft_sent_at", sa.DateTime(), nullable=True))
    op.add_column("audit_reports", sa.Column("response_due_at", sa.DateTime(), nullable=True))
    op.add_column("audit_reports", sa.Column("response_received_at", sa.DateTime(), nullable=True))
    op.create_table(
        "report_distributions", _id(),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("audit_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient", sa.String(160), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        _user("recorded_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_report_distributions_report_id", "report_distributions", ["report_id"])
    # --- Audit Committee meetings and decisions
    op.create_table(
        "committee_meetings", _id(),
        sa.Column("meeting_ref", sa.String(20), nullable=False, unique=True),
        sa.Column("meeting_date", sa.DateTime(), nullable=False),
        sa.Column("meeting_type", sa.String(20), nullable=False),
        sa.Column("venue", sa.String(160), nullable=False),
        sa.Column("agenda", sa.Text(), nullable=False),
        sa.Column("attendees", sa.Text(), nullable=False),
        sa.Column("apologies", sa.Text(), nullable=False),
        sa.Column("quorum", sa.Boolean(), nullable=False),
        sa.Column("minutes", sa.Text(), nullable=False),
        sa.Column("followup_report_considered", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("minutes_approved_at", sa.DateTime(), nullable=True),
        _user("minutes_approved_by"),
        _user("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_committee_meetings_meeting_date", "committee_meetings", ["meeting_date"])
    op.create_table(
        "committee_decisions", _id(),
        sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("committee_meetings.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("subject_type", sa.String(30), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("new_due_date", sa.DateTime(), nullable=True),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        _user("recorded_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_committee_decisions_meeting_id", "committee_decisions", ["meeting_id"])
    # --- follow-up report register
    op.create_table(
        "followup_submissions", _id(),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=True),
        sa.Column("period_label", sa.String(60), nullable=False),
        sa.Column("recipients", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("snapshot", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column("counts", sa.Text(), nullable=False),
        _user("recorded_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    # --- charter and external quality assessments
    op.create_table(
        "ia_charters", _id(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approval_reference", sa.String(120), nullable=True),
        sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("committee_meetings.id", ondelete="SET NULL"),
                  nullable=True),
        _user("approved_recorded_by"),
        sa.Column("next_review_due", sa.DateTime(), nullable=True),
        _user("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "external_assessments", _id(),
        sa.Column("assessment_type", sa.String(60), nullable=False),
        sa.Column("assessor", sa.String(200), nullable=False),
        sa.Column("assessor_independent", sa.Boolean(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.Column("conclusion", sa.String(40), nullable=False),
        sa.Column("report_reference", sa.String(120), nullable=True),
        sa.Column("action_plan", sa.Text(), nullable=False),
        sa.Column("reported_to_committee_at", sa.DateTime(), nullable=True),
        sa.Column("next_due", sa.DateTime(), nullable=False),
        _user("recorded_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    # --- declarations and CPD
    op.create_table(
        "declarations", _id(),
        _user("user_id", nullable=False, cascade=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("independence_confirmed", sa.Boolean(), nullable=False),
        sa.Column("ethics_confirmed", sa.Boolean(), nullable=False),
        sa.Column("confidentiality_confirmed", sa.Boolean(), nullable=False),
        sa.Column("has_conflict", sa.Boolean(), nullable=False),
        sa.Column("conflict_details", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        _user("reviewed_by"),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=False),
    )
    op.create_index("ix_declarations_user_id", "declarations", ["user_id"])
    op.create_index("ix_declarations_audit_id", "declarations", ["audit_id"])
    op.create_table(
        "cpd_records", _id(),
        _user("user_id", nullable=False, cascade=True),
        sa.Column("activity_date", sa.DateTime(), nullable=False),
        sa.Column("activity", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(160), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("ethics_hours", sa.Float(), nullable=False),
        sa.Column("evidence_ref", sa.String(255), nullable=False),
        _user("verified_by"),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cpd_records_user_id", "cpd_records", ["user_id"])
    op.create_table(
        "certifications", _id(),
        _user("user_id", nullable=False, cascade=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("issuer", sa.String(160), nullable=False),
        sa.Column("number", sa.String(80), nullable=False),
        sa.Column("obtained_on", sa.DateTime(), nullable=True),
        sa.Column("expires_on", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_certifications_user_id", "certifications", ["user_id"])
    # --- automation rules
    op.create_table(
        "automation_rules", _id(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("trigger", sa.String(60), nullable=False),
        sa.Column("offset_days", sa.Integer(), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=False),
        sa.Column("actions", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("builtin_key", sa.String(60), nullable=True, unique=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        _user("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_automation_rules_trigger", "automation_rules", ["trigger"])
    op.create_table(
        "automation_runs", _id(),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_type", sa.String(40), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("period_key", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(255), nullable=False),
        sa.Column("fired_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("rule_id", "record_type", "record_id", "period_key", name="uq_automation_runs_once"),
    )
    op.create_index("ix_automation_runs_rule_id", "automation_runs", ["rule_id"])
    op.create_index("ix_automation_runs_fired_at", "automation_runs", ["fired_at"])


def downgrade() -> None:
    for table in ("automation_runs", "automation_rules", "certifications", "cpd_records", "declarations",
                  "external_assessments", "ia_charters", "followup_submissions", "committee_decisions",
                  "committee_meetings", "report_distributions"):
        op.drop_table(table)
    for col in ("response_received_at", "response_due_at", "draft_sent_at"):
        op.drop_column("audit_reports", col)
    for table in ("audits", "findings"):
        op.drop_column(table, "custom_fields")
    for col in ("custom_fields", "external_closure_ref", "withdrawal_proposed_at", "withdrawal_proposed_by",
                "withdrawal_reason", "progress_note", "followup_comment", "source_year", "source_reference",
                "source_body", "timeframe", "implementation_status"):
        op.drop_column("capa", col)
