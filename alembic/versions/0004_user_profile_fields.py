"""user profile fields (first/last name, company)

Revision ID: 0004_user_profile_fields
Revises: 0003_reference_sequences
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0004_user_profile_fields"
down_revision: str | None = "0003_reference_sequences"
branch_labels = None
depends_on = None

_COLUMNS = ("first_name", "last_name", "company")


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column(
            "users",
            sa.Column(name, sa.String(length=255), nullable=False, server_default=""),
        )


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("users", name)
