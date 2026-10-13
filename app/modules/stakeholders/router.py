"""Stakeholder routes (straight CRUD, no approval cycle)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, visible
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier
from app.core.enums import Role, StakeholderStatus
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import MessageOut
from app.modules.stakeholders.models import Stakeholder
from app.modules.stakeholders.schemas import (
    StakeholderCreate,
    StakeholderList,
    StakeholderOut,
    StakeholderUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/api/stakeholders", tags=["stakeholders"])

WriteSh = Depends(require_module_tier("stakeholders", Role.Admin, Role.Auditor))
AdminSh = Depends(require_module_tier("stakeholders", Role.Admin))


def _get_or_404(db: DBSession, sh_id: int) -> Stakeholder:
    sh = db.get(Stakeholder, sh_id)
    if sh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stakeholder not found")
    return sh


@router.get("", response_model=StakeholderList)
def list_stakeholders(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    q: str | None = Query(default=None),
    status_filter: StakeholderStatus | None = Query(default=None, alias="status"),
) -> StakeholderList:
    stmt = select(Stakeholder).order_by(Stakeholder.name)
    if q:
        stmt = stmt.where(func.lower(Stakeholder.name).like(f"%{q.lower()}%"))
    if status_filter is not None:
        stmt = stmt.where(Stakeholder.status == status_filter)
    items = visible(db, user, "stakeholder", list(db.execute(stmt).scalars().all()))
    return StakeholderList(total=len(items), items=[StakeholderOut.model_validate(s) for s in items])


@router.post("", response_model=StakeholderOut, status_code=status.HTTP_201_CREATED)
def create_stakeholder(
    payload: StakeholderCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteSh,
) -> Stakeholder:
    sh = Stakeholder(
        sh_ref=next_reference(db, "SH"),
        name=payload.name,
        stakeholder_type=payload.stakeholder_type,
        contact_name=payload.contact_name,
        contact_email=str(payload.contact_email) if payload.contact_email else None,
        contact_phone=payload.contact_phone,
        status=payload.status,
        notes=payload.notes,
        created_by=user.id,
    )
    db.add(sh)
    db.flush()
    log_action(db, user_id=user.id, action=f"SH_CREATE id={sh.id} ref={sh.sh_ref}", request=request)
    log_record_history(
        db, record_type="stakeholder", record_id=sh.id, user_id=user.id, action="CREATED", request=request
    )
    db.commit()
    db.refresh(sh)
    return sh


@router.get("/{sh_id}", response_model=StakeholderOut)
def get_stakeholder(
    sh_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> Stakeholder:
    sh = db.get(Stakeholder, sh_id)
    ensure_can_view(db, user, "stakeholder", sh)
    return sh


@router.patch("/{sh_id}", response_model=StakeholderOut)
def update_stakeholder(
    sh_id: int,
    payload: StakeholderUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteSh,
) -> Stakeholder:
    sh = _get_or_404(db, sh_id)
    changes: list[str] = []
    for field in ("name", "stakeholder_type", "contact_name", "contact_phone", "status", "notes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(sh, field, value)
            changes.append(field)
    if payload.contact_email is not None:
        sh.contact_email = str(payload.contact_email)
        changes.append("contact_email")
    log_action(db, user_id=user.id, action=f"SH_UPDATE id={sh.id} [{', '.join(changes)}]", request=request)
    log_record_history(
        db,
        record_type="stakeholder",
        record_id=sh.id,
        user_id=user.id,
        action=f"UPDATED [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(sh)
    return sh


@router.delete("/{sh_id}", response_model=MessageOut)
def delete_stakeholder(
    sh_id: int, request: Request, db: DBSession = Depends(get_db), user: User = AdminSh
) -> MessageOut:
    sh = _get_or_404(db, sh_id)
    ref = sh.sh_ref
    db.delete(sh)
    log_record_history(db, record_type="stakeholder", record_id=sh_id, user_id=user.id, action=f"DELETED {ref}")
    log_action(db, user_id=user.id, action=f"SH_DELETE id={sh_id} ref={ref}", request=request)
    db.commit()
    return MessageOut(message=f"Stakeholder {ref} deleted")