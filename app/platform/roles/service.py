"""Assigning one of the five standard roles to a user, with the separation-of-duties guards."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core import permissions as perms
from app.core.enums import ReviewLevel, Role
from app.platform.users.models import User

ADMIN_ROLES = {"super_admin", "admin"}
TIER_DEFAULT_ROLE = {Role.Admin: "admin", Role.Auditor: "auditor", Role.Auditee: "audit_client",
                     Role.Committee: "audit_client"}


def normalise(code: str | None) -> str | None:
    if not code:
        return None
    code = perms.LEGACY_ROLES.get(code, code)
    if code not in perms.JOB_ROLE_CODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Unknown role: choose Super Administrator, Administrator, Manager, Auditor, "
                                   "Read-only User or Audit Client")
    return code


def active_super_admins(db: DBSession, excluding: int | None = None) -> list[User]:
    rows = db.execute(select(User).where(User.is_active.is_(True))).scalars()
    return [u for u in rows if perms.is_super_admin(u) and u.id != excluding]


def check_can_manage(actor: User, target: User | None, new_code: str | None) -> None:
    """Only a Super Administrator may appoint, change or remove administrators."""
    touches_admin = (new_code in ADMIN_ROLES) or (target is not None and perms.job_role_of(target) in ADMIN_ROLES)
    if touches_admin and not perms.is_super_admin(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only a Super Administrator can appoint or change administrators")


def active_admins(db: DBSession, excluding: int | None = None) -> list[User]:
    rows = db.execute(select(User).where(User.is_active.is_(True))).scalars()
    return [u for u in rows if perms.job_role_of(u) in ADMIN_ROLES and u.id != excluding]


def guard_last_super_admin(db: DBSession, target: User, new_code: str | None = None,
                           deactivating: bool = False) -> None:
    """Never leave the platform without an active administrator, nor without an active Super Administrator."""
    removing = deactivating or (new_code is not None and new_code not in ADMIN_ROLES)
    if removing and target.is_active and perms.job_role_of(target) in ADMIN_ROLES \
            and not active_admins(db, excluding=target.id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="This is the last active administrator: appoint another administrator first")
    if not perms.is_super_admin(target):
        return
    if (new_code is not None and new_code != "super_admin") or deactivating:
        if not active_super_admins(db, excluding=target.id):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="This is the only Super Administrator: appoint another one first")


def apply_role(target: User, code: str, approval_level: str | None = None) -> bool:
    """Set the role, the access tier that follows from it and the approval level. Returns True if the tier changed."""
    role = perms.JOB_ROLES_BY_CODE[code]
    tier_before = target.role
    target.job_role = role.code
    target.role = role.tier
    if role.code == "manager":
        if approval_level:
            target.review_level = ReviewLevel(approval_level)
        elif target.review_level is None:
            target.review_level = ReviewLevel.Manager
    else:
        if approval_level:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Only a Manager holds an approval level (Unit Head, Audit Manager, PIA or "
                                       "GM Audit)")
        target.review_level = None
    return tier_before != target.role
