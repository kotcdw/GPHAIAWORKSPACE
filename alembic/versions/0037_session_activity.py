"""Idle sign-out: when each session was last used

- ``sessions.last_activity_at``: the last request the person made (background refreshes excluded). With the
  ``session_idle_minutes`` setting (default 10) a session that has been idle longer is ended.

Revision ID: 0037_session_activity
Revises: 0036_workflow_engine
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0037_session_activity"
down_revision: str | None = "0036_workflow_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("last_activity_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "last_activity_at")
