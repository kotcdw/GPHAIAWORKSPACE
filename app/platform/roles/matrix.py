"""Access matrix: what each role may do, module by module and action by action.

GPHA INTERNAL AUDIT WORKSPACE's permissions are capabilities (for example "Fieldwork" or "Approve reports");
this table maps them onto the
familiar actions per module so administrators can read the role design at a glance. Each cell lists the permissions
that grant it; ``tier:staff`` means every internal audit account (Administrator, Manager, Auditor, Read-only User),
``tier:all`` every signed-in account. Deletion follows one rule everywhere and is described per row.
"""

from __future__ import annotations

import re
import threading
import time

from fastapi import Request
from sqlalchemy import select

ACTIONS = ("view", "create", "edit", "approve", "export", "configure")
# Rights the Super Administrator can refuse per role and module where no single permission stands for them; the
# server enforces them by request (GET = view, POST to a list = create, PUT/PATCH of a record = edit, DELETE).
GUARDED = ("view", "create", "edit", "delete")
DELETE_RULE = "Only records still in draft, never e-signed or linked; signed and issued records are kept"

ROWS: list[dict] = [
    {"module": "Users, roles and access", "view": ["system.users", "system.roles"], "create": ["system.users"],
     "edit": ["system.users"], "approve": ["system.users"], "export": ["system.users"],
     "configure": ["system.roles"],
     "delete": "Accounts without recorded activity only; the last administrator can never be removed"},
    {"module": "Organisational structure", "view": ["tier:staff"], "create": ["system.reference", "tier:staff"],
     "edit": ["system.reference", "tier:staff"], "approve": ["system.reference"], "export": ["data.export"],
     "configure": ["system.reference"],
     "delete": "Only pending units nothing uses; approved units are deactivated instead, keeping their history"},
    {"module": "Application settings", "view": ["system.config", "system.workflow", "system.reference"],
     "create": [], "edit": ["system.config", "system.workflow", "system.reference", "method.reporting",
                            "method.audit_types", "method.plan_config"],
     "approve": [], "export": [], "configure": ["system.config", "system.workflow", "system.automation"],
     "delete": "Settings are reset to their default, never deleted"},
    {"module": "Audit universe and libraries", "view": ["tier:staff"], "create": ["method.library"],
     "edit": ["method.library"], "approve": [], "export": ["data.export"],
     "configure": ["method.library", "method.programs"], "delete": DELETE_RULE},
    {"module": "Assurance planning", "view": ["tier:staff", "governance.view"], "create": ["plan.prepare"],
     "edit": ["plan.prepare", "plan.amend"], "approve": ["plan.approve"], "export": ["data.export"],
     "configure": ["method.plan_config"], "delete": DELETE_RULE},
    {"module": "Audit engagements and fieldwork", "view": ["tier:staff"], "create": ["audit.create"],
     "edit": ["audit.plan", "audit.fieldwork", "audit.workpapers", "audit.evidence"],
     "approve": ["audit.memo_approve", "review.workpapers", "audit.close"], "export": ["data.export"],
     "configure": ["method.audit_types", "method.programs"], "delete": DELETE_RULE},
    {"module": "Findings", "view": ["tier:staff"], "create": ["audit.findings"], "edit": ["audit.findings"],
     "approve": ["review.workpapers"], "export": ["data.export"], "configure": ["method.audit_types"],
     "delete": DELETE_RULE},
    {"module": "Audit reports", "view": ["tier:staff", "governance.view"], "create": ["report.prepare"],
     "edit": ["report.prepare"], "approve": ["report.review", "report.approve"], "export": ["data.export"],
     "configure": ["method.reporting"], "delete": "Reports are never deleted once sent to management"},
    {"module": "Follow-up and remediation", "view": ["tier:staff"], "create": ["audit.findings", "followup.manage"],
     "edit": ["followup.manage", "auditee.respond"], "approve": ["followup.validate", "followup.manage"],
     "export": ["data.export"], "configure": ["system.workflow"], "delete": DELETE_RULE},
    {"module": "Governance and quality", "view": ["governance.view"], "create": ["committee.record"],
     "edit": ["committee.record"], "approve": ["committee.record"], "export": ["data.export"],
     "configure": ["governance.charter"], "delete": DELETE_RULE},
    {"module": "Risk and compliance registers", "view": ["grc.view"],
     "create": ["grc.risk", "grc.compliance", "grc.policy", "grc.assets"],
     "edit": ["grc.risk", "grc.compliance", "grc.policy", "grc.assets"], "approve": ["grc.policy_approve"],
     "export": ["data.export"], "configure": ["grc.manage"], "delete": DELETE_RULE},
    {"module": "Audit trail and backups", "view": ["system.technical"], "create": ["system.technical"],
     "edit": [], "approve": [], "export": ["system.technical"], "configure": ["system.technical"],
     "delete": "The audit trail can never be edited or deleted; old backups are removed by retention"},
]


