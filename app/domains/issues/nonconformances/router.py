"""Nonconformance routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, ensure_deletable, visible
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier
from app.core.enums import NCStatus, Role, Severity
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import MessageOut
from app.core.tasksvc import auto_task_for_record
from app.domains.issues.capa.models import Capa
from app.domains.issues.nonconformances.models import Nonconformance
from app.domains.issues.nonconformances.schemas import NCCreate, NCLink, NCList, NCOut, NCUpdate
from app.platform.users.models import User

router = APIRouter(prefix="/api/nonconformances", tags=["nonconformances"])

WriteNC = Depends(require_module_tier("nonconformances", Role.Admin, Role.Auditor))
AdminNC = Depends(require_module_tier("nonconformances", Role.Admin))


def _get_or_404(db: DBSession, nc_id: int) -> Nonconformance:
    nc = db.get(Nonconformance, nc_id)
    if nc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nonconformance not found")
    return nc


@router.get("", response_model=NCList)
def list_ncs(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    q: str | None = Query(default=None),
    status_filter: NCStatus | None = Query(default=None, alias="status"),
    severity: Severity | None = Query(default=None),
    audit_id: int | None = Query(default=None),
) -> NCList:
    stmt = select(Nonconformance).order_by(Nonconformance.id.desc())
    if q:
        stmt = stmt.where(func.lower(Nonconformance.title).like(f"%{q.lower()}%"))
    if status_filter is not None:
        stmt = stmt.where(Nonconformance.status == status_filter)
    if severity is not None:
        stmt = stmt.where(Nonconformance.severity == severity)
    if audit_id is not None:
        stmt = stmt.where(Nonconformance.audit_id == audit_id)
    items = visible(db, user, "nonconformance", list(db.execute(stmt).scalars().all()))
    return NCList(total=len(items), items=[NCOut.model_validate(n) for n in items])


@router.post("", response_model=NCOut, status_code=status.HTTP_201_CREATED)
def create_nc(
    payload: NCCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteNC,
) -> Nonconformance:
    nc = Nonconformance(
        nc_ref=next_reference(db, "NC"),
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        disposition=payload.disposition,
        status=payload.status,
        owner_email=payload.owner_email,
        audit_id=payload.audit_id,
        created_by=user.id,
    )
    db.add(nc)
    db.flush()
    auto_task_for_record(
        db, record_type="nonconformance", record=nc, action="Review nonconformance", assignor_id=user.id
    )
    log_action(db, user_id=user.id, action=f"NC_CREATE id={nc.id} ref={nc.nc_ref}", request=request)
    log_record_history(
        db, record_type="nonconformance", record_id=nc.id, user_id=user.id, action="CREATED", request=request
    )
    db.commit()
    db.refresh(nc)
    return nc


@router.get("/{nc_id}", response_model=NCOut)
def get_nc(
    nc_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> Nonconformance:
    nc = db.get(Nonconformance, nc_id)
    ensure_can_view(db, user, "nonconformance", nc)
    return nc


@router.patch("/{nc_id}", response_model=NCOut)
def update_nc(
    nc_id: int,
    payload: NCUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteNC,
) -> Nonconformance:
    nc = _get_or_404(db, nc_id)
    changes: list[str] = []
    for field in ("title", "description", "severity", "disposition", "status", "owner_email", "audit_id"):
        value = getattr(payload, field)
        if value is not None:
            setattr(nc, field, value)
            changes.append(field)
    log_action(db, user_id=user.id, action=f"NC_UPDATE id={nc.id} [{', '.join(changes)}]", request=request)
    log_record_history(
        db,
        record_type="nonconformance",
        record_id=nc.id,
        user_id=user.id,
        action=f"UPDATED [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(nc)
    return nc


@router.delete("/{nc_id}", response_model=MessageOut)
def delete_nc(nc_id: int, request: Request, db: DBSession = Depends(get_db), user: User = AdminNC) -> MessageOut:
    nc = _get_or_404(db, nc_id)
    ensure_deletable(db, "nonconformance", nc, allowed_statuses=("Open",), link_fields=("linked_capa_id",))
    ref = nc.nc_ref
    db.delete(nc)
    log_record_history(db, record_type="nonconformance", record_id=nc_id, user_id=user.id, action=f"DELETED {ref}")
    log_action(db, user_id=user.id, action=f"NC_DELETE id={nc_id} ref={ref}", request=request)
    db.commit()
    return MessageOut(message=f"Nonconformance {ref} deleted")


@router.post("/{nc_id}/copy", response_model=NCOut, status_code=status.HTTP_201_CREATED)
def copy_nc(nc_id: int, request: Request, db: DBSession = Depends(get_db), user: User = WriteNC) -> Nonconformance:
    source = _get_or_404(db, nc_id)
    copy = Nonconformance(
        nc_ref=next_reference(db, "NC"),
        title=f"{source.title} (Copy)",
        description=source.description,
        severity=source.severity,
        disposition=source.disposition,
        status=NCStatus.Open,
        owner_email=source.owner_email,
        audit_id=source.audit_id,
        created_by=user.id,
    )
    db.add(copy)
    db.flush()
    log_action(db, user_id=user.id, action=f"NC_COPY from={source.id} to={copy.id} ref={copy.nc_ref}", request=request)
    log_record_history(
        db,
        record_type="nonconformance",
        record_id=copy.id,
        user_id=user.id,
        action=f"COPIED from {source.nc_ref}",
        request=request,
    )
    db.commit()
    db.refresh(copy)
    return copy


@router.post("/{nc_id}/link-capa", response_model=NCOut)
def link_capa(
    nc_id: int,
    payload: NCLink,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteNC,
) -> Nonconformance:
    nc = _get_or_404(db, nc_id)
    capa = db.get(Capa, payload.capa_id)
    if capa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remediation not found")
    nc.linked_capa_id = capa.id
    capa.linked_nc_id = nc.id
    if nc.status == NCStatus.Open:
        nc.status = NCStatus.Remediating
    log_action(db, user_id=user.id, action=f"NC_LINK_REMEDIATION nc={nc.id} capa={capa.id}", request=request)
    log_record_history(
        db,
        record_type="nonconformance",
        record_id=nc.id,
        user_id=user.id,
        action=f"LINKED REMEDIATION {capa.capa_ref}",
        request=request,
    )
    db.commit()
    db.refresh(nc)
    return nc