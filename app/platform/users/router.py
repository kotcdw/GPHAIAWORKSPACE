"""User administration routes (Admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core import permissions as perms
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import Role
from app.core.schemas import MessageOut
from app.core.security import hash_password
from app.core.validators import password_problems
from app.platform.auth.service import revoke_sessions
from app.platform.roles import service as role_service
from app.platform.users.models import User
from app.platform.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])

AdminUser = Depends(require_role(Role.Admin))


def _current_role(user: User) -> str:
    return perms.job_role_of(user)


@router.get("", response_model=list[UserOut])
def list_users(db: DBSession = Depends(get_db), _: User = AdminUser) -> list[User]:
    return list(db.execute(select(User).order_by(User.username)).scalars().all())


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

        if payload.work_entity_id is not None and db.get(Organization, payload.work_entity_id) is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown entity")
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
