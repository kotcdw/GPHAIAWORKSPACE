"""GPHA Working Paper Template content and the split Audit Client / Management responses on findings

Revision ID: 0027_gpha_templates
Revises: 0026_review_chain
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0027_gpha_templates"
down_revision: str | None = "0026_review_chain"
branch_labels = None
depends_on = None

_FKS = ("management_response_by", "client_response_by")


def upgrade() -> None:
    op.add_column("working_papers", sa.Column("template", sa.Text(), nullable=True))
    op.add_column("findings", sa.Column("responsible_officer", sa.String(255), nullable=True))
    op.add_column("findings", sa.Column("target_date", sa.DateTime(), nullable=True))
    op.add_column("findings", sa.Column("management_response_by", sa.Integer(), nullable=True))
    op.add_column("findings", sa.Column("management_response_at", sa.DateTime(), nullable=True))
    op.add_column("findings", sa.Column("client_response", sa.Text(), nullable=True))
    op.add_column("findings", sa.Column("client_response_by", sa.Integer(), nullable=True))
    op.add_column("findings", sa.Column("client_response_at", sa.DateTime(), nullable=True))
    op.add_column("findings", sa.Column("client_confirmed_at_exit", sa.Boolean(), nullable=False,
                                        server_default="0"))
    for col in _FKS:
        op.create_foreign_key(f"fk_findings_{col}", "findings", "users", [col], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    for col in _FKS:
        op.drop_constraint(f"fk_findings_{col}", "findings", type_="foreignkey")
    for col in ("client_confirmed_at_exit", "client_response_at", "client_response_by", "client_response",
                "management_response_at", "management_response_by", "target_date", "responsible_officer"):
        op.drop_column("findings", col)
    op.drop_column("working_papers", "template")
