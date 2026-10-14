"""Role-based access control: five standard roles and their permissions.

Roles: Super Administrator, Administrator, Manager, Auditor and Audit Client. Each user has one role
(``users.job_role``); the role decides the access *tier* the older endpoints check (``users.role``:
Admin / Auditor / Auditee) and the fine-grained permissions below. The Super Administrator always holds
every permission and can change what the other four roles may do on the Roles & permissions screen
(stored as differences from the defaults in ``role_permissions``).
"""

from __future__ import annotations

import dataclasses
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
    "system.superadmin": ("Platform",
                          "Full control: customize the app, switch apps on and off, appoint administrators"),
    # risk & compliance apps
    "grc.view": ("Risk & compliance", "View the risk register, compliance maps, policies and asset inventory"),
    "grc.manage": ("Risk & compliance", "Risk & compliance configuration; manage every register"),
    "grc.risk": ("Risk & compliance", "Risk Manager: strategic objectives, enterprise risks and KRIs"),
    "grc.compliance": ("Risk & compliance", "Compliance Maps: obligations, requirements and control mapping"),
    "grc.policy": ("Risk & compliance", "Policy Manager: draft and publish policies, run attestations"),
    "grc.policy_approve": ("Risk & compliance", "Approve policies (never one's own draft)"),
    "grc.assets": ("Risk & compliance", "Asset Inventory: assets, systems and third parties"),
    # services
    "ai.use": ("Services", "Use AI drafting assistance (only when an administrator has enabled the AI Service)"),
}

_ALL = set(PERMISSIONS)
_PLATFORM = {p for p in _ALL if p.startswith("system.")}
_METHOD = {p for p in _ALL if p.startswith("method.")}
_GRC = {p for p in _ALL if p.startswith("grc.")}
_FIELD = {"audit.plan", "audit.fieldwork", "audit.findings", "audit.workpapers", "audit.evidence", "report.prepare",
          "ai.use"}
_REVIEW = {"review.workpapers", "review.notes"}
# Only the Super Administrator holds these (full control of the platform and of who administers it).
SUPER_ONLY = {"system.superadmin", "system.roles"}
# Within the Manager role these are exercised only by the Chief Audit Executive (GM Audit): a Manager whose
# approval level is CAE. Unit Heads, Audit Managers and PIAs review; the GM Audit approves and distributes.
CAE_ONLY = {"plan.approve", "plan.amend", "oversight.portfolio", "oversight.qaip", "report.approve", "audit.close",
            "governance.charter"}


@dataclass(frozen=True)
class JobRole:
    code: str
    name: str
    tier: Role
    review_level: ReviewLevel | None
    description: str
    defaults: frozenset[str] = field(default_factory=frozenset)
    icon: str = "person"
    locked: bool = False  # permissions cannot be changed (the Super Administrator always holds everything)


