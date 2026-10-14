"""configurable entities: organization hierarchy, address, custom fields; user workplace

Revision ID: 0012_entities_custom_fields
Revises: 0011_backlog_modules
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0012_entities_custom_fields"
down_revision: str | None = "0011_backlog_modules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_organizations_parent", "organizations", "organizations", ["parent_id"], ["id"],
                          ondelete="SET NULL")
    op.add_column("organizations", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("custom_fields", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("work_entity_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_users_work_entity", "users", "organizations", ["work_entity_id"], ["id"],
                          ondelete="SET NULL")
    op.create_table(
        "custom_fields",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column("field_key", sa.String(60), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("field_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("options", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("help", sa.String(255), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("module", "field_key", name="uq_custom_fields_module_key"),
        sa.CheckConstraint("field_type IN ('text','longtext','number','date','select','yesno')",
                           name="ck_custom_fields_type"),
    )


def downgrade() -> None:
    op.drop_table("custom_fields")
    op.drop_constraint("fk_users_work_entity", "users", type_="foreignkey")
    op.drop_column("users", "work_entity_id")
    op.drop_column("organizations", "custom_fields")
    op.drop_column("organizations", "address")
    op.drop_constraint("fk_organizations_parent", "organizations", type_="foreignkey")
    op.drop_column("organizations", "parent_id")
