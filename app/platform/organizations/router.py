"""Organization / entity routes: GPHA ports, offices, departments, units and external parties.

Entity types come from the ``organization_categories`` rule; types listed in ``port_categories``
are ports / sites. Every entity reports the port it sits under (itself, or its nearest ancestor of
a port type). Admin-defined custom fields are validated and stored with the record.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, ensure_deletable, visible
from app.core.appconfig import cfg
from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm, require_active_user, require_module_tier, require_role
from app.core.enums import AuditStatus, OrganizationStatus, Role, utcnow
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.schemas import ESignRequest, MessageOut
from app.domains.audit.audits.models import Audit
from app.platform.customfields.router import clean_values
from app.platform.organizations.models import Organization
from app.platform.organizations.schemas import (
    DeactivateRequest,
    DeleteRequest,
    EntityLite,
    OrganizationCreate,
    OrganizationList,
    OrganizationOut,
    OrganizationUpdate,
)
from app.platform.users.models import User

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

WriteOrg = Depends(require_module_tier("organizations", Role.Admin, Role.Auditor))
AdminOrg = Depends(require_module_tier("organizations", Role.Admin))
StaffOnly = Depends(require_role(Role.Admin, Role.Auditor))
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
        heads = {o.head_user_id for o in self.rows.values() if o.head_user_id}
        self.head_names = {u.id: u.full_name or u.username for u in db.execute(
            select(User).where(User.id.in_(heads))).scalars()} if heads else {}

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

    def descendants(self, oid: int) -> list[int]:
        kids: dict[int, list[int]] = {}
        for o in self.rows.values():
            if o.parent_id:
                kids.setdefault(o.parent_id, []).append(o.id)
        out, stack = [], list(kids.get(oid, []))
        while stack and len(out) < 10000:
            cur = stack.pop()
            if cur in out or cur == oid:
                continue
            out.append(cur)
            stack.extend(kids.get(cur, []))
        return out

    def ancestors(self, parent_id: int | None) -> list[int]:
        out, cur = [], parent_id
        while cur and cur not in out and len(out) < MAX_DEPTH:
            out.append(cur)
            row = self.rows.get(cur)
            cur = row.parent_id if row else None
        return out


def _destination(user: User, flag: bool | None, label: str | None) -> dict:
    """Plan distribution settings are reference data: only users with 'system.reference' may set them."""
    flag = bool(flag)
    label = (label or "").strip() or None
    if flag or label:
        from app.core.deps import ensure_perm

        ensure_perm(user, "system.reference")
    return {"plan_destination": flag, "destination_label": label if flag else None}


def _out(o: Organization, idx: Index) -> OrganizationOut:
    parent = idx.rows.get(o.parent_id) if o.parent_id else None
    port = idx.port_of(o)
    return OrganizationOut(
        id=o.id, org_ref=o.org_ref, name=o.name, category=o.category, is_port=idx.is_port(o),
        parent_id=o.parent_id, parent_name=parent.name if parent else None,
        port_id=port.id if port else None, port_name=port.name if port else None,
        children=idx.children.get(o.id, 0), address=o.address, plan_destination=o.plan_destination,
        destination_label=o.destination_label, contact_name=o.contact_name,
        contact_email=o.contact_email, contact_phone=o.contact_phone, status=o.status,
        evaluation_end_date=o.evaluation_end_date, approved_by=o.approved_by, approved_at=o.approved_at,
        notes=o.notes, custom_fields=json.loads(o.custom_fields or "{}"), head_user_id=o.head_user_id,
        head_name=idx.head_names.get(o.head_user_id) if o.head_user_id else None, is_active=o.is_active,
        deactivated_at=o.deactivated_at, deactivation_reason=o.deactivation_reason, created_by=o.created_by,
        created_at=o.created_at, updated_at=o.updated_at,
    )


def _one(db: DBSession, o: Organization) -> OrganizationOut:
    return _out(o, Index(db))


def _check_category(category: str | None, current: str | None = None, *, db: DBSession | None = None,
                    user: User | None = None) -> str | None:
    if category is None or category.strip() == "":
        return None
    if current is not None and category.strip() == current:
        return current  # a type retired from the list stays valid on records that already use it
    allowed = cfg("organization_categories")
    match = next((c for c in allowed if c.lower() == category.strip().lower()), None)
    if match is not None:
        return match
    from app.core.permissions import has_perm

    if db is None or user is None or not has_perm(user, "system.reference"):
        raise field_error("category", f"must be one of the configured entity types: {', '.join(allowed)}")
    return _add_category(db, user, category)


def _add_category(db: DBSession, user: User, category: str) -> str:
    """A type typed into the unit form by someone who manages reference data joins the configured entity types and
    the Org Structure types (Configuration > Organizations), with the change in the configuration history."""
    from app.core.appconfig import AppConfig, AppConfigHistory
    from app.core.appconfig import invalidate as invalidate_config

    name = " ".join(category.split())[:60]
    if len(name) < 2:
        raise field_error("category", "type at least 2 characters for a new type")
    for key in ("organization_categories", "org_structure_categories"):
        old = list(cfg(key))
        if any(c.lower() == name.lower() for c in old):
            continue
        new = [*old, name]
        row = db.get(AppConfig, key)
        if row is None:
            db.add(AppConfig(key=key, value=json.dumps(new), updated_by=user.id))
        else:
            row.value, row.updated_by = json.dumps(new), user.id
        db.add(AppConfigHistory(key=key, action="update", old_value=json.dumps(old), new_value=json.dumps(new),
                                reason=f"New type '{name}' added from the unit form", changed_by=user.id,
                                changed_by_name=user.full_name or user.username))
    db.flush()
    invalidate_config()
    return name


def _check_parent(db: DBSession, org_id: int | None, parent_id: int | None) -> int | None:
    if parent_id is None:
        return None
    parent = db.get(Organization, parent_id)
    if parent is None:
        raise field_error("parent_id", "is not a known entity")
    if not parent.is_active:
        raise field_error("parent_id", f"{parent.name} is deactivated: reactivate it or choose another parent")
    if org_id is not None:
        if parent_id == org_id:
            raise field_error("parent_id", "an entity cannot sit under itself")
        if org_id in Index(db).ancestors(parent_id):
            raise field_error("parent_id", "would create a loop (the chosen parent sits under this entity)")
    return parent_id


def _check_head(db: DBSession, user: User, head_user_id: int | None) -> int | None:
    """Naming a unit head is reference data: it needs 'system.reference', and the person must have an active account."""
    ensure_perm(user, "system.reference")
    if head_user_id is None:
        return None
    head = db.get(User, head_user_id)
    if head is None or not head.is_active:
        raise field_error("head_user_id", "must be a person with an active account")
    return head_user_id


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
    active: bool | None = Query(default=None, description="Only units in use (true) or deactivated (false)"),
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
    if active is not None:
        stmt = stmt.where(Organization.is_active.is_(active))
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
    return {"categories": cfg("organization_categories"), "port_categories": cfg("port_categories"),
            "audit_types": cfg("audit_types")}


@router.get("/entities", response_model=list[EntityLite])
def list_entities(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list[EntityLite]:
    """Names, types and ports of every entity - for pickers such as "where I work"."""
    idx = Index(db)
    out = []
    for o in sorted(idx.rows.values(), key=lambda r: r.name.lower()):
        port = idx.port_of(o)
        out.append(EntityLite(id=o.id, name=o.name, category=o.category, is_port=idx.is_port(o),
                              port_id=port.id if port else None, port_name=port.name if port else None,
                              parent_id=o.parent_id, plan_destination=o.plan_destination,
                              destination_label=o.destination_label, is_active=o.is_active))
    return out


@router.get("/people")
def people_for_units(db: DBSession = Depends(get_db), user: User = StaffOnly) -> list[dict]:
    """Active accounts for the unit head picker (heads of audited units are often Audit Clients): names only, for
    people who maintain the structure."""
    ensure_perm(user, "system.reference")
    rows = db.execute(select(User).where(User.is_active.is_(True)).order_by(User.full_name, User.username)).scalars()
    return [{"id": u.id, "name": u.full_name or u.username, "username": u.username} for u in rows]


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteOrg,
) -> OrganizationOut:
    category = _check_category(payload.category, db=db, user=user)
    parent_id = _check_parent(db, None, payload.parent_id)
    custom = clean_values(db, "organizations", payload.custom_fields)
    org = Organization(
        org_ref=next_reference(db, "ORG"),
        name=payload.name,
        category=category,
        parent_id=parent_id,
        address=(payload.address or "").strip() or None,
        **_destination(user, payload.plan_destination, payload.destination_label),
        contact_name=payload.contact_name,
        contact_email=str(payload.contact_email) if payload.contact_email else None,
        contact_phone=payload.contact_phone,
        status=OrganizationStatus.Pending,
        evaluation_end_date=payload.evaluation_end_date,
        notes=payload.notes,
        custom_fields=json.dumps(custom),
        head_user_id=_check_head(db, user, payload.head_user_id) if payload.head_user_id else None,
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
        org.category = _check_category(payload.category, org.category, db=db, user=user)
        changes.append("category")
    if "parent_id" in sent and payload.parent_id != org.parent_id:  # forms resend the parent unchanged
        org.parent_id = _check_parent(db, org.id, payload.parent_id)
        changes.append("parent")
    if "address" in sent:
        org.address = (payload.address or "").strip() or None
        changes.append("address")
    if "plan_destination" in sent or "destination_label" in sent:
        dest = _destination(user, payload.plan_destination if "plan_destination" in sent else org.plan_destination,
                            payload.destination_label if "destination_label" in sent else org.destination_label)
        if (dest["plan_destination"], dest["destination_label"]) != (org.plan_destination, org.destination_label):
            from app.core.deps import ensure_perm

            ensure_perm(user, "system.reference")  # removing a destination is as controlled as adding one
            org.plan_destination, org.destination_label = dest["plan_destination"], dest["destination_label"]
            changes.append("plan destination")
    if "head_user_id" in sent and payload.head_user_id != org.head_user_id:
        org.head_user_id = _check_head(db, user, payload.head_user_id)
        changes.append("head")
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


def _delete_check(
    db: DBSession, org: Organization, idx: Index, with_subunits: bool
) -> tuple[list[int], list[str], int]:
    """What deleting ``org`` would remove: the unit ids, what blocks it, and how many process mappings go with it.

    Audits, workplaces, auditable entities and enterprise risk assessments are never removed silently: they block
    the delete until someone moves or edits them."""
    from app.domains.assurance.planning.models import EntityUnit
    from app.domains.assurance.universe.models import EntityOrgUnit, ProcessOrgUnit
    from app.domains.grc.risk.models import RiskSegmentAssessment

    below = idx.descendants(org.id)
    ids = [org.id, *below] if with_subunits else [org.id]
    blockers: list[str] = []
    if below and not with_subunits:
        blockers.append(f"{len(below)} unit(s) sit under it: move them, or delete them with it")
    audits = db.execute(select(func.count()).select_from(Audit).where(
        Audit.organization_id.in_(ids) | Audit.port_entity_id.in_(ids))).scalar_one()
    if audits:
        blockers.append(f"{audits} audit(s) name it: audits are kept as evidence")
    people = db.execute(select(func.count()).select_from(User).where(User.work_entity_id.in_(ids))).scalar_one()
    if people:
        blockers.append(f"{people} person(s) have it as their workplace: move them first")
    codes = db.execute(select(EntityUnit.code).join(EntityOrgUnit, EntityOrgUnit.entity_id == EntityUnit.id)
                       .where(EntityOrgUnit.org_id.in_(ids)).distinct()).scalars().all()
    if codes:
        shown = ", ".join(sorted(codes)[:5]) + ("…" if len(codes) > 5 else "")
        blockers.append(f"Auditable entities use it ({shown}): edit those entities first")
    risks = db.execute(select(func.count()).select_from(RiskSegmentAssessment)
                       .where(RiskSegmentAssessment.org_id.in_(ids))).scalar_one()
    if risks:
        blockers.append(f"{risks} enterprise risk assessment(s) are recorded for it")
    mapped = db.execute(select(func.count()).select_from(ProcessOrgUnit)
                        .where(ProcessOrgUnit.org_id.in_(ids))).scalar_one()
    return ids, blockers, mapped


@router.delete("/{org_id}", response_model=MessageOut)
def delete_organization(
    org_id: int,
    request: Request,
    payload: DeleteRequest | None = Body(default=None),
    db: DBSession = Depends(get_db),
    user: User = AdminOrg,
) -> MessageOut:
    from app.core import permissions as perms
    from app.core.security import verify_password
    from app.domains.assurance.universe.models import UniverseReview

    org = _get_or_404(db, org_id)
    payload = payload or DeleteRequest()
    superadmin = perms.has_perm(user, "system.superadmin")
    if not superadmin:
        # Administrators: an empty pending unit only; anything approved or e-signed is kept for the audit trail.
        ensure_deletable(db, "organization", org, allowed_statuses=("Pending",))
        if payload.with_subunits:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Only a Super Administrator deletes a unit together with its sub-units")
    ids, blockers, mapped = _delete_check(db, org, Index(db), payload.with_subunits and superadmin)
    if blockers:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="; ".join(blockers))
    if superadmin and len(payload.reason.strip()) < 5:
        raise field_error("reason", "say why the unit is deleted (at least 5 characters)")
    if superadmin and not verify_password(payload.password, user.password_hash):
        db.rollback()
        log_action(db, user_id=user.id, request=request, commit=True,
                   action=f"ORG_DELETE_FAILED wrong_password id={org.id}", entity_type="organization",
                   entity_id=org.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password verification failed")
    rows = sorted((db.get(Organization, i) for i in ids), key=lambda o: o.id != org.id)
    refs = [o.org_ref for o in rows]
    reason = f" reason={payload.reason.strip()!r}" if superadmin else ""
    for o in reversed(rows):  # sub-units first, the unit last
        db.execute(UniverseReview.__table__.delete().where(UniverseReview.object_type == "unit",
                                                           UniverseReview.object_id == o.id))
        oid, ref, status_was = o.id, o.org_ref, o.status.value
        db.delete(o)
        db.flush()
        log_record_history(db, record_type="organization", record_id=oid, user_id=user.id,
                           action=f"DELETED {ref} (was {status_was}){reason}")
    extra = f" sub-units={','.join(refs[1:])}" if len(refs) > 1 else ""
    log_action(db, user_id=user.id, action=f"ORG_DELETE id={org_id} ref={refs[0]}{extra} "
                                           f"process_mappings={mapped}{reason}", request=request)
    db.commit()
    more = f" and {len(refs) - 1} sub-unit(s)" if len(refs) > 1 else ""
    return MessageOut(message=f"Organization {refs[0]}{more} deleted")


@router.post("/{org_id}/copy", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def copy_organization(
    org_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteOrg,
) -> OrganizationOut:
    source = _get_or_404(db, org_id)
    parent_id = _check_parent(db, None, source.parent_id)  # never place an active copy under a deactivated unit
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
        parent_id=parent_id,
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
    if not org.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reactivate this unit before approving it")

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

# ---------------------------------------------------------------- administration: deactivate, reactivate, overview


@router.post("/{org_id}/deactivate", response_model=OrganizationOut)
def deactivate_organization(
    org_id: int,
    payload: DeactivateRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteOrg,
) -> OrganizationOut:
    """Take a unit out of use. It stays on the audits, plans and history that name it, but is no longer offered
    for new work. Units under it must be deactivated or moved first."""
    ensure_perm(user, "system.reference")
    org = _get_or_404(db, org_id)
    if not org.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This unit is already deactivated")
    active_kids = db.execute(select(func.count()).select_from(Organization).where(
        Organization.parent_id == org.id, Organization.is_active.is_(True))).scalar_one()
    if active_kids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Deactivate or move the {active_kids} active unit{'s' if active_kids != 1 else ''} "
                                   "under this one first")
    reason = payload.reason.strip()
    org.is_active = False
    org.deactivated_at = utcnow()
    org.deactivated_by = user.id
    org.deactivation_reason = reason
    log_action(db, user_id=user.id, action=f"ORG_DEACTIVATE id={org.id} ref={org.org_ref}", request=request)
    log_record_history(db, record_type="organization", record_id=org.id, user_id=user.id,
                       action=f"DEACTIVATED: {reason}", request=request)
    db.commit()
    db.refresh(org)
    return _one(db, org)


@router.post("/{org_id}/reactivate", response_model=OrganizationOut)
def reactivate_organization(
    org_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = WriteOrg,
) -> OrganizationOut:
    ensure_perm(user, "system.reference")
    org = _get_or_404(db, org_id)
    if org.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This unit is already active")
    parent = db.get(Organization, org.parent_id) if org.parent_id else None
    if parent is not None and not parent.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Reactivate {parent.name} first, or move this unit under an active one")
    org.is_active = True
    org.deactivated_at = org.deactivated_by = org.deactivation_reason = None
    log_action(db, user_id=user.id, action=f"ORG_REACTIVATE id={org.id} ref={org.org_ref}", request=request)
    log_record_history(db, record_type="organization", record_id=org.id, user_id=user.id, action="REACTIVATED",
                       request=request)
    db.commit()
    db.refresh(org)
    return _one(db, org)


@router.get("/{org_id}/overview")
def organization_overview(org_id: int, db: DBSession = Depends(get_db), user: User = StaffOnly) -> dict:
    """Everything an administrator needs about one unit: where it sits, who heads it and works there, the units
    under it, the audits and processes that name it, and its change history."""
    from app.core import permissions as perms
    from app.domains.assurance.universe.models import Process, ProcessOrgUnit
    from app.platform.history.models import RecordHistory

    org = _get_or_404(db, org_id)
    idx = Index(db)
    path, cur, seen = [], org.parent_id, set()
    while cur and cur in idx.rows and cur not in seen and len(seen) < MAX_DEPTH:
        seen.add(cur)
        path.append({"id": cur, "name": idx.rows[cur].name})
        cur = idx.rows[cur].parent_id
    path.reverse()
    kids = sorted((o for o in idx.rows.values() if o.parent_id == org.id),
                  key=lambda o: (not o.is_active, o.name.lower()))
    subtree = [org.id, *idx.descendants(org.id)]
    people = list(db.execute(select(User).where(User.work_entity_id == org.id)
                             .order_by(User.full_name, User.username)).scalars())
    people_below = db.execute(select(func.count()).select_from(User).where(
        User.work_entity_id.in_(subtree[1:]), User.is_active.is_(True))).scalar_one() if len(subtree) > 1 else 0
    names = {r.code: r.name for r in perms.JOB_ROLES}
    from app.core.access import staff_audit_scope

    unit_audits = (Audit.organization_id == org.id) | (Audit.port_entity_id == org.id)
    scope = staff_audit_scope(db, user)  # only audits the caller may see (port scope)
    if scope is not None:
        unit_audits = unit_audits & Audit.id.in_(scope or {-1})
    audits = db.execute(select(Audit).where(unit_audits).order_by(Audit.id.desc()).limit(10)).scalars().all()
    audit_total = db.execute(select(func.count()).select_from(Audit).where(unit_audits)).scalar_one()
    audit_open = db.execute(select(func.count()).select_from(Audit).where(
        unit_audits, Audit.status != AuditStatus.Closed)).scalar_one()
    processes = db.execute(select(Process.id, Process.name)
                           .join(ProcessOrgUnit, ProcessOrgUnit.process_id == Process.id)
                           .where(ProcessOrgUnit.org_id == org.id).order_by(Process.name)).all()
    hist = db.execute(select(RecordHistory).where(RecordHistory.record_type == "organization",
                                                  RecordHistory.record_id == org.id)
                      .order_by(RecordHistory.timestamp.desc(), RecordHistory.id.desc()).limit(40)).scalars().all()
    who = {u.id: u.full_name or u.username for u in db.execute(select(User).where(
        User.id.in_({h.user_id for h in hist if h.user_id} | ({org.deactivated_by} if org.deactivated_by else set()))
    )).scalars()} if hist or org.deactivated_by else {}
    reference = perms.has_perm(user, "system.reference")
    superadmin = perms.has_perm(user, "system.superadmin")
    check = _delete_check(db, org, idx, False) if superadmin else None
    check_all = _delete_check(db, org, idx, True) if superadmin else None
    return {
        "unit": _out(org, idx).model_dump(mode="json"),
        "path": path,
        "deactivated_by": who.get(org.deactivated_by) if org.deactivated_by else None,
        "children": [{"id": o.id, "name": o.name, "org_ref": o.org_ref, "category": o.category,
                      "is_active": o.is_active, "status": o.status.value} for o in kids],
        "people": [{"id": u.id, "name": u.full_name or u.username, "username": u.username, "is_active": u.is_active,
                    "role": names.get(perms.job_role_of(u), perms.job_role_of(u))} for u in people[:200]],
        "people_total": len(people), "people_below": people_below,
        "audits": [{"id": a.id, "title": a.title, "status": a.status.value} for a in audits],
        "audit_total": audit_total, "audit_open": audit_open,
        "processes": [{"id": pid, "name": name} for pid, name in processes],
        "history": [{"at": h.timestamp.isoformat(), "action": h.action, "by": who.get(h.user_id) or "-"}
                    for h in hist],
        "can": {
            "edit": perms.has_perm(user, "method.library", "system.reference"),
            "administer": reference,
            "approve": user.role == Role.Admin and org.status == OrganizationStatus.Pending and org.is_active,
            "delete": user.role == Role.Admin and org.status == OrganizationStatus.Pending and not people
                      and audit_total == 0 and not kids,
            "superdelete": superadmin,
        },
        "delete_check": {"blockers": check[1], "with_subunits_blockers": check_all[1], "subunits": len(subtree) - 1,
                         "process_mappings": check_all[2]} if superadmin else None,
    }
