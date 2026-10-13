"""CAPA routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, ensure_deletable, visible
from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier
from app.core.enums import CapaStatus, NCStatus, Role, Severity
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import ESignRequest, MessageOut
from app.core.tasksvc import auto_task_for_record
from app.modules.capa.models import Capa
from app.modules.capa.schemas import CapaCreate, CapaLink, CapaList, CapaOut, CapaUpdate
from app.modules.nonconformances.models import Nonconformance
from app.modules.users.models import User

router = APIRouter(prefix="/api/capa", tags=["capa"])

WriteCapa = Depends(require_module_tier("capa", Role.Admin, Role.Auditor))
AdminCapa = Depends(require_module_tier("capa", Role.Admin))
_CLOSE_VIA_ESIGN = "CAPA can only be closed by an e-signed sign-off (POST /api/capa/{id}/close)"


def _get_or_404(db: DBSession, capa_id: int) -> Capa:
    capa = db.get(Capa, capa_id)
    if capa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CAPA not found")
    return capa


@router.get("", response_model=CapaList)
def list_capa(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    q: str | None = Query(default=None),
    status_filter: CapaStatus | None = Query(default=None, alias="status"),
    severity: Severity | None = Query(default=None),
) -> CapaList:
    stmt = select(Capa).order_by(Capa.id.desc())
    if q:
        stmt = stmt.where(func.lower(Capa.title).like(f"%{q.lower()}%"))
    if status_filter is not None:
        stmt = stmt.where(Capa.status == status_filter)
    if severity is not None:
        stmt = stmt.where(Capa.severity == severity)
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
        capa_ref=next_reference(db, "CAPA"),
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
        due_date=payload.due_date,
        linked_nc_id=payload.linked_nc_id,
        created_by=user.id,
    )
    db.add(capa)
    db.flush()
    if capa.linked_nc_id is not None:
        nc = db.get(Nonconformance, capa.linked_nc_id)
        if nc is not None:
            nc.linked_capa_id = capa.id
    auto_task_for_record(db, record_type="capa", record=capa, action="Action CAPA", assignor_id=user.id)
    log_action(db, user_id=user.id, action=f"CAPA_CREATE id={capa.id} ref={capa.capa_ref}", request=request)
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A closed CAPA cannot be edited")
    if payload.status == CapaStatus.Closed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_CLOSE_VIA_ESIGN)
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
        "due_date",
        "linked_nc_id",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(capa, field, value)
            changes.append(field)
    log_action(db, user_id=user.id, action=f"CAPA_UPDATE id={capa.id} [{', '.join(changes)}]", request=request)
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
    log_action(db, user_id=user.id, action=f"CAPA_DELETE id={capa_id} ref={ref}", request=request)
    db.commit()
    return MessageOut(message=f"CAPA {ref} deleted")


@router.post("/{capa_id}/copy", response_model=CapaOut, status_code=status.HTTP_201_CREATED)
def copy_capa(capa_id: int, request: Request, db: DBSession = Depends(get_db), user: User = WriteCapa) -> Capa:
    source = _get_or_404(db, capa_id)
    copy = Capa(
        capa_ref=next_reference(db, "CAPA"),
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
        created_by=user.id,
    )
    db.add(copy)
    db.flush()
    log_action(
        db, user_id=user.id, action=f"CAPA_COPY from={source.id} to={copy.id} ref={copy.capa_ref}", request=request
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
    log_action(db, user_id=user.id, action=f"CAPA_LINK_NC capa={capa.id} nc={nc.id}", request=request)
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
    user: User = AdminCapa,
) -> Capa:
    capa = _get_or_404(db, capa_id)
    if capa.status != CapaStatus.Review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only CAPA in Review can be closed (current status: {capa.status.value})",
        )

    def _on_approve(session: DBSession) -> None:
        capa.status = CapaStatus.Closed
        capa.closed_by = user.id
        capa.closed_at = datetime.now(UTC).replace(tzinfo=None)
        if capa.linked_nc_id is not None:
            nc = db.get(Nonconformance, capa.linked_nc_id)
            if nc is not None:
                nc.status = NCStatus.Closed

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
    log_action(db, user_id=user.id, action=f"CAPA_CLOSE id={capa.id} ref={capa.capa_ref}", request=request)
    db.commit()
    db.refresh(capa)
    return capa