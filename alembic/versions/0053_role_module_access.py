"""Module actions refused per role (Roles & permissions > Access by module).

Revision ID: 0053_role_module_access
Revises: 0052_home_pad
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0053_role_module_access"
down_revision: str | None = "0052_home_pad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_module_access",
        sa.Column("job_role", sa.String(40), primary_key=True),
        sa.Column("module", sa.String(80), primary_key=True),
        sa.Column("action", sa.String(20), primary_key=True),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("role_module_access")
