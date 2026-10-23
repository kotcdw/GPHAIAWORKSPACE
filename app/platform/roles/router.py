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


class Catalogue(BaseModel):
    permissions: list[PermissionOut]
    roles: list[JobRoleOut]
    can_edit: bool
    can_assign: bool
    can_appoint_admins: bool


def _catalogue(db: DBSession, user: User) -> Catalogue:
    current = perms.matrix()
    counts = Counter(perms.job_role_of(u) for u in db.execute(select(User).where(User.is_active.is_(True))).scalars())
    return Catalogue(
        permissions=[PermissionOut(code=c, group=g, label=label, super_only=c in perms.SUPER_ONLY,
                                   cae_only=c in perms.CAE_ONLY)
                     for c, (g, label) in perms.PERMISSIONS.items()],
        roles=[JobRoleOut(code=r.code, name=r.name, tier=r.tier.value,
                          review_level=r.review_level.value if r.review_level else None, description=r.description,
                          icon=r.icon, locked=r.locked, permissions=sorted(current[r.code]),
                          customised=current[r.code] != set(r.defaults), users=counts.get(r.code, 0))
               for r in perms.JOB_ROLES],
        can_edit=perms.has_perm(user, "system.superadmin"),
        can_assign=perms.has_perm(user, "system.users"),
        can_appoint_admins=perms.is_super_admin(user),
    )


@router.get("/api/roles", response_model=Catalogue)
def get_roles(db: DBSession = Depends(get_db), user: User = CanView) -> Catalogue:
    return _catalogue(db, user)


class PermissionsIn(BaseModel):
    permissions: list[str]


def _role_or_404(code: str) -> perms.JobRole:
    role = perms.JOB_ROLES_BY_CODE.get(code)
    if role is None or role.code != code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown role")
    return role


def _save_permissions(db: DBSession, role: perms.JobRole, wanted: set[str], user: User, request: Request,
                      note: str = "") -> None:
    """Store a role's permissions as differences from its defaults (the Super Administrator's role never changes)."""
    if role.locked:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="The Super Administrator always has full control; its permissions cannot change")
    unknown = wanted - set(perms.PERMISSIONS)
    if unknown:
        raise field_error("permissions", f"unknown permission(s): {', '.join(sorted(unknown))}")
    if wanted & perms.SUPER_ONLY:
        raise field_error("permissions", "full control and role management stay with the Super Administrator")
    db.execute(delete(RolePermission).where(RolePermission.job_role == role.code))
    defaults = set(role.defaults)
    for p in sorted(wanted ^ defaults):  # store only the differences from the defaults
        db.add(RolePermission(job_role=role.code, permission=p, granted=p in wanted, updated_by=user.id))
    added, removed = sorted(wanted - defaults), sorted(defaults - wanted)
    log_action(db, user_id=user.id, request=request,
               action=f"ROLE_PERMISSIONS {role.code}{note} +[{','.join(added)}] -[{','.join(removed)}]"[:490])
    db.commit()
    perms.invalidate()


@router.put("/api/roles/{code}/permissions", response_model=Catalogue)
def set_permissions(code: str, payload: PermissionsIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = SuperAdmin) -> Catalogue:
    _save_permissions(db, _role_or_404(code), set(payload.permissions), user, request)
    return _catalogue(db, user)


class AccessCellIn(BaseModel):
    module: str
    action: Literal["view", "create", "edit", "approve", "export", "configure", "delete"]
    allowed: bool
    preview: bool = False


ALL_ACTIONS = ("view", "create", "edit", "approve", "export", "configure", "delete")


def _tokens(row: dict, action: str) -> list[str]:
    return row["edit"] if action == "delete" else row[action]  # deleting follows the right to edit


def _cell(row: dict, action: str, granted: set[str], tier: str, read_only: bool, refused: set) -> bool:
    from app.platform.roles import matrix as access

    tokens = _tokens(row, action)
    if not tokens:
        return False
    base = access.cell_granted(tokens, granted, tier, read_only, "edit" if action == "delete" else action)
    return base and (row["module"], action) not in refused


def _cells(granted: set[str], tier: str, read_only: bool, refused: set) -> dict[tuple[str, str], bool]:
    from app.platform.roles import matrix as access

    return {(row["module"], a): _cell(row, a, granted, tier, read_only, refused)
            for row in access.ROWS for a in ALL_ACTIONS}


