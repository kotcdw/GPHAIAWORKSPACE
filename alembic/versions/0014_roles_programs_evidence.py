"""job roles + permission matrix, Committee tier, audit types and ports, audit programmes,
evidence requests

Revision ID: 0014_roles_programs_evidence
Revises: 0013_gias_completion
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0014_roles_programs_evidence"
down_revision: str | None = "0013_gias_completion"
branch_labels = None
depends_on = None


def _user(name: str, nullable: bool = True, ondelete: str = "SET NULL") -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    # Committee (read-only governance) tier and job roles
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", "role IN ('Admin','Auditor','Auditee','Committee')")
    op.add_column("users", sa.Column("job_role", sa.String(40), nullable=True))
    op.create_table(
        "role_permissions",
        sa.Column("job_role", sa.String(40), primary_key=True),
        sa.Column("permission", sa.String(60), primary_key=True),
        sa.Column("granted", sa.Boolean(), nullable=False),
        _user("updated_by"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Audit type and the port an audit belongs to
    op.add_column("audits", sa.Column("audit_type", sa.String(60), nullable=True))
    op.add_column("audits", sa.Column("port_entity_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_audits_port_entity", "audits", "organizations", ["port_entity_id"], ["id"],
                          ondelete="SET NULL")

    # Audit programme library (templates applied to an audit's risk & control matrix)
    op.create_table(
        "audit_programs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prog_ref", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("audit_type", sa.String(60), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("steps", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Active"),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="0"),
        _user("created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('Active','Retired')", name="ck_audit_programs_status"),
    )

    # Evidence requests (prepared-by-client list)
    op.create_table(
        "evidence_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_ref", sa.String(20), nullable=False, unique=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        _user("assignee_id"),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="Requested"),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        _user("requested_by"),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        _user("reviewed_by"),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('Requested','Submitted','Accepted','Returned','Cancelled')",
                           name="ck_evidence_requests_status"),
    )
    op.create_index("ix_evidence_requests_audit_id", "evidence_requests", ["audit_id"])
    op.create_table(
        "evidence_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("evidence_requests.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        _user("uploaded_by"),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_evidence_files_request_id", "evidence_files", ["request_id"])
    for prefix in ("PRG", "ER"):
        op.execute(f"INSERT INTO reference_sequences (prefix, next_value) SELECT '{prefix}', 0 FROM DUAL "
                   f"WHERE NOT EXISTS (SELECT 1 FROM reference_sequences WHERE prefix = '{prefix}')")


def downgrade() -> None:
    op.execute("DELETE FROM reference_sequences WHERE prefix IN ('PRG','ER')")
    op.drop_table("evidence_files")
    op.drop_table("evidence_requests")
    op.drop_table("audit_programs")
    op.drop_constraint("fk_audits_port_entity", "audits", type_="foreignkey")
    op.drop_column("audits", "port_entity_id")
    op.drop_column("audits", "audit_type")
    op.drop_table("role_permissions")
    op.drop_column("users", "job_role")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", "role IN ('Admin','Auditor','Auditee')")
