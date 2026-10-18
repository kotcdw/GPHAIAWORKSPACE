"""User administration routes (the "Manage user accounts" permission, system.users)."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.core import permissions as perms
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_perm
from app.core.enums import utcnow
from app.core.schemas import MessageOut
from app.core.security import hash_password
from app.core.validators import password_problems
from app.platform.auth.service import revoke_sessions
from app.platform.roles import service as role_service
from app.platform.users.models import User
from app.platform.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])

AdminUser = Depends(require_perm("system.users"))


def _current_role(user: User) -> str:
    return perms.job_role_of(user)


@router.get("", response_model=list[UserOut])
def list_users(db: DBSession = Depends(get_db), _: User = AdminUser) -> list[User]:
    return list(db.execute(select(User).order_by(User.username)).scalars().all())


SIGN_IN_ACTIONS = ("LOGIN", "LOGIN directory")


def _last_sign_ins(db: DBSession, ids: list[int] | None = None) -> dict[int, datetime]:
    from app.platform.history.models import AuditLog

    stmt = select(AuditLog.user_id, func.max(AuditLog.timestamp)).where(
        AuditLog.user_id.is_not(None), AuditLog.action_performed.in_(SIGN_IN_ACTIONS)).group_by(AuditLog.user_id)
    if ids is not None:
        stmt = stmt.where(AuditLog.user_id.in_(ids))
    return dict(db.execute(stmt).all())


@router.get("/search")
def search_users(
    q: str | None = Query(default=None, max_length=100),
    job_role: str | None = Query(default=None, max_length=40),
    status_filter: str | None = Query(default=None, alias="status",
                                      pattern="^(active|pending|deactivated|locked|inactive)$"),
    mfa: bool | None = Query(default=None),
    workplace: str | None = Query(default=None, pattern="^(none|inactive)$"),
    sort: str = Query(default="name", pattern="^(name|username|role|last_sign_in|created)$"),
    desc: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=5, le=200),
    db: DBSession = Depends(get_db),
    _: User = AdminUser,
) -> dict:
    """Users with search, filters, sorting and paging. ``inactive`` = active accounts with no sign-in for 90 days."""
    from app.platform.admin.router import INACTIVE_DAYS, NEW_ACCOUNT_GRACE_DAYS

    now = utcnow()
    users = list(db.execute(select(User)).scalars())
    last = _last_sign_ins(db)
    if q:
        needle = q.strip().lower()
        users = [u for u in users if needle in " ".join(
            (u.username, u.full_name or "", u.email or "", u.company or "")).lower()]
    if job_role:
        code = perms.LEGACY_ROLES.get(job_role, job_role)
        users = [u for u in users if perms.job_role_of(u) == code]

    def state(u: User) -> str:
        if u.is_active:
            return "locked" if u.locked_until and u.locked_until > now else "active"
        return "pending" if last.get(u.id) is None else "deactivated"

    if status_filter == "inactive":
        cutoff, grace = now - timedelta(days=INACTIVE_DAYS), now - timedelta(days=NEW_ACCOUNT_GRACE_DAYS)
        users = [u for u in users if u.is_active and ((last.get(u.id) and last[u.id] < cutoff)
                                                      or (last.get(u.id) is None and u.created_at < grace))]
    elif status_filter:
        users = [u for u in users if state(u) == status_filter]
    if mfa is not None:
        users = [u for u in users if bool(u.mfa_enabled) == mfa]
    from app.platform.organizations.models import Organization

    units = {o.id: o for o in db.execute(select(Organization)).scalars()}
    if workplace == "none":
        users = [u for u in users if u.work_entity_id is None]
    elif workplace == "inactive":
        users = [u for u in users if u.work_entity_id in units and not units[u.work_entity_id].is_active]
    keys = {"name": lambda u: (u.full_name or u.username).lower(), "username": lambda u: u.username.lower(),
            "role": lambda u: perms.job_role_of(u), "created": lambda u: u.created_at,
            "last_sign_in": lambda u: last.get(u.id) or datetime.min}
    users.sort(key=keys[sort], reverse=desc)
    total = len(users)
    chunk = users[(page - 1) * page_size: page * page_size]
    counts: dict[str, int] = {}
    for u in db.execute(select(User)).scalars():
        counts[state(u)] = counts.get(state(u), 0) + 1
    return {
        "items": [{**UserOut.model_validate(u).model_dump(mode="json"), "status": state(u),
                   "last_sign_in": last[u.id].isoformat() if last.get(u.id) else None,
                   "workplace": units[u.work_entity_id].name if u.work_entity_id in units else None,
                   "workplace_active": units[u.work_entity_id].is_active if u.work_entity_id in units else None}
                  for u in chunk],
        "total": total, "page": page, "page_size": page_size, "counts": counts,
    }


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: DBSession = Depends(get_db),
    admin: User = AdminUser,
) -> User:
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
        role=payload.role,
        is_active=payload.is_active,
    )
    code = role_service.normalise(payload.job_role) or role_service.TIER_DEFAULT_ROLE[payload.role]
    role_service.check_can_manage(admin, None, code)
    role_service.apply_role(user, code)
    db.add(user)
    db.flush()
    log_action(
        db,
        user_id=admin.id,
        action=f"USER_CREATE username={user.username} role={user.role.value}",
        request=request,
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: DBSession = Depends(get_db), _: User = AdminUser) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: DBSession = Depends(get_db),
    admin: User = AdminUser,
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Editing an administrator's details, password or two-step setup is a Super Administrator task.
    touched = {"email", "full_name", "first_name", "last_name", "company", "password", "reset_mfa",
               "work_entity_id"} & payload.model_fields_set
    if touched and user.id != admin.id:
        role_service.check_can_manage(admin, user, None)
    if payload.password is not None:
        problem = password_problems(payload.password, user.username)
        if problem:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Password {problem}")
    if payload.full_name is not None and not payload.full_name.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Full name cannot be blank")

    changes: list[str] = []
    if payload.email is not None:
        user.email = str(payload.email)
        changes.append("email")
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
        changes.append("full_name")
    if payload.first_name is not None:
        user.first_name = payload.first_name
        changes.append("first_name")
    if payload.last_name is not None:
        user.last_name = payload.last_name
        changes.append("last_name")
    if payload.company is not None:
        user.company = payload.company
        changes.append("company")
    # Role, access tier and approval level change together (one of the five standard roles).
    new_code = role_service.normalise(payload.job_role)
    current_tier = perms.JOB_ROLES_BY_CODE[_current_role(user)].tier
    if new_code is None and payload.role is not None and current_tier != payload.role:
        new_code = role_service.TIER_DEFAULT_ROLE[payload.role]
    level = payload.review_level
    if new_code is not None or level is not None:
        target_code = new_code or _current_role(user)
        role_service.check_can_manage(admin, user, target_code)
        if user.id == admin.id and target_code not in role_service.ADMIN_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role")
        role_service.guard_last_super_admin(db, user, target_code)
        if level and target_code != "manager":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Only a Manager holds an approval level (Unit Head, Audit Manager, PIA "
                                       "or GM Audit)")
        tier_before = user.role
        role_service.apply_role(user, target_code, level or None)
        changes.append(f"job_role={user.job_role} level={user.review_level.value if user.review_level else '-'}")
        if user.role != tier_before:
            changes.append(f"role={user.role.value}")
    if payload.is_active is not None:
        if user.id == admin.id and payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account",
            )
        if payload.is_active is False:
            role_service.check_can_manage(admin, user, None)
            role_service.guard_last_super_admin(db, user, deactivating=True)
        user.is_active = payload.is_active
        changes.append(f"is_active={payload.is_active}")
    if "work_entity_id" in payload.model_fields_set:
        from app.platform.organizations.models import Organization

        unit = db.get(Organization, payload.work_entity_id) if payload.work_entity_id is not None else None
        if payload.work_entity_id is not None and unit is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown entity")
        if unit is not None and not unit.is_active and unit.id != user.work_entity_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"{unit.name} is deactivated: choose an active unit")
        user.work_entity_id = payload.work_entity_id
        changes.append(f"work_entity={payload.work_entity_id}")
    if payload.reset_mfa:
        user.mfa_enabled = False
        user.mfa_secret = None
        changes.append("mfa_reset")
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        user.failed_login_count = 0
        user.locked_until = None
        changes.append("password")
    # Deactivation, a role change or a password reset ends the user's sessions.
    if user.id != admin.id and (payload.is_active is False or payload.role is not None or payload.password is not None
                                 or any(c.startswith("role=") for c in changes)):
        revoked = revoke_sessions(db, user.id)
        if revoked:
            changes.append(f"sessions_revoked={revoked}")

    log_action(
        db,
        user_id=admin.id,
        action=f"USER_UPDATE username={user.username} [{', '.join(changes)}]",
        request=request,
    )
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=MessageOut)
def delete_user(
    user_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    admin: User = AdminUser,
) -> MessageOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")
    role_service.check_can_manage(admin, user, None)
    role_service.guard_last_super_admin(db, user, deactivating=True)
    if _has_activity(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user has recorded activity and is retained for the audit trail; deactivate it instead",
        )
    username = user.username
    db.delete(user)
    log_action(db, user_id=admin.id, action=f"USER_DELETE username={username}", request=request)
    db.commit()
    return MessageOut(message=f"User {username} deleted")

def _has_activity(db: DBSession, user_id: int) -> bool:
    """True when deleting the user would erase or orphan audit-trail evidence."""
    from app.domains.audit.audits.models import Audit, Finding, WorkingPaper
    from app.platform.approvals.models import ApprovalCycle
    from app.platform.history.models import RecordHistory

    checks = (
        (RecordHistory, RecordHistory.user_id),
        (ApprovalCycle, ApprovalCycle.approver_id),
        (Audit, Audit.created_by),
        (Finding, Finding.created_by),
        (WorkingPaper, WorkingPaper.uploaded_by),
    )
    return any(
        db.execute(select(func.count()).select_from(model).where(column == user_id)).scalar_one()
        for model, column in checks
    )


@router.post("/{user_id}/unlock", response_model=UserOut)
def unlock_user(
    user_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    admin: User = AdminUser,
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.failed_login_count = 0
    user.locked_until = None
    log_action(db, user_id=admin.id, action=f"USER_UNLOCK username={user.username}", request=request)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------- access history and sessions

@router.get("/{user_id}/access")
def user_access(user_id: int, db: DBSession = Depends(get_db), _: User = AdminUser) -> dict:
    """Sign-in history, account changes made by administrators, and the user's open sessions."""
    from app.core.audit_describe import describe
    from app.platform.auth.models import Session as UserSession
    from app.platform.history.models import AuditLog

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    sign = db.execute(select(AuditLog).where(
        or_(AuditLog.user_id == user.id, AuditLog.username == user.username),
        # Entries written before categories existed are recognised by their action text.
        or_(AuditLog.category == "authentication",
            AuditLog.category.is_(None) & or_(AuditLog.action_performed.like("LOGIN%"),
                                              AuditLog.action_performed.like("LOGOUT%"),
                                              AuditLog.action_performed.like("ACCOUNT_LOCKED%"))),
    ).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(50)).scalars().all()
    tag = f"username={user.username}"
    changes = db.execute(select(AuditLog).where(
        AuditLog.category == "user_admin", AuditLog.action_performed.like(f"%{tag}%"),
    ).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(50)).scalars().all()
    changes = [c for c in changes if f"{tag} " in f"{c.action_performed} " or c.action_performed.endswith(tag)]
    actor_ids = {c.user_id for c in changes if c.user_id}
    names = {u.id: (u.full_name or u.username) for u in db.execute(
        select(User).where(User.id.in_(actor_ids))).scalars()} if actor_ids else {}
    now = utcnow()
    sessions = db.execute(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked.is_(False),
                                                    UserSession.expires_at > now)
                          .order_by(UserSession.created_at.desc())).scalars().all()
    last = _last_sign_ins(db, [user.id]).get(user.id)
    from app.platform.organizations.models import Organization

    unit = db.get(Organization, user.work_entity_id) if user.work_entity_id else None
    return {
        "workplace": {"id": unit.id, "name": unit.name, "is_active": unit.is_active} if unit else None,
        "last_sign_in": last.isoformat() if last else None,
        "sign_ins": [{"at": r.timestamp.isoformat(), "action": r.action_performed,
                      "event": describe(r.action_performed)[0], "outcome": r.outcome,
                      "ip": r.ip_address, "browser": r.user_agent} for r in sign],
        "changes": [{"at": c.timestamp.isoformat(), "action": c.action_performed,
                     "event": describe(c.action_performed)[0],
                     "details": describe(c.action_performed)[1].replace(f"username={user.username}", "").strip(),
                     "by": names.get(c.user_id) or "-",
                     "outcome": c.outcome} for c in changes],
        "sessions": [{"id": x.id, "started": x.created_at.isoformat(),
                      "last_activity": (x.last_activity_at or x.created_at).isoformat(),
                      "expires": x.expires_at.isoformat(), "ip": x.ip_address, "browser": x.user_agent}
                     for x in sessions],
    }


@router.post("/{user_id}/sessions/revoke", response_model=MessageOut)
def revoke_user_sessions(user_id: int, request: Request, db: DBSession = Depends(get_db),
                         admin: User = AdminUser) -> MessageOut:
    """Sign the user out on every device (their open sessions end at once)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id != admin.id:
        role_service.check_can_manage(admin, user, None)
    keep = None
    if user.id == admin.id:
        from app.core.deps import SESSION_COOKIE
        from app.core.security import hash_token
        from app.platform.auth.models import Session as UserSession

        token = request.cookies.get(SESSION_COOKIE)
        mine = db.execute(select(UserSession).where(UserSession.token_hash == hash_token(token or ""))) \
            .scalar_one_or_none()
        keep = mine.id if mine else None  # signing yourself out elsewhere keeps this session
    count = revoke_sessions(db, user.id, keep_session_id=keep)
    log_action(db, user_id=admin.id, request=request,
               action=f"USER_SESSIONS_REVOKED username={user.username} sessions={count}")
    db.commit()
    return MessageOut(message=f"{count} session{'s' if count != 1 else ''} ended")
