"""PROJECTBLUEPRINT reporting: saved reports, dashboards and presentations, and AI Reporting workstreams.

Revision ID: 0046_reporting
Revises: 0045_blueprint_core
Create Date: 2026-10-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0046_reporting"
down_revision: str | None = "0045_blueprint_core"
branch_labels = None
depends_on = None


def _owner() -> sa.Column:
    return sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
                     index=True)


def upgrade() -> None:
    op.create_table(
        "report_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Draft"),
        sa.Column("access", sa.String(20), nullable=False, server_default="Private"),
        sa.Column("group_ids", sa.Text(), nullable=False),
        _owner(),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "ai_report_workstreams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("sources", sa.Text(), nullable=False),
        sa.Column("facts", sa.Text(), nullable=True),
        sa.Column("facts_generated_at", sa.DateTime(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("narrative_origin", sa.String(20), nullable=False, server_default="none"),
        sa.Column("status", sa.String(20), nullable=False, server_default="Draft"),
        sa.Column("review_note", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("access", sa.String(20), nullable=False, server_default="Private"),
        sa.Column("group_ids", sa.Text(), nullable=False),
        _owner(),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_report_workstreams")
    op.drop_table("report_items")
