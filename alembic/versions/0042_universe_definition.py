"""Audit universe definition

* ``entity_units``: entity type, definition status (Draft / Needs review / Ready / Retired), scope, objectives,
  rationale and effective dates. Existing active entities become Ready and archived ones Retired.
* ``universe_reviews``: an auditor's Included / Not included decision on an org unit or a process.

Revision ID: 0042_universe_definition
Revises: 0041_backup_checks
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0042_universe_definition"
down_revision: str | None = "0041_backup_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("entity_units") as t:
        t.add_column(sa.Column("entity_type", sa.String(40), nullable=True))
        t.add_column(sa.Column("definition_status", sa.String(20), nullable=False, server_default="Ready"))
        t.add_column(sa.Column("scope", sa.Text(), nullable=True))
        t.add_column(sa.Column("objectives", sa.Text(), nullable=True))
        t.add_column(sa.Column("rationale", sa.Text(), nullable=True))
        t.add_column(sa.Column("effective_from", sa.Date(), nullable=True))
        t.add_column(sa.Column("effective_to", sa.Date(), nullable=True))
    op.execute("UPDATE entity_units SET definition_status = 'Retired' WHERE is_active = 0")
    op.execute("UPDATE entity_units SET scope = '', objectives = '', rationale = ''")
    with op.batch_alter_table("entity_units") as t:
        for col in ("scope", "objectives", "rationale"):
            t.alter_column(col, existing_type=sa.Text(), nullable=False)
    op.create_table(
        "universe_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_type", sa.String(10), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("object_type", "object_id", name="uq_universe_reviews_object"),
    )


def downgrade() -> None:
    op.drop_table("universe_reviews")
    with op.batch_alter_table("entity_units") as t:
        for col in ("effective_to", "effective_from", "rationale", "objectives", "scope", "definition_status",
                    "entity_type"):
            t.drop_column(col)
