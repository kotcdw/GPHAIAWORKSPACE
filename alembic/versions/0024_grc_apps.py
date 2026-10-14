"""Risk & compliance apps: Risk Manager & Strategy, Compliance Maps, Policy Manager, Asset Inventory; GRC links

Revision ID: 0024_grc_apps
Revises: 0023_frameworks_scheduler
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = "0024_grc_apps"
down_revision: str | None = "0023_frameworks_scheduler"
branch_labels = None
depends_on = None

TABLES = ("grc_links", "strategic_objectives", "enterprise_risks", "risk_assessments", "key_risk_indicators",
          "kri_readings", "regulations", "requirements", "policies", "policy_versions", "attestation_campaigns",
          "attestations", "assets", "third_party_assessments")


def upgrade() -> None:
    op.create_table(
        "grc_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("a_type", sa.String(20), nullable=False),
        sa.Column("a_id", sa.Integer(), nullable=False),
        sa.Column("b_type", sa.String(20), nullable=False),
        sa.Column("b_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("a_type", "a_id", "b_type", "b_id", name="uq_grc_links"),
    )
    op.create_table(
        "strategic_objectives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("period", sa.String(40), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "enterprise_risks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("consequence", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("objective_id", sa.Integer(), sa.ForeignKey("strategic_objectives.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("inherent_likelihood", sa.Integer(), nullable=False),
        sa.Column("inherent_impact", sa.Integer(), nullable=False),
        sa.Column("residual_likelihood", sa.Integer(), nullable=False),
        sa.Column("residual_impact", sa.Integer(), nullable=False),
        sa.Column("target_likelihood", sa.Integer(), nullable=True),
        sa.Column("target_impact", sa.Integer(), nullable=True),
        sa.Column("appetite", sa.String(40), nullable=False),
        sa.Column("treatment", sa.String(40), nullable=False),
        sa.Column("treatment_plan", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("last_assessed_at", sa.DateTime(), nullable=True),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_enterprise_risks_objective_id", "enterprise_risks", ["objective_id"])
    op.create_index("ix_enterprise_risks_owner_id", "enterprise_risks", ["owner_id"])
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("risk_id", sa.Integer(), sa.ForeignKey("enterprise_risks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inherent_likelihood", sa.Integer(), nullable=False),
        sa.Column("inherent_impact", sa.Integer(), nullable=False),
        sa.Column("residual_likelihood", sa.Integer(), nullable=False),
        sa.Column("residual_impact", sa.Integer(), nullable=False),
        sa.Column("control_effectiveness", sa.String(30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("assessed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assessed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_risk_assessments_risk_id", "risk_assessments", ["risk_id"])
    op.create_table(
        "key_risk_indicators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("risk_id", sa.Integer(), sa.ForeignKey("enterprise_risks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("higher_is_worse", sa.Boolean(), nullable=False),
        sa.Column("amber_at", sa.Float(), nullable=False),
        sa.Column("red_at", sa.Float(), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_key_risk_indicators_risk_id", "key_risk_indicators", ["risk_id"])
    op.create_table(
        "kri_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kri_id", sa.Integer(), sa.ForeignKey("key_risk_indicators.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_kri_readings_kri_id", "kri_readings", ["kri_id"])
    op.create_table(
        "regulations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("reg_type", sa.String(100), nullable=False),
        sa.Column("issuer", sa.String(160), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("regulation_id", sa.Integer(), sa.ForeignKey("regulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.Column("last_assessed_at", sa.DateTime(), nullable=True),
        sa.Column("assessed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assessment_comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("regulation_id", "ref", name="uq_requirements_regulation_ref"),
    )
    op.create_index("ix_requirements_regulation_id", "requirements", ["regulation_id"])
    op.create_index("ix_requirements_owner_id", "requirements", ["owner_id"])
    op.create_table(
        "policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approver_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("published_version", sa.Integer(), nullable=True),
        sa.Column("review_months", sa.Integer(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("next_review_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("stored_path", sa.String(500), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("policy_id", "version", name="uq_policy_versions"),
    )
    op.create_index("ix_policy_versions_policy_id", "policy_versions", ["policy_id"])
    op.create_table(
        "attestation_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_attestation_campaigns_policy_id", "attestation_campaigns", ["policy_id"])
    op.create_table(
        "attestations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("attestation_campaigns.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("campaign_id", "user_id", name="uq_attestations"),
    )
    op.create_index("ix_attestations_campaign_id", "attestations", ["campaign_id"])
    op.create_index("ix_attestations_user_id", "attestations", ["user_id"])
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("location", sa.String(160), nullable=False),
        sa.Column("criticality", sa.String(20), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("vendor_contact", sa.String(255), nullable=False),
        sa.Column("services", sa.Text(), nullable=False),
        sa.Column("contract_ref", sa.String(80), nullable=False),
        sa.Column("contract_start", sa.Date(), nullable=True),
        sa.Column("contract_end", sa.Date(), nullable=True),
        sa.Column("due_diligence", sa.String(40), nullable=False),
        sa.Column("risk_rating", sa.String(20), nullable=False),
        sa.Column("last_assessed_at", sa.Date(), nullable=True),
        sa.Column("next_assessment_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_assets_owner_id", "assets", ["owner_id"])
    op.create_table(
        "third_party_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assessed_on", sa.Date(), nullable=False),
        sa.Column("rating", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("areas", sa.Text(), nullable=False),
        sa.Column("findings", sa.Text(), nullable=False),
        sa.Column("assessor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_third_party_assessments_asset_id", "third_party_assessments", ["asset_id"])
    op.create_index("ix_grc_links_b", "grc_links", ["b_type", "b_id"])


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
