"""The apps of the workspace and the Super Administrator's customization of them.

Each app has a key, a default name, the sidebar screen(s) it owns and the API paths it serves. The Super
Administrator can switch an app off (its screens disappear and its API answers 404 for everyone), rename it and
set the workspace branding. Core apps cannot be switched off because the rest of the platform depends on them.
Settings are stored as one JSON value (``app_customization``) in the configuration table.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session as DBSession

from app.core import appconfig

KEY = "app_customization"


# Solution groups (titles and order match the sidebar and the All apps page).
HOME = "Home"
AUDIT = "Audit management"
RESOURCE = "Resource management"
RISK = "Risk management"
COMPLIANCE = "Compliance management"
REPORTING = "Analytics & reporting"
SETTINGS = "Platform settings"
SERVICES = "Services"


@dataclass(frozen=True)
class App:
    key: str
    name: str
    section: str
    icon: str
    description: str
    views: tuple[str, ...] = ()
    api: tuple[str, ...] = ()
    core: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)


APPS: list[App] = [
    # Home
    App("dashboard", "Workspace Apps", HOME, "grid-3x3-gap", "Home page that hosts every app and feature.",
        ("dashboard",), (), core=True),
    App("drafts", "My Drafts", HOME, "pencil-square", "Autosaved forms waiting to be finished.",
        ("drafts",), (), core=True),
    # Audit management
    App("universe", "Audit universe", AUDIT, "diagram-3",
        "Auditable entities from the Org Structure and Process library.",
        ("universe",), (), core=True),
    App("plans", "Assurance Plans", AUDIT, "calendar3", "Annual plan, approval cycle and distribution.",
        ("plans",), (), core=True),
    App("audits", "Audits", AUDIT, "clipboard-check", "Engagements from planning to closure.",
        ("audits",), (), core=True),
    App("programs", "Project Library", AUDIT, "list-check", "Reusable work programmes.", ("programs",),
        ("/api/audit-programs",)),
    App("tasks", "Task Tracker", AUDIT, "check2-square",
        "Priorities, to-dos and requests assigned to you or by you, across all audits.",
        ("portal", "tasks"), ("/api/portal", "/api/tasks")),
    App("evidence", "Requests", AUDIT, "inbox", "Requests to auditees and the evidence received.",
        ("evidence",), (), core=True),
    App("capa", "Remediation & Follow-up", AUDIT, "tools", "Agreed actions, follow-up and MoF returns.",
        ("capa",), (), core=True),
    # Resource management
    App("scheduler", "Scheduler", RESOURCE, "calendar-week", "Engagement dates and staff bookings.",
        ("scheduler",), ("/api/schedule",)),
    App("capacity", "Timesheets & capacity", RESOURCE, "people-fill", "Available hours, utilisation and time sheets.",
        ("capacity",), ("/api/capacity",)),
    App("practice", "Professional practice", RESOURCE, "person-check",
        "Charter, independence declarations, CPD and external assessments.", ("practice",),
        ("/api/proficiency", "/api/charter")),
    # Risk management
    App("risk", "Risk Manager", RISK, "shield-exclamation",
        "Enterprise risk register, strategic objectives, heat maps and KRIs.", ("risk",),
        ("/api/grc/risks", "/api/grc/objectives", "/api/grc/kris")),
    App("assets", "Asset Inventory", RISK, "hdd-network",
        "Systems, data, facilities and third parties with due diligence.", ("assets",), ("/api/grc/assets",)),
    # Compliance management
    App("library", "Frameworks", COMPLIANCE, "diagram-3-fill", "Frameworks and standard controls.",
        ("library",), ("/api/library",)),
    App("compliance", "Compliance Maps", COMPLIANCE, "diagram-2",
        "Obligations, requirements and the controls that meet them.", ("compliance",),
        ("/api/grc/regulations", "/api/grc/requirements", "/api/grc/compliance")),
    App("policies", "Policy Manager", COMPLIANCE, "file-earmark-ruled",
        "Policy drafting, approval, publication and attestations.", ("policies",),
        ("/api/grc/policies", "/api/grc/campaigns", "/api/grc/attestations")),
    App("nonconformances", "Nonconformance", COMPLIANCE, "exclamation-triangle", "Nonconformance register.",
        ("nonconformances",), ("/api/nonconformances",)),
    # Analytics & reporting
    App("analytics", "Analytics", REPORTING, "graph-up-arrow", "KPIs, trends and heat maps.", ("analytics",),
        ("/api/analytics",)),
    App("committee", "Audit Committee", REPORTING, "bar-chart-line",
        "Committee packs, meetings, minutes and decisions.", ("committee",), ("/api/committee",)),
    App("governance", "Governance portal", REPORTING, "bank", "Read-only view for governing bodies.",
        ("governance",), ("/api/governance",)),
    App("portfolio", "Port portfolio", REPORTING, "geo-alt", "Audit coverage and results by port.",
        ("portfolio",), ("/api/portfolio",)),
    App("qaip", "Quality (QAIP)", REPORTING, "patch-check", "Quality assurance and improvement programme.",
        ("qaip",), ("/api/qaip",)),
    App("results", "Results", REPORTING, "table", "Collections of analytic tables with triage workflow and triggers.",
        ("results",), ("/api/results",)),
    App("storyboards", "Storyboards", REPORTING, "easel", "Charts, metrics and text from Results, shared read-only.",
        ("storyboards",), ("/api/storyboards",)),
    App("reports", "Reports", REPORTING, "file-earmark-bar-graph",
        "Reports, dashboards and presentations over live data, and AI Reporting with human review.",
        ("reports",), ("/api/reporting", "/api/ai-reporting")),
    App("robots", "Robots", REPORTING, "robot", "Scheduled analytic tasks that publish into Results tables.",
        ("robots",), ("/api/robots", "/api/robot-tasks", "/api/robot-runs")),
    App("service-feedback", "Service Feedback", REPORTING, "chat-left-text", "Feedback on audit services.",
        ("service-feedback",), ("/api/service-feedback",)),
    # Platform settings
    App("organizations", "Organizations", SETTINGS, "building", "GPHA ports, departments, units and parties.",
        ("organizations",), (), core=True),
    App("stakeholders", "Stakeholders", SETTINGS, "people", "Stakeholder and auditee contacts.",
        ("stakeholders",), ("/api/stakeholders",)),
    App("automations", "Automations", SETTINGS, "lightning-charge", "Reminders, routing and escalation rules.",
        ("automations",), ("/api/automations",)),
    # Services
    App("ai", "AI assistance", SERVICES, "stars", "Optional drafting help (also needs the AI settings).", (),
        ("/api/ai",)),
]
APPS_BY_KEY = {a.key: a for a in APPS}

DEFAULT_BRANDING = {"name": "GPHA INTERNAL AUDIT", "sub": "WORKSPACE", "title": "GPHA Internal Audit Workspace"}


def settings() -> dict:
    raw = appconfig._load().get(KEY) or {}  # noqa: SLF001 - shared cached read of the configuration table
    apps = raw.get("apps", {}) if isinstance(raw, dict) else {}
    branding = {**DEFAULT_BRANDING, **(raw.get("branding", {}) if isinstance(raw, dict) else {})}
    return {"apps": apps, "branding": branding}


def enabled(key: str) -> bool:
    app = APPS_BY_KEY.get(key)
    if app is None or app.core:
        return True
    return bool(settings()["apps"].get(key, {}).get("enabled", True))


def disabled_prefixes() -> list[tuple[str, str]]:
    cfg = settings()["apps"]
    out = []
    for a in APPS:
        if not a.core and not cfg.get(a.key, {}).get("enabled", True):
            out += [(p, cfg.get(a.key, {}).get("label") or a.name) for p in a.api]
    return out


def catalogue() -> dict:
    s = settings()
    return {"branding": s["branding"], "apps": [
        {"key": a.key, "name": a.name, "label": s["apps"].get(a.key, {}).get("label") or a.name, "section": a.section,
         "icon": a.icon, "description": a.description, "views": list(a.views), "core": a.core,
         "enabled": a.core or bool(s["apps"].get(a.key, {}).get("enabled", True))} for a in APPS]}


def save(db: DBSession, apps: dict[str, dict], branding: dict[str, str], user_id: int) -> None:
    from app.core.appconfig import AppConfig

    clean = {}
    for key, value in apps.items():
        app = APPS_BY_KEY.get(key)
        if app is None:
            continue
        label = (value.get("label") or "").strip()[:60]
        clean[key] = {"enabled": True if app.core else bool(value.get("enabled", True)),
                      "label": "" if label == app.name else label}
    brand = {k: (branding.get(k) or DEFAULT_BRANDING[k]).strip()[:80] for k in DEFAULT_BRANDING}
    row = db.get(AppConfig, KEY)
    value = json.dumps({"apps": clean, "branding": brand})
    if row is None or row.value != value:  # keep the change in the settings history (append-only)
        from app.core.appconfig import AppConfigHistory
        from app.platform.users.models import User

        who = db.get(User, user_id)
        db.add(AppConfigHistory(key=KEY, action="update", old_value=row.value if row else None, new_value=value,
                                changed_by=user_id, changed_by_name=(who.full_name or who.username) if who else None))
    if row is None:
        db.add(AppConfig(key=KEY, value=value, updated_by=user_id))
    else:
        row.value, row.updated_by = value, user_id
    db.flush()
