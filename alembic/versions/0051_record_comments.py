"""Comments and @mentions on records.

Revision ID: 0051_record_comments
Revises: 0050_topical_requirements
Create Date: 2026-10-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0051_record_comments"
down_revision: str | None = "0050_topical_requirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "record_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_type", sa.String(40), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_record_comments_record", "record_comments", ["record_type", "record_id"])
    op.create_table(
        "comment_mentions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("comment_id", sa.Integer(), sa.ForeignKey("record_comments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("done_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_comment_mentions_comment_id", "comment_mentions", ["comment_id"])
    op.create_index("ix_comment_mentions_user_id", "comment_mentions", ["user_id"])


def downgrade() -> None:
    op.drop_table("comment_mentions")
    op.drop_index("ix_record_comments_record", table_name="record_comments")
    op.drop_table("record_comments")
