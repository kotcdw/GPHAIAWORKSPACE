"""Integrated audit universe: process library, auditable entities on org units and processes, audit risk assessments

Revision ID: 0030_integrated_universe
Revises: 0029_fieldwork_issues
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0030_integrated_universe"
down_revision: str | None = "0029_fieldwork_issues"
branch_labels = None
depends_on = None

_DEFAULT_FACTORS = [
    ("Financial materiality", "Value of revenue, expenditure or assets that pass through the entity."),
    ("Fraud and integrity risk", "Exposure to cash, procurement, waivers or other fraud-prone activity."),
    ("Regulatory and compliance exposure",
     "Laws, regulations, PPA, IMO/ISPS and other obligations the entity must meet."),
    ("Operational complexity", "Volume, systems, sites and change affecting how the entity operates."),
    ("Time since last audit", "Longer since the last audit means higher risk."),
    ("Prior audit results", "Open, repeat or overdue findings from earlier audits."),
]


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "processes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("processes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="Active"),
        _user("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "process_org_units",
        sa.Column("process_id", sa.Integer(), sa.ForeignKey("processes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "assessment_factors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        _user("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "audit_risk_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("scale", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Draft"),
        sa.Column("conclusion", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("assurance_plans.id", ondelete="SET NULL"), nullable=True),
        _user("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        _user("completed_by"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    op.add_column("entity_units", sa.Column("org_unit_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_entity_units_org_unit_id", "entity_units", "organizations", ["org_unit_id"], ["id"],
                          ondelete="SET NULL")
    op.create_index("ix_entity_units_org_unit_id", "entity_units", ["org_unit_id"])
    op.add_column("entity_units", sa.Column("audit_frequency_months", sa.Integer(), nullable=True))
    op.add_column("entity_units", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.add_column("entity_units", sa.Column("defined_at", sa.DateTime(), nullable=True))
    op.add_column("entity_units", sa.Column("assessed_score", sa.Float(), nullable=True))
    op.add_column("entity_units", sa.Column("assessed_rating", sa.String(30), nullable=True))
    op.add_column("entity_units", sa.Column("assessed_at", sa.DateTime(), nullable=True))
    op.add_column("entity_units", sa.Column("assessment_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_entity_units_assessment_id", "entity_units", "audit_risk_assessments",
                          ["assessment_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "entity_org_units",
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entity_units.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "entity_processes",
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entity_units.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("process_id", sa.Integer(), sa.ForeignKey("processes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_table(
        "ara_entities",
        sa.Column("ara_id", sa.Integer(), sa.ForeignKey("audit_risk_assessments.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entity_units.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _user("note_by"),
        sa.Column("note_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "ara_factors",
        sa.Column("ara_id", sa.Integer(), sa.ForeignKey("audit_risk_assessments.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("factor_id", sa.Integer(), sa.ForeignKey("assessment_factors.id", ondelete="CASCADE"),
                  primary_key=True),
    )
    op.create_table(
        "ara_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ara_id", sa.Integer(), sa.ForeignKey("audit_risk_assessments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entity_units.id", ondelete="CASCADE"), nullable=False),
        sa.Column("factor_id", sa.Integer(), sa.ForeignKey("assessment_factors.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        _user("scored_by"),
        sa.Column("scored_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("ara_id", "entity_id", "factor_id", name="uq_ara_scores_cell"),
    )
    op.create_index("ix_ara_scores_ara_id", "ara_scores", ["ara_id"])

    conn = op.get_bind()
    # Existing auditable units: map each to the org unit whose name matches its location, where one does.
    orgs = {name.strip().lower(): oid for oid, name in conn.execute(sa.text("SELECT id, name FROM organizations"))}
    rows = conn.execute(sa.text(
        "SELECT u.id, l.name FROM entity_units u JOIN locations l ON l.id = u.location_id")).fetchall()
    for uid, loc_name in rows:
        oid = orgs.get((loc_name or "").strip().lower())
        if oid:
            conn.execute(sa.text("UPDATE entity_units SET org_unit_id = :o WHERE id = :u"), {"o": oid, "u": uid})
            conn.execute(sa.text("INSERT INTO entity_org_units (entity_id, org_id) VALUES (:u, :o)"),
                         {"u": uid, "o": oid})
    conn.execute(sa.text("UPDATE entity_units SET archived_at = updated_at WHERE is_active = 0"))
    # Starter assessment factors (HighBond needs at least one); administrators rename, add or delete them.
    for n, (name, desc) in enumerate(_DEFAULT_FACTORS, start=1):
        conn.execute(sa.text("INSERT INTO assessment_factors (ref, name, description, is_active, created_at) "
                             "VALUES (:r, :n, :d, 1, UTC_TIMESTAMP())"), {"r": f"AF-{n:04d}", "n": name, "d": desc})
    existing = conn.execute(sa.text("SELECT next_value FROM reference_sequences WHERE prefix = 'AF'")).fetchone()
    if existing is None:
        conn.execute(sa.text("INSERT INTO reference_sequences (prefix, next_value) VALUES ('AF', :v)"),
                     {"v": len(_DEFAULT_FACTORS)})


def downgrade() -> None:
    op.drop_index("ix_ara_scores_ara_id", "ara_scores")
    for table in ("ara_scores", "ara_factors", "ara_entities", "entity_processes", "entity_org_units"):
        op.drop_table(table)
    op.drop_constraint("fk_entity_units_assessment_id", "entity_units", type_="foreignkey")
    op.drop_constraint("fk_entity_units_org_unit_id", "entity_units", type_="foreignkey")
    op.drop_index("ix_entity_units_org_unit_id", "entity_units")
    for col in ("assessment_id", "assessed_at", "assessed_rating", "assessed_score", "defined_at", "archived_at",
                "audit_frequency_months", "org_unit_id"):
        op.drop_column("entity_units", col)
    op.drop_table("audit_risk_assessments")
    op.drop_table("assessment_factors")
    op.drop_table("process_org_units")
    op.drop_table("processes")
    op.execute("DELETE FROM reference_sequences WHERE prefix = 'AF'")
