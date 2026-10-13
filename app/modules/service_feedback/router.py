"""Service feedback routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, ensure_deletable, visible
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier
from app.core.enums import FeedbackStatus, Role
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import MessageOut
from app.core.tasksvc import auto_task_for_record
from app.modules.capa.models import Capa
from app.modules.nonconformances.models import Nonconformance
from app.modules.service_feedback.models import ServiceFeedback
from app.modules.service_feedback.schemas import SFCreate, SFLink, SFList, SFOut, SFUpdate
from app.modules.users.models import User

router = APIRouter(prefix="/api/service-feedback", tags=["service-feedback"])

WriteSF = Depends(require_module_tier("service_feedback", Role.Admin, Role.Auditor))
AdminSF = Depends(require_module_tier("service_feedback", Role.Admin))


def _get_or_404(db: DBSession, sf_id: int) -> ServiceFeedback:
    sf = db.get(ServiceFeedback, sf_id)
    if sf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service feedback not found")
    return sf


@router.get("", response_model=SFList)
def list_sf(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    q: str | None = Query(default=None),
    status_filter: FeedbackStatus | None = Query(default=None, alias="status"),
) -> SFList:
    stmt = select(ServiceFeedback).order_by(ServiceFeedback.id.desc())
    if q:
        stmt = stmt.where(func.lower(ServiceFeedback.subject).like(f"%{q.lower()}%"))
    if status_filter is not None:
        stmt = stmt.where(ServiceFeedback.status == status_filter)
    items = visible(db, user, "service_feedback", list(db.execute(stmt).scalars().all()))
    return SFList(total=len(items), items=[SFOut.model_validate(s) for s in items])


@router.post("", response_model=SFOut, status_code=status.HTTP_201_CREATED)
def create_sf(
    payload: SFCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteSF,
) -> ServiceFeedback:
    sf = ServiceFeedback(
        sf_ref=next_reference(db, "SF"),
        subject=payload.subject,
        description=payload.description,
        source=payload.source,
        status=payload.status,
        owner_email=payload.owner_email,
        created_by=user.id,
    )
    if payload.received_date is not None:
        sf.received_date = payload.received_date
    db.add(sf)
    db.flush()
    auto_task_for_record(db, record_type="service_feedback", record=sf, action="Handle feedback", assignor_id=user.id)
    log_action(db, user_id=user.id, action=f"SF_CREATE id={sf.id} ref={sf.sf_ref}", request=request)
    log_record_history(
        db, record_type="service_feedback", record_id=sf.id, user_id=user.id, action="CREATED", request=request
    )
    db.commit()
    db.refresh(sf)
    return sf


@router.get("/{sf_id}", response_model=SFOut)
def get_sf(
    sf_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> ServiceFeedback:
    sf = db.get(ServiceFeedback, sf_id)
    ensure_can_view(db, user, "service_feedback", sf)
    return sf


@router.patch("/{sf_id}", response_model=SFOut)
def update_sf(
    sf_id: int,
    payload: SFUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteSF,
) -> ServiceFeedback:
    sf = _get_or_404(db, sf_id)
    changes: list[str] = []
    for field in ("subject", "description", "source", "received_date", "status", "owner_email"):
        value = getattr(payload, field)
        if value is not None:
            setattr(sf, field, value)
            changes.append(field)
    log_action(db, user_id=user.id, action=f"SF_UPDATE id={sf.id} [{', '.join(changes)}]", request=request)
    log_record_history(
        db,
        record_type="service_feedback",
        record_id=sf.id,
        user_id=user.id,
        action=f"UPDATED [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(sf)
    return sf


@router.delete("/{sf_id}", response_model=MessageOut)
def delete_sf(sf_id: int, request: Request, db: DBSession = Depends(get_db), user: User = AdminSF) -> MessageOut:
    sf = _get_or_404(db, sf_id)
    ensure_deletable(
        db, "service_feedback", sf, allowed_statuses=("Open",), link_fields=("linked_nc_id", "linked_capa_id")
    )
    ref = sf.sf_ref
    db.delete(sf)
    log_record_history(db, record_type="service_feedback", record_id=sf_id, user_id=user.id, action=f"DELETED {ref}")
    log_action(db, user_id=user.id, action=f"SF_DELETE id={sf_id} ref={ref}", request=request)
    db.commit()
    return MessageOut(message=f"Service feedback {ref} deleted")


@router.post("/{sf_id}/copy", response_model=SFOut, status_code=status.HTTP_201_CREATED)
def copy_sf(sf_id: int, request: Request, db: DBSession = Depends(get_db), user: User = WriteSF) -> ServiceFeedback:
    source = _get_or_404(db, sf_id)
    copy = ServiceFeedback(
        sf_ref=next_reference(db, "SF"),
        subject=f"{source.subject} (Copy)",
        description=source.description,
        source=source.source,
        received_date=source.received_date,
        status=FeedbackStatus.Open,
        owner_email=source.owner_email,
        created_by=user.id,
    )
    db.add(copy)
    db.flush()
    log_action(db, user_id=user.id, action=f"SF_COPY from={source.id} to={copy.id} ref={copy.sf_ref}", request=request)
    log_record_history(
        db,
        record_type="service_feedback",
        record_id=copy.id,
        user_id=user.id,
        action=f"COPIED from {source.sf_ref}",
        request=request,
    )
    db.commit()
    db.refresh(copy)
    return copy


@router.post("/{sf_id}/link", response_model=SFOut)
def link_sf(
    sf_id: int,
    payload: SFLink,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteSF,
) -> ServiceFeedback:
    sf = _get_or_404(db, sf_id)
    linked: list[str] = []
    if payload.nc_id is not None:
        nc = db.get(Nonconformance, payload.nc_id)
        if nc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nonconformance not found")
        sf.linked_nc_id = nc.id
        linked.append(nc.nc_ref)
    if payload.capa_id is not None:
        capa = db.get(Capa, payload.capa_id)
        if capa is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CAPA not found")
        sf.linked_capa_id = capa.id
        linked.append(capa.capa_ref)
    if sf.status == FeedbackStatus.Open:
        sf.status = FeedbackStatus.InProgress
    log_action(db, user_id=user.id, action=f"SF_LINK id={sf.id} [{', '.join(linked)}]", request=request)
    log_record_history(
        db,
        record_type="service_feedback",
        record_id=sf.id,
        user_id=user.id,
        action=f"LINKED {', '.join(linked)}",
        request=request,
    )
    db.commit()
    db.refresh(sf)
    return sf