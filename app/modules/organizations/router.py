"""Organization / entity routes: GPHA ports, offices, departments, units and external parties.

Entity types come from the ``organization_categories`` rule; types listed in ``port_categories``
are ports / sites. Every entity reports the port it sits under (itself, or its nearest ancestor of
a port type). Admin-defined custom fields are validated and stored with the record.
"""

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
from app.core.enums import OrganizationStatus, Role
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import ESignRequest, MessageOut
from app.modules.audits.models import Audit
from app.modules.customfields.router import clean_values
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import (
    EntityLite,
    OrganizationCreate,
    OrganizationList,
    OrganizationOut,
    OrganizationUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

WriteOrg = Depends(require_module_tier("organizations", Role.Admin, Role.Auditor))
AdminOrg = Depends(require_module_tier("organizations", Role.Admin))
MAX_DEPTH = 25


class Index:
    """All entities in memory (a few hundred at most) for hierarchy and port look-ups."""

    def __init__(self, db: DBSession) -> None:
        self.rows = {o.id: o for o in db.execute(select(Organization)).scalars()}
        self.port_types = {c.lower() for c in cfg("port_categories")}
        self.children: dict[int, int] = {}
        for o in self.rows.values():
            if o.parent_id:
                self.children[o.parent_id] = self.children.get(o.parent_id, 0) + 1

    def is_port(self, o: Organization) -> bool:
        return (o.category or "").lower() in self.port_types

    def port_of(self, o: Organization) -> Organization | None:
        seen: set[int] = set()
        cur: Organization | None = o
        while cur is not None and cur.id not in seen and len(seen) < MAX_DEPTH:
            if self.is_port(cur):
                return cur
            seen.add(cur.id)
            cur = self.rows.get(cur.parent_id) if cur.parent_id else None
        return None

    def ancestors(self, parent_id: int | None) -> list[int]:
        out, cur = [], parent_id
        while cur and cur not in out and len(out) < MAX_DEPTH:
            out.append(cur)
            row = self.rows.get(cur)
            cur = row.parent_id if row else None
        return out


def _out(o: Organization, idx: Index) -> OrganizationOut:
    parent = idx.rows.get(o.parent_id) if o.parent_id else None
    port = idx.port_of(o)
    return OrganizationOut(
        id=o.id, org_ref=o.org_ref, name=o.name, category=o.category, is_port=idx.is_port(o),
        parent_id=o.parent_id, parent_name=parent.name if parent else None,
        port_id=port.id if port else None, port_name=port.name if port else None,
        children=idx.children.get(o.id, 0), address=o.address, contact_name=o.contact_name,
        contact_email=o.contact_email, contact_phone=o.contact_phone, status=o.status,
        evaluation_end_date=o.evaluation_end_date, approved_by=o.approved_by, approved_at=o.approved_at,
        notes=o.notes, custom_fields=json.loads(o.custom_fields or "{}"), created_by=o.created_by,
        created_at=o.created_at, updated_at=o.updated_at,
    )


def _one(db: DBSession, o: Organization) -> OrganizationOut:
    return _out(o, Index(db))


def _check_category(category: str | None, current: str | None = None) -> str | None:
    if category is None or category.strip() == "":
        return None
    if current is not None and category.strip() == current:
        return current  # a type retired from the list stays valid on records that already use it
    allowed = cfg("organization_categories")
    match = next((c for c in allowed if c.lower() == category.strip().lower()), None)
    if match is None:
        raise field_error("category", f"must be one of the configured entity types: {', '.join(allowed)}")
    return match


def _check_parent(db: DBSession, org_id: int | None, parent_id: int | None) -> int | None:
    if parent_id is None:
        return None
    if db.get(Organization, parent_id) is None:
        raise field_error("parent_id", "is not a known entity")
    if org_id is not None:
        if parent_id == org_id:
            raise field_error("parent_id", "an entity cannot sit under itself")
        if org_id in Index(db).ancestors(parent_id):
            raise field_error("parent_id", "would create a loop (the chosen parent sits under this entity)")
    return parent_id


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
    category: str | None = Query(default=None),
    port_id: int | None = Query(default=None),
    parent_id: int | None = Query(default=None),
    mine: bool = Query(default=False, description="Only entities in the user's own port"),
) -> OrganizationList:
    stmt = select(Organization).order_by(Organization.name)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Organization.name).like(like) | func.lower(Organization.org_ref).like(like))
    if status_filter is not None:
        stmt = stmt.where(Organization.status == status_filter)
    if category:
        stmt = stmt.where(func.lower(Organization.category) == category.lower())
    if parent_id is not None:
        stmt = stmt.where(Organization.parent_id == parent_id)
    items = visible(db, user, "organization", list(db.execute(stmt).scalars().all()))
    idx = Index(db)
    if mine:
        home = idx.rows.get(user.work_entity_id) if user.work_entity_id else None
        home_port = idx.port_of(home) if home else None
        port_id = home_port.id if home_port else -1
    if port_id is not None:
        items = [o for o in items if (p := idx.port_of(o)) is not None and p.id == port_id]
    return OrganizationList(total=len(items), items=[_out(o, idx) for o in items])


