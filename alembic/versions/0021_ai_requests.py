"""AI Service request log

Revision ID: 0021_ai_requests
Revises: 0020_plan_destinations
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0021_ai_requests"
down_revision: str | None = "0020_plan_destinations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("record_type", sa.String(40), nullable=True),
        sa.Column("record_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("input_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_requests_user_id", "ai_requests", ["user_id"])
    op.create_index("ix_ai_requests_created_at", "ai_requests", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_requests")
