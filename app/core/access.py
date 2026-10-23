"""Record-level access rules (who may *see* what).

Administrators see every record. Audit staff (Auditor tier) see engagements in their scope (``staff_audit_scope``):

* HQ staff (workplace type listed in "Workplace types whose audit staff see every port", default Head Office)
  and the GM Audit (CAE) see every port;
* staff based at a port (their workplace is a port or sits under one) see that port's audits;
* anyone on an audit's engagement team, or who created it, sees that audit wherever it is;
* staff with no workplace set see only their team's audits.

The rule covers the audit and everything that belongs to it (findings, working papers, reports, review notes,
evidence requests, control tests, remediation raised from its findings). ``audit_scope_guard`` applies it to every
audit and remediation route by resolving the record in the URL to its audit. Configuration > Security >
"Restrict audit staff to their port and teams" switches the rule off (everyone in the Auditor tier sees all).

Auditees only see what concerns them:

* audits they are assigned to (``audit_auditees``) and those audits' findings
  and (non-withdrawn) working papers;
* nonconformances raised against an assigned audit, or owned by them;
* CAPA owned by them, or linked to a nonconformance they can see;
* service feedback owned by them;
* never organizations or stakeholders (internal master data).

Every read endpoint routes through these helpers so the rule lives in one
place. A record an Auditee may not see is reported as 404 (not 403) so the
API does not reveal that it exists.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.enums import Role
from app.platform.users.models import User

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")


def is_privileged(user: User) -> bool:
    """Audit staff or administrators (internal users). Their reach over audits is limited by ``staff_audit_scope``."""
    return user.role in (Role.Admin, Role.Auditor)


def team_audit_ids(db: DBSession, user: User) -> set[int]:
    from app.domains.audit.audits.models import AuditTeamMember

    return set(db.execute(select(AuditTeamMember.audit_id).where(AuditTeamMember.user_id == user.id)).scalars())


def staff_audit_scope(db: DBSession, user: User) -> set[int] | None:
    """Audit ids an Auditor-tier user may work on; ``None`` means every audit."""
    from app.core.appconfig import cfg
    from app.core.enums import ReviewLevel
    from app.core.least_privilege import is_field_auditor
    from app.domains.audit.audits.models import Audit

    if user.role == Role.Admin:
        return None
    if is_field_auditor(user) and cfg("auditor_assigned_only"):
        # Least privilege: an Auditor sees the engagements they are assigned to, nothing port-wide.
        return team_audit_ids(db, user) | set(db.execute(select(Audit.id).where(Audit.created_by == user.id)).scalars())
    if not cfg("port_scope_enforced") or user.review_level == ReviewLevel.CAE:
        return None
    ids = team_audit_ids(db, user)
    ids |= set(db.execute(select(Audit.id).where(Audit.created_by == user.id)).scalars())
    if user.work_entity_id:
        from app.platform.organizations.router import Index

        idx = Index(db)
        home = idx.rows.get(user.work_entity_id)
        port = idx.port_of(home) if home else None
        wide = {c.lower() for c in (cfg("authority_wide_categories") or [])}
        if home is not None and (port or home) and ((port or home).category or "").lower() in wide:
            return None  # based at HQ (or a unit under it): authority-wide view
        if port is not None:
            ids |= set(db.execute(select(Audit.id).where(Audit.port_entity_id == port.id)).scalars())
    return ids


def _audit_of(db: DBSession, record_type: str, record) -> int | None:  # noqa: ANN001
    """The audit a record belongs to (None when it belongs to none)."""
    if record_type == "audit":
        return record.id
    if record_type in ("finding", "working_paper", "nonconformance"):
        return getattr(record, "audit_id", None)
    if record_type == "capa" and getattr(record, "source_type", None) == "finding" and record.source_id:
        from app.domains.audit.audits.models import Finding

        f = db.get(Finding, record.source_id)
        return f.audit_id if f else None
    return None


def _staff_can_view(db: DBSession, user: User, record_type: str, record, scope=...) -> bool:  # noqa: ANN001
    if scope is ...:
        scope = staff_audit_scope(db, user)
    if scope is None:
        return True
    audit_id = _audit_of(db, record_type, record)
    if audit_id is None:
        return True  # not tied to an audit (e.g. an external recommendation): staff-wide record
    return audit_id in scope


def assigned_audit_ids(db: DBSession, user: User) -> set[int]:
    from app.domains.audit.audits.models import AuditAuditee

    rows = db.execute(select(AuditAuditee.audit_id).where(AuditAuditee.user_id == user.id)).scalars().all()
    return set(rows)


def _same_email(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def can_view(db: DBSession, user: User, record_type: str, record) -> bool:  # noqa: ANN001
    """Return True when ``user`` may read ``record`` (an ORM instance)."""
    if user.role == Role.Admin:
        return True
    if record is None:
        return False
    if user.role == Role.Auditor:
        return _staff_can_view(db, user, record_type, record)
    if record_type == "audit":
        return record.id in assigned_audit_ids(db, user)
    if record_type in ("finding", "working_paper"):
        if getattr(record, "is_deleted", False):
            return False
        if record_type == "finding" and not getattr(record, "published", True):
            return False  # unpublished issues are visible to audit staff only (Issue Tracker publish gate)
        return record.audit_id in assigned_audit_ids(db, user)
    if record_type == "nonconformance":
        return _same_email(record.owner_email, user.email) or (
            record.audit_id is not None and record.audit_id in assigned_audit_ids(db, user)
        )
    if record_type == "capa":
        if _same_email(record.owner_email, user.email):
            return True
        if record.linked_nc_id is not None:
            from app.domains.issues.nonconformances.models import Nonconformance

            return can_view(db, user, "nonconformance", db.get(Nonconformance, record.linked_nc_id))
        return False
    if record_type == "service_feedback":
        return _same_email(record.owner_email, user.email)
    return False


def ensure_can_view(db: DBSession, user: User, record_type: str, record) -> None:  # noqa: ANN001
    if record is None or not can_view(db, user, record_type, record):
        raise _NOT_FOUND


def visible(db: DBSession, user: User, record_type: str, items: list) -> list:
    """Filter a list of records down to those ``user`` may read (the scope is worked out once)."""
    if user.role == Role.Admin:
        return items
    if user.role == Role.Auditor:
        scope = staff_audit_scope(db, user)
        if scope is None:
            return items
        return [item for item in items if _staff_can_view(db, user, record_type, item, scope)]
    return [item for item in items if can_view(db, user, record_type, item)]


# Route parameters that identify a record inside an audit, and how to find that audit.
def _resolve_audit(db: DBSession, name: str, value: int) -> int | None:
    from app.domains.audit.audits.models import Finding, WorkingPaper

    if name == "audit_id":
        return value
    if name == "finding_id":
        f = db.get(Finding, value)
        return f.audit_id if f else None
    if name == "paper_id":
        w = db.get(WorkingPaper, value)
        return w.audit_id if w else None
    if name == "report_id":
        from app.domains.audit.reports.models import AuditReport

        r = db.get(AuditReport, value)
        return r.audit_id if r else None
    if name in ("objective_id", "risk_id", "control_id", "test_id", "procedure_id"):
        from app.domains.audit.rcm.models import Control, ControlTest, Objective, Procedure, Risk

        obj_id = None
        if name == "objective_id":
            obj_id = value
        elif name == "procedure_id":
            p = db.get(Procedure, value)
            obj_id = p.objective_id if p else None
        elif name == "risk_id":
            r = db.get(Risk, value)
            obj_id = r.objective_id if r else None
        else:
            c = db.get(Control, value) if name == "control_id" else None
            if name == "test_id":
                t = db.get(ControlTest, value)
                c = db.get(Control, t.control_id) if t else None
            obj_id = c.objective_id if c else None
        o = db.get(Objective, obj_id) if obj_id else None
        return o.audit_id if o else None
    if name == "narrative_id":
        from app.domains.audit.rcm.models import Narrative, Objective

        nar = db.get(Narrative, value)
        o = db.get(Objective, nar.objective_id) if nar else None
        return o.audit_id if o else None
    if name == "note_id":
        from app.domains.audit.methodology.models import ReviewNote

        n = db.get(ReviewNote, value)
        return n.audit_id if n else None
    if name in ("request_id", "file_id"):
        from app.domains.audit.evidence.models import EvidenceFile, EvidenceRequest

        if name == "file_id":
            f = db.get(EvidenceFile, value)
            value = f.request_id if f else 0
        r = db.get(EvidenceRequest, value)
        return r.audit_id if r else None
    if name == "capa_id":
        from app.domains.issues.capa.models import Capa

        c = db.get(Capa, value)
        return _audit_of(db, "capa", c) if c else None
    if name == "nc_id":
        from app.domains.issues.nonconformances.models import Nonconformance

        n = db.get(Nonconformance, value)
        return n.audit_id if n else None
    if name == "entry_id":
        from app.domains.audit.capacity.models import TimeEntry

        t = db.get(TimeEntry, value)
        return t.audit_id if t else None
    return None


def audit_scope_guard(request: Request, db: DBSession = Depends(get_db)) -> None:
    """Router dependency: refuse (404) any audit-related route whose record lies outside the caller's scope.

    Runs before the endpoint, for reads and writes alike, so a record outside scope cannot be read or changed by
    guessing its id. Unauthenticated calls pass through to the endpoint's own sign-in check.
    """
    params = request.path_params
    if not params or request.url.path.startswith("/api/library/"):  # library controls are not audit records
        return
    from app.core.deps import get_current_session

    session = get_current_session(request, db)
    if session is None:
        return
    user = db.get(User, session.user_id)
    if user is None or user.role != Role.Auditor:
        return
    scope = None
    checked = False
    for name, raw in params.items():
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        audit_id = _resolve_audit(db, name, value)
        if audit_id is None:
            continue
        if not checked:
            scope = staff_audit_scope(db, user)
            checked = True
            if scope is None:
                return
        if audit_id not in scope:
            raise _NOT_FOUND


def load_record(db: DBSession, record_type: str, record_id: int):  # noqa: ANN201
    """Load any record by its history ``record_type`` name (None if unknown)."""
    model = _model_for(record_type)
    return db.get(model, record_id) if model is not None else None


def _model_for(record_type: str):  # noqa: ANN202
    from app.domains.assurance.planning.models import AssurancePlan
    from app.domains.audit.audits.models import Audit, Finding, WorkingPaper
    from app.domains.audit.methodology.models import Criterion
    from app.domains.audit.rcm.models import ControlTest
    from app.domains.audit.reports.models import AuditReport
    from app.domains.audit.service_feedback.models import ServiceFeedback
    from app.domains.issues.capa.models import Capa
    from app.domains.issues.nonconformances.models import Nonconformance
    from app.platform.organizations.models import Organization
    from app.platform.stakeholders.models import Stakeholder

    return {
        "audit": Audit,
        "finding": Finding,
        "working_paper": WorkingPaper,
        "capa": Capa,
        "nonconformance": Nonconformance,
        "organization": Organization,
        "service_feedback": ServiceFeedback,
        "stakeholder": Stakeholder,
        "assurance_plan": AssurancePlan,
        "control_test": ControlTest,
        "audit_report": AuditReport,
        "criterion": Criterion,
    }.get(record_type)


def ensure_deletable(
    db: DBSession,
    record_type: str,
    record,  # noqa: ANN001
    *,
    allowed_statuses: tuple[str, ...],
    link_fields: tuple[str, ...] = (),
) -> None:
    """Refuse to hard-delete a record that has progressed or carries evidence.

    A record may only be deleted while it is still in one of
    ``allowed_statuses``, is not linked to other records and has never been
    e-signed. Everything else is retained for the audit trail.
    """
    from sqlalchemy import func

    from app.platform.approvals.models import ApprovalCycle

    current = getattr(record.status, "value", record.status)
    if current not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Records in status '{current}' are retained and cannot be deleted",
        )
    for name in link_fields:
        if getattr(record, name, None) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Linked records are retained and cannot be deleted"
            )
    signed = db.execute(
        select(func.count())
        .select_from(ApprovalCycle)
        .where(ApprovalCycle.record_type == record_type, ApprovalCycle.record_id == record.id)
    ).scalar_one()
    if signed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="E-signed records are retained and cannot be deleted"
        )
