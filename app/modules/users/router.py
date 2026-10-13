"""User administration routes (Admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import Role
from app.core.schemas import MessageOut
from app.core.security import hash_password
from app.modules.auth.service import revoke_sessions
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])

AdminUser = Depends(require_role(Role.Admin))


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

    changes: list[str] = []
    if payload.email is not None:
        user.email = str(payload.email)
        changes.append("email")
    if payload.full_name is not None:
        user.full_name = payload.full_name
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
    if payload.role is not None:
        if user.id == admin.id and payload.role != Role.Admin:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role")
        user.role = payload.role
        changes.append(f"role={payload.role.value}")
    if payload.is_active is not None:
        if user.id == admin.id and payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account",
            )
        user.is_active = payload.is_active
        changes.append(f"is_active={payload.is_active}")
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        user.failed_login_count = 0
        user.locked_until = None
        changes.append("password")
    # Deactivation, a role change or a password reset ends the user's sessions.
    if user.id != admin.id and (payload.is_active is False or payload.role is not None or payload.password is not None):
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
    from app.modules.approvals.models import ApprovalCycle
    from app.modules.audits.models import Audit, Finding, WorkingPaper
    from app.modules.history.models import RecordHistory

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
