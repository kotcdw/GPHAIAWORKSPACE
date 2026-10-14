"""Assurance Plan lifecycle status (Draft ... Archived) and archiving

Revision ID: 0016_plan_lifecycle_status
Revises: 0015_plan_cycle
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0016_plan_lifecycle_status"
down_revision: str | None = "0015_plan_cycle"
branch_labels = None
depends_on = None

STATUSES = ("Draft", "In Review", "Submitted", "Returned", "Approved", "Distributed", "In Execution", "Revised",
            "Closed", "Archived")


def upgrade() -> None:
    op.add_column("assurance_plans", sa.Column("lifecycle_status", sa.String(20), nullable=False,
                                               server_default="Draft"))
    op.add_column("assurance_plans", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("assurance_plans", sa.Column("archived_by", sa.Integer(),
                                               sa.ForeignKey("users.id", ondelete="SET NULL",
                                                             name="fk_assurance_plans_archived_by"), nullable=True))
    allowed = ",".join(f"'{s}'" for s in STATUSES)
    op.create_check_constraint("ck_assurance_plans_lifecycle_status", "assurance_plans",
                               f"lifecycle_status IN ({allowed})")
    # Backfill from the edit-lock status and the cycle stage.
    op.execute("UPDATE assurance_plans SET lifecycle_status = CASE "
               "WHEN status = 'Closed' THEN 'Closed' "
               "WHEN cycle_stage = 'internal_review' THEN 'In Review' "
               "WHEN cycle_stage IN ('submission','committee') THEN 'Submitted' "
               "WHEN status = 'Draft' AND current_version > 0 THEN 'Revised' "
               "WHEN status = 'Draft' THEN 'Draft' "
               "WHEN cycle_stage IN ('approved','distribution') THEN 'Approved' "
               "WHEN cycle_stage = 'execution' AND EXISTS (SELECT 1 FROM plan_engagements e "
               "  WHERE e.plan_id = assurance_plans.id AND e.status = 'Started') THEN 'In Execution' "
               "WHEN cycle_stage = 'execution' THEN 'Distributed' "
               "ELSE 'Approved' END")


def downgrade() -> None:
    op.drop_constraint("ck_assurance_plans_lifecycle_status", "assurance_plans", type_="check")
    op.drop_constraint("fk_assurance_plans_archived_by", "assurance_plans", type_="foreignkey")
    op.drop_column("assurance_plans", "archived_by")
    op.drop_column("assurance_plans", "archived_at")
    op.drop_column("assurance_plans", "lifecycle_status")
