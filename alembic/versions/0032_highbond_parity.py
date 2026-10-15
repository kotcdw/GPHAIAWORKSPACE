"""HighBond parity: five-level sign-offs, narratives, favourites, audit type terms and custom attributes,
Results (collections, tables, records, interpretations, triggers), Storyboards and Robots

Revision ID: 0032_highbond_parity
Revises: 0031_connected_universe
Create Date: 2026-10-15
"""

from __future__ import annotations

import json

import sqlalchemy as sa

from alembic import op

revision: str = "0032_highbond_parity"
down_revision: str | None = "0031_connected_universe"
branch_labels = None
depends_on = None

_CUSTOM = ("objectives", "risks", "controls", "procedures", "control_tests")


def _user(nullable: bool = True, name: str = "user_id") -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=nullable)


def upgrade() -> None:
    # ---- sign-offs (Preparer, Detail Reviewer, General Reviewer, Supplemental Reviewer, Specialty Reviewer)
    op.create_table(
        "signoffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        _user(),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
        sa.Column("override", sa.Boolean(), nullable=False, server_default="0"),
        sa.UniqueConstraint("target_type", "target_id", "level", name="uq_signoffs_target_level"),
    )
    op.create_index("ix_signoffs_target", "signoffs", ["target_type", "target_id"])
    op.create_table(
        "signoff_reviewers",
        sa.Column("target_type", sa.String(20), primary_key=True),
        sa.Column("target_id", sa.Integer(), primary_key=True),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        _user(name="set_by"),
        sa.Column("set_at", sa.DateTime(), nullable=False),
    )

    # ---- narratives (Internal Control workflow)
    op.create_table(
        "narratives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("objective_id", sa.Integer(), sa.ForeignKey("objectives.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(60), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("custom_fields", sa.Text(), nullable=False),
        _user(name="created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "narrative_controls",
        sa.Column("narrative_id", sa.Integer(), sa.ForeignKey("narratives.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("control_id", sa.Integer(), sa.ForeignKey("controls.id", ondelete="CASCADE"), primary_key=True),
    )

    # ---- favourites on the audit list
    op.create_table(
        "audit_favorites",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # ---- terminology and custom attributes per audit type
    op.create_table(
        "audit_type_terms",
        sa.Column("audit_type", sa.String(60), primary_key=True),
        sa.Column("term_key", sa.String(40), primary_key=True),
        sa.Column("label", sa.String(60), nullable=False),
    )
    op.add_column("custom_fields", sa.Column("audit_type", sa.String(60), nullable=True))
    for table in _CUSTOM:
        op.add_column(table, sa.Column("custom_fields", sa.Text(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET custom_fields = '{{}}'"))
        op.alter_column(table, "custom_fields", existing_type=sa.Text(), nullable=False)

    # ---- Results, Storyboards, Robots
    op.create_table(
        "results_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="0"),
        _user(name="created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "results_tables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("results_collections.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("analytic", sa.String(40), nullable=True),
        _user(name="created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "results_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("results_tables.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("record_key", sa.String(120), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="Medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="New"),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("table_id", "record_key", name="uq_results_records_key"),
    )
    op.create_table(
        "results_interpretations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("results_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config", sa.Text(), nullable=False),
        _user(name="created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "results_triggers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("results_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        _user(name="created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "storyboards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("blocks", sa.Text(), nullable=False),
        sa.Column("shared_with", sa.Text(), nullable=False),
        _user(name="created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "robots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        _user(name="created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "robot_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("robot_id", sa.Integer(), sa.ForeignKey("robots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("analytic", sa.String(40), nullable=False),
        sa.Column("params", sa.Text(), nullable=False),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("results_tables.id", ondelete="SET NULL"), nullable=True),
        sa.Column("frequency", sa.String(10), nullable=True),
        sa.Column("starting_at", sa.String(5), nullable=False, server_default="06:00"),
        sa.Column("beginning_on", sa.Date(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("notify_on_failure", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        _user(name="created_by"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "robot_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("robot_tasks.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("method", sa.String(12), nullable=False),
        _user(),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=False),
    )

    # ---- carry existing preparer / reviewer sign-offs into the sign-off table
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO signoffs (target_type, target_id, audit_id, level, user_id, signed_at, override) "
        "SELECT 'procedure', p.id, o.audit_id, 1, p.performed_by, p.performed_at, 0 FROM procedures p "
        "JOIN objectives o ON o.id = p.objective_id WHERE p.performed_at IS NOT NULL"))
    conn.execute(sa.text(
        "INSERT INTO signoffs (target_type, target_id, audit_id, level, user_id, signed_at, override) "
        "SELECT 'procedure', p.id, o.audit_id, 2, p.reviewed_by, p.reviewed_at, 0 FROM procedures p "
        "JOIN objectives o ON o.id = p.objective_id WHERE p.reviewed_at IS NOT NULL"))
    for level, who, when in ((1, "performed_by", "performed_at"), (2, "reviewed_by", "reviewed_at")):
        conn.execute(sa.text(
            "INSERT INTO signoffs (target_type, target_id, audit_id, level, user_id, signed_at, override) "
            f"SELECT 'test', t.id, o.audit_id, {level}, t.{who}, t.{when}, 0 FROM control_tests t "
            "JOIN controls c ON c.id = t.control_id JOIN objectives o ON o.id = c.objective_id "
            f"WHERE t.{when} IS NOT NULL"))
    rows = conn.execute(sa.text("SELECT id, audit_id, created_by, created_at, reviewed_at, review_trail "
                                "FROM findings WHERE reviewed_at IS NOT NULL")).all()
    for fid, audit_id, created_by, created_at, reviewed_at, raw in rows:
        try:
            trail = json.loads(raw or "[]")
        except ValueError:
            trail = []
        signers = [created_by] + [t.get("user_id") for t in trail if isinstance(t, dict)][:4]
        for level, uid in enumerate(signers, start=1):
            conn.execute(sa.text(
                "INSERT INTO signoffs (target_type, target_id, audit_id, level, user_id, signed_at, override) "
                "VALUES ('finding', :t, :a, :l, :u, :s, 0)"),
                {"t": fid, "a": audit_id, "l": level, "u": uid, "s": reviewed_at if level > 1 else created_at})


def downgrade() -> None:
    for table in ("robot_runs", "robot_tasks", "robots", "storyboards", "results_triggers",
                  "results_interpretations", "results_records", "results_tables", "results_collections",
                  "audit_type_terms", "audit_favorites", "narrative_controls", "narratives", "signoff_reviewers",
                  "signoffs"):
        op.drop_table(table)
    for table in _CUSTOM:
        op.drop_column(table, "custom_fields")
    op.drop_column("custom_fields", "audit_type")
