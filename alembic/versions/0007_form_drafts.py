"""form drafts (autosaved data entry)

Revision ID: 0007_form_drafts
Revises: 0006_planning_rcm
Create Date: 2026-10-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007_form_drafts"
down_revision: str | None = "0006_planning_rcm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("form_key", sa.String(200), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("record_type", sa.String(50), nullable=True),
        sa.Column("record_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "form_key", name="uq_form_drafts_user_key"),
    )
    op.create_index("ix_form_drafts_user_id", "form_drafts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_form_drafts_user_id", table_name="form_drafts")
    op.drop_table("form_drafts")
