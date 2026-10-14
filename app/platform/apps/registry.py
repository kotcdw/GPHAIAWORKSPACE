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
    # Overview
    App("portal", "Task Manager", "Overview", "inboxes", "One page of everything waiting for a person.",
        ("portal",), ("/api/portal",)),
    App("dashboard", "Dashboard", "Overview", "grid-1x2", "Role-based home page with KPIs and work in progress.",
        ("dashboard",), (), core=True),
    App("workspace", "GPHA Workspace", "Overview", "grid-3x3-gap", "Launch page for every app.", ("workspace",),
        (), core=True),
    App("tasks", "Task Center", "Overview", "check2-square", "Tasks assigned to people, with due dates.",
        ("tasks",), ("/api/tasks",)),
    App("drafts", "My Drafts", "Overview", "pencil-square", "Autosaved forms waiting to be finished.",
        ("drafts",), (), core=True),
    App("governance", "Governance portal", "Overview", "bank", "Read-only view for governing bodies.",
        ("governance",), ("/api/governance",)),
    App("portfolio", "Port portfolio", "Overview", "geo-alt", "Audit coverage and results by port.",
        ("portfolio",), ("/api/portfolio",)),
    App("committee", "Audit Committee", "Overview", "bar-chart-line",
        "Committee packs, meetings, minutes and decisions.", ("committee",), ("/api/committee",)),
    App("analytics", "Analytics", "Overview", "graph-up-arrow", "KPIs, trends and heat maps.", ("analytics",),
        ("/api/analytics",)),
    App("qaip", "Quality (QAIP)", "Overview", "patch-check", "Quality assurance and improvement programme.",
        ("qaip",), ("/api/qaip",)),
    # Planning
    App("plans", "Assurance Plan", "Planning", "calendar3", "Annual plan, approval cycle and distribution.",
        ("plans",), (), core=True),
    App("universe", "Audit Universe", "Planning", "diagram-3", "Auditable units and their risk ratings.",
        ("universe",), (), core=True),
    App("scheduler", "Scheduler", "Planning", "calendar-week", "Engagement dates and staff bookings.",
        ("scheduler",), ("/api/schedule",)),
    App("capacity", "Capacity & time", "Planning", "people-fill", "Available hours, utilisation and time sheets.",
        ("capacity",), ("/api/capacity",)),
    App("practice", "Professional practice", "Planning", "person-check",
        "Charter, independence declarations, CPD and external assessments.", ("practice",),
        ("/api/proficiency", "/api/charter")),
    # Audit work
    App("audits", "Audits", "Audit work", "clipboard-check", "Engagements from planning to closure.",
        ("audits",), (), core=True),
    App("capa", "Remediation & Follow-up", "Audit work", "tools", "Agreed actions, follow-up and MoF returns.",
        ("capa",), (), core=True),
    App("evidence", "Evidence requests", "Audit work", "inbox", "Requests to auditees and the evidence received.",
        ("evidence",), (), core=True),
    App("nonconformances", "Nonconformance", "Audit work", "exclamation-triangle", "Nonconformance register.",
        ("nonconformances",), ("/api/nonconformances",)),
    # Risk & compliance
    App("risk", "Risk Manager", "Risk & compliance", "shield-exclamation",
        "Enterprise risk register, strategic objectives, heat maps and KRIs.", ("risk",),
        ("/api/grc/risks", "/api/grc/objectives", "/api/grc/kris")),
    App("compliance", "Compliance Maps", "Risk & compliance", "diagram-2",
        "Obligations, requirements and the controls that meet them.", ("compliance",),
        ("/api/grc/regulations", "/api/grc/requirements", "/api/grc/compliance")),
    App("policies", "Policy Manager", "Risk & compliance", "file-earmark-ruled",
        "Policy drafting, approval, publication and attestations.", ("policies",),
        ("/api/grc/policies", "/api/grc/campaigns", "/api/grc/attestations")),
    App("assets", "Asset Inventory", "Risk & compliance", "hdd-network",
        "Systems, data, facilities and third parties with due diligence.", ("assets",), ("/api/grc/assets",)),
    # Registers
    App("organizations", "Organizations", "Registers", "building", "GPHA ports, departments, units and parties.",
        ("organizations",), (), core=True),
    App("stakeholders", "Stakeholders", "Registers", "people", "Stakeholder and auditee contacts.",
        ("stakeholders",), ("/api/stakeholders",)),
    App("library", "Frameworks & controls", "Registers", "diagram-3-fill", "Frameworks and standard controls.",
        ("library",), ("/api/library",)),
    App("criteria", "Criteria library", "Registers", "journal-bookmark", "Laws, policies and standards cited.",
        ("criteria",), ("/api/criteria",)),
    App("programs", "Audit programmes", "Registers", "list-check", "Reusable work programmes.", ("programs",),
        ("/api/audit-programs",)),
    App("service-feedback", "Service Feedback", "Registers", "chat-left-text", "Feedback on audit services.",
        ("service-feedback",), ("/api/service-feedback",)),
    # Platform
    App("automations", "Automations", "Account", "lightning-charge", "Reminders, routing and escalation rules.",
        ("automations",), ("/api/automations",)),
    App("ai", "AI assistance", "Services", "stars", "Optional drafting help (also needs the AI settings).", (),
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
    if row is None:
        db.add(AppConfig(key=KEY, value=value, updated_by=user_id))
    else:
        row.value, row.updated_by = value, user_id
    db.flush()
