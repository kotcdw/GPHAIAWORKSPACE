"""Admin backup routes: run a backup, list backup sets, verify a set, delete a set, and the check history.

There is deliberately no download and no restore from the browser: restores are done on the server with
``scripts.restore_backup`` (see the restore guide on the Backups page)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_perm
from app.core.schemas import MessageOut
from app.platform.backups import service
from app.platform.backups.models import BackupCheck
from app.platform.users.models import User

router = APIRouter(prefix="/api/admin", tags=["backups"])

AdminOnly = Depends(require_perm("system.technical"))


def _check_out(c: BackupCheck) -> dict:
    try:
        details = json.loads(c.details or "[]")
    except ValueError:
        details = []
    return {"id": c.id, "backup": c.backup, "kind": c.kind, "outcome": c.outcome, "checks": details,
            "by": c.user_name or ("Automatic" if c.kind == "check" else "Server script"), "at": c.at.isoformat()}


def latest_checks(db: DBSession, stamps: list[str]) -> dict[str, BackupCheck]:
    if not stamps:
        return {}
    rows = db.execute(select(BackupCheck).where(BackupCheck.backup.in_(stamps))
                      .order_by(BackupCheck.at.desc(), BackupCheck.id.desc())).scalars()
    out: dict[str, BackupCheck] = {}
    for row in rows:
        out.setdefault(row.backup, row)
    return out


def verify_and_record(db: DBSession, stamp: str, user: User | None, request: Request | None = None) -> dict:
    result = service.verify_backup(stamp)
    service.record_check(db, stamp, result, user=user)
    log_action(db, user_id=getattr(user, "id", None), request=request,
               outcome="success" if result["ok"] else "failure",
               action=f"BACKUP_VERIFY set={stamp} result={'passed' if result['ok'] else 'failed'}")
    db.commit()
    return result


def _info_out(info: service.BackupInfo, check: BackupCheck | None) -> dict:
    return {**info.__dict__, "verified": _check_out(check) if check else None}


@router.post("/backup")
def make_backup(
    request: Request, db: DBSession = Depends(get_db), user: User = AdminOnly
) -> dict:
    try:
        info = service.create_backup(db)
    except Exception as exc:
        db.rollback()
        log_action(db, user_id=user.id, request=request, commit=True, outcome="failure",
                   action=f"BACKUP_FAILED manual {type(exc).__name__}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="The backup could not be created; the failure is recorded in the audit trail",
                            ) from exc
    log_action(db, user_id=user.id, request=request,
               action=f"BACKUP_CREATE file={info.filename} bytes={info.size_bytes}"
                      f" attachments={info.file_count if info.files_name else 'no'}")
    db.commit()
    verify_and_record(db, info.stamp, user, request)
    return _info_out(info, latest_checks(db, [info.stamp]).get(info.stamp))


@router.get("/backups")
def get_backups(db: DBSession = Depends(get_db), _: User = AdminOnly) -> list[dict]:
    sets = service.list_backups()
    checks = latest_checks(db, [s.stamp for s in sets])
    return [_info_out(s, checks.get(s.stamp)) for s in sets]


@router.get("/backups/status")
def backup_status(db: DBSession = Depends(get_db), _: User = AdminOnly) -> dict:
    from datetime import UTC, datetime

    from app.platform.admin.router import backups_summary

    return backups_summary(db, datetime.now(UTC).replace(tzinfo=None))


@router.get("/backups/checks")
def backup_checks(limit: int = 50, db: DBSession = Depends(get_db), _: User = AdminOnly) -> dict:
    rows = db.execute(select(BackupCheck).order_by(BackupCheck.at.desc(), BackupCheck.id.desc())
                      .limit(max(1, min(limit, 500)))).scalars().all()
    return {"items": [_check_out(r) for r in rows]}


def _stamp_or_404(name: str) -> str:
    stamp = service.stamp_of(name)
    if stamp is None or "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid backup name")
    if not any(s.stamp == stamp for s in service.list_backups()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    return stamp


@router.post("/backups/{name}/verify")
def verify(name: str, request: Request, db: DBSession = Depends(get_db), user: User = AdminOnly) -> dict:
    stamp = _stamp_or_404(name)
    result = verify_and_record(db, stamp, user, request)
    return {"backup": stamp, **result}


@router.delete("/backups/{name}", response_model=MessageOut)
def delete_backup(
    name: str, request: Request, db: DBSession = Depends(get_db), user: User = AdminOnly
) -> MessageOut:
    stamp = _stamp_or_404(name)
    if len(service.list_backups()) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The only backup cannot be deleted")
    removed = service.delete_set(stamp)
    log_action(db, user_id=user.id, action=f"BACKUP_DELETE set={stamp} files={len(removed)}", request=request)
    db.commit()
    return MessageOut(message="Backup deleted")
