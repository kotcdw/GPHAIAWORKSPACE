"""Platform administration: account invitations and a personal language preference.

* ``user_invitations``: one row per invitation link sent to a new account (only the token's hash is stored).
* ``users.locale``: the language a person prefers for their own screens (empty = the workspace language).

Revision ID: 0049_admin_invitations
Revises: 0048_reports_risk_extensions
Create Date: 2026-10-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0049_admin_invitations"
down_revision: str | None = "0048_reports_risk_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("locale", sa.String(20), nullable=True))
    op.create_table(
        "user_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_user_invitations_user_id", "user_invitations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_invitations_user_id", table_name="user_invitations")
    op.drop_table("user_invitations")
    op.drop_column("users", "locale")
