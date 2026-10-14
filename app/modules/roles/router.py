"""Roles & permissions: the job-role catalogue, the editable permission matrix and job-role assignment."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from app.core import permissions as perms
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_perm
from app.core.errors import field_error
from app.modules.auth.service import revoke_sessions
from app.modules.roles.models import RolePermission
from app.modules.users.models import User

router = APIRouter(tags=["roles"])
CanView = Depends(require_perm("system.roles", "system.users"))
CanEdit = Depends(require_perm("system.roles"))
CanAssign = Depends(require_perm("system.users"))


class PermissionOut(BaseModel):
    code: str
    group: str
    label: str


class JobRoleOut(BaseModel):
    code: str
    name: str
    tier: str
    review_level: str | None
    description: str
    permissions: list[str]
    customised: bool
    users: int


class Catalogue(BaseModel):
    permissions: list[PermissionOut]
    roles: list[JobRoleOut]


def _catalogue(db: DBSession) -> Catalogue:
    current = perms.matrix()
    counts = Counter(perms.job_role_of(u) for u in db.execute(select(User).where(User.is_active.is_(True))).scalars())
    return Catalogue(
        permissions=[PermissionOut(code=c, group=g, label=label) for c, (g, label) in perms.PERMISSIONS.items()],
        roles=[JobRoleOut(code=r.code, name=r.name, tier=r.tier.value,
                          review_level=r.review_level.value if r.review_level else None, description=r.description,
                          permissions=sorted(current[r.code]), customised=current[r.code] != set(r.defaults),
                          users=counts.get(r.code, 0)) for r in perms.JOB_ROLES],
    )


@router.get("/api/roles", response_model=Catalogue)
def get_roles(db: DBSession = Depends(get_db), user: User = CanView) -> Catalogue:
    return _catalogue(db)


@router.get("/api/roles/options")
def role_options(user: User = CanAssign) -> list[dict]:
    return [{"code": r.code, "name": r.name, "tier": r.tier.value} for r in perms.JOB_ROLES]


class PermissionsIn(BaseModel):
    permissions: list[str]


@router.put("/api/roles/{code}/permissions", response_model=Catalogue)
def set_permissions(code: str, payload: PermissionsIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = CanEdit) -> Catalogue:
    role = perms.JOB_ROLES_BY_CODE.get(code)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown job role")
    wanted = set(payload.permissions)
    unknown = wanted - set(perms.PERMISSIONS)
    if unknown:
        raise field_error("permissions", f"unknown permission(s): {', '.join(sorted(unknown))}")
    if code == "platform_admin" and "system.roles" not in wanted:
        raise field_error("permissions", "the Platform Administrator must keep 'Manage roles and permissions'")
    if code == "committee" and wanted - {"governance.view"}:
        raise field_error("permissions", "the Audit Committee role is read-only (governance view only)")
    db.execute(delete(RolePermission).where(RolePermission.job_role == code))
    defaults = set(role.defaults)
    for p in sorted(wanted ^ defaults):  # store only the differences from the defaults
        db.add(RolePermission(job_role=code, permission=p, granted=p in wanted, updated_by=user.id))
    added, removed = sorted(wanted - defaults), sorted(defaults - wanted)
    log_action(db, user_id=user.id, request=request,
               action=f"ROLE_PERMISSIONS {code} +[{','.join(added)}] -[{','.join(removed)}]"[:490])
    db.commit()
    perms.invalidate()
    return _catalogue(db)


@router.post("/api/roles/{code}/reset", response_model=Catalogue)
def reset_role(code: str, request: Request, db: DBSession = Depends(get_db), user: User = CanEdit) -> Catalogue:
    if code not in perms.JOB_ROLES_BY_CODE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown job role")
    db.execute(delete(RolePermission).where(RolePermission.job_role == code))
    log_action(db, user_id=user.id, action=f"ROLE_RESET {code}", request=request)
    db.commit()
    perms.invalidate()
    return _catalogue(db)


class AssignIn(BaseModel):
    job_role: str


@router.patch("/api/users/{user_id}/job-role")
def assign_job_role(user_id: int, payload: AssignIn, request: Request, db: DBSession = Depends(get_db),
                    actor: User = CanAssign) -> dict:
    """Give a user a job role; their access tier and review level follow the role."""
    role = perms.JOB_ROLES_BY_CODE.get(payload.job_role)
    if role is None:
        raise field_error("job_role", "is not a known job role")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == actor.id and role.code != "platform_admin" and perms.job_role_of(actor) == "platform_admin":
        others = [u for u in db.execute(select(User).where(User.is_active.is_(True), User.id != actor.id)).scalars()
                  if perms.job_role_of(u) == "platform_admin"]
        if not others:
            raise field_error("job_role", "you are the only Platform Administrator; appoint another one first")
    tier_changed = target.role != role.tier
    target.job_role = role.code
    target.role = role.tier
    target.review_level = role.review_level
    revoked = revoke_sessions(db, target.id) if tier_changed and target.id != actor.id else 0
    log_action(db, user_id=actor.id, request=request,
               action=f"JOB_ROLE user={target.id} role={role.code} tier={role.tier.value}")
    db.commit()
    return {"user_id": target.id, "job_role": role.code, "job_role_name": role.name, "role": role.tier.value,
            "review_level": role.review_level.value if role.review_level else None, "sessions_ended": revoked}
