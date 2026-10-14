"""responsible site (HQ / port) on plan engagements; distribution by site

Revision ID: 0019_plan_sites
Revises: 0018_change_governance
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0019_plan_sites"
down_revision: str | None = "0018_change_governance"
branch_labels = None
depends_on = None


_TABLES = (("plan_engagements", "fk_plan_engagements_site"), ("plan_distributions", "fk_plan_distributions_site"))


def upgrade() -> None:
    for table, fk in _TABLES:
        op.add_column(table, sa.Column("site_entity_id", sa.Integer(),
                                       sa.ForeignKey("organizations.id", ondelete="SET NULL", name=fk), nullable=True))


def downgrade() -> None:
    for table, fk in _TABLES:
        op.drop_constraint(fk, table, type_="foreignkey")
        op.drop_column(table, "site_entity_id")
