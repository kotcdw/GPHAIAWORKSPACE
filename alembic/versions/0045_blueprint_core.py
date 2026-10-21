"""PROJECTBLUEPRINT core: user groups, strategic-risk treatments and issue remediation / retest information.

Revision ID: 0045_blueprint_core
Revises: 0044_plan_projects
Create Date: 2026-10-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0045_blueprint_core"
down_revision: str | None = "0044_plan_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "user_group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("added_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )
    op.create_table(
        "risk_treatments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("risk_id", sa.Integer(), sa.ForeignKey("enterprise_risks.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("objective_id", sa.Integer(), sa.ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("risk_id", "objective_id", name="uq_risk_treatment"),
    )
    with op.batch_alter_table("findings") as t:
        t.add_column(sa.Column("remediation_status", sa.String(40), nullable=False, server_default="Open"))
        t.add_column(sa.Column("remediation_plan", sa.Text(), nullable=True))
        t.add_column(sa.Column("remediation_deadline", sa.DateTime(), nullable=True))
        t.add_column(sa.Column("actual_remediation_date", sa.DateTime(), nullable=True))
        t.add_column(sa.Column("retest_deadline", sa.DateTime(), nullable=True))
        t.add_column(sa.Column("retest_date", sa.DateTime(), nullable=True))
        t.add_column(sa.Column("retest_result", sa.String(20), nullable=True))
        t.add_column(sa.Column("retest_notes", sa.Text(), nullable=True))
        t.add_column(sa.Column("retest_working_paper_id", sa.Integer(), nullable=True))
        t.add_column(sa.Column("retested_by", sa.Integer(), nullable=True))
        t.create_foreign_key("fk_findings_retest_wp", "working_papers", ["retest_working_paper_id"], ["id"],
                             ondelete="SET NULL")
        t.create_foreign_key("fk_findings_retested_by", "users", ["retested_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("findings") as t:
        t.drop_constraint("fk_findings_retested_by", type_="foreignkey")
        t.drop_constraint("fk_findings_retest_wp", type_="foreignkey")
        for c in ("retested_by", "retest_working_paper_id", "retest_notes", "retest_result", "retest_date",
                  "retest_deadline", "actual_remediation_date", "remediation_deadline", "remediation_plan",
                  "remediation_status"):
            t.drop_column(c)
    op.drop_table("risk_treatments")
    op.drop_table("user_group_members")
    op.drop_table("user_groups")