@router.put("/api/roles/{code}/access")
def set_access_cell(code: str, payload: AccessCellIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = SuperAdmin) -> dict:
    """Allow or refuse one module action for a role (Roles & permissions > Access by module). Super Administrator only.

    View, Create, Edit and Delete are refused per module, enforced on every request to that module. Approve, Export
    and Configure are permissions; a permission can stand for cells in other modules too (Export is one permission
    for every register), so ``preview`` lists every other cell a change reaches before it is saved."""
    from app.platform.roles import matrix as access
    from app.platform.roles.models import RoleModuleAccess

    role = _role_or_404(code)
    if role.locked:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="The Super Administrator always has every right, so the workspace can never be "
                                   "locked out; its access cannot be reduced")
    row = next((r for r in access.ROWS if r["module"] == payload.module), None)
    if row is None:
        raise field_error("module", "is not a module of the access matrix")
    tokens = _tokens(row, payload.action)
    if not tokens:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Not applicable to this module")
    read_only = code == "read_only"
    if read_only and payload.allowed and payload.action not in ("view", "export"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="A Read-only User can never change records; choose another role")
    tier = role.tier.value
    current = set(perms.matrix().get(code, set()))
    refused_now = set(access.refused().get(code, set()))
    wanted, refused_new = set(current), set(refused_now)
    key = (payload.module, payload.action)
    usable = {t for t in tokens if not t.startswith("tier:") and t not in perms.SUPER_ONLY}
    if payload.action in access.GUARDED:
        if payload.allowed:
            refused_new.discard(key)
            if not _cell(row, payload.action, wanted, tier, read_only, refused_new):
                if not usable:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                        detail="Only the Super Administrator can do this")
                wanted |= usable
        else:
            refused_new.add(key)
    else:
        if not usable:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Only the Super Administrator can do this")
        wanted = (wanted | usable) if payload.allowed else (wanted - set(tokens))
    before = _cells(current, tier, read_only, refused_now)
    after = _cells(wanted, tier, read_only, refused_new)
    changes = [{"module": m, "action": a, "allowed": after[(m, a)]} for (m, a) in after
               if after[(m, a)] != before[(m, a)] and (m, a) != key]
    if payload.preview:
        return {"changes": changes, "permissions": sorted(wanted ^ current)}
    if refused_new != refused_now:
        db.execute(delete(RoleModuleAccess).where(RoleModuleAccess.job_role == code,
                                                  RoleModuleAccess.module == payload.module,
                                                  RoleModuleAccess.action == payload.action))
        if key in refused_new:
            db.add(RoleModuleAccess(job_role=code, module=payload.module, action=payload.action, updated_by=user.id))
        log_action(db, user_id=user.id, request=request,
                   action=f"ROLE_ACCESS {code} {payload.module}/{payload.action} "
                          f"{'allowed' if payload.allowed else 'refused'}"[:490])
        db.commit()
        access.invalidate()
    if wanted != current:
        _save_permissions(db, role, wanted, user, request, note=f" access[{payload.module}/{payload.action}]")
    return {"changes": changes, "matrix": access_matrix(user)}


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
    approval_level: Literal["Unit Head", "Manager", "PIA", "CAE"] | None = None


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
    old_code = perms.job_role_of(target)
    tier_changed = service.apply_role(target, code, payload.approval_level)
    # Any change of role signs the person out, so the new access applies at once (e.g. Auditor -> Read-only User).
    changed = tier_changed or old_code != code
    revoked = revoke_sessions(db, target.id) if changed and target.id != actor.id else 0
    role = perms.JOB_ROLES_BY_CODE[code]
    log_action(db, user_id=actor.id, request=request,
               action=f"JOB_ROLE user={target.id} role={code} tier={role.tier.value} "
                      f"level={target.review_level.value if target.review_level else '-'}")
    db.commit()
    return {"user_id": target.id, "job_role": code, "job_role_name": role.name, "role": role.tier.value,
            "review_level": target.review_level.value if target.review_level else None, "sessions_ended": revoked}


@router.get("/api/roles/matrix")
def access_matrix(_: User = CanView) -> dict:
    """Module x action view of every role's effective permissions (defaults with saved changes applied)."""
    from app.platform.roles import matrix as access

    current = perms.matrix()
    columns = []
    for r in perms.JOB_ROLES:
        have = current.get(r.code, set())
        variants = [(r.code, r.name, have)]
        if r.code == "manager":
            variants = [("manager", "Manager (Unit Head, Audit Manager, PIA)", have - perms.CAE_ONLY),
                        ("manager_cae", "Manager at GM Audit (CAE) level", have)]
        for code, name, granted in variants:
            columns.append({"code": code, "name": name, "tier": r.tier.value, "read_only": r.code == "read_only",
                            "granted": granted})
    refused = access.refused()
    rows = []
    for row in access.ROWS:
        cells = {}
        for action in ALL_ACTIONS:
            tokens = _tokens(row, action)
            cells[action] = {"permissions": tokens, "roles": [
                c["code"] for c in columns
                if _cell(row, action, c["granted"], c["tier"], c["read_only"],
                         set() if c["code"] == "super_admin" else refused.get(_base_code(c["code"]), set()))]}
        rows.append({"module": row["module"], "cells": cells, "delete": row["delete"]})
    return {"actions": list(ALL_ACTIONS),
            "roles": [{k: v for k, v in c.items() if k != "granted"} for c in columns],
            "rows": rows, "labels": {p: label for p, (_, label) in perms.PERMISSIONS.items()}}


def _base_code(code: str) -> str:
    return "manager" if code == "manager_cae" else code
