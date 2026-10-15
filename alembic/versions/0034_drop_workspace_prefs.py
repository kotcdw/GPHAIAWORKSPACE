"""Workspace is the app catalogue only: drop the per-user favourites table and its role defaults

Revision ID: 0034_drop_workspace_prefs
Revises: 0033_workspace
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0034_drop_workspace_prefs"
down_revision: str | None = "0033_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("user_workspace")
    op.execute(sa.text("DELETE FROM app_config WHERE `key` = 'workspace_defaults'"))


def downgrade() -> None:
    op.create_table(
        "user_workspace",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("favorites", sa.Text(), nullable=False),
        sa.Column("recent", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
