"""rename CAPA to Remediation: new references use the REM- prefix

Existing CAPA-#### references are kept unchanged.

Revision ID: 0010_remediation_refs
Revises: 0009_app_config
Create Date: 2026-10-13
"""

from __future__ import annotations

from alembic import op

revision: str = "0010_remediation_refs"
down_revision: str | None = "0009_app_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO reference_sequences (prefix, next_value) "
        "SELECT 'REM', 0 FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM reference_sequences WHERE prefix = 'REM')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM reference_sequences WHERE prefix = 'REM'")
