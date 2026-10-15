"""Admin backup routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_module_tier
from app.core.enums import Role
from app.core.schemas import MessageOut
from app.platform.backups.service import backup_root, create_backup, list_backups
from app.platform.users.models import User

router = APIRouter(prefix="/api/admin", tags=["backups"])

AdminOnly = Depends(require_module_tier("backups", Role.Admin))


@router.post("/backup")
def make_backup(
    request: Request, db: DBSession = Depends(get_db), user: User = AdminOnly
) -> dict:
    info = create_backup(db)
    log_action(db, user_id=user.id, action=f"BACKUP_CREATE file={info.filename}", request=request)
    db.commit()
    return info.__dict__


@router.get("/backups")
def get_backups(_: User = AdminOnly) -> list[dict]:
    return [info.__dict__ for info in list_backups()]


@router.delete("/backups/{filename}", response_model=MessageOut)
def delete_backup(
    filename: str, request: Request, db: DBSession = Depends(get_db), user: User = AdminOnly
) -> MessageOut:
    # Prevent path traversal: only a bare filename inside the backup root.
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.startswith("backup_"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid backup name")
    target = backup_root() / safe_name
    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    target.unlink()
    log_action(db, user_id=user.id, action=f"BACKUP_DELETE file={safe_name}", request=request)
    db.commit()
    return MessageOut(message=f"Backup {safe_name} deleted")