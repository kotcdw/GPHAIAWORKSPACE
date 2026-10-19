"""Standards conformance: report corrections, assurance map, auditor prior roles, risk acceptance escalation

* ``report_revisions``: every issued version of an audit report, frozen (append-only), kept when a corrected
  version is issued (IIA GIAS 11.4). ``audit_reports.correction_reason``; ``report_distributions.version``.
* ``assurance_providers`` and ``assurance_coverage``: the assurance map of other providers per auditable entity
  and the reliance placed on them (GIAS 9.5).
* ``auditor_prior_roles``: org units an auditor worked in before joining Internal Audit (cooling-off, GIAS 2.2).
* ``capa``: risk acceptance is proposed, decided by the GM Audit and, above the set severity, by the Audit
  Committee (GIAS 11.5). Earlier risk acceptances become Accepted.
* ``app_config``: "Advisory" is added to a customised list of audit types.

Revision ID: 0043_standards_conformance
Revises: 0042_universe_definition
Create Date: 2026-10-19
"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op

revision: str = "0043_standards_conformance"
down_revision: str | None = "0042_universe_definition"
branch_labels = None
depends_on = None

REVISIONS = "report_revisions"


def _append_only(table: str) -> None:
    dialect = op.get_bind().dialect.name
    for verb in ("UPDATE", "DELETE"):
        name = f"{table}_no_{verb.lower()}"
        message = f"{table} is append-only: {verb} not permitted"
        if dialect == "mysql":
            op.execute(f"CREATE TRIGGER {name} BEFORE {verb} ON {table} FOR EACH ROW "
                       f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{message}'")
        else:
            op.execute(f"CREATE TRIGGER {name} BEFORE {verb} ON {table} BEGIN SELECT RAISE(ABORT, '{message}'); END;")


def upgrade() -> None:
    op.create_table(
        REVISIONS,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("audit_reports.id", ondelete="RESTRICT"), nullable=False,
                  index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(), nullable=False),
        sa.Column("correction_reason", sa.Text(), nullable=False),
        sa.Column("opened_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("report_id", "version", name="uq_report_revisions_version"),
    )
    _append_only(REVISIONS)
    with op.batch_alter_table("audit_reports") as t:
        t.add_column(sa.Column("correction_reason", sa.Text(), nullable=True))
    with op.batch_alter_table("report_distributions") as t:
        t.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "assurance_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("line", sa.String(60), nullable=False),
        sa.Column("contact", sa.String(160), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "assurance_coverage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entity_units.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("assurance_providers.id", ondelete="RESTRICT"),
                  nullable=False, index=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("last_assurance_on", sa.Date(), nullable=True),
        sa.Column("next_planned_on", sa.Date(), nullable=True),
        sa.Column("result", sa.String(40), nullable=False),
        sa.Column("reliance", sa.String(10), nullable=False, server_default="None"),
        sa.Column("reliance_basis", sa.Text(), nullable=True),
        sa.Column("evidence_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("entity_id", "provider_id", name="uq_assurance_coverage_entity_provider"),
    )
    op.create_table(
        "auditor_prior_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("org_unit_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(160), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    with op.batch_alter_table("capa") as t:
        t.add_column(sa.Column("risk_acceptance_status", sa.String(20), nullable=True))
        t.add_column(sa.Column("risk_proposed_by", sa.Integer(), nullable=True))
        t.add_column(sa.Column("risk_proposed_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE capa SET risk_acceptance_status = 'Accepted' WHERE risk_accepted_at IS NOT NULL")

    config = sa.table("app_config", sa.column("key", sa.String), sa.column("value", sa.Text))
    bind = op.get_bind()
    row = bind.execute(sa.select(config.c.value).where(config.c.key == "audit_types")).first()
    if row is not None:
        types = json.loads(row[0])
        if isinstance(types, list) and not any(str(t).lower() == "advisory" for t in types):
            bind.execute(config.update().where(config.c.key == "audit_types")
                         .values(value=json.dumps([*types, "Advisory"])))


def downgrade() -> None:
    with op.batch_alter_table("capa") as t:
        for col in ("risk_proposed_at", "risk_proposed_by", "risk_acceptance_status"):
            t.drop_column(col)
    op.drop_table("auditor_prior_roles")
    op.drop_table("assurance_coverage")
    op.drop_table("assurance_providers")
    with op.batch_alter_table("report_distributions") as t:
        t.drop_column("version")
    with op.batch_alter_table("audit_reports") as t:
        t.drop_column("correction_reason")
    for verb in ("update", "delete"):
        op.execute(f"DROP TRIGGER IF EXISTS {REVISIONS}_no_{verb}")
    op.drop_table(REVISIONS)
