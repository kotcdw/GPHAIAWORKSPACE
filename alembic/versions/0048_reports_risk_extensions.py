"""Reports broadcast schedules and slide videos; KRI-driven and per-segment risk assessment.

* ``report_broadcasts``: send an active report, dashboard or presentation on a schedule (Daily, Weekly, Monthly at
  an hour in the workspace time zone) to chosen users and groups.
* ``report_media``: MP4 / WebM videos uploaded for presentation slides, stored with the other uploads.
* ``key_risk_indicators.drives``, ``amber_step``, ``red_step``: an indicator can drive the risk's residual
  likelihood or impact when its latest reading is Amber or Red.
* ``risk_assessments.origin``: manual, kri or segments.
* ``risk_segment_assessments``: dated assessments of one risk for one organisation segment.

Revision ID: 0048_reports_risk_extensions
Revises: 0047_walkthrough_ui
Create Date: 2026-10-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0048_reports_risk_extensions"
down_revision: str | None = "0047_walkthrough_ui"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_broadcasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("report_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("frequency", sa.String(20), nullable=False, server_default="Weekly"),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("hour", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("user_ids", sa.Text(), nullable=False),
        sa.Column("group_ids", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_result", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_report_broadcasts_item_id", "report_broadcasts", ["item_id"])
    op.create_index("ix_report_broadcasts_next_run_at", "report_broadcasts", ["next_run_at"])
    op.create_table(
        "report_media",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("stored_name", sa.String(80), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table("key_risk_indicators") as t:
        t.add_column(sa.Column("drives", sa.String(20), nullable=False, server_default=""))
        t.add_column(sa.Column("amber_step", sa.Integer(), nullable=False, server_default="1"))
        t.add_column(sa.Column("red_step", sa.Integer(), nullable=False, server_default="2"))
    with op.batch_alter_table("risk_assessments") as t:
        t.add_column(sa.Column("origin", sa.String(20), nullable=False, server_default="manual"))
    op.create_table(
        "risk_segment_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("risk_id", sa.Integer(), sa.ForeignKey("enterprise_risks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inherent_likelihood", sa.Integer(), nullable=False),
        sa.Column("inherent_impact", sa.Integer(), nullable=False),
        sa.Column("residual_likelihood", sa.Integer(), nullable=False),
        sa.Column("residual_impact", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("assessed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assessed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_risk_segment_assessments_risk_id", "risk_segment_assessments", ["risk_id"])
    op.create_index("ix_risk_segment_assessments_org_id", "risk_segment_assessments", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_segment_assessments_org_id", table_name="risk_segment_assessments")
    op.drop_index("ix_risk_segment_assessments_risk_id", table_name="risk_segment_assessments")
    op.drop_table("risk_segment_assessments")
    with op.batch_alter_table("risk_assessments") as t:
        t.drop_column("origin")
    with op.batch_alter_table("key_risk_indicators") as t:
        t.drop_column("red_step")
        t.drop_column("amber_step")
        t.drop_column("drives")
    op.drop_table("report_media")
    op.drop_index("ix_report_broadcasts_next_run_at", table_name="report_broadcasts")
    op.drop_index("ix_report_broadcasts_item_id", table_name="report_broadcasts")
    op.drop_table("report_broadcasts")
