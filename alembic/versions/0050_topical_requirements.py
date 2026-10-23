"""IIA Topical Requirements: catalogue, per-engagement applicability and checklist results.

Seeds the Cybersecurity Topical Requirement (IIA, 2025; in force from 5 February 2026) with its requirements under
Governance, Risk management and Control processes, worded briefly for the checklist.

Revision ID: 0050_topical_requirements
Revises: 0049_admin_invitations
Create Date: 2026-10-22
"""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa

from alembic import op

revision: str = "0050_topical_requirements"
down_revision: str | None = "0049_admin_invitations"
branch_labels = None
depends_on = None

CYBER_ITEMS = [
    ("Governance", "G-A", "A cybersecurity strategy and objectives are formally set, updated periodically, and the board "
                          "reviews progress and resourcing."),
    ("Governance", "G-B", "Cybersecurity policies and procedures exist and are updated periodically."),
    ("Governance", "G-C", "Cybersecurity roles and responsibilities are defined, and role holders' knowledge and skills "
                          "are assessed periodically."),
    ("Governance", "G-D", "Relevant stakeholders (management, legal, HR, vendors and others) are engaged on "
                          "vulnerabilities and emerging threats."),
    ("Risk management", "R-A", "Risk processes identify, analyse, mitigate and monitor cyber threats and their effect "
                               "on strategic objectives."),
    ("Risk management", "R-B", "Cybersecurity risk is managed across the organisation (IT, ERM, HR, legal, operations, "
                               "supply chain, finance)."),
    ("Risk management", "R-C", "Accountability for cybersecurity risk is set, with a person or team that monitors and "
                               "reports on it and its resourcing."),
    ("Risk management", "R-D", "Cyber risks above acceptable levels are escalated, considering financial and "
                               "non-financial impact."),
    ("Risk management", "R-E", "Cyber risk awareness reaches management and staff; issues and control failures are "
                               "reviewed and remediated promptly."),
    ("Risk management", "R-F", "Incident response and recovery (detection, containment, recovery, post-incident review) "
                               "exists and is tested periodically."),
    ("Control processes", "C-A", "Internal and vendor controls protect confidentiality, integrity and availability, and "
                                 "are evaluated periodically."),
    ("Control processes", "C-B", "Talent management, including training, keeps cybersecurity skills current and is "
                                 "reviewed periodically."),
    ("Control processes", "C-C", "Emerging threats and vulnerabilities are monitored and reported, and improvements are "
                                 "prioritised."),
    ("Control processes", "C-D", "Cybersecurity is part of the life cycle of IT assets (hardware, software, vendor "
                                 "services) from selection to decommissioning."),
    ("Control processes", "C-E", "Configuration, end-user devices, encryption, patching, user access, availability "
                                 "monitoring and secure development are controlled."),
    ("Control processes", "C-F", "Network controls are in place: access, segmentation, firewalls, external connections, "
                                 "VPN/zero trust, IoT and intrusion detection."),
    ("Control processes", "C-G", "Endpoint communication channels are secured: e-mail, browsers, video calls, messaging, "
                                 "social media, cloud and file sharing."),
]


def upgrade() -> None:
    reqs = op.create_table(
        "topical_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("version", sa.String(40), nullable=False, server_default=""),
        sa.Column("effective_on", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    items = op.create_table(
        "topical_requirement_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("topical_requirements.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("area", sa.String(40), nullable=False),
        sa.Column("ref", sa.String(10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_topical_requirement_items_requirement_id", "topical_requirement_items", ["requirement_id"])
    op.create_table(
        "engagement_topicals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("topical_requirements.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("in_scope", sa.Boolean(), nullable=False),
        sa.Column("trigger", sa.String(60), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("audit_id", "requirement_id", name="uq_engagement_topical"),
    )
    op.create_index("ix_engagement_topicals_audit_id", "engagement_topicals", ["audit_id"])
    op.create_table(
        "engagement_topical_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engagement_topical_id", sa.Integer(), sa.ForeignKey("engagement_topicals.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("topical_requirement_items.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("conclusion", sa.String(30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("findings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assessed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assessed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("engagement_topical_id", "item_id", name="uq_engagement_topical_item"),
    )
    op.create_index("ix_engagement_topical_items_engagement_topical_id", "engagement_topical_items",
                    ["engagement_topical_id"])
    op.bulk_insert(reqs, [{
        "id": 1, "code": "cybersecurity", "title": "Cybersecurity", "version": "2025",
        "effective_on": date(2026, 2, 5), "is_active": True,
        "source_url": "https://www.theiia.org/en/standards/2024-standards/topical-requirements/cybersecurity/",
        "description": ("Applies when cybersecurity is the subject of a planned engagement, is identified during an "
                        "engagement, or is the subject of an engagement request. Mandatory for assurance engagements, "
                        "recommended for advisory ones. Each requirement is assessed; exclusions keep their rationale."),
    }])
    op.bulk_insert(items, [{"requirement_id": 1, "area": a, "ref": r, "text": t, "sort": i}
                           for i, (a, r, t) in enumerate(CYBER_ITEMS)])


def downgrade() -> None:
    op.drop_table("engagement_topical_items")
    op.drop_table("engagement_topicals")
    op.drop_index("ix_topical_requirement_items_requirement_id", table_name="topical_requirement_items")
    op.drop_table("topical_requirement_items")
    op.drop_table("topical_requirements")
