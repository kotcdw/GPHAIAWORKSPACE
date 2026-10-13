"""module tables

Revision ID: 0002_module_tables
Revises: 0001_initial
Create Date: 2026-10-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0002_module_tables"
down_revision: str | None = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_ref", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("evaluation_end_date", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('Pending','Approved')", name="ck_organizations_status"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_organizations_org_ref", "organizations", ["org_ref"], unique=True)

    # ------------------------------------------------------------------ stakeholders
    op.create_table(
        "stakeholders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sh_ref", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("stakeholder_type", sa.String(length=100), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('Active','Inactive')", name="ck_stakeholders_status"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_stakeholders_sh_ref", "stakeholders", ["sh_ref"], unique=True)

    # ------------------------------------------------------------------ nonconformances
    op.create_table(
        "nonconformances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nc_ref", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("disposition", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("owner_email", sa.String(length=255), nullable=True),
        sa.Column("audit_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("severity IN ('Low','Medium','High')", name="ck_nonconformances_severity"),
        sa.CheckConstraint("status IN ('Open','Remediating','Closed')", name="ck_nonconformances_status"),
        sa.ForeignKeyConstraint(["audit_id"], ["audits.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_nonconformances_nc_ref", "nonconformances", ["nc_ref"], unique=True)
    op.create_index("ix_nonconformances_audit_id", "nonconformances", ["audit_id"], unique=False)

    # ------------------------------------------------------------------ capa
    op.create_table(
        "capa",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capa_ref", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("corrective_action", sa.Text(), nullable=False),
        sa.Column("preventive_action", sa.Text(), nullable=False),
        sa.Column("effectiveness_check", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("disposition", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("owner_email", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("severity IN ('Low','Medium','High')", name="ck_capa_severity"),
        sa.CheckConstraint("status IN ('Open','In Progress','Review','Closed')", name="ck_capa_status"),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_capa_capa_ref", "capa", ["capa_ref"], unique=True)

    # Cross-links between nonconformances and capa
    # batch_alter_table issues plain ALTERs on MySQL and a copy-and-move on
    # SQLite (which cannot ALTER constraints), so this migration runs on both.
    with op.batch_alter_table("nonconformances") as batch:
        batch.add_column(sa.Column("linked_capa_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_nonconformances_linked_capa", "capa", ["linked_capa_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("capa") as batch:
        batch.add_column(sa.Column("linked_nc_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_capa_linked_nc", "nonconformances", ["linked_nc_id"], ["id"], ondelete="SET NULL")

    # ------------------------------------------------------------------ service_feedback
    op.create_table(
        "service_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sf_ref", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("received_date", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("owner_email", sa.String(length=255), nullable=True),
        sa.Column("linked_nc_id", sa.Integer(), nullable=True),
        sa.Column("linked_capa_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('Open','In Progress','Closed')", name="ck_service_feedback_status"),
        sa.ForeignKeyConstraint(["linked_nc_id"], ["nonconformances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_capa_id"], ["capa.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_service_feedback_sf_ref", "service_feedback", ["sf_ref"], unique=True)

    # ------------------------------------------------------------------ tasks
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("assignor_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("system_generated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('Open','In Progress','Closed')", name="ck_tasks_status"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"], unique=False)
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)

    # ------------------------------------------------------------------ record_history
    op.create_table(
        "record_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=500), nullable=False),
        sa.Column("cycle_no", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_record_history_record",
        "record_history",
        ["record_type", "record_id"],
        unique=False,
    )

    # ------------------------------------------------------------------ approval_cycles
    op.create_table(
        "approval_cycles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_type", sa.String(length=50), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("cycle_no", sa.Integer(), nullable=False),
        sa.Column("approver_id", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.CheckConstraint("decision IN ('Approve','Reject')", name="ck_approval_cycles_decision"),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_approval_cycles_record",
        "approval_cycles",
        ["record_type", "record_id", "cycle_no"],
        unique=False,
    )

    # ------------------------------------------------------------------ audits extension
    with op.batch_alter_table("audits") as batch:
        batch.add_column(sa.Column("approval_status", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch.create_check_constraint(
            "ck_audits_approval_status",
            "approval_status IS NULL OR approval_status IN ('On Hold','In Approval','Approved')",
        )
        batch.create_foreign_key(
            "fk_audits_organization", "organizations", ["organization_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("audits") as batch:
        batch.drop_constraint("fk_audits_organization", type_="foreignkey")
        batch.drop_constraint("ck_audits_approval_status", type_="check")
        batch.drop_column("organization_id")
        batch.drop_column("approval_status")

    op.drop_index("ix_approval_cycles_record", table_name="approval_cycles")
    op.drop_table("approval_cycles")

    op.drop_index("ix_record_history_record", table_name="record_history")
    op.drop_table("record_history")

    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_assignee_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_service_feedback_sf_ref", table_name="service_feedback")
    op.drop_table("service_feedback")

    with op.batch_alter_table("capa") as batch:
        batch.drop_constraint("fk_capa_linked_nc", type_="foreignkey")
        batch.drop_column("linked_nc_id")
    with op.batch_alter_table("nonconformances") as batch:
        batch.drop_constraint("fk_nonconformances_linked_capa", type_="foreignkey")
        batch.drop_column("linked_capa_id")

    op.drop_index("ix_capa_capa_ref", table_name="capa")
    op.drop_table("capa")

    op.drop_index("ix_nonconformances_audit_id", table_name="nonconformances")
    op.drop_index("ix_nonconformances_nc_ref", table_name="nonconformances")
    op.drop_table("nonconformances")

    op.drop_index("ix_stakeholders_sh_ref", table_name="stakeholders")
    op.drop_table("stakeholders")

    op.drop_index("ix_organizations_org_ref", table_name="organizations")
    op.drop_table("organizations")