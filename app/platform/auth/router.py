"""Authentication routes: register, login, logout, me."""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core import directory, totp
from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import CSRF_COOKIE, SESSION_COOKIE, get_current_session, get_current_user, mfa_setup_required
from app.core.enums import Role, utcnow
from app.core.schemas import MessageOut
from app.core.security import hash_password, hash_token, new_csrf_token, new_token, verify_password
from app.platform.auth.models import Session as UserSession
from app.platform.auth.schemas import (
    LoginRequest,
    MeOut,
    MfaCode,
    MfaDisable,
    MfaSetupOut,
    PasswordChange,
    ProfileUpdate,
    RegisterRequest,
)
from app.platform.auth.service import revoke_sessions
from app.platform.users.models import User
from app.platform.users.schemas import UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

_LOCKED_MESSAGE = (
    "Account temporarily locked after repeated failed sign-in attempts. "
    "Try again later or ask an administrator to unlock it."
)


# --- per-IP throttle on sign-in / registration (in addition to account lockout)
_ATTEMPTS: dict[str, deque] = {}
_ATTEMPTS_LOCK = threading.Lock()


def _throttle(request: Request) -> None:
    limit = cfg("login_rate_limit_per_minute")
    if limit <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _ATTEMPTS_LOCK:
        window = _ATTEMPTS.setdefault(ip, deque())
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many sign-in attempts from this computer. Wait a minute and try again.",
            )
        window.append(now)


def _me(user: User, csrf_token: str) -> MeOut:
    from app.core.permissions import permissions_of

    return MeOut(user=UserOut.model_validate(user), csrf_token=csrf_token,
                 mfa_setup_required=mfa_setup_required(user), permissions=sorted(permissions_of(user)))


def _set_auth_cookies(response: Response, raw_token: str, csrf_token: str, max_age: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    # Readable by JS on purpose: used for the double-submit CSRF check.
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/register", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: DBSession = Depends(get_db)) -> MessageOut:
    _throttle(request)
    exists = db.execute(select(User).where(func.lower(User.username) == payload.username.lower())).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    full_name = payload.full_name.strip() or " ".join(
        part for part in (payload.first_name.strip(), payload.last_name.strip()) if part
    )
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        email=str(payload.email),
        full_name=full_name,
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        company=payload.company.strip(),
        role=Role.Auditee,
        is_active=False,  # pending administrator approval
    )
    db.add(user)
    db.flush()
    log_action(db, user_id=user.id, action=f"REGISTER username={user.username}", request=request)
    db.commit()
    return MessageOut(
        message="Registration received. An administrator must approve your account before you can sign in."
    )


@router.post("/login", response_model=MeOut)
def login(payload: LoginRequest, request: Request, response: Response, db: DBSession = Depends(get_db)) -> MeOut:
    _throttle(request)
    user = db.execute(select(User).where(func.lower(User.username) == payload.username.lower())).scalar_one_or_none()
    now = utcnow()
    if user is not None and user.locked_until is not None and user.locked_until > now:
        log_action(db, user_id=user.id, action="LOGIN_DENIED account_locked", request=request)
        db.commit()
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=_LOCKED_MESSAGE)
    local_ok = user is not None and verify_password(payload.password, user.password_hash)
    via_directory = False
    is_breakglass = user is not None and user.username.lower() == settings.admin_username.lower()
    if not local_ok and directory.enabled() and not is_breakglass:
        found = directory.authenticate(payload.username, payload.password)
        if found is not None:
            via_directory = True
            if user is None:
                if not settings.ldap_auto_create:
                    log_action(db, user_id=None, action=f"LOGIN_DENIED not_registered username={payload.username[:64]}",
                               request=request)
                    db.commit()
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                        detail="Your network account is not registered in the workspace. "
                                               "Ask the Internal Audit administrator to add you.")
                user = User(username=payload.username.strip()[:64], email=found.email[:255],
                            full_name=found.full_name[:255], role=Role.Auditee, is_active=False,
                            password_hash=hash_password(new_token()))
                db.add(user)
                db.flush()
                log_action(db, user_id=user.id, action="DIRECTORY_ACCOUNT_CREATED pending_approval", request=request)
            elif found.full_name and not user.full_name:
                user.full_name = found.full_name[:255]
    if not local_ok and not via_directory:
        log_action(db, user_id=None, action=f"LOGIN_FAILED username={payload.username[:64]}", request=request)
        if user is not None:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
                log_action(db, user_id=user.id, action="ACCOUNT_LOCKED too_many_failed_logins", request=request)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    if user.mfa_enabled and user.mfa_secret:
        if not payload.otp:
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="MFA_REQUIRED: enter the 6-digit code from your authenticator app")
        if not totp.verify(totp.unseal(user.mfa_secret), payload.otp):
            log_action(db, user_id=user.id, action="LOGIN_FAILED bad_mfa_code", request=request)
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= settings.login_max_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
                log_action(db, user_id=user.id, action="ACCOUNT_LOCKED too_many_failed_logins", request=request)
            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication code")
    user.failed_login_count = 0
    user.locked_until = None
    if not user.is_active:
        log_action(db, user_id=user.id, action="LOGIN_DENIED pending_approval", request=request)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is pending administrator approval",
        )

    raw_token = new_token()
    csrf_token = new_csrf_token()
    ttl_seconds = settings.session_ttl_hours * 3600
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        csrf_token=csrf_token,
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:500],
    )
    db.add(session)
    log_action(db, user_id=user.id, action="LOGIN directory" if via_directory else "LOGIN", request=request)
    db.commit()

    _set_auth_cookies(response, raw_token, csrf_token, ttl_seconds)
    return _me(user, csrf_token)


