"""Record-level access rules (who may *see* what).

Admins and Auditors see every record. Auditees only see what concerns them:

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

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import Role
from app.modules.users.models import User

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")


def is_privileged(user: User) -> bool:
    return user.role in (Role.Admin, Role.Auditor)


def assigned_audit_ids(db: DBSession, user: User) -> set[int]:
    from app.modules.audits.models import AuditAuditee

    rows = db.execute(select(AuditAuditee.audit_id).where(AuditAuditee.user_id == user.id)).scalars().all()
    return set(rows)


def _same_email(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def can_view(db: DBSession, user: User, record_type: str, record) -> bool:  # noqa: ANN001
    """Return True when ``user`` may read ``record`` (an ORM instance)."""
    if is_privileged(user):
        return True
    if record is None:
        return False
    if record_type == "audit":
        return record.id in assigned_audit_ids(db, user)
    if record_type in ("finding", "working_paper"):
        if getattr(record, "is_deleted", False):
            return False
        return record.audit_id in assigned_audit_ids(db, user)
    if record_type == "nonconformance":
        return _same_email(record.owner_email, user.email) or (
            record.audit_id is not None and record.audit_id in assigned_audit_ids(db, user)
        )
    if record_type == "capa":
        if _same_email(record.owner_email, user.email):
            return True
        if record.linked_nc_id is not None:
            from app.modules.nonconformances.models import Nonconformance

            return can_view(db, user, "nonconformance", db.get(Nonconformance, record.linked_nc_id))
        return False
    if record_type == "service_feedback":
        return _same_email(record.owner_email, user.email)
    return False


def ensure_can_view(db: DBSession, user: User, record_type: str, record) -> None:  # noqa: ANN001
    if record is None or not can_view(db, user, record_type, record):
        raise _NOT_FOUND


def visible(db: DBSession, user: User, record_type: str, items: list) -> list:
    """Filter a list of records down to those ``user`` may read."""
    if is_privileged(user):
        return items
    return [item for item in items if can_view(db, user, record_type, item)]


def load_record(db: DBSession, record_type: str, record_id: int):  # noqa: ANN201
    """Load any record by its history ``record_type`` name (None if unknown)."""
    model = _model_for(record_type)
    return db.get(model, record_id) if model is not None else None


def _model_for(record_type: str):  # noqa: ANN202
    from app.modules.audits.models import Audit, Finding, WorkingPaper
    from app.modules.capa.models import Capa
    from app.modules.methodology.models import Criterion
    from app.modules.nonconformances.models import Nonconformance
    from app.modules.organizations.models import Organization
    from app.modules.planning.models import AssurancePlan
    from app.modules.rcm.models import ControlTest
    from app.modules.reports.models import AuditReport
    from app.modules.service_feedback.models import ServiceFeedback
    from app.modules.stakeholders.models import Stakeholder

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

    from app.modules.approvals.models import ApprovalCycle

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
