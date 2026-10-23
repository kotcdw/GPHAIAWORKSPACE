"""Each person's own home pad (the apps on their Workspace Apps page, in order).

Revision ID: 0052_home_pad
Revises: 0051_record_comments
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0052_home_pad"
down_revision: str | None = "0051_record_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("home_pad", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "home_pad")