@router.get("/types")
def entity_types(user: User = Depends(require_active_user)) -> dict[str, list[str]]:
    """The configured entity types and which of them are ports / sites."""
    return {"categories": cfg("organization_categories"), "port_categories": cfg("port_categories")}


@router.get("/entities", response_model=list[EntityLite])
def list_entities(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list[EntityLite]:
    """Names, types and ports of every entity - for pickers such as "where I work"."""
    idx = Index(db)
    out = []
    for o in sorted(idx.rows.values(), key=lambda r: r.name.lower()):
        port = idx.port_of(o)
        out.append(EntityLite(id=o.id, name=o.name, category=o.category, is_port=idx.is_port(o),
                              port_id=port.id if port else None, port_name=port.name if port else None,
                              parent_id=o.parent_id))
    return out


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteOrg,
) -> OrganizationOut:
    category = _check_category(payload.category)
    parent_id = _check_parent(db, None, payload.parent_id)
    custom = clean_values(db, "organizations", payload.custom_fields)
    org = Organization(
        org_ref=next_reference(db, "ORG"),
        name=payload.name,
        category=category,
        parent_id=parent_id,
        address=(payload.address or "").strip() or None,
        contact_name=payload.contact_name,
        contact_email=str(payload.contact_email) if payload.contact_email else None,
        contact_phone=payload.contact_phone,
        status=OrganizationStatus.Pending,
        evaluation_end_date=payload.evaluation_end_date,
        notes=payload.notes,
        custom_fields=json.dumps(custom),
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
    return _one(db, org)


@router.get("/{org_id}", response_model=OrganizationOut)
def get_organization(
    org_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> OrganizationOut:
    org = db.get(Organization, org_id)
    ensure_can_view(db, user, "organization", org)
    return _one(db, org)


@router.patch("/{org_id}", response_model=OrganizationOut)
def update_organization(
    org_id: int,
    payload: OrganizationUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteOrg,
) -> OrganizationOut:
    org = _get_or_404(db, org_id)
    sent = payload.model_fields_set
    changes: list[str] = []
    for field in ("name", "contact_name", "contact_phone", "evaluation_end_date", "notes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(org, field, value)
            changes.append(field)
    if payload.contact_email is not None:
        org.contact_email = str(payload.contact_email)
        changes.append("contact_email")
    if "category" in sent:
        org.category = _check_category(payload.category, org.category)
        changes.append("category")
    if "parent_id" in sent:
        org.parent_id = _check_parent(db, org.id, payload.parent_id)
        changes.append("parent")
    if "address" in sent:
        org.address = (payload.address or "").strip() or None
        changes.append("address")
    if "custom_fields" in sent:
        org.custom_fields = json.dumps(clean_values(db, "organizations", payload.custom_fields,
                                                    json.loads(org.custom_fields or "{}")))
        changes.append("custom fields")

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
    return _one(db, org)


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
    if db.execute(select(func.count()).select_from(Organization).where(Organization.parent_id == org.id)).scalar_one():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Move or delete the entities under this one first")
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
) -> OrganizationOut:
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
        parent_id=source.parent_id,
        address=source.address,
        custom_fields=source.custom_fields,
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
    return _one(db, copy)


@router.post("/{org_id}/approve", response_model=OrganizationOut)
def approve_organization(
    org_id: int,
    payload: ESignRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = AdminOrg,
) -> OrganizationOut:
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
    return _one(db, org)


@router.post("/{org_id}/set-pending", response_model=OrganizationOut)
def set_pending(
    org_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = AdminOrg,
) -> OrganizationOut:
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
    return _one(db, org)