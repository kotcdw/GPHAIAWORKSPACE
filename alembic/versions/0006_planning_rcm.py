"""planning & risk-control layer

Audit universe (``locations`` -> ``entity_units``), the annual Assurance Plan
(``assurance_plans`` + ``plan_engagements``), and the risk & control matrix of
each audit project (``objectives``, ``risks``, ``controls``, ``risk_controls``,
``control_tests``). Findings gain issue attributes and links to the control /
test they came from; audits gain their plan and entity-unit links.

Revision ID: 0006_planning_rcm
Revises: 0005_controls_hardening
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0006_planning_rcm"
down_revision: str | None = "0005_controls_hardening"
branch_labels = None
depends_on = None


def _ts() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(), nullable=False)]


def _creator() -> sa.Column:
    return sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
    )
    op.create_table(
        "entity_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_email", sa.String(255), nullable=True),
        sa.Column("risk_likelihood", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("risk_impact", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_audited_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("location_id", "code", name="uq_entity_units_location_code"),
        sa.CheckConstraint("risk_likelihood BETWEEN 1 AND 5", name="ck_entity_units_likelihood"),
        sa.CheckConstraint("risk_impact BETWEEN 1 AND 5", name="ck_entity_units_impact"),
    )
    op.create_index("ix_entity_units_location_id", "entity_units", ["location_id"])

    op.create_table(
        "assurance_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_ref", sa.String(20), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("total_budget_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        _creator(),
        *_ts(),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('Draft','Approved','Closed')", name="ck_assurance_plans_status"),
    )
    op.create_index("ix_assurance_plans_plan_ref", "assurance_plans", ["plan_ref"], unique=True)

    op.create_table(
        "plan_engagements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("assurance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_unit_id", sa.Integer(), sa.ForeignKey("entity_units.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("planned_quarter", sa.String(2), nullable=False),
        sa.Column("budget_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lead_auditor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="SET NULL"), nullable=True),
        _creator(),
        *_ts(),
        sa.CheckConstraint("planned_quarter IN ('Q1','Q2','Q3','Q4')", name="ck_plan_engagements_quarter"),
        sa.CheckConstraint("status IN ('Planned','Started','Cancelled')", name="ck_plan_engagements_status"),
    )
    op.create_index("ix_plan_engagements_plan_id", "plan_engagements", ["plan_id"])
    op.create_index("ix_plan_engagements_entity_unit_id", "plan_engagements", ["entity_unit_id"])

    op.create_table(
        "objectives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        _creator(),
        *_ts(),
    )
    op.create_index("ix_objectives_audit_id", "objectives", ["audit_id"])

    op.create_table(
        "risks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("objective_id", sa.Integer(), sa.ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("likelihood", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("impact", sa.Integer(), nullable=False, server_default="3"),
        _creator(),
        *_ts(),
        sa.CheckConstraint("likelihood BETWEEN 1 AND 5", name="ck_risks_likelihood"),
        sa.CheckConstraint("impact BETWEEN 1 AND 5", name="ck_risks_impact"),
    )
    op.create_index("ix_risks_objective_id", "risks", ["objective_id"])

    op.create_table(
        "controls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("objective_id", sa.Integer(), sa.ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("control_type", sa.String(20), nullable=False),
        sa.Column("nature", sa.String(20), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("owner_email", sa.String(255), nullable=True),
        sa.Column("is_key", sa.Boolean(), nullable=False, server_default=sa.true()),
        _creator(),
        *_ts(),
        sa.CheckConstraint("control_type IN ('Preventive','Detective','Corrective')", name="ck_controls_type"),
        sa.CheckConstraint("nature IN ('Manual','Automated','IT-Dependent Manual')", name="ck_controls_nature"),
        sa.CheckConstraint(
            "frequency IN ('Annual','Quarterly','Monthly','Weekly','Daily','Multiple Daily','Ad Hoc')",
            name="ck_controls_frequency",
        ),
    )
    op.create_index("ix_controls_objective_id", "controls", ["objective_id"])

    op.create_table(
        "risk_controls",
        sa.Column("risk_id", sa.Integer(), sa.ForeignKey("risks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("control_id", sa.Integer(), sa.ForeignKey("controls.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "control_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("control_id", sa.Integer(), sa.ForeignKey("controls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("test_type", sa.String(30), nullable=False),
        sa.Column("procedure", sa.Text(), nullable=False),
        sa.Column("population_size", sa.Integer(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("sample_seed", sa.Integer(), nullable=True),
        sa.Column("sample_items", sa.Text(), nullable=False),
        sa.Column("exceptions_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("results", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("conclusion", sa.String(20), nullable=False),
        sa.Column("performed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("performed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=False),
        _creator(),
        *_ts(),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "test_type IN ('Walkthrough','Design','Operating Effectiveness')", name="ck_control_tests_type"
        ),
        sa.CheckConstraint(
            "status IN ('Not Started','In Progress','Completed','Reviewed')", name="ck_control_tests_status"
        ),
        sa.CheckConstraint(
            "conclusion IN ('Not Tested','Effective','Ineffective')", name="ck_control_tests_conclusion"
        ),
    )
    op.create_index("ix_control_tests_control_id", "control_tests", ["control_id"])

    with op.batch_alter_table("audits") as batch:
        batch.add_column(sa.Column("plan_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("entity_unit_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_audits_plan", "assurance_plans", ["plan_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key(
            "fk_audits_entity_unit", "entity_units", ["entity_unit_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("findings") as batch:
        batch.add_column(sa.Column("control_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("test_id", sa.Integer(), nullable=True))
        for name in (
            "criteria",
            "condition",
            "cause",
            "effect",
            "recommendation",
            "root_cause_whys",
            "management_response",
        ):
            batch.add_column(sa.Column(name, sa.Text(), nullable=True))
        batch.create_foreign_key("fk_findings_control", "controls", ["control_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_findings_test", "control_tests", ["test_id"], ["id"], ondelete="SET NULL")

    seq = sa.table("reference_sequences", sa.column("prefix", sa.String), sa.column("next_value", sa.Integer))
    op.bulk_insert(seq, [{"prefix": p, "next_value": 0} for p in ("AP", "OBJ", "RSK", "CTL", "TST")])


def downgrade() -> None:
    op.execute("DELETE FROM reference_sequences WHERE prefix IN ('AP','OBJ','RSK','CTL','TST')")
    with op.batch_alter_table("findings") as batch:
        batch.drop_constraint("fk_findings_test", type_="foreignkey")
        batch.drop_constraint("fk_findings_control", type_="foreignkey")
        for name in (
            "management_response",
            "root_cause_whys",
            "recommendation",
            "effect",
            "cause",
            "condition",
            "criteria",
            "test_id",
            "control_id",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("audits") as batch:
        batch.drop_constraint("fk_audits_entity_unit", type_="foreignkey")
        batch.drop_constraint("fk_audits_plan", type_="foreignkey")
        batch.drop_column("entity_unit_id")
        batch.drop_column("plan_id")
    for table in (
        "control_tests",
        "risk_controls",
        "controls",
        "risks",
        "objectives",
        "plan_engagements",
        "assurance_plans",
        "entity_units",
        "locations",
    ):
        op.drop_table(table)
