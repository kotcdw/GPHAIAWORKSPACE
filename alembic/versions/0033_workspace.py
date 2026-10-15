"""Workspace: per-user favourite and recently opened apps

Revision ID: 0033_workspace
Revises: 0032_highbond_parity
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0033_workspace"
down_revision: str | None = "0032_highbond_parity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_workspace",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("favorites", sa.Text(), nullable=False),
        sa.Column("recent", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_workspace")
