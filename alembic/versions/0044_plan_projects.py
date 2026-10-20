"""Assurance plan projects: what each planned engagement brings into its audit, and the planning period

* ``plan_engagements.audit_type``: chosen when the engagement is planned; the audit started from it takes it (and
  with it the fieldwork workflow and whether the engagement is advisory).
* ``plan_engagements.program_id``: an audit programme from the Project Library, applied when the audit starts.
* ``plan_engagements.source_audit_id``: roll forward - the earlier audit whose objectives, risks, controls, test
  plan and narratives are copied into the new audit when it starts.
* ``assurance_plans.period_start`` / ``period_end``: the planning period.

Revision ID: 0044_plan_projects
Revises: 0043_standards_conformance
Create Date: 2026-10-20
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0044_plan_projects"
down_revision: str | None = "0043_standards_conformance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("plan_engagements") as t:
        t.add_column(sa.Column("audit_type", sa.String(60), nullable=True))
        t.add_column(sa.Column("program_id", sa.Integer(), nullable=True))
        t.add_column(sa.Column("source_audit_id", sa.Integer(), nullable=True))
        t.create_foreign_key("fk_plan_engagements_program", "audit_programs", ["program_id"], ["id"],
                             ondelete="SET NULL")
        t.create_foreign_key("fk_plan_engagements_source_audit", "audits", ["source_audit_id"], ["id"],
                             ondelete="SET NULL")
    with op.batch_alter_table("assurance_plans") as t:
        t.add_column(sa.Column("period_start", sa.Date(), nullable=True))
        t.add_column(sa.Column("period_end", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("assurance_plans") as t:
        t.drop_column("period_end")
        t.drop_column("period_start")
    with op.batch_alter_table("plan_engagements") as t:
        t.drop_constraint("fk_plan_engagements_source_audit", type_="foreignkey")
        t.drop_constraint("fk_plan_engagements_program", type_="foreignkey")
        t.drop_column("source_audit_id")
        t.drop_column("program_id")
        t.drop_column("audit_type")
