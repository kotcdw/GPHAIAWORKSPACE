"""API / Platform Core: identity, access, configuration, workflow plumbing and reference data.

Every domain module sits on top of this layer. Cross-cutting primitives that are not HTTP modules
(permissions, config rules, audit log, e-signatures, encryption, database session) live in ``app.core``.
"""

from __future__ import annotations

NAME = "API / Platform Core"
DESCRIPTION = (
    "Sign-in and two-step verification, users, roles and permissions, configuration, reference data, "
    "approvals, tasks, notifications, history and backups."
)
MODULES = {
    "auth": "Sign-in, sessions, two-step verification, password policy",
    "users": "User accounts, job roles, access tiers",
    "roles": "Roles & permissions matrix",
    "configuration": "Admin-configurable rules (no hard-coding)",
    "organizations": "Organization entities, ports, plan destinations",
    "stakeholders": "Stakeholders and auditee contacts",
    "customfields": "Admin-defined custom fields",
    "approvals": "E-signatures and approval routing",
    "tasks": "Tasks and assignments",
    "notifications": "In-app notifications",
    "history": "Record history and the audit log",
    "drafts": "Autosaved drafts",
    "views": "Saved views and filters",
    "dataio": "Import and export",
    "backups": "Encrypted database backups",
    "automations": "Admin-defined automation rules: reminders, routing and escalation",
    "portal": "Task Manager: one simple page of everything waiting for a business user",
    "apps": "Apps & customization: the Super Administrator switches apps on and off, renames them and sets branding",
}


def routers() -> list:
    from app.platform.approvals.router import router as approvals
    from app.platform.apps.router import router as apps
    from app.platform.architecture import router as architecture
    from app.platform.auth.router import router as auth
    from app.platform.automations.router import router as automations
    from app.platform.backups.router import router as backups
    from app.platform.configuration.router import router as configuration
    from app.platform.customfields.router import router as customfields
    from app.platform.dataio.router import router as dataio
    from app.platform.drafts.router import router as drafts
    from app.platform.history.router import records_router
    from app.platform.history.router import router as history
    from app.platform.notifications.router import router as notifications
    from app.platform.organizations.router import router as organizations
    from app.platform.portal.router import router as portal
    from app.platform.roles.router import router as roles
    from app.platform.stakeholders.router import router as stakeholders
    from app.platform.tasks.router import router as tasks
    from app.platform.users.router import router as users
    from app.platform.views.router import router as views

    return [auth, users, history, records_router, organizations, stakeholders, tasks, approvals, backups,
            drafts, notifications, configuration, dataio, views, customfields, roles, architecture, automations,
            portal, apps]
