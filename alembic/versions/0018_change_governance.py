"""significant plan changes go to the Audit Committee (IIA GIAS 9.4); IAA submission of approved versions

Revision ID: 0018_change_governance
Revises: 0017_plan_change_requests
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0018_change_governance"
down_revision: str | None = "0017_plan_change_requests"
branch_labels = None
depends_on = None


def _user(name: str, fk: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL", name=fk), nullable=True)


def upgrade() -> None:
    t = "plan_change_requests"
    op.add_column(t, sa.Column("significant", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column(t, sa.Column("committee_decision", sa.String(40), nullable=True))
    op.add_column(t, sa.Column("committee_meeting_date", sa.DateTime(), nullable=True))
    op.add_column(t, sa.Column("committee_reference", sa.String(100), nullable=True))
    op.add_column(t, sa.Column("committee_notes", sa.Text(), nullable=True))
    op.add_column(t, _user("committee_recorded_by", "fk_pcr_committee_recorded_by"))
    op.drop_constraint("ck_plan_change_requests_status", t, type_="check")
    op.create_check_constraint(
        "ck_plan_change_requests_status", t,
        "status IN ('Submitted','Endorsed','Returned','Awaiting Committee','Approved','Rejected','Withdrawn')")
    op.alter_column("plan_versions", "decision", existing_type=sa.String(40), type_=sa.String(160),
                    existing_nullable=False)
    op.add_column("plan_versions", sa.Column("iaa_submitted_at", sa.DateTime(), nullable=True))
    op.add_column("plan_versions", sa.Column("iaa_reference", sa.String(100), nullable=True))
    op.add_column("plan_versions", _user("iaa_recorded_by", "fk_plan_versions_iaa_recorded_by"))


def downgrade() -> None:
    op.drop_constraint("fk_plan_versions_iaa_recorded_by", "plan_versions", type_="foreignkey")
    for c in ("iaa_recorded_by", "iaa_reference", "iaa_submitted_at"):
        op.drop_column("plan_versions", c)
    t = "plan_change_requests"
    op.drop_constraint("ck_plan_change_requests_status", t, type_="check")
    op.create_check_constraint("ck_plan_change_requests_status", t,
                               "status IN ('Submitted','Endorsed','Returned','Approved','Rejected','Withdrawn')")
    op.drop_constraint("fk_pcr_committee_recorded_by", t, type_="foreignkey")
    for c in ("committee_recorded_by", "committee_notes", "committee_reference", "committee_meeting_date",
              "committee_decision", "significant"):
        op.drop_column(t, c)
