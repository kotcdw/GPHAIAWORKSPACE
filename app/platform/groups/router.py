"""User groups (PROJECTBLUEPRINT 6.3): named sets of people, managed by account administrators (system.users).

Groups are an audience for sharing reports, dashboards and presentations, and a unit for access reviews. They
never grant a permission: what each member can do still comes from their own job role.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_perm
from app.core.enums import Role
from app.platform.groups.models import UserGroup, UserGroupMember
from app.platform.users.models import User

router = APIRouter(prefix="/api/groups", tags=["groups"])
Manage = Depends(require_perm("system.users"))


class GroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    owner_id: int | None = None


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    owner_id: int | None = None
    is_active: bool | None = None


class GroupRoleIn(BaseModel):
    job_role: str = Field(min_length=2, max_length=40)


class MembersIn(BaseModel):
    user_ids: list[int] = Field(default_factory=list, max_length=2000)


def groups_of(db: DBSession, user_id: int) -> set[int]:
    """Ids of the active groups a person belongs to."""
    return set(db.execute(select(UserGroupMember.group_id).join(UserGroup, UserGroup.id == UserGroupMember.group_id)
                          .where(UserGroupMember.user_id == user_id, UserGroup.is_active.is_(True))).scalars())


def _name(u: User | None) -> str | None:
    return (u.full_name or u.username) if u else None


def _out(db: DBSession, g: UserGroup, members: bool = False) -> dict:
    count = db.execute(select(func.count()).select_from(UserGroupMember)
                       .where(UserGroupMember.group_id == g.id)).scalar_one()
    out = {"id": g.id, "name": g.name, "description": g.description, "owner_id": g.owner_id,
           "owner": _name(db.get(User, g.owner_id)) if g.owner_id else None, "is_active": g.is_active,
           "members": count, "created_at": g.created_at, "updated_at": g.updated_at}
    if members:
        rows = db.execute(select(User).join(UserGroupMember, UserGroupMember.user_id == User.id)
                          .where(UserGroupMember.group_id == g.id).order_by(User.full_name, User.username)).scalars()
        out["member_list"] = [{"id": u.id, "name": _name(u), "username": u.username, "email": u.email,
                               "role": u.role.value, "is_active": u.is_active} for u in rows]
    return out


def _group(db: DBSession, group_id: int) -> UserGroup:
    g = db.get(UserGroup, group_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return g


def _check_owner(db: DBSession, owner_id: int | None) -> None:
    if owner_id is None:
        return
    u = db.get(User, owner_id)
    if u is None or not u.is_active:
        raise HTTPException(status_code=422, detail="Group owner: choose an active user")


def _unique(db: DBSession, name: str, exclude: int | None = None) -> None:
    clash = db.execute(select(UserGroup).where(func.lower(UserGroup.name) == name.strip().lower())).scalar_one_or_none()
    if clash is not None and clash.id != exclude:
        raise HTTPException(status_code=409, detail=f"A group named '{name.strip()}' already exists")


@router.get("")
def list_groups(include_inactive: bool = False, db: DBSession = Depends(get_db),
                user: User = Depends(require_active_user)) -> list[dict]:
    """Groups are listed to audit staff so they can share with them; members are shown to administrators only."""
    if user.role == Role.Auditee:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    stmt = select(UserGroup).order_by(UserGroup.name)
    if not include_inactive:
        stmt = stmt.where(UserGroup.is_active.is_(True))
    return [_out(db, g) for g in db.execute(stmt).scalars()]


@router.post("", status_code=201)
def create_group(payload: GroupIn, request: Request, db: DBSession = Depends(get_db), user: User = Manage) -> dict:
    _unique(db, payload.name)
    _check_owner(db, payload.owner_id)
    g = UserGroup(name=payload.name.strip(), description=payload.description.strip(), owner_id=payload.owner_id,
                  created_by=user.id)
    db.add(g)
    db.flush()
    log_action(db, user_id=user.id, action=f"GROUP_CREATE id={g.id} {g.name}", request=request)
    db.commit()
    return _out(db, g, members=True)


@router.get("/{group_id}")
def get_group(group_id: int, db: DBSession = Depends(get_db), _: User = Manage) -> dict:
    return _out(db, _group(db, group_id), members=True)


@router.patch("/{group_id}")
def update_group(group_id: int, payload: GroupUpdate, request: Request, db: DBSession = Depends(get_db),
                 user: User = Manage) -> dict:
    g = _group(db, group_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        _unique(db, changes["name"], exclude=g.id)
        changes["name"] = changes["name"].strip()
    if "owner_id" in changes:
        _check_owner(db, changes["owner_id"])
    for k, v in changes.items():
        if v is not None or k == "owner_id":
            setattr(g, k, v)
    log_action(db, user_id=user.id, action=f"GROUP_UPDATE id={g.id} [{', '.join(changes)}]", request=request)
    db.commit()
    return _out(db, g, members=True)


@router.put("/{group_id}/members")
def set_members(group_id: int, payload: MembersIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Manage) -> dict:
    g = _group(db, group_id)
    wanted = set(payload.user_ids)
    known = set(db.execute(select(User.id).where(User.id.in_(wanted or {0}))).scalars())
    if wanted - known:
        raise HTTPException(status_code=422, detail="Some members are not user accounts")
    current = {m.user_id: m for m in db.execute(select(UserGroupMember)
                                                .where(UserGroupMember.group_id == g.id)).scalars()}
    added = wanted - set(current)
    removed = set(current) - wanted
    for uid in added:
        db.add(UserGroupMember(group_id=g.id, user_id=uid, added_by=user.id))
    for uid in removed:
        db.delete(current[uid])
    log_action(db, user_id=user.id, request=request,
               action=f"GROUP_MEMBERS id={g.id} added={sorted(added)} removed={sorted(removed)}")
    db.commit()
    return _out(db, g, members=True)


@router.post("/{group_id}/role")
def give_members_role(group_id: int, payload: GroupRoleIn, request: Request, db: DBSession = Depends(get_db),
                      user: User = Manage) -> dict:
    """Give every member of a group the same role in one step. A group never holds a permission itself: this
    changes each member's own role, with the same checks as changing it one person at a time (administrators,
    the last administrator, licensed seats); your own account is never changed this way."""
    from app.core import permissions as perms
    from app.platform.auth.service import revoke_sessions
    from app.platform.roles import service as role_service
    from app.platform.users.licenses import check_seat

    g = _group(db, group_id)
    code = role_service.normalise(payload.job_role)
    if code is None:
        raise HTTPException(status_code=422, detail="Unknown role")
    role_service.check_can_manage(user, None, code)
    members = db.execute(select(User).join(UserGroupMember, UserGroupMember.user_id == User.id)
                         .where(UserGroupMember.group_id == g.id)).scalars().all()
    changed, skipped = [], []
    for m in members:
        if m.id == user.id or perms.job_role_of(m) == code:
            skipped.append(m.username)
            continue
        role_service.check_can_manage(user, m, code)
        role_service.guard_last_super_admin(db, m, code)
        if m.is_active:
            check_seat(db, code, exclude_user_id=m.id)
        tier_before = m.role
        role_service.apply_role(m, code)
        if m.role != tier_before:
            revoke_sessions(db, m.id)
        db.flush()
        changed.append(m.username)
    log_action(db, user_id=user.id, request=request,
               action=f"USER_GROUP_ROLE group={g.id} job_role={code} changed={len(changed)}"[:490])
    db.commit()
    return {"changed": changed, "unchanged": skipped}


@router.delete("/{group_id}")
def deactivate_group(group_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Manage) -> dict:
    """Groups are deactivated, not erased, so past sharing decisions stay explainable."""
    g = _group(db, group_id)
    g.is_active = False
    log_action(db, user_id=user.id, action=f"GROUP_DEACTIVATE id={g.id} {g.name}", request=request)
    db.commit()
    return _out(db, g)
