"""admin-configured plan distribution destinations on organization entities

Revision ID: 0020_plan_destinations
Revises: 0019_plan_sites
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0020_plan_destinations"
down_revision: str | None = "0019_plan_sites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("plan_destination", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("organizations", sa.Column("destination_label", sa.String(60), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "destination_label")
    op.drop_column("organizations", "plan_destination")