# The five standard roles (role-based access control). The Super Administrator can change what Administrator,
# Manager, Auditor and Audit Client may do on the Roles & permissions screen; their own role is fixed.
JOB_ROLES: list[JobRole] = [
    JobRole("super_admin", "Super Administrator", Role.Admin, None,
            "Root administrator with full control: every permission, the Roles & permissions matrix, app "
            "customization (switch apps on and off, rename them, branding) and appointing administrators.",
            frozenset(_ALL), icon="shield-fill-check", locked=True),
    JobRole("admin", "Administrator", Role.Admin, None,
            "Runs the platform day to day: user accounts, configuration, reference data, workflow rules, "
            "methodology libraries, backups and the audit log. Does not perform or approve audit work.",
            frozenset((_PLATFORM - SUPER_ONLY) | _METHOD | {"committee.record", "followup.report", "governance.view",
                                                            "governance.charter", "grc.view", "grc.manage"}),
            icon="gear-fill"),
    JobRole("manager", "Manager", Role.Auditor, ReviewLevel.Manager,
            "Unit Heads, Audit Managers, Port Internal Auditors and the GM Audit: prepare the Assurance Plan, "
            "allocate staff, supervise and review engagements and follow up recommendations. Only a Manager "
            "with the GM Audit (CAE) approval level approves and distributes the plan and approves reports.",
            frozenset(_FIELD | _REVIEW | {
                "plan.prepare", "plan.approve", "plan.amend", "oversight.portfolio", "oversight.port",
                "oversight.resources", "oversight.qaip", "oversight.reporting", "audit.create", "audit.memo_approve",
                "audit.close", "report.review", "report.approve", "quality.review", "followup.manage",
                "followup.validate", "governance.view", "committee.record", "followup.report",
                "governance.charter", "proficiency.manage", "grc.view", "grc.risk"}),
            icon="person-badge-fill"),
    JobRole("auditor", "Auditor", Role.Auditor, None,
            "Senior Auditors, Auditors and Audit Clerks: plan and perform assigned engagements, test controls, "
            "file working papers and evidence, raise findings and validate remediation.",
            frozenset(_FIELD | _REVIEW | {"audit.create", "followup.validate", "grc.view"}),
            icon="clipboard-check-fill"),
    JobRole("audit_client", "Audit Client", Role.Auditee, None,
            "Management and staff of audited units (auditees): answer evidence requests, respond to findings, "
            "agree and update actions, attest to policies and keep their own risks and controls current.",
            frozenset({"auditee.respond"}), icon="building"),
]
JOB_ROLE_CODES = [r.code for r in JOB_ROLES]
# Job roles used before the five standard roles; old accounts and links keep working.
LEGACY_ROLES = {
    "platform_admin": "super_admin", "audit_admin": "admin", "gm_audit": "manager", "pia": "manager",
    "audit_manager": "manager", "unit_head": "manager", "senior_auditor": "auditor", "audit_clerk": "auditor",
    "auditee": "audit_client", "risk_officer": "audit_client", "committee": "audit_client",
}
JOB_ROLES_BY_CODE = {r.code: r for r in JOB_ROLES}
JOB_ROLES_BY_CODE.update({old: JOB_ROLES_BY_CODE[new] for old, new in LEGACY_ROLES.items()})
# The former GM Audit role is a Manager with the Chief Audit Executive approval level.
JOB_ROLES_BY_CODE["gm_audit"] = dataclasses.replace(JOB_ROLES_BY_CODE["manager"], review_level=ReviewLevel.CAE)


def default_job_role(user) -> str:  # noqa: ANN001
    """Job role for accounts without one: the first administrators are Super Administrators."""
    if user.role == Role.Admin:
        return "super_admin"
    if user.role in (Role.Auditee, Role.Committee):
        return "audit_client"
    if user.review_level in (ReviewLevel.Manager, ReviewLevel.CAE):
        return "manager"
    return "auditor"


def job_role_of(user) -> str:  # noqa: ANN001
    code = getattr(user, "job_role", None)
    code = LEGACY_ROLES.get(code, code)
    return code if code in JOB_ROLE_CODES else default_job_role(user)


def is_super_admin(user) -> bool:  # noqa: ANN001
    return user is not None and job_role_of(user) == "super_admin"


def is_cae(user) -> bool:  # noqa: ANN001
    """The Chief Audit Executive (GM Audit): a Manager given the CAE approval level."""
    return user is not None and user.review_level == ReviewLevel.CAE


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
            if row.job_role in out and row.permission in PERMISSIONS and not JOB_ROLES_BY_CODE[row.job_role].locked:
                if row.permission in SUPER_ONLY:
                    continue  # full control stays with the Super Administrator
                (out[row.job_role].add if row.granted else out[row.job_role].discard)(row.permission)
    except Exception:  # noqa: BLE001 - table missing / database down: defaults
        pass
    finally:
        db.close()
    out["super_admin"] = set(_ALL)  # the Super Administrator always has full control
    with _LOCK:
        _CACHE.clear()
        _CACHE.update(out)
        _CACHE_AT = time.monotonic()
    return {k: set(v) for k, v in out.items()}


def permissions_of(user) -> set[str]:  # noqa: ANN001
    if user is None:
        return set()
    code = job_role_of(user)
    have = matrix().get(code, set())
    if code == "manager" and not is_cae(user):
        have = have - CAE_ONLY
    return have


def has_perm(user, *perms: str) -> bool:  # noqa: ANN001
    """True when the user holds any of ``perms``."""
    have = permissions_of(user)
    return any(p in have for p in perms)
