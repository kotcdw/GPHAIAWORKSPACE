"""Who may see a report, dashboard, presentation or AI Reporting workstream (Publish › User Access).

* **Public**: public to folder users: every audit staff member (Admin or Auditor tier).
* **Private**: the owner and the users and groups chosen under User Access.

Drafts are visible to their owner only. Sharing never widens data access: shared reports run with the viewer's
own access, and stored facts are shown only to readers who may see every audit they came from.
"""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import Role
from app.platform.users.models import User

ACCESS = ("Public", "Private")


def is_staff(user: User) -> bool:
    return user.role in (Role.Admin, Role.Auditor)


def ensure_staff(user: User) -> None:
    if not is_staff(user):
        raise HTTPException(status_code=403, detail="Reports are for audit staff")


def ids(text: str | None) -> list[int]:
    try:
        return [int(x) for x in json.loads(text or "[]")]
    except (TypeError, ValueError):
        return []


def check_audience(db: DBSession, access: str, group_ids: list[int],
                   user_ids: list[int]) -> tuple[list[int], list[int]]:
    """Validate Private access users and groups; Public access keeps none."""
    from app.platform.groups.models import UserGroup

    if access != "Private":
        return [], []
    groups = set(db.execute(select(UserGroup.id).where(UserGroup.id.in_(group_ids or [0]),
                                                       UserGroup.is_active.is_(True))).scalars())
    if groups != set(group_ids):
        raise HTTPException(status_code=422, detail="Some groups do not exist or are inactive")
    users = set(db.execute(select(User.id).where(User.id.in_(user_ids or [0]), User.is_active.is_(True),
                                                 User.role.in_([Role.Admin, Role.Auditor]))).scalars())
    if users != set(user_ids):
        raise HTTPException(status_code=422, detail="Share privately with active audit staff only")
    return sorted(groups), sorted(users)


def shared_with(db: DBSession, user: User, *, owner_id: int | None, access: str, group_ids: str,
                user_ids: str | None = None) -> bool:
    """True when ``user`` is in the audience (ignores Draft/Active; callers check status)."""
    from app.platform.groups.router import groups_of

    if owner_id == user.id:
        return True
    if not is_staff(user):
        return False
    if access == "Public":
        return True
    return user.id in ids(user_ids) or bool(set(ids(group_ids)) & groups_of(db, user.id))


def may_read_facts(db: DBSession, user: User, facts: dict) -> bool:
    """Stored facts may be read only by someone who could see every audit (and module) they came from."""
    from app.core.access import staff_audit_scope
    from app.core.permissions import has_perm

    scope = staff_audit_scope(db, user)
    for s in facts.get("sources", []):
        if s.get("perms") and not has_perm(user, *s["perms"]):
            return False
        if scope is not None and not set(s.get("audit_ids", [])) <= scope:
            return False
    return True