# The API paths of each module (first match wins, so the more specific modules come first).
PATHS: list[tuple[str, tuple[str, ...]]] = [
    ("Findings", (r"/api/findings", r"/api/audits/\d+/findings")),
    ("Audit reports", (r"/api/reports", r"/api/audits/\d+/report", r"/api/reporting", r"/api/ai-reporting",
                       r"/api/storyboards")),
    ("Follow-up and remediation", (r"/api/capa", r"/api/capa-files", r"/api/followup", r"/api/follow-up",
                                   r"/api/nonconformances", r"/api/activity-center")),
    ("Audit engagements and fieldwork", (r"/api/audits", r"/api/objectives", r"/api/risks", r"/api/controls",
                                         r"/api/control-tests", r"/api/procedures", r"/api/narratives",
                                         r"/api/working-papers", r"/api/evidence-requests", r"/api/evidence-files",
                                         r"/api/signoffs", r"/api/review-notes", r"/api/topical-requirements")),
    ("Assurance planning", (r"/api/assurance-plans", r"/api/plan-engagements", r"/api/plan-change-requests",
                            r"/api/audit-risk-assessments", r"/api/assessment-factors", r"/api/schedule",
                            r"/api/capacity")),
    ("Audit universe and libraries", (r"/api/audit-universe", r"/api/auditable-entities", r"/api/entity-units",
                                      r"/api/processes", r"/api/library", r"/api/object-library", r"/api/criteria",
                                      r"/api/audit-programs", r"/api/assurance-providers",
                                      r"/api/assurance-coverage", r"/api/assurance-map")),
    ("Organisational structure", (r"/api/organizations", r"/api/org-structure", r"/api/stakeholders")),
    ("Users, roles and access", (r"/api/users", r"/api/groups", r"/api/roles")),
    ("Application settings", (r"/api/config", r"/api/audit-types", r"/api/apps", r"/api/custom-fields",
                              r"/api/sla-policies", r"/api/workflows", r"/api/automations")),
    ("Governance and quality", (r"/api/charter", r"/api/qaip",
                                        r"/api/quality", r"/api/proficiency", r"/api/service-feedback")),
    ("Risk and compliance registers", (r"/api/grc",)),
    ("Audit trail and backups", (r"/api/audit-logs", r"/api/admin/backups?")),
]
_COMPILED = [(m, re.compile("^(?:" + "|".join(ps) + r")(?:/|$|\?)")) for m, ps in PATHS]
_LISTS = [re.compile("^(?:" + "|".join(ps) + r")/?$") for _, ps in PATHS]


def module_of(path: str) -> str | None:
    return next((m for m, rx in _COMPILED if rx.match(path)), None)


def action_of(method: str, path: str) -> str | None:
    """The guarded right a request uses: actions on a record (approve, sign, close...) follow their permissions."""
    if method in ("GET", "HEAD"):
        return "view"
    if method == "DELETE":
        return "delete"
    has_id = re.search(r"/\d+(?:/|$)", path) is not None
    if method == "POST" and (not has_id or any(rx.match(path) for rx in _LISTS)):
        return "create"
    if method in ("PUT", "PATCH") and has_id and not re.search(r"/\d+/[a-z-]+/?$", path):
        return "edit"
    return None


_LOCK = threading.Lock()
_CACHE: dict[str, set[tuple[str, str]]] = {}
_CACHE_AT = 0.0
_TTL = 5.0


def invalidate() -> None:
    global _CACHE_AT
    with _LOCK:
        _CACHE.clear()
        _CACHE_AT = 0.0


def refused() -> dict[str, set[tuple[str, str]]]:
    """Role -> {(module, action)} refused by the Super Administrator."""
    global _CACHE_AT
    with _LOCK:
        if _CACHE_AT and time.monotonic() - _CACHE_AT < _TTL:
            return {k: set(v) for k, v in _CACHE.items()}
    from app.core.database import SessionLocal
    from app.platform.roles.models import RoleModuleAccess

    out: dict[str, set[tuple[str, str]]] = {}
    try:
        with SessionLocal() as db:
            for r in db.execute(select(RoleModuleAccess)).scalars():
                out.setdefault(r.job_role, set()).add((r.module, r.action))
    except Exception:  # noqa: BLE001 - table not there yet (before the migration): nothing is refused
        out = {}
    with _LOCK:
        _CACHE.clear()
        _CACHE.update(out)
        _CACHE_AT = time.monotonic()
    return out


def cell_granted(tokens: list[str], perms: set[str], tier: str, read_only: bool, action: str) -> bool:
    if read_only and action != "view" and action != "export":
        return False  # the server refuses every change from a Read-only User
    for t in tokens:
        if t == "tier:all":
            return True
        if t == "tier:staff" and tier in ("Admin", "Auditor"):
            return True
        if t in perms:
            return True
    return False


def module_access_guard(request: Request) -> None:
    """App-wide dependency: refuse a request that uses a module right the caller's role has been refused.

    Costs nothing while no right is refused. The Super Administrator is never refused anything, so the workspace
    can always be administered."""
    rules = refused()
    if not rules:
        return
    path = request.url.path
    module = module_of(path)
    action = action_of(request.method, path) if module else None
    if action is None:
        return
    from fastapi import HTTPException, status

    from app.core import permissions as perms
    from app.core.database import SessionLocal
    from app.core.deps import get_current_session
    from app.platform.users.models import User

    with SessionLocal() as db:
        session = get_current_session(request, db)
        user = db.get(User, session.user_id) if session else None
        code = perms.job_role_of(user) if user else None
    if code is None or code == "super_admin":
        return
    if (module, action) in rules.get(code, set()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Your role may not {action} in {module} (Roles & permissions > Access by module)")
