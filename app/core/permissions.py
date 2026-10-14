"""Job roles and permissions (role-based access control).

Every user has an access *tier* (``users.role``: Admin / Auditor / Auditee / Committee) that the
older endpoints check, and a *job role* (``users.job_role``) that maps to a set of fine-grained
permissions. The defaults below follow the GPHA Internal Audit structure; the Platform
Administrator can change them on the Roles & permissions screen (stored in ``role_permissions``).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.enums import ReviewLevel, Role

# ---------------------------------------------------------------- permission catalogue
# code: (group, label)
PERMISSIONS: dict[str, tuple[str, str]] = {
    # platform
    "system.config": ("Platform", "System configuration (security, sign-in)"),
    "system.users": ("Platform", "Manage user accounts"),
    "system.roles": ("Platform", "Manage roles and permissions"),
    "system.reference": ("Platform", "Reference data: organization entities, custom fields, locations"),
    "system.workflow": ("Platform", "Workflow configuration (gates, SLAs, escalation)"),
    "system.technical": ("Platform", "Technical administration: backups, audit log, health"),
    # audit methodology
    "method.audit_types": ("Audit methodology", "Audit types"),
    "method.programs": ("Audit methodology", "Audit programmes and project templates"),
    "method.plan_config": ("Audit methodology", "Plan configuration (risk thresholds, audit cycle)"),
    "method.library": ("Audit methodology", "Audit object library (universe, criteria)"),
    "method.reporting": ("Audit methodology", "Reporting configuration (letterhead, methodology, KPI targets)"),
    # planning & oversight
    "plan.prepare": ("Planning & oversight", "Prepare the Assurance Plan"),
    "plan.approve": ("Planning & oversight", "Approve the Assurance Plan (e-sign)"),
    "plan.amend": ("Planning & oversight", "Amend the approved plan; record Audit Committee approval"),
    "oversight.portfolio": ("Planning & oversight", "Portfolio oversight across all ports"),
    "oversight.port": ("Planning & oversight", "Port audit oversight (own port)"),
    "oversight.resources": ("Planning & oversight", "Resource allocation, capacity and time sheets of others"),
    "oversight.qaip": ("Planning & oversight", "QAIP oversight and internal assessment"),
    "oversight.reporting": ("Planning & oversight", "Analytics and reporting to governing bodies"),
    # engagements
    "audit.create": ("Engagements", "Create audits and allocate the team"),
    "audit.plan": ("Engagements", "Engagement planning (planning memo, programme)"),
    "audit.memo_approve": ("Engagements", "Approve planning memos"),
    "audit.fieldwork": ("Engagements", "Fieldwork: risk & control matrix, tests"),
    "audit.findings": ("Engagements", "Findings management"),
    "audit.workpapers": ("Engagements", "Upload and file working papers"),
    "audit.evidence": ("Engagements", "Evidence requests to auditees"),
    "audit.close": ("Engagements", "Close audits (e-sign)"),
    # review & reporting
    "review.workpapers": ("Review & reporting", "Review and sign off working papers and tests"),
    "review.notes": ("Review & reporting", "Raise and clear review notes"),
    "report.prepare": ("Review & reporting", "Prepare audit reports"),
    "report.review": ("Review & reporting", "Review reports (Audit Manager level)"),
    "report.approve": ("Review & reporting", "Approve and issue reports (CAE level)"),
    "quality.review": ("Review & reporting", "Engagement quality reviews"),
    # follow-up
    "followup.validate": ("Follow-up", "Validate remediation (follow-up testing)"),
    "followup.manage": ("Follow-up", "Manage remediation and escalations"),
    # auditee / governance
    "auditee.respond": ("Auditee & governance", "Respond to evidence requests, findings and actions"),
    "governance.view": ("Auditee & governance", "View approved plans, issued reports and dashboards"),
    "committee.record": ("Auditee & governance", "Record Audit Committee meetings, minutes and decisions"),
    "followup.report": ("Follow-up", "Quarterly follow-up reports and the annual implementation statement"),
    "governance.charter": ("Planning & oversight", "Internal audit charter and external quality assessments"),
    "proficiency.manage": ("Planning & oversight", "Review independence declarations and staff CPD"),
    "system.automation": ("Platform", "Automation rules (notifications, tasks, reminders)"),
    # services
    "ai.use": ("Services", "Use AI drafting assistance (only when an administrator has enabled the AI Service)"),
}

_ALL = set(PERMISSIONS)
_PLATFORM = {p for p in _ALL if p.startswith("system.")}
_METHOD = {p for p in _ALL if p.startswith("method.")}
_FIELD = {"audit.plan", "audit.fieldwork", "audit.findings", "audit.workpapers", "audit.evidence", "report.prepare",
          "ai.use"}
_REVIEW = {"review.workpapers", "review.notes"}


@dataclass(frozen=True)
class JobRole:
    code: str
    name: str
    tier: Role
    review_level: ReviewLevel | None
    description: str
    defaults: frozenset[str] = field(default_factory=frozenset)


JOB_ROLES: list[JobRole] = [
    JobRole("platform_admin", "Platform Administrator", Role.Admin, None,
            "System configuration, reference data, roles and permissions, organization entities, workflow "
            "configuration and technical administration.", frozenset(_ALL)),
    JobRole("audit_admin", "Audit Administrator", Role.Auditor, None,
            "Audit types, audit programmes, project templates, plan configuration, audit object library and "
            "reporting configuration.",
            frozenset(_METHOD | {"system.reference", "plan.prepare", "oversight.reporting", "audit.create",
                                 "committee.record", "followup.report", "governance.charter", "system.automation"})),
    JobRole("gm_audit", "GM Audit (Chief Audit Executive)", Role.Auditor, ReviewLevel.CAE,
            "Internal Audit strategy, annual plan and portfolio oversight, high-level approvals, QAIP oversight "
            "and reporting to governing bodies.",
            frozenset({"plan.prepare", "plan.approve", "plan.amend", "oversight.portfolio", "oversight.port",
                       "oversight.resources", "oversight.qaip", "oversight.reporting", "audit.create",
                       "audit.memo_approve", "audit.close", "report.review", "report.approve", "quality.review",
                       "followup.manage", "followup.validate", "governance.view", "ai.use", "committee.record",
                       "followup.report", "governance.charter", "proficiency.manage"} | _REVIEW)),
    JobRole("pia", "PIA (Principal Internal Auditor)", Role.Auditor, ReviewLevel.Manager,
            "Port audit oversight, resource allocation, audit review, follow-up and port portfolio management.",
            frozenset({"oversight.port", "oversight.resources", "plan.prepare", "audit.create", "audit.memo_approve",
                       "report.review", "quality.review", "followup.manage", "followup.validate",
                       "oversight.reporting", "ai.use", "followup.report", "proficiency.manage"} | _REVIEW)),
    JobRole("audit_manager", "Audit Manager", Role.Auditor, ReviewLevel.Manager,
            "Engagement planning, team allocation, supervision, review, findings management and report "
            "preparation and review.",
            frozenset(_FIELD | _REVIEW | {"audit.create", "audit.memo_approve", "report.review", "quality.review",
                                          "plan.prepare",
                                          "followup.validate", "followup.manage", "oversight.resources",
                                          "followup.report", "proficiency.manage"})),
    JobRole("unit_head", "Unit Head / Supervisor", Role.Auditor, None,
            "Day-to-day review, working-paper review, coaching, quality checks and assignment monitoring.",
            frozenset(_FIELD | _REVIEW | {"quality.review", "oversight.resources", "followup.validate"})),
    JobRole("senior_auditor", "Senior Auditor", Role.Auditor, None,
            "Fieldwork, testing, supervision of assigned tasks, working-paper quality and review support.",
            frozenset(_FIELD | {"review.workpapers", "followup.validate"})),
    JobRole("auditor", "Auditor", Role.Auditor, None,
            "Planning support, fieldwork, evidence analysis, tests, working papers and findings.",
            frozenset(_FIELD | {"review.workpapers", "review.notes", "followup.validate", "audit.create"})),
    JobRole("audit_clerk", "Audit Clerk / Assistant", Role.Auditor, None,
            "Documentation support, evidence and records administration, logistics, filing and administrative "
            "tracking.", frozenset({"audit.workpapers", "audit.evidence"})),
    JobRole("auditee", "Management / Auditee", Role.Auditee, None,
            "Receives evidence requests, submits evidence, responds to findings, provides action plans and updates "
            "remediation status.", frozenset({"auditee.respond"})),
    JobRole("committee", "Audit Committee / Executive Reviewer", Role.Committee, None,
            "Controlled, read-only access to approved plans, issued reports and dashboards.",
            frozenset({"governance.view"})),
]
JOB_ROLES_BY_CODE = {r.code: r for r in JOB_ROLES}


def default_job_role(user) -> str:  # noqa: ANN001
    """Job role for accounts created before job roles existed."""
    if user.role == Role.Admin:
        return "platform_admin"
    if user.role == Role.Auditee:
        return "auditee"
    if user.role == Role.Committee:
        return "committee"
    if user.review_level == ReviewLevel.CAE:
        return "gm_audit"
    if user.review_level == ReviewLevel.Manager:
        return "audit_manager"
    return "auditor"


def job_role_of(user) -> str:  # noqa: ANN001
    code = getattr(user, "job_role", None)
    return code if code in JOB_ROLES_BY_CODE else default_job_role(user)


# ---------------------------------------------------------------- matrix with admin overrides

_CACHE: dict[str, set[str]] = {}
_CACHE_AT = 0.0
_LOCK = threading.Lock()


def invalidate() -> None:
    global _CACHE_AT
    with _LOCK:
        _CACHE.clear()
        _CACHE_AT = 0.0


def matrix() -> dict[str, set[str]]:
    """{job_role: permissions} = defaults with the saved overrides applied (cached 30 s)."""
    global _CACHE_AT
    with _LOCK:
        if _CACHE_AT and time.monotonic() - _CACHE_AT < 30:
            return {k: set(v) for k, v in _CACHE.items()}
    out = {r.code: set(r.defaults) for r in JOB_ROLES}
    db = SessionLocal()
    try:
        from app.platform.roles.models import RolePermission

        for row in db.execute(select(RolePermission)).scalars():
            if row.job_role in out and row.permission in PERMISSIONS:
                (out[row.job_role].add if row.granted else out[row.job_role].discard)(row.permission)
    except Exception:  # noqa: BLE001 - table missing / database down: defaults
        pass
    finally:
        db.close()
    out["platform_admin"].add("system.roles")  # never lock the administrators out
    with _LOCK:
        _CACHE.clear()
        _CACHE.update(out)
        _CACHE_AT = time.monotonic()
    return {k: set(v) for k, v in out.items()}


def permissions_of(user) -> set[str]:  # noqa: ANN001
    if user is None:
        return set()
    return matrix().get(job_role_of(user), set())


def has_perm(user, *perms: str) -> bool:  # noqa: ANN001
    """True when the user holds any of ``perms``."""
    have = permissions_of(user)
    return any(p in have for p in perms)
