"""reference sequences

Revision ID: 0003_reference_sequences
Revises: 0002_module_tables
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0003_reference_sequences"
down_revision: str | None = "0002_module_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reference_sequences",
        sa.Column("prefix", sa.String(length=20), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False),
    )
    # Seed every prefix so the generator only ever UPDATEs existing rows.
    op.bulk_insert(
        sa.table(
            "reference_sequences",
            sa.column("prefix", sa.String),
            sa.column("next_value", sa.Integer),
        ),
        [
            {"prefix": "ORG", "next_value": 0},
            {"prefix": "SH", "next_value": 0},
            {"prefix": "NC", "next_value": 0},
            {"prefix": "CAPA", "next_value": 0},
            {"prefix": "SF", "next_value": 0},
        ],
    )


def downgrade() -> None:
    op.drop_table("reference_sequences")