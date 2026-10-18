"""Helpers shared by the risk & compliance apps: access rules, people and score bands."""

from __future__ import annotations

from datetime import date

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.deps import require_active_user
from app.platform.users.models import User

GRC_PERMS = ("grc.view", "grc.manage", "grc.risk", "grc.compliance", "grc.policy", "grc.policy_approve", "grc.assets")


def can(user: User, *perms: str) -> bool:
    from app.core.permissions import has_perm

    return has_perm(user, "grc.manage", *perms)


def _viewer(user: User = Depends(require_active_user)) -> User:
    from app.core.permissions import has_perm

    if not has_perm(user, *GRC_PERMS):
        raise HTTPException(status_code=403, detail="Your role does not include the risk & compliance apps")
    return user


Viewer = Depends(_viewer)


def editor(perm: str):  # noqa: ANN201
    def dependency(user: User = Depends(require_active_user)) -> User:
        if not can(user, perm):
            from app.core.permissions import PERMISSIONS

            raise HTTPException(status_code=403,
                                detail=f"Your role does not allow this ({PERMISSIONS[perm][1].lower()})")
        return user

    return Depends(dependency)


def name_of(db: DBSession, user_id: int | None) -> str | None:
    if not user_id:
        return None
    u = db.get(User, user_id)
    return (u.full_name or u.username) if u else None


def check_user(db: DBSession, user_id: int | None, label: str = "Owner") -> None:
    if user_id is None:
        return
    u = db.get(User, user_id)
    if u is None or not u.is_active:
        raise HTTPException(status_code=422, detail=f"{label}: choose an active user")


def check_entity(db: DBSession, entity_id: int | None) -> None:
    if entity_id is None:
        return
    from app.platform.organizations.models import Organization

    if db.get(Organization, entity_id) is None:
        raise HTTPException(status_code=422, detail="Unknown organization entity")


def entity_name(db: DBSession, entity_id: int | None) -> str | None:
    if not entity_id:
        return None
    from app.platform.organizations.models import Organization

    o = db.get(Organization, entity_id)
    return o.name if o else None


def band(score: int) -> str:
    """High / Medium / Low from likelihood x impact, using the plan configuration thresholds."""
    from app.core.appconfig import cfg

    if score >= cfg("risk_high_threshold"):
        return "High"
    if score >= cfg("risk_medium_threshold"):
        return "Medium"
    return "Low"


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    import calendar

    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def in_list(value: str, key: str, label: str, allow_empty: bool = True) -> str:
    """The value must be one of the admin-maintained list ``key`` (case-insensitive); returns its canonical form."""
    from app.core.appconfig import cfg

    value = (value or "").strip()
    if not value:
        if allow_empty:
            return ""
        raise HTTPException(status_code=422, detail=f"{label}: choose a value")
    for option in cfg(key):
        if option.lower() == value.lower():
            return option
    raise HTTPException(status_code=422, detail=f"{label}: '{value}' is not in the configured list")


async def read_upload(file) -> tuple[str, bytes]:  # noqa: ANN001
    """Read an uploaded file within the configured size limit and allowed types; returns (safe name, bytes)."""
    from app.core.upload_policy import read_upload as policy_read

    data, _, original = await policy_read(file)
    return original, data


def audience_user_ids(db: DBSession, user_ids: list[int], job_roles: list[str], tiers: list[str],
                      entity_ids: list[int] | None = None) -> list[int]:
    """Active users chosen directly, by job role or by access tier (optionally limited to organization entities)."""
    from sqlalchemy import select

    from app.core.permissions import job_role_of

    chosen: set[int] = set()
    users = list(db.execute(select(User).where(User.is_active.is_(True))).scalars())
    for u in users:
        if entity_ids and u.work_entity_id not in entity_ids:
            if u.id not in user_ids:
                continue
        if u.id in user_ids or job_role_of(u) in job_roles or u.role.value in tiers:
            chosen.add(u.id)
    return sorted(chosen)
