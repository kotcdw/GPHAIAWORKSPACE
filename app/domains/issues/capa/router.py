"""CAPA routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, ensure_deletable, visible
from app.core.appconfig import cfg
from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier
from app.core.enums import CapaStatus, NCStatus, Role, Severity, ValidationResult, utcnow
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import ESignRequest, MessageOut
from app.core.tasksvc import auto_task_for_record
from app.domains.audit.audits.lifecycle import default_due_date
from app.domains.issues.capa.models import Capa
from app.domains.issues.capa.schemas import CapaCreate, CapaLink, CapaList, CapaOut, CapaUpdate
from app.domains.issues.capa.status import FULLY, IMPLEMENTATION_STATUSES, is_internal
from app.domains.issues.capa.timeline import add_event, change_due_date
from app.domains.issues.nonconformances.models import Nonconformance
from app.platform.users.models import User

router = APIRouter(prefix="/api/capa", tags=["capa"])

WriteCapa = Depends(require_module_tier("capa", Role.Admin, Role.Auditor))
AdminCapa = Depends(require_module_tier("capa", Role.Admin))
_CLOSE_VIA_ESIGN = "A remediation can only be closed by an e-signed sign-off (POST /api/capa/{id}/close)"
_FOLLOWUP_FIELDS = ("timeframe", "source_body", "source_reference", "source_year", "followup_comment",
                    "external_closure_ref")


def _apply_followup_fields(db: DBSession, capa: Capa, payload: CapaCreate | CapaUpdate, changes: list[str]) -> None:
    """Source of the recommendation, timeframe, IAU comment and admin-defined custom fields."""
    sent = payload.model_fields_set
    if "source_body" in sent and payload.source_body:
        if payload.source_body not in (cfg("recommendation_sources") or []):
            raise field_error("source_body", "choose one of the configured sources")
    if "timeframe" in sent and payload.timeframe:
        if payload.timeframe not in (cfg("action_timeframes") or []):
            raise field_error("timeframe", "choose one of the configured timeframes")
    for name in _FOLLOWUP_FIELDS:
        if name in sent:
            value = getattr(payload, name)
            setattr(capa, name, value.strip() if isinstance(value, str) else value)
            changes.append(name)
    if "custom_fields" in sent:
        from app.platform.customfields.router import clean_values

        capa.custom_fields = json.dumps(clean_values(db, "capa", payload.custom_fields,
                                                     json.loads(capa.custom_fields or "{}")))
        changes.append("custom fields")


def _get_or_404(db: DBSession, capa_id: int) -> Capa:
    capa = db.get(Capa, capa_id)
    if capa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remediation not found")
    return capa


@router.get("", response_model=CapaList)
def list_capa(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    q: str | None = Query(default=None),
    status_filter: CapaStatus | None = Query(default=None, alias="status"),
    severity: Severity | None = Query(default=None),
    source_body: str | None = Query(default=None),
    implementation_status: str | None = Query(default=None),
) -> CapaList:
    stmt = select(Capa).order_by(Capa.id.desc())
    if q:
        stmt = stmt.where(func.lower(Capa.title).like(f"%{q.lower()}%"))
    if status_filter is not None:
        stmt = stmt.where(Capa.status == status_filter)
    if severity is not None:
        stmt = stmt.where(Capa.severity == severity)
    if source_body:
        stmt = stmt.where(Capa.source_body == source_body)
    if implementation_status in IMPLEMENTATION_STATUSES:
        stmt = stmt.where(Capa.implementation_status == implementation_status)
    items = visible(db, user, "capa", list(db.execute(stmt).scalars().all()))
    return CapaList(total=len(items), items=[CapaOut.model_validate(c) for c in items])


@router.post("", response_model=CapaOut, status_code=status.HTTP_201_CREATED)
def create_capa(
    payload: CapaCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteCapa,
) -> Capa:
    if payload.status == CapaStatus.Closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_CLOSE_VIA_ESIGN)
    capa = Capa(
        capa_ref=next_reference(db, "REM"),
        title=payload.title,
        description=payload.description,
        root_cause=payload.root_cause,
        corrective_action=payload.corrective_action,
        preventive_action=payload.preventive_action,
        effectiveness_check=payload.effectiveness_check,
        severity=payload.severity,
        disposition=payload.disposition,
        status=payload.status,
        owner_email=payload.owner_email,
        due_date=payload.due_date or default_due_date(payload.severity),
        linked_nc_id=payload.linked_nc_id,
        extension_count=0,
        custom_fields="{}",
        source_year=utcnow().year,
        created_by=user.id,
    )
    _apply_followup_fields(db, capa, payload, [])
    capa.original_due_date = capa.due_date
    if not capa.source_body:
        capa.source_body = (cfg("recommendation_sources") or ["Internal Audit"])[0]
    db.add(capa)
    db.flush()
    from app.platform.automations.engine import capa_context, emit

    emit(db, "action.created", "capa", capa.id, capa_context(db, capa))
    if capa.linked_nc_id is not None:
        nc = db.get(Nonconformance, capa.linked_nc_id)
        if nc is not None:
            nc.linked_capa_id = capa.id
    auto_task_for_record(db, record_type="capa", record=capa, action="Action remediation", assignor_id=user.id)
    add_event(db, capa, "created", user_id=user.id, request=request,
              text=f"Action raised; target date {capa.due_date:%d %b %Y}" if capa.due_date else "Action raised")
    log_action(db, user_id=user.id, action=f"REMEDIATION_CREATE id={capa.id} ref={capa.capa_ref}", request=request)
    log_record_history(
        db, record_type="capa", record_id=capa.id, user_id=user.id, action="CREATED", request=request
    )
    db.commit()
    db.refresh(capa)
    return capa


@router.get("/{capa_id}", response_model=CapaOut)
def get_capa(capa_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> Capa:
    capa = db.get(Capa, capa_id)
    ensure_can_view(db, user, "capa", capa)
    return capa


@router.patch("/{capa_id}", response_model=CapaOut)
def update_capa(
    capa_id: int,
    payload: CapaUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteCapa,
) -> Capa:
    capa = _get_or_404(db, capa_id)
    if capa.status == CapaStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A closed remediation cannot be edited; reopen it first")
    if payload.status == CapaStatus.Closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_CLOSE_VIA_ESIGN)
    # The follow-up workflow owns Review and Closed: implementation is recorded (-> Review), an auditor validates
    # it (-> In Progress if not effective) and an e-signature closes it.
    if payload.status is not None and payload.status != capa.status:
        if payload.status == CapaStatus.Review:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="An action goes to Review when its implementation is recorded "
                                       "(Record implementation), not by changing the status")
        if capa.status == CapaStatus.Review:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="The action is awaiting validation; an auditor validates it as Effective "
                                       "or Not effective")
    changes: list[str] = []
    for field in (
        "title",
        "description",
        "root_cause",
        "corrective_action",
        "preventive_action",
        "effectiveness_check",
        "severity",
        "disposition",
        "status",
        "owner_email",
        "linked_nc_id",
    ):
        value = getattr(payload, field)
        if value is not None and value != getattr(capa, field):
            setattr(capa, field, value)
            changes.append(field)
    if payload.due_date is not None and (capa.due_date is None or payload.due_date.date() != capa.due_date.date()):
        # Revising an agreed target date is an extension: it needs the follow-up manager and a reason.
        from app.core.deps import ensure_perm

        if capa.due_date is not None:
            ensure_perm(user, "followup.manage")
        if change_due_date(db, capa, payload.due_date, reason=payload.due_date_reason or "", user_id=user.id,
                           request=request):
            changes.append("due_date")
    _apply_followup_fields(db, capa, payload, changes)
    log_action(db, user_id=user.id, action=f"REMEDIATION_UPDATE id={capa.id} [{', '.join(changes)}]", request=request)
    log_record_history(
        db,
        record_type="capa",
        record_id=capa.id,
        user_id=user.id,
        action=f"UPDATED [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(capa)
    return capa


@router.delete("/{capa_id}", response_model=MessageOut)
def delete_capa(capa_id: int, request: Request, db: DBSession = Depends(get_db), user: User = AdminCapa) -> MessageOut:
    capa = _get_or_404(db, capa_id)
    ensure_deletable(db, "capa", capa, allowed_statuses=("Open",), link_fields=("linked_nc_id",))
    ref = capa.capa_ref
    db.delete(capa)
    log_record_history(db, record_type="capa", record_id=capa_id, user_id=user.id, action=f"DELETED {ref}")
    log_action(db, user_id=user.id, action=f"REMEDIATION_DELETE id={capa_id} ref={ref}", request=request)
    db.commit()
    return MessageOut(message=f"Remediation {ref} deleted")


@router.post("/{capa_id}/copy", response_model=CapaOut, status_code=status.HTTP_201_CREATED)
def copy_capa(capa_id: int, request: Request, db: DBSession = Depends(get_db), user: User = WriteCapa) -> Capa:
    source = _get_or_404(db, capa_id)
    copy = Capa(
        capa_ref=next_reference(db, "REM"),
        title=f"{source.title} (Copy)",
        description=source.description,
        root_cause=source.root_cause,
        corrective_action=source.corrective_action,
        preventive_action=source.preventive_action,
        effectiveness_check=source.effectiveness_check,
        severity=source.severity,
        disposition=source.disposition,
        status=CapaStatus.Open,
        owner_email=source.owner_email,
        due_date=source.due_date,
        timeframe=source.timeframe,
        source_body=source.source_body,
        source_reference=source.source_reference,
        source_year=source.source_year,
        custom_fields=source.custom_fields or "{}",
        created_by=user.id,
    )
    db.add(copy)
    db.flush()
    log_action(
        db, user_id=user.id, request=request,
        action=f"REMEDIATION_COPY from={source.id} to={copy.id} ref={copy.capa_ref}",
    )
    log_record_history(
        db,
        record_type="capa",
        record_id=copy.id,
        user_id=user.id,
        action=f"COPIED from {source.capa_ref}",
        request=request,
    )
    db.commit()
    db.refresh(copy)
    return copy


@router.post("/{capa_id}/link-nc", response_model=CapaOut)
def link_nc(
    capa_id: int,
    payload: CapaLink,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteCapa,
) -> Capa:
    capa = _get_or_404(db, capa_id)
    nc = db.get(Nonconformance, payload.nc_id)
    if nc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nonconformance not found")
    capa.linked_nc_id = nc.id
    nc.linked_capa_id = capa.id
    if nc.status == NCStatus.Open:
        nc.status = NCStatus.Remediating
    log_action(db, user_id=user.id, action=f"REMEDIATION_LINK_NC capa={capa.id} nc={nc.id}", request=request)
    log_record_history(
        db,
        record_type="capa",
        record_id=capa.id,
        user_id=user.id,
        action=f"LINKED NC {nc.nc_ref}",
        request=request,
    )
    db.commit()
    db.refresh(capa)
    return capa


@router.post("/{capa_id}/close", response_model=CapaOut)
def close_capa(
    capa_id: int,
    payload: ESignRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteCapa,
) -> Capa:
    from app.core.deps import ensure_perm

    # Closing is an audit sign-off: the follow-up manager (Audit Manager / CAE), not the system administrator.
    ensure_perm(user, "followup.manage")
    capa = _get_or_404(db, capa_id)
    if capa.status != CapaStatus.Review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only a remediation in Review can be closed (current status: {capa.status.value})",
        )
    if capa.validation_result != ValidationResult.Effective:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An auditor must validate the implementation as Effective before the action can be closed",
        )
    if not is_internal(capa) and not (capa.external_closure_ref or "").strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Recommendations from {capa.source_body} are closed by that body. Record its "
                                   "closure reference (e.g. the Auditor-General's letter) before closing.")

    def _on_approve(session: DBSession) -> None:
        from app.domains.issues.followup.actions import drop_pending_risk_acceptance

        drop_pending_risk_acceptance(session, capa, user.id, request)
        capa.status = CapaStatus.Closed
        capa.implementation_status = FULLY
        capa.closed_by = user.id
        capa.closed_at = datetime.now(UTC).replace(tzinfo=None)
        add_event(session, capa, "closed", user_id=user.id, request=request,
                  text="Closed with an e-signature" + (f": {payload.comment}" if payload.comment else ""))
        if capa.linked_nc_id is not None:
            nc = db.get(Nonconformance, capa.linked_nc_id)
            if nc is not None:
                nc.status = NCStatus.Closed
        if capa.source_type == "finding":
            from app.domains.issues.capa.closure import sync_finding

            db.flush()
            sync_finding(db, capa.source_id, user.id, request)

    sign(
        db,
        record_type="capa",
        record_id=capa.id,
        user=user,
        preparer_id=capa.created_by,
        password=payload.password,
        decision="Approve",
        comment=payload.comment,
        request=request,
        on_approve=_on_approve,
    )
    log_action(db, user_id=user.id, action=f"REMEDIATION_CLOSE id={capa.id} ref={capa.capa_ref}", request=request)
    db.commit()
    db.refresh(capa)
    return capa