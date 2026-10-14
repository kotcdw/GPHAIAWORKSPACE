"""Roles & permissions: the five standard roles, their permission matrix (changed only by the Super
Administrator) and assigning a role to a user."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from app.core import permissions as perms
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_perm
from app.core.errors import field_error
from app.platform.auth.service import revoke_sessions
from app.platform.roles import service
from app.platform.roles.models import RolePermission
from app.platform.users.models import User

router = APIRouter(tags=["roles"])
CanView = Depends(require_perm("system.roles", "system.users"))
SuperAdmin = Depends(require_perm("system.superadmin"))
CanAssign = Depends(require_perm("system.users"))


class PermissionOut(BaseModel):
    code: str
    group: str
    label: str
    super_only: bool
    cae_only: bool


class MemberOut(BaseModel):
    id: int
    name: str
    username: str
    approval_level: str | None
    active: bool


class JobRoleOut(BaseModel):
    code: str
    name: str
    tier: str
    review_level: str | None
    description: str
    icon: str
    locked: bool
    permissions: list[str]
    customised: bool
    users: int
    members: list[MemberOut]


class Catalogue(BaseModel):
    permissions: list[PermissionOut]
    roles: list[JobRoleOut]
    can_edit: bool
    can_assign: bool
    can_appoint_admins: bool


def _catalogue(db: DBSession, user: User) -> Catalogue:
    current = perms.matrix()
    people = list(db.execute(select(User).order_by(User.full_name, User.username)).scalars())
    by_role: dict[str, list[User]] = {}
    for u in people:
        by_role.setdefault(perms.job_role_of(u), []).append(u)
    counts = Counter(perms.job_role_of(u) for u in people if u.is_active)
    return Catalogue(
        permissions=[PermissionOut(code=c, group=g, label=label, super_only=c in perms.SUPER_ONLY,
                                   cae_only=c in perms.CAE_ONLY)
                     for c, (g, label) in perms.PERMISSIONS.items()],
        roles=[JobRoleOut(code=r.code, name=r.name, tier=r.tier.value,
                          review_level=r.review_level.value if r.review_level else None, description=r.description,
                          icon=r.icon, locked=r.locked, permissions=sorted(current[r.code]),
                          customised=current[r.code] != set(r.defaults), users=counts.get(r.code, 0),
                          members=[MemberOut(id=u.id, name=u.full_name or u.username, username=u.username,
                                             approval_level=u.review_level.value if u.review_level else None,
                                             active=u.is_active) for u in by_role.get(r.code, [])])
               for r in perms.JOB_ROLES],
        can_edit=perms.has_perm(user, "system.superadmin"),
        can_assign=perms.has_perm(user, "system.users"),
        can_appoint_admins=perms.is_super_admin(user),
    )


@router.get("/api/roles", response_model=Catalogue)
def get_roles(db: DBSession = Depends(get_db), user: User = CanView) -> Catalogue:
    return _catalogue(db, user)


@router.get("/api/roles/options")
def role_options(user: User = CanAssign) -> list[dict]:
    sup = perms.is_super_admin(user)
    return [{"code": r.code, "name": r.name, "tier": r.tier.value,
             "assignable": sup or r.code not in service.ADMIN_ROLES} for r in perms.JOB_ROLES]


class PermissionsIn(BaseModel):
    permissions: list[str]


def _role_or_404(code: str) -> perms.JobRole:
    role = perms.JOB_ROLES_BY_CODE.get(code)
    if role is None or role.code != code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown role")
    return role


@router.put("/api/roles/{code}/permissions", response_model=Catalogue)
def set_permissions(code: str, payload: PermissionsIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = SuperAdmin) -> Catalogue:
    role = _role_or_404(code)
    if role.locked:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="The Super Administrator always has full control; its permissions cannot change")
    wanted = set(payload.permissions)
    unknown = wanted - set(perms.PERMISSIONS)
    if unknown:
        raise field_error("permissions", f"unknown permission(s): {', '.join(sorted(unknown))}")
    if wanted & perms.SUPER_ONLY:
        raise field_error("permissions", "full control and role management stay with the Super Administrator")
    db.execute(delete(RolePermission).where(RolePermission.job_role == code))
    defaults = set(role.defaults)
    for p in sorted(wanted ^ defaults):  # store only the differences from the defaults
        db.add(RolePermission(job_role=code, permission=p, granted=p in wanted, updated_by=user.id))
    added, removed = sorted(wanted - defaults), sorted(defaults - wanted)
    log_action(db, user_id=user.id, request=request,
               action=f"ROLE_PERMISSIONS {code} +[{','.join(added)}] -[{','.join(removed)}]"[:490])
    db.commit()
    perms.invalidate()
    return _catalogue(db, user)


@router.post("/api/roles/{code}/reset", response_model=Catalogue)
def reset_role(code: str, request: Request, db: DBSession = Depends(get_db), user: User = SuperAdmin) -> Catalogue:
    _role_or_404(code)
    db.execute(delete(RolePermission).where(RolePermission.job_role == code))
    log_action(db, user_id=user.id, action=f"ROLE_RESET {code}", request=request)
    db.commit()
    perms.invalidate()
    return _catalogue(db, user)


class AssignIn(BaseModel):
    job_role: str
    approval_level: Literal["Manager", "CAE"] | None = None


@router.patch("/api/users/{user_id}/job-role")
def assign_job_role(user_id: int, payload: AssignIn, request: Request, db: DBSession = Depends(get_db),
                    actor: User = CanAssign) -> dict:
    """Give a user one of the five roles; their access tier and approval level follow the role."""
    code = service.normalise(payload.job_role)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    service.check_can_manage(actor, target, code)
    service.guard_last_super_admin(db, target, code)
    tier_changed = service.apply_role(target, code, payload.approval_level)
    revoked = revoke_sessions(db, target.id) if tier_changed and target.id != actor.id else 0
    role = perms.JOB_ROLES_BY_CODE[code]
    log_action(db, user_id=actor.id, request=request,
               action=f"JOB_ROLE user={target.id} role={code} tier={role.tier.value} "
                      f"level={target.review_level.value if target.review_level else '-'}")
    db.commit()
    return {"user_id": target.id, "job_role": code, "job_role_name": role.name, "role": role.tier.value,
            "review_level": target.review_level.value if target.review_level else None, "sessions_ended": revoked}
