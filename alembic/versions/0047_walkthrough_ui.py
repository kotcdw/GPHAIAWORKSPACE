"""Interface walkthroughs: framework treatment links, project entities and objectives chosen at planning, report
folders and settings, and per-action reminder preference.

* ``objectives.source_program_id``: the framework (audit programme) an objective was copied from, so a strategic
  risk linked to a framework objective rolls up assurance from every project that uses it.
* ``risk_treatments``: a treatment links either a project objective or a framework objective (programme + title).
* ``plan_engagement_entities`` / ``plan_engagement_objectives``: entities and framework objectives chosen when a new
  project is created in a plan (Create project › Objectives › Entities).
* ``report_items.folder``, ``settings`` and ``user_ids`` (Publish › Folder, Report settings, private access for
  chosen users); ``ai_report_workstreams.user_ids``.

Revision ID: 0047_walkthrough_ui
Revises: 0046_reporting
Create Date: 2026-10-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0047_walkthrough_ui"
down_revision: str | None = "0046_reporting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("objectives") as t:
        t.add_column(sa.Column("source_program_id", sa.Integer(), nullable=True))
        t.create_foreign_key("fk_objectives_source_program", "audit_programs", ["source_program_id"], ["id"],
                             ondelete="SET NULL")
    with op.batch_alter_table("risk_treatments") as t:
        t.drop_constraint("uq_risk_treatment", type_="unique")
        t.alter_column("objective_id", existing_type=sa.Integer(), nullable=True)
        t.add_column(sa.Column("program_id", sa.Integer(), nullable=True))
        t.add_column(sa.Column("program_objective", sa.String(255), nullable=True))
        t.create_foreign_key("fk_risk_treatments_program", "audit_programs", ["program_id"], ["id"],
                             ondelete="CASCADE")
        t.create_unique_constraint("uq_risk_treatment", ["risk_id", "objective_id"])
        t.create_unique_constraint("uq_risk_treatment_framework", ["risk_id", "program_id", "program_objective"])
    op.create_table(
        "plan_engagement_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("plan_engagements.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("entity_unit_id", sa.Integer(), sa.ForeignKey("entity_units.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.UniqueConstraint("engagement_id", "entity_unit_id", name="uq_engagement_entity"),
    )
    op.create_table(
        "plan_engagement_objectives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_id", sa.Integer(), sa.ForeignKey("plan_engagements.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("audit_programs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.UniqueConstraint("engagement_id", "program_id", "title", name="uq_engagement_objective"),
    )
    with op.batch_alter_table("report_items") as t:
        t.add_column(sa.Column("folder", sa.String(120), nullable=False, server_default="My Reports"))
        t.add_column(sa.Column("settings", sa.Text(), nullable=True))
        t.add_column(sa.Column("user_ids", sa.Text(), nullable=True))
    with op.batch_alter_table("ai_report_workstreams") as t:
        t.add_column(sa.Column("user_ids", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_report_workstreams") as t:
        t.drop_column("user_ids")
    with op.batch_alter_table("report_items") as t:
        t.drop_column("user_ids")
        t.drop_column("settings")
        t.drop_column("folder")
    op.drop_table("plan_engagement_objectives")
    op.drop_table("plan_engagement_entities")
    with op.batch_alter_table("risk_treatments") as t:
        t.drop_constraint("uq_risk_treatment_framework", type_="unique")
        t.drop_constraint("fk_risk_treatments_program", type_="foreignkey")
        t.drop_column("program_objective")
        t.drop_column("program_id")
    op.execute("DELETE FROM risk_treatments WHERE objective_id IS NULL")
    with op.batch_alter_table("risk_treatments") as t:
        t.alter_column("objective_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("objectives") as t:
        t.drop_constraint("fk_objectives_source_program", type_="foreignkey")
        t.drop_column("source_program_id")
