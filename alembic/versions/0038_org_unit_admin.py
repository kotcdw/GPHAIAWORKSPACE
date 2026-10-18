"""Organisational structure administration: unit heads and deactivation

- ``organizations.head_user_id``: the person who heads the unit (optional).
- ``organizations.is_active`` with ``deactivated_at`` / ``deactivated_by`` / ``deactivation_reason``: a unit that
  is no longer in use is deactivated instead of deleted, so audits, plans and history that name it stay intact.

Revision ID: 0038_org_unit_admin
Revises: 0037_session_activity
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0038_org_unit_admin"
down_revision: str | None = "0037_session_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("head_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_organizations_head_user", "organizations", "users", ["head_user_id"], ["id"],
                          ondelete="SET NULL")
    op.add_column("organizations", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("organizations", sa.Column("deactivated_at", sa.DateTime(), nullable=True))
    op.add_column("organizations", sa.Column("deactivated_by", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_organizations_deactivated_by", "organizations", "users", ["deactivated_by"], ["id"],
                          ondelete="SET NULL")
    op.add_column("organizations", sa.Column("deactivation_reason", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_constraint("fk_organizations_deactivated_by", "organizations", type_="foreignkey")
    op.drop_constraint("fk_organizations_head_user", "organizations", type_="foreignkey")
    for col in ("deactivation_reason", "deactivated_by", "deactivated_at", "is_active", "head_user_id"):
        op.drop_column("organizations", col)
