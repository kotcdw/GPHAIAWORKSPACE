"""Shared FastAPI dependencies: authentication, authorization and CSRF."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.enums import Role, utcnow
from app.core.security import constant_time_equals, hash_token
from app.platform.auth.models import Session as UserSession
from app.platform.users.models import User

SESSION_COOKIE = "gpha_session"
CSRF_COOKIE = "gpha_csrf"
CSRF_HEADER = "x-csrf-token"

_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def get_current_session(request: Request, db: DBSession = Depends(get_db)) -> UserSession | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = db.execute(select(UserSession).where(UserSession.token_hash == hash_token(token))).scalar_one_or_none()
    if session is None or session.revoked or session.expires_at < utcnow():
        return None
    return session


def get_current_user(
    session: UserSession | None = Depends(get_current_session),
    db: DBSession = Depends(get_db),
) -> User:
    if session is None:
        raise _UNAUTHORIZED
    user = db.get(User, session.user_id)
    if user is None:
        raise _UNAUTHORIZED
    return user


def mfa_setup_required(user: User) -> bool:
    """True when the user's role must use MFA but it is not set up yet."""
    from app.core.appconfig import cfg

    return user.role.value in cfg("mfa_required_roles") and not user.mfa_enabled


def require_active_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is pending administrator approval",
        )
    if mfa_setup_required(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Set up two-step verification in your profile before continuing",
        )
    return user


def require_role(*roles: Role) -> Callable[[User], User]:
    """Dependency factory that restricts a route to the given roles."""

    def dependency(user: User = Depends(require_active_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


def require_module_tier(module: str, *roles: Role) -> Callable[[User], User]:
    """Dependency factory for a module's minimum role tier.

    ``module`` only names the area (used in the error message and ready for a
    finer-grained per-module permission matrix later); access is granted when
    the user's role is one of ``roles``.
    """

    def dependency(user: User = Depends(require_active_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for {module}",
            )
        return user

    return dependency


def csrf_protect(request: Request, db: DBSession = Depends(get_db)) -> None:
    """Validate the CSRF token for state-changing authenticated requests.

    Unauthenticated requests (e.g. login/register) are skipped here; the auth
    dependencies decide whether the route is allowed. Safe methods return
    before touching the database, so read-only endpoints such as /health keep
    working even when the database is down.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    # Login and registration happen before a session (and its CSRF token)
    # exists, so they are exempt from the double-submit check.
    if request.url.path in ("/api/auth/login", "/api/auth/register"):
        return
    session = get_current_session(request, db)
    if session is None:
        return
    header = request.headers.get(CSRF_HEADER)
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing")
    if not constant_time_equals(header, session.csrf_token) or not constant_time_equals(cookie, session.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


def require_perm(*perms: str) -> Callable[[User], User]:
    """Dependency factory: the user's job role must hold one of ``perms`` (see app.core.permissions)."""

    def dependency(user: User = Depends(require_active_user)) -> User:
        from app.core.permissions import PERMISSIONS, has_perm

        if not has_perm(user, *perms):
            names = ", ".join(PERMISSIONS.get(p, (None, p))[1].lower() for p in perms)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Your role does not allow this ({names})")
        return user

    return dependency


def ensure_perm(user: User, *perms: str) -> None:
    from app.core.permissions import PERMISSIONS, has_perm

    if not has_perm(user, *perms):
        names = ", ".join(PERMISSIONS.get(p, (None, p))[1].lower() for p in perms)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Your role does not allow this ({names})")


def staff_or_perm(*perms: str) -> Callable[[User], User]:
    """Audit staff (Admin / Auditor tier) or anyone whose job role holds one of ``perms``."""

    def dependency(user: User = Depends(require_active_user)) -> User:
        from app.core.permissions import has_perm

        if user.role in (Role.Admin, Role.Auditor) or has_perm(user, *perms):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return dependency
