"""GPHA review chain: Unit Head -> Audit Manager -> PIA -> GM Audit on reports and working papers

Revision ID: 0026_review_chain
Revises: 0025_standard_roles
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0026_review_chain"
down_revision: str | None = "0025_standard_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("audit_reports", "working_papers"):
        op.add_column(table, sa.Column("review_stage", sa.String(20), nullable=True))
        op.add_column(table, sa.Column("review_trail", sa.Text(), nullable=True))
    # Reports already waiting for review continue at the Audit Manager stage.
    op.execute("UPDATE audit_reports SET review_stage='Manager', review_trail='[]' WHERE status='Manager Review'")


def downgrade() -> None:
    for table in ("audit_reports", "working_papers"):
        op.drop_column(table, "review_trail")
        op.drop_column(table, "review_stage")
