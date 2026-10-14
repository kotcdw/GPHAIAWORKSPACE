"""Five standard roles (Super Administrator, Administrator, Manager, Auditor, Audit Client)

Every account is moved from the old job roles to one of the five; the access tier follows the role and the
GM Audit keeps the CAE approval level. Old permission overrides are dropped (they belonged to the old roles).

Revision ID: 0025_standard_roles
Revises: 0024_grc_apps
Create Date: 2026-10-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0025_standard_roles"
down_revision: str | None = "0024_grc_apps"
branch_labels = None
depends_on = None

MAP = {
    "platform_admin": "super_admin", "audit_admin": "admin", "gm_audit": "manager", "pia": "manager",
    "audit_manager": "manager", "unit_head": "manager", "senior_auditor": "auditor", "auditor": "auditor",
    "audit_clerk": "auditor", "auditee": "audit_client", "risk_officer": "audit_client",
    "committee": "audit_client",
}
TIER = {"super_admin": "Admin", "admin": "Admin", "manager": "Auditor", "auditor": "Auditor",
        "audit_client": "Auditee"}


def upgrade() -> None:
    bind = op.get_bind()
    users = bind.execute(sa.text("SELECT id, role, job_role, review_level FROM users")).fetchall()
    for uid, tier, job, level in users:
        new = MAP.get(job or "")
        if new is None:
            if tier == "Admin":
                new = "super_admin"
            elif tier in ("Auditee", "Committee"):
                new = "audit_client"
            elif level in ("Manager", "CAE"):
                new = "manager"
            else:
                new = "auditor"
        if new == "manager":
            level = "CAE" if (job == "gm_audit" or level == "CAE") else "Manager"
        else:
            level = None
        bind.execute(sa.text("UPDATE users SET job_role=:j, role=:r, review_level=:l WHERE id=:i"),
                     {"j": new, "r": TIER[new], "l": level, "i": uid})
    bind.execute(sa.text("DELETE FROM role_permissions"))
    bind.execute(sa.text("UPDATE automation_rules SET actions = REPLACE(actions, '\"role:gm_audit\"', "
                         "'\"level:CAE\"')"))


def downgrade() -> None:
    bind = op.get_bind()
    back = {"super_admin": "platform_admin", "admin": "audit_admin", "manager": "audit_manager",
            "auditor": "auditor", "audit_client": "auditee"}
    for new, old in back.items():
        bind.execute(sa.text("UPDATE users SET job_role=:o WHERE job_role=:n"), {"o": old, "n": new})
    bind.execute(sa.text("UPDATE users SET job_role='gm_audit' WHERE job_role='audit_manager' "
                         "AND review_level='CAE'"))
