"""Engagement teams (lead, auditors, reviewers) for port/team-scoped access

Revision ID: 0028_audit_team
Revises: 0027_gpha_templates
Create Date: 2026-10-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0028_audit_team"
down_revision: str | None = "0027_gpha_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_team_members",
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("team_role", sa.String(30), nullable=False, server_default="Auditor"),
        sa.Column("added_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_team_members_user_id", "audit_team_members", ["user_id"])
    # Existing audits: the plan's lead auditor leads the team; the creator joins it (and leads when no plan lead).
    bind = op.get_bind()
    leads = bind.execute(sa.text(
        "SELECT e.audit_id, e.lead_auditor_id FROM plan_engagements e JOIN users u ON u.id = e.lead_auditor_id "
        "WHERE e.audit_id IS NOT NULL")).all()
    creators = bind.execute(sa.text(
        "SELECT a.id, a.created_by FROM audits a JOIN users u ON u.id = a.created_by "
        "WHERE u.role IN ('Admin', 'Auditor')")).all()
    rows: dict[tuple[int, int], str] = {}
    led: set[int] = set()
    for audit_id, user_id in leads:
        if audit_id not in led:
            rows[(audit_id, user_id)] = "Lead auditor"
            led.add(audit_id)
    for audit_id, user_id in creators:
        if (audit_id, user_id) not in rows:
            rows[(audit_id, user_id)] = "Auditor" if audit_id in led else "Lead auditor"
            led.add(audit_id)
    for (audit_id, user_id), role in rows.items():
        bind.execute(sa.text("INSERT INTO audit_team_members (audit_id, user_id, team_role, added_at) "
                             "VALUES (:a, :u, :r, NOW())"), {"a": audit_id, "u": user_id, "r": role})


def downgrade() -> None:
    op.drop_table("audit_team_members")
