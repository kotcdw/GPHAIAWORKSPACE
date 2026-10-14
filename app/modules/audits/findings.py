"""Finding routes (nested under an audit)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_role
from app.core.enums import AuditStatus, FindingStatus, Role
from app.core.history import log_record_history
from app.core.schemas import MessageOut
from app.modules.audits.models import Audit, Finding
from app.modules.audits.schemas import FindingCreate, FindingOut, FindingUpdate, ManagementResponse
from app.modules.users.models import User

router = APIRouter(tags=["findings"])


def _get_audit_or_404(db: DBSession, audit_id: int) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


def _ensure_audit_open(audit: Audit) -> None:
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed; findings are locked")


_ISSUE_TEXT = ("criteria", "condition", "cause", "effect", "recommendation")


def _apply_issue_fields(db: DBSession, finding: Finding, payload, audit_id: int) -> list[str]:  # noqa: ANN001
    """Copy the issue attributes (5 Cs, 5 Whys, control link) onto ``finding``."""
    changed: list[str] = []
    for name in _ISSUE_TEXT:
        value = getattr(payload, name, None)
        if value is not None:
            setattr(finding, name, value)
            changed.append(name)
    if payload.root_cause_whys is not None:
        finding.root_cause_whys = json.dumps([w.strip() for w in payload.root_cause_whys if w and w.strip()])
        changed.append("root_cause_whys")
    if payload.control_id is not None:
        from app.modules.rcm.models import Control, Objective

        control = db.get(Control, payload.control_id)
        if control is None or db.get(Objective, control.objective_id).audit_id != audit_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Control does not belong to this audit")
        finding.control_id = control.id
        changed.append("control_id")
    if payload.criterion_id is not None:
        from app.modules.methodology.models import Criterion

        crit = db.get(Criterion, payload.criterion_id)
        if crit is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown criterion")
        finding.criterion_id = crit.id
        changed.append("criterion_id")
    return changed


def _get_finding_or_404(db: DBSession, finding_id: int) -> Finding:
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    return finding


@router.get("/api/audits/{audit_id}/findings", response_model=list[FindingOut])
def list_findings(
    audit_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> list[Finding]:
    ensure_can_view(db, user, "audit", db.get(Audit, audit_id))
    return list(
        db.execute(select(Finding).where(Finding.audit_id == audit_id).order_by(Finding.created_at.desc()))
        .scalars()
        .all()
    )


@router.post(
    "/api/audits/{audit_id}/findings",
    response_model=FindingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_finding(
    audit_id: int,
    payload: FindingCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Finding:
    _ensure_audit_open(_get_audit_or_404(db, audit_id))
    finding = Finding(
        audit_id=audit_id,
        title=payload.title,
        description=payload.description,
        risk_rating=payload.risk_rating,
        status=payload.status,
        assigned_owner_email=str(payload.assigned_owner_email) if payload.assigned_owner_email else None,
        created_by=user.id,
    )
    _apply_issue_fields(db, finding, payload, audit_id)
    db.add(finding)
    db.flush()
    log_action(
        db,
        user_id=user.id,
        action=f"FINDING_CREATE id={finding.id} audit={audit_id} risk={finding.risk_rating.value}",
        request=request,
    )
    log_record_history(
        db,
        record_type="audit",
        record_id=audit_id,
        user_id=user.id,
        action=f"FINDING ADDED #{finding.id} {finding.title}",
        request=request,
    )
    db.commit()
    db.refresh(finding)
    return finding


@router.get("/api/findings/{finding_id}", response_model=FindingOut)
def get_finding(
    finding_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> Finding:
    finding = db.get(Finding, finding_id)
    ensure_can_view(db, user, "finding", finding)
    return finding


@router.patch("/api/findings/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: int,
    payload: FindingUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Finding:
    finding = _get_finding_or_404(db, finding_id)
    _ensure_audit_open(_get_audit_or_404(db, finding.audit_id))
    changes: list[str] = []
    if payload.title is not None:
        finding.title = payload.title
        changes.append("title")
    if payload.description is not None:
        finding.description = payload.description
        changes.append("description")
    if payload.risk_rating is not None:
        finding.risk_rating = payload.risk_rating
        changes.append(f"risk_rating={payload.risk_rating.value}")
    if payload.status is not None:
        finding.status = payload.status
        changes.append(f"status={payload.status.value}")
    if payload.assigned_owner_email is not None:
        finding.assigned_owner_email = str(payload.assigned_owner_email)
        changes.append("assigned_owner_email")
    changes.extend(_apply_issue_fields(db, finding, payload, finding.audit_id))

    log_action(db, user_id=user.id, action=f"FINDING_UPDATE id={finding.id} [{', '.join(changes)}]", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=finding.audit_id,
        user_id=user.id,
        action=f"FINDING UPDATED #{finding.id} [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(finding)
    return finding


@router.delete("/api/findings/{finding_id}", response_model=MessageOut)
def delete_finding(
    finding_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin)),
) -> MessageOut:
    finding = _get_finding_or_404(db, finding_id)
    _ensure_audit_open(_get_audit_or_404(db, finding.audit_id))
    if finding.status != FindingStatus.Open:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only Open findings can be deleted; findings under remediation or closed are retained",
        )
    audit_id, title = finding.audit_id, finding.title
    db.delete(finding)
    log_action(db, user_id=user.id, action=f"FINDING_DELETE id={finding_id} title={title}", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=audit_id,
        user_id=user.id,
        action=f"FINDING DELETED #{finding_id} {title}",
        request=request,
    )
    db.commit()
    return MessageOut(message=f"Finding {finding_id} deleted")

@router.post("/api/findings/{finding_id}/response", response_model=FindingOut)
def respond_to_finding(
    finding_id: int,
    payload: ManagementResponse,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> Finding:
    """Management response to an issue - typically entered by the auditee."""
    finding = db.get(Finding, finding_id)
    ensure_can_view(db, user, "finding", finding)
    _ensure_audit_open(_get_audit_or_404(db, finding.audit_id))
    finding.management_response = payload.management_response
    log_action(db, user_id=user.id, action=f"FINDING_RESPONSE id={finding.id}", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=finding.audit_id,
        user_id=user.id,
        action=f"MANAGEMENT RESPONSE on finding #{finding.id} by {user.username}",
        request=request,
    )
    db.commit()
    db.refresh(finding)
    return finding
