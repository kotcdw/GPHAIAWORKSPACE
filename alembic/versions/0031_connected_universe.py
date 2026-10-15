"""Connected universe: audit risks linked to enterprise risks, automatic assessment factors, audits on several entities

Revision ID: 0031_connected_universe
Revises: 0030_integrated_universe
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0031_connected_universe"
down_revision: str | None = "0030_integrated_universe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risks", sa.Column("enterprise_risk_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_risks_enterprise_risk_id", "risks", "enterprise_risks", ["enterprise_risk_id"], ["id"],
                          ondelete="SET NULL")
    op.add_column("assessment_factors", sa.Column("auto_source", sa.String(30), nullable=True))
    op.create_table(
        "audit_entities",
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entity_units.id", ondelete="CASCADE"), primary_key=True),
    )
    conn = op.get_bind()
    conn.execute(sa.text("INSERT INTO audit_entities (audit_id, entity_id) "
                         "SELECT id, entity_unit_id FROM audits WHERE entity_unit_id IS NOT NULL"))
    conn.execute(sa.text("UPDATE assessment_factors SET auto_source = 'time_since_audit' "
                         "WHERE name = 'Time since last audit'"))
    conn.execute(sa.text("UPDATE assessment_factors SET auto_source = 'prior_results' "
                         "WHERE name = 'Prior audit results'"))


def downgrade() -> None:
    op.drop_table("audit_entities")
    op.drop_column("assessment_factors", "auto_source")
    op.drop_constraint("fk_risks_enterprise_risk_id", "risks", type_="foreignkey")
    op.drop_column("risks", "enterprise_risk_id")