@router.post("/logout", response_model=MessageOut)
def logout(
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
    session: UserSession | None = Depends(get_current_session),
) -> MessageOut:
    if session is not None:
        session.revoked = True
        log_action(db, user_id=session.user_id, action="LOGOUT", request=request)
        db.commit()
    _clear_auth_cookies(response)
    return MessageOut(message="Signed out")


@router.get("/me", response_model=MeOut)
def me(
    user: User = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
) -> MeOut:
    return _me(user, session.csrf_token)


@router.patch("/me", response_model=MeOut)
def update_profile(
    payload: ProfileUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
) -> MeOut:
    if payload.email is not None:
        user.email = str(payload.email)
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if "work_entity_id" in payload.model_fields_set:
        from app.platform.organizations.models import Organization

        if payload.work_entity_id is not None and db.get(Organization, payload.work_entity_id) is None:
            from app.core.errors import field_error

            raise field_error("work_entity_id", "is not a known entity")
        user.work_entity_id = payload.work_entity_id
    log_action(db, user_id=user.id, action="PROFILE_UPDATE", request=request)
    db.commit()
    db.refresh(user)
    return _me(user, session.csrf_token)


@router.post("/me/password", response_model=MessageOut)
def change_password(
    payload: PasswordChange,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
) -> MessageOut:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    # Sign out every other session (e.g. a stolen cookie); keep the current one.
    revoked = revoke_sessions(db, user.id, keep_session_id=session.id)
    log_action(db, user_id=user.id, action=f"PASSWORD_CHANGE other_sessions_revoked={revoked}", request=request)
    db.commit()
    return MessageOut(message="Password changed successfully")

# --- two-step verification (TOTP) --------------------------------------------


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(request: Request, db: DBSession = Depends(get_db), user: User = Depends(get_current_user)) -> MfaSetupOut:
    """Start enrolment: a new secret to add to the authenticator app (not active until confirmed)."""
    if user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step verification is already on")
    secret = totp.new_secret()
    user.mfa_secret = totp.seal(secret)
    log_action(db, user_id=user.id, action="MFA_SETUP_STARTED", request=request)
    db.commit()
    return MfaSetupOut(secret=secret, otpauth_uri=totp.provisioning_uri(secret, user.username))


@router.post("/mfa/enable", response_model=MeOut)
def mfa_enable(payload: MfaCode, request: Request, db: DBSession = Depends(get_db),
               user: User = Depends(get_current_user),
               session: UserSession = Depends(get_current_session)) -> MeOut:
    if not user.mfa_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start the set-up first")
    if not totp.verify(totp.unseal(user.mfa_secret), payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="That code is not right. Check the time on your phone and try the newest code.")
    user.mfa_enabled = True
    log_action(db, user_id=user.id, action="MFA_ENABLED", request=request)
    db.commit()
    return _me(user, session.csrf_token)


@router.post("/mfa/disable", response_model=MeOut)
def mfa_disable(payload: MfaDisable, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(get_current_user),
                session: UserSession = Depends(get_current_session)) -> MeOut:
    if user.role.value in cfg("mfa_required_roles"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Two-step verification is required for your role and cannot be turned off")
    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Two-step verification is not on")
    if not verify_password(payload.password, user.password_hash) or not totp.verify(
        totp.unseal(user.mfa_secret), payload.code
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password or code is not right")
    user.mfa_enabled = False
    user.mfa_secret = None
    log_action(db, user_id=user.id, action="MFA_DISABLED", request=request)
    db.commit()
    return _me(user, session.csrf_token)
