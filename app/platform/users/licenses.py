"""Licensed seats per role (the ``license_seats`` setting) and account invitations.

A seat is used by every active account in the role and by every invited account whose invitation is still open.
A role with no line in the setting has no limit.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core import appconfig
from app.core import permissions as perms
from app.core.enums import utcnow
from app.platform.users.models import User, UserInvitation


def seat_limits() -> dict[str, int]:
    try:
        return appconfig.parse_license_seats(appconfig.cfg("license_seats"))
    except ValueError:  # an old saved value that no longer parses: no limits rather than a locked-out workspace
        return {}


def open_invitation_user_ids(db: DBSession) -> set[int]:
    now = utcnow()
    return set(db.execute(select(UserInvitation.user_id).where(
        UserInvitation.accepted_at.is_(None), UserInvitation.revoked_at.is_(None),
        UserInvitation.expires_at > now)).scalars())


def seats_used(db: DBSession, exclude_user_id: int | None = None) -> dict[str, dict[str, int]]:
    invited = open_invitation_user_ids(db)
    used: dict[str, dict[str, int]] = {r.code: {"active": 0, "invited": 0} for r in perms.JOB_ROLES}
    for u in db.execute(select(User)).scalars():
        if u.id == exclude_user_id:
            continue
        code = perms.job_role_of(u)
        if u.is_active:
            used[code]["active"] += 1
        elif u.id in invited:
            used[code]["invited"] += 1
    return used


def check_seat(db: DBSession, code: str, exclude_user_id: int | None = None) -> None:
    """Refuse when the role is licensed and every seat is taken."""
    limit = seat_limits().get(code)
    if limit is None:
        return
    u = seats_used(db, exclude_user_id)[code]
    if u["active"] + u["invited"] >= limit:
        name = perms.JOB_ROLES_BY_CODE[code].name
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"All {limit} licensed {name} seat{'s are' if limit != 1 else ' is'} in use. "
                                   "Free a seat or raise the limit under Configuration > Users & licenses.")


def licenses(db: DBSession) -> list[dict]:
    limits = seat_limits()
    used = seats_used(db)
    out = []
    for r in perms.JOB_ROLES:
        u = used[r.code]
        seats = limits.get(r.code)
        out.append({"code": r.code, "name": r.name, "tier": r.tier.value, "active": u["active"],
                    "invited": u["invited"], "seats": seats,
                    "available": None if seats is None else max(0, seats - u["active"] - u["invited"])})
    return out


# ------------------------------------------------------------------ invitations

def hash_invite(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_invitation(db: DBSession, user: User, invited_by: int | None) -> str:
    """Revoke any open link for the account and issue a new one; returns the raw token (never stored)."""
    now = utcnow()
    for old in db.execute(select(UserInvitation).where(UserInvitation.user_id == user.id,
                                                       UserInvitation.accepted_at.is_(None),
                                                       UserInvitation.revoked_at.is_(None))).scalars():
        old.revoked_at = now
    token = secrets.token_urlsafe(32)
    db.add(UserInvitation(user_id=user.id, token_hash=hash_invite(token), invited_by=invited_by, created_at=now,
                          expires_at=now + timedelta(days=int(appconfig.cfg("invitation_valid_days")))))
    db.flush()
    return token


def find_open_invitation(db: DBSession, token: str) -> UserInvitation | None:
    if not token or len(token) > 200:
        return None
    inv = db.execute(select(UserInvitation).where(UserInvitation.token_hash == hash_invite(token))).scalar_one_or_none()
    if inv is None or inv.accepted_at or inv.revoked_at or inv.expires_at <= utcnow():
        return None
    user = db.get(User, inv.user_id)
    if user is None or user.is_active:
        return None
    return inv


def invite_link(token: str) -> str:
    from app.core.config import settings

    return f"{settings.app_base_url.rstrip('/')}/#activate/{token}"
