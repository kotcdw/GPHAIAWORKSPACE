"""Frameworks and standard controls library; scheduler bookings and engagement dates

Revision ID: 0023_frameworks_scheduler
Revises: 0022_ams_compliance
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0023_frameworks_scheduler"
down_revision: str | None = "0022_ams_compliance"
branch_labels = None
depends_on = None



def upgrade() -> None:
    op.create_table(
        "frameworks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("framework_type", sa.String(100), nullable=False),
        sa.Column("issuer", sa.String(160), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "library_controls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("framework_id", sa.Integer(), sa.ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("process_area", sa.String(100), nullable=False),
        sa.Column("risk_statement", sa.Text(), nullable=False),
        sa.Column("control_type", sa.String(20), nullable=False),
        sa.Column("nature", sa.String(20), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("is_key", sa.Boolean(), nullable=False),
        sa.Column("test_procedure", sa.Text(), nullable=False),
        sa.Column("criterion_id", sa.Integer(), sa.ForeignKey("criteria.id", ondelete="SET NULL"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("framework_id", "ref", name="uq_library_controls_framework_ref"),
        sa.CheckConstraint("control_type IN ('Preventive','Detective','Corrective')", name="ck_libctl_type"),
    )
    op.create_index("ix_library_controls_framework_id", "library_controls", ["framework_id"])
    op.add_column("controls", sa.Column("library_control_id", sa.Integer(),
                                        sa.ForeignKey("library_controls.id", ondelete="SET NULL"), nullable=True))
    op.add_column("plan_engagements", sa.Column("planned_start", sa.Date(), nullable=True))
    op.add_column("plan_engagements", sa.Column("planned_end", sa.Date(), nullable=True))
    op.create_table(
        "schedule_bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("plan_engagement_id", sa.Integer(), sa.ForeignKey("plan_engagements.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for col in ("user_id", "plan_engagement_id", "start_date", "end_date"):
        op.create_index(f"ix_schedule_bookings_{col}", "schedule_bookings", [col])


def downgrade() -> None:
    op.drop_table("schedule_bookings")
    op.drop_column("plan_engagements", "planned_end")
    op.drop_column("plan_engagements", "planned_start")
    op.drop_column("controls", "library_control_id")
    op.drop_table("library_controls")
    op.drop_table("frameworks")
