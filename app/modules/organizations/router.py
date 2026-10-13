"""Organization (third-party) routes."""

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
from app.core.enums import OrganizationStatus, Role
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import ESignRequest, MessageOut
from app.modules.audits.models import Audit
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import (
    OrganizationCreate,
    OrganizationList,
    OrganizationOut,
    OrganizationUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

WriteOrg = Depends(require_module_tier("organizations", Role.Admin, Role.Auditor))
AdminOrg = Depends(require_module_tier("organizations", Role.Admin))


def _get_or_404(db: DBSession, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.get("", response_model=OrganizationList)
def list_organizations(
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    q: str | None = Query(default=None),
    status_filter: OrganizationStatus | None = Query(default=None, alias="status"),
) -> OrganizationList:
    stmt = select(Organization).order_by(Organization.name)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Organization.name).like(like))
    if status_filter is not None:
        stmt = stmt.where(Organization.status == status_filter)
    items = visible(db, user, "organization", list(db.execute(stmt).scalars().all()))
    return OrganizationList(total=len(items), items=[OrganizationOut.model_validate(o) for o in items])


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteOrg,
) -> Organization:
    org = Organization(
        org_ref=next_reference(db, "ORG"),
        name=payload.name,
        category=payload.category,
        contact_name=payload.contact_name,
        contact_email=str(payload.contact_email) if payload.contact_email else None,
        contact_phone=payload.contact_phone,
        status=OrganizationStatus.Pending,
        evaluation_end_date=payload.evaluation_end_date,
        notes=payload.notes,
        created_by=user.id,
    )
    db.add(org)
    db.flush()
    log_action(db, user_id=user.id, action=f"ORG_CREATE id={org.id} ref={org.org_ref}", request=request)
    log_record_history(
        db, record_type="organization", record_id=org.id, user_id=user.id, action="CREATED", request=request
    )
    db.commit()
    db.refresh(org)
    return org


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(
    org_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> Organization:
    org = db.get(Organization, org_id)
    ensure_can_view(db, user, "organization", org)
    return org


@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(
    org_id: int,
    payload: OrganizationUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteOrg,
) -> Organization:
    org = _get_or_404(db, org_id)
    changes: list[str] = []
    for field in ("name", "category", "contact_name", "contact_phone", "evaluation_end_date", "notes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(org, field, value)
            changes.append(field)
    if payload.contact_email is not None:
        org.contact_email = str(payload.contact_email)
        changes.append("contact_email")

    log_action(db, user_id=user.id, action=f"ORG_UPDATE id={org.id} [{', '.join(changes)}]", request=request)
    log_record_history(
        db,
        record_type="organization",
        record_id=org.id,
        user_id=user.id,
        action=f"UPDATED [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(org)
    return org


@router.delete("/{org_id}", response_model=MessageOut)
def delete_organization(
    org_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = AdminOrg,
) -> MessageOut:
    org = _get_or_404(db, org_id)
    ensure_deletable(db, "organization", org, allowed_statuses=("Pending",))
    if db.execute(select(func.count()).select_from(Audit).where(Audit.organization_id == org.id)).scalar_one():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization is referenced by audits")
    ref = org.org_ref
    db.delete(org)
    log_record_history(db, record_type="organization", record_id=org_id, user_id=user.id, action=f"DELETED {ref}")
    log_action(db, user_id=user.id, action=f"ORG_DELETE id={org_id} ref={ref}", request=request)
    db.commit()
    return MessageOut(message=f"Organization {ref} deleted")


@router.post("/{org_id}/copy", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def copy_organization(
    org_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteOrg,
) -> Organization:
    source = _get_or_404(db, org_id)
    copy = Organization(
        org_ref=next_reference(db, "ORG"),
        name=f"{source.name} (Copy)",
        category=source.category,
        contact_name=source.contact_name,
        contact_email=source.contact_email,
        contact_phone=source.contact_phone,
        status=OrganizationStatus.Pending,
        evaluation_end_date=source.evaluation_end_date,
        notes=source.notes,
        created_by=user.id,
    )
    db.add(copy)
    db.flush()
    log_action(
        db, user_id=user.id, action=f"ORG_COPY from={source.id} to={copy.id} ref={copy.org_ref}", request=request
    )
    log_record_history(
        db, record_type="organization", record_id=copy.id, user_id=user.id, action="COPIED", request=request
    )
    db.commit()
    db.refresh(copy)
    return copy


@router.post("/{org_id}/approve", response_model=OrganizationOut)
def approve_organization(
    org_id: int,
    payload: ESignRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = AdminOrg,
) -> Organization:
    org = _get_or_404(db, org_id)
    if org.status != OrganizationStatus.Pending:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization is already approved")

    def _on_approve(session: DBSession) -> None:
        org.status = OrganizationStatus.Approved
        org.approved_by = user.id
        org.approved_at = datetime.now(UTC).replace(tzinfo=None)

    sign(
        db,
        record_type="organization",
        record_id=org.id,
        user=user,
        preparer_id=org.created_by,
        password=payload.password,
        decision="Approve",
        comment=payload.comment,
        request=request,
        on_approve=_on_approve,
    )
    log_action(db, user_id=user.id, action=f"ORG_APPROVE id={org.id} ref={org.org_ref}", request=request)
    db.commit()
    db.refresh(org)
    return org


@router.post("/{org_id}/set-pending", response_model=OrganizationOut)
def set_pending(
    org_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = AdminOrg,
) -> Organization:
    org = _get_or_404(db, org_id)
    org.status = OrganizationStatus.Pending
    org.approved_by = None
    org.approved_at = None
    log_action(db, user_id=user.id, action=f"ORG_SET_PENDING id={org.id} ref={org.org_ref}", request=request)
    log_record_history(
        db, record_type="organization", record_id=org.id, user_id=user.id, action="SET PENDING", request=request
    )
    db.commit()
    db.refresh(org)
    return org