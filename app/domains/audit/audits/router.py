"""Audit routes with a simple status workflow."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, visible
from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier, require_perm, require_role
from app.core.enums import ApprovalStatus, AuditStatus, Role, TestStatus, utcnow
from app.core.history import log_record_history
from app.core.schemas import ESignRequest, MessageOut
from app.domains.audit.audits.models import Audit, AuditAuditee, Finding, WorkingPaper
from app.domains.audit.audits.schemas import AuditCreate, AuditeeAssign, AuditeeOut, AuditOut, AuditUpdate
from app.domains.issues.nonconformances.models import Nonconformance
from app.platform.approvals.models import ApprovalCycle
from app.platform.users.models import User

router = APIRouter(prefix="/api/audits", tags=["audits"])

AdminAudit = Depends(require_module_tier("audits", Role.Admin))
CloseAudit = Depends(require_perm("audit.close"))

WriteAudit = Depends(require_role(Role.Admin, Role.Auditor))

# Status transitions allowed through PATCH (a no-op change is allowed).
# Review -> Closed is deliberately absent: closing an audit is only possible
# through the e-signed ``POST /{id}/close`` route.
_ALLOWED_TRANSITIONS: dict[AuditStatus, set[AuditStatus]] = {
    AuditStatus.Planned: {AuditStatus.InProgress},
    AuditStatus.InProgress: {AuditStatus.Review, AuditStatus.Planned},
    AuditStatus.Review: {AuditStatus.InProgress},
    AuditStatus.Closed: set(),
}


def _check_transition(current: AuditStatus, new: AuditStatus) -> None:
    if new == current:
        return
    if new == AuditStatus.Closed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audits can only be closed by an e-signed sign-off (POST /api/audits/{id}/close)",
        )
    if new not in _ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition: {current.value} -> {new.value}",
        )


@router.get("", response_model=list[AuditOut])
def list_audits(db: DBSession = Depends(get_db), user: User = Depends(require_active_user),
                audit_type: str | None = None, port_id: int | None = None, mine: bool = False) -> list[Audit]:
    stmt = select(Audit).order_by(Audit.created_at.desc())
    if audit_type:
        stmt = stmt.where(Audit.audit_type == audit_type)
    if mine:
        from app.platform.organizations.router import Index

        idx = Index(db)
        home = idx.rows.get(user.work_entity_id) if user.work_entity_id else None
        port = idx.port_of(home) if home else None
        port_id = port.id if port else -1
    if port_id is not None:
        stmt = stmt.where(Audit.port_entity_id == port_id)
    audits = list(db.execute(stmt).scalars().all())
    return visible(db, user, "audit", audits)


def _audit_type(value: str | None) -> str | None:
    from app.core.appconfig import cfg
    from app.core.errors import field_error

    if not value or not value.strip():
        return None
    match = next((t for t in cfg("audit_types") if t.lower() == value.strip().lower()), None)
    if match is None:
        raise field_error("audit_type", f"must be one of: {', '.join(cfg('audit_types'))}")
    return match


def _port(db: DBSession, port_id: int | None) -> int | None:
    from app.core.errors import field_error
    from app.platform.organizations.router import Index

    if port_id is None:
        return None
    idx = Index(db)
    row = idx.rows.get(port_id)
    if row is None or not idx.is_port(row):
        raise field_error("port_entity_id", "is not a port / site entity")
    return port_id


def _home_port(db: DBSession, user: User) -> int | None:
    from app.platform.organizations.router import Index

    if not user.work_entity_id:
        return None
    idx = Index(db)
    home = idx.rows.get(user.work_entity_id)
    port = idx.port_of(home) if home else None
    return port.id if port else None


@router.get("/auditee-candidates", response_model=list[AuditeeOut])
def auditee_candidates(db: DBSession = Depends(get_db), _: User = WriteAudit) -> list[AuditeeOut]:
    """Active Auditee accounts that can be assigned to an audit."""
    users = db.execute(
        select(User).where(User.role == Role.Auditee, User.is_active.is_(True)).order_by(User.username)
    ).scalars()
    return [AuditeeOut(user_id=u.id, username=u.username, full_name=u.full_name, email=u.email) for u in users]


@router.post("", response_model=AuditOut, status_code=status.HTTP_201_CREATED)
def create_audit(
    payload: AuditCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Audit:
    if payload.status != AuditStatus.Planned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New audits must start as Planned")
    from app.core.deps import ensure_perm

    ensure_perm(user, "audit.create")
    audit = Audit(
        title=payload.title,
        description=payload.description,
        scope=payload.scope,
        status=payload.status,
        organization_id=payload.organization_id,
        audit_type=_audit_type(payload.audit_type),
        port_entity_id=_port(db, payload.port_entity_id) if payload.port_entity_id else _home_port(db, user),
        created_by=user.id,
    )
    db.add(audit)
    db.flush()
    log_action(db, user_id=user.id, action=f"AUDIT_CREATE id={audit.id} title={audit.title}", request=request)
    log_record_history(
        db, record_type="audit", record_id=audit.id, user_id=user.id, action="CREATED", request=request
    )
    db.commit()
    db.refresh(audit)
    return audit


@router.get("/{audit_id}", response_model=AuditOut)
def get_audit(audit_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> Audit:
    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    return audit


@router.patch("/{audit_id}", response_model=AuditOut)
def update_audit(
    audit_id: int,
    payload: AuditUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A closed audit cannot be edited")

    changes: list[str] = []
    if payload.title is not None:
        audit.title = payload.title
        changes.append("title")
    if payload.description is not None:
        audit.description = payload.description
        changes.append("description")
    if payload.scope is not None:
        audit.scope = payload.scope
        changes.append("scope")
    if payload.organization_id is not None:
        audit.organization_id = payload.organization_id
        changes.append("organization_id")
    if "audit_type" in payload.model_fields_set:
        audit.audit_type = _audit_type(payload.audit_type)
        changes.append("audit_type")
    if "port_entity_id" in payload.model_fields_set:
        audit.port_entity_id = _port(db, payload.port_entity_id)
        changes.append("port")
    if payload.status is not None:
        _check_transition(audit.status, payload.status)
        if payload.status != audit.status:
            changes.append(f"status={payload.status.value}")
            started = audit.status == AuditStatus.Planned and payload.status == AuditStatus.InProgress
            if started:
                from app.domains.audit.memos.router import ensure_fieldwork_can_start

                ensure_fieldwork_can_start(db, audit)
            audit.status = payload.status
            if started:
                from app.domains.audit.audits.lifecycle import notify_fieldwork_started

                notify_fieldwork_started(db, audit, user)

    log_action(db, user_id=user.id, action=f"AUDIT_UPDATE id={audit.id} [{', '.join(changes)}]", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=audit.id,
        user_id=user.id,
        action=f"UPDATED [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(audit)
    return audit


@router.delete("/{audit_id}", response_model=MessageOut)
def delete_audit(
    audit_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin)),
) -> MessageOut:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    _ensure_deletable(db, audit)
    title = audit.title
    db.delete(audit)
    log_action(db, user_id=user.id, action=f"AUDIT_DELETE id={audit_id} title={title}", request=request)
    db.commit()
    return MessageOut(message=f"Audit {audit_id} deleted")


def _ensure_fieldwork_reviewed(db: DBSession, audit: Audit) -> None:
    """Every control test must be reviewed (or not started) before sign-off."""
    from app.domains.audit.rcm.models import Control, ControlTest, Objective

    pending = db.execute(
        select(ControlTest.ref)
        .join(Control, Control.id == ControlTest.control_id)
        .join(Objective, Objective.id == Control.objective_id)
        .where(
            Objective.audit_id == audit.id,
            ControlTest.status.in_([TestStatus.InProgress, TestStatus.Completed]),
        )
    ).scalars().all()
    if pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Control tests not yet reviewed: {', '.join(pending)}",
        )


def _ensure_deletable(db: DBSession, audit: Audit) -> None:
    """Only an untouched, Planned audit may be deleted - never one with evidence."""
    if audit.status != AuditStatus.Planned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only audits still in Planned status can be deleted"
        )
    checks = (
        (Finding, Finding.audit_id, "findings"),
        (WorkingPaper, WorkingPaper.audit_id, "working papers"),
        (Nonconformance, Nonconformance.audit_id, "nonconformances"),
    )
    for model, column, label in checks:
        if db.execute(select(func.count()).select_from(model).where(column == audit.id)).scalar_one():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=f"Audit has {label} and cannot be deleted"
            )
    signed = db.execute(
        select(func.count())
        .select_from(ApprovalCycle)
        .where(ApprovalCycle.record_type == "audit", ApprovalCycle.record_id == audit.id)
    ).scalar_one()
    if signed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Audit has e-signatures and cannot be deleted")


@router.post("/{audit_id}/in-approval", response_model=AuditOut)
def set_in_approval(
    audit_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    if audit.status != AuditStatus.Review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only audits in Review can be submitted for approval"
        )
    audit.approval_status = ApprovalStatus.InApproval
    log_action(db, user_id=user.id, action=f"AUDIT_IN_APPROVAL id={audit.id}", request=request)
    log_record_history(
        db, record_type="audit", record_id=audit.id, user_id=user.id, action="MOVED TO IN APPROVAL", request=request
    )
    db.commit()
    db.refresh(audit)
    return audit


@router.post("/{audit_id}/close", response_model=AuditOut)
def close_audit(
    audit_id: int,
    payload: ESignRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = CloseAudit,
) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    if audit.status != AuditStatus.Review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only audits in Review can be closed (current status: {audit.status.value})",
        )

    _ensure_fieldwork_reviewed(db, audit)
    from app.domains.audit.audits.lifecycle import ensure_closable

    ensure_closable(db, audit)

    def _on_approve(session: DBSession) -> None:
        audit.status = AuditStatus.Closed
        audit.approval_status = ApprovalStatus.Approved
        if audit.entity_unit_id is not None:
            from app.domains.assurance.planning.models import EntityUnit

            unit = session.get(EntityUnit, audit.entity_unit_id)
            if unit is not None:
                unit.last_audited_at = utcnow()

    sign(
        db,
        record_type="audit",
        record_id=audit.id,
        user=user,
        password=payload.password,
        decision="Approve",
        preparer_id=audit.created_by,
        comment=payload.comment,
        request=request,
        on_approve=_on_approve,
    )
    log_action(db, user_id=user.id, action=f"AUDIT_CLOSE id={audit.id} title={audit.title}", request=request)
    if audit.status == AuditStatus.Closed:
        from app.domains.assurance.qaip.router import invite_survey

        invite_survey(db, audit)
    db.commit()
    db.refresh(audit)
    return audit

# ---------------------------------------------------------------- auditees


def _audit_or_404(db: DBSession, audit_id: int) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


@router.get("/{audit_id}/auditees", response_model=list[AuditeeOut])
def list_auditees(audit_id: int, db: DBSession = Depends(get_db), _: User = WriteAudit) -> list[AuditeeOut]:
    _audit_or_404(db, audit_id)
    rows = db.execute(
        select(AuditAuditee, User)
        .join(User, User.id == AuditAuditee.user_id)
        .where(AuditAuditee.audit_id == audit_id)
        .order_by(User.username)
    ).all()
    return [
        AuditeeOut(
            user_id=u.id, username=u.username, full_name=u.full_name, email=u.email, assigned_at=link.assigned_at
        )
        for link, u in rows
    ]


@router.post("/{audit_id}/auditees", response_model=list[AuditeeOut], status_code=status.HTTP_201_CREATED)
def assign_auditee(
    audit_id: int,
    payload: AuditeeAssign,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteAudit,
) -> list[AuditeeOut]:
    _audit_or_404(db, audit_id)
    target = db.get(User, payload.user_id)
    if target is None or target.role != Role.Auditee:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not an Auditee account")
    if db.get(AuditAuditee, (audit_id, target.id)) is None:
        db.add(AuditAuditee(audit_id=audit_id, user_id=target.id, assigned_by=user.id))
        log_action(db, user_id=user.id, action=f"AUDIT_AUDITEE_ADD audit={audit_id} user={target.id}", request=request)
        log_record_history(
            db,
            record_type="audit",
            record_id=audit_id,
            user_id=user.id,
            action=f"AUDITEE ASSIGNED {target.username}",
            request=request,
        )
        db.commit()
    return list_auditees(audit_id, db, user)


@router.delete("/{audit_id}/auditees/{user_id}", response_model=list[AuditeeOut])
def remove_auditee(
    audit_id: int,
    user_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteAudit,
) -> list[AuditeeOut]:
    _audit_or_404(db, audit_id)
    link = db.get(AuditAuditee, (audit_id, user_id))
    if link is not None:
        db.delete(link)
        log_action(db, user_id=user.id, action=f"AUDIT_AUDITEE_REMOVE audit={audit_id} user={user_id}", request=request)
        log_record_history(
            db,
            record_type="audit",
            record_id=audit_id,
            user_id=user.id,
            action=f"AUDITEE REMOVED user#{user_id}",
            request=request,
        )
        db.commit()
    return list_auditees(audit_id, db, user)
