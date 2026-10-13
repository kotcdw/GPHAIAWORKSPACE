"""Working paper routes: upload with automatic versioning, download, withdraw.

Evidence handling:

* uploads are streamed in chunks and rejected as soon as they exceed the size
  limit; only allow-listed file extensions are accepted;
* every file gets a SHA-256 integrity hash and is stored encrypted at rest
  (``app.core.crypto``); legacy plaintext files remain downloadable;
* papers are never physically deleted - an Admin can *withdraw* one, which
  hides it from normal views but keeps the file, the row and the trail.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from urllib.parse import quote

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, is_privileged
from app.core.audit import log_action
from app.core.config import settings
from app.core.crypto import InvalidToken, decrypt, encrypt
from app.core.database import get_db
from app.core.deps import require_active_user, require_role
from app.core.enums import AuditStatus, Role, utcnow
from app.core.history import log_record_history
from app.core.schemas import MessageOut
from app.modules.audits.models import Audit, WorkingPaper
from app.modules.audits.schemas import WorkingPaperOut
from app.modules.users.models import User

router = APIRouter(tags=["working-papers"])

_CHUNK = 1024 * 1024
_LOCKED = "The audit is closed; working papers are locked"


def _max_bytes() -> int:
    return settings.max_upload_mb * 1024 * 1024


def _safe_name(name: str) -> str:
    return Path(name).name.replace("\x00", "")[:200] or "upload.bin"


def _get_audit_or_404(db: DBSession, audit_id: int) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


@router.get("/api/audits/{audit_id}/working-papers", response_model=list[WorkingPaperOut])
def list_working_papers(
    audit_id: int,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
    include_withdrawn: bool = Query(default=False),
) -> list[WorkingPaper]:
    ensure_can_view(db, user, "audit", db.get(Audit, audit_id))
    stmt = (
        select(WorkingPaper)
        .where(WorkingPaper.audit_id == audit_id)
        .order_by(WorkingPaper.title, WorkingPaper.version_number.desc())
    )
    if not (include_withdrawn and is_privileged(user)):
        stmt = stmt.where(WorkingPaper.is_deleted.is_(False))
    return list(db.execute(stmt).scalars().all())


@router.post(
    "/api/audits/{audit_id}/working-papers",
    response_model=WorkingPaperOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_working_paper(
    audit_id: int,
    request: Request,
    title: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> WorkingPaper:
    audit = _get_audit_or_404(db, audit_id)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_LOCKED)

    original = _safe_name(file.filename or "upload.bin")
    suffix = Path(original).suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{suffix or 'none'}' is not allowed",
        )

    # Stream the upload, stopping as soon as the size limit is exceeded.
    limit = _max_bytes()
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {settings.max_upload_mb} MB limit",
            )
        digest.update(chunk)
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty")

    # Determine the next version for this (audit, title).
    current_max = db.execute(
        select(func.max(WorkingPaper.version_number)).where(
            WorkingPaper.audit_id == audit_id, WorkingPaper.title == title
        )
    ).scalar_one_or_none()
    version = (current_max or 0) + 1

    folder = Path(settings.upload_dir) / str(audit_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored_path = folder / f"{uuid.uuid4().hex}_{original}.enc"
    async with aiofiles.open(stored_path, "wb") as out:
        await out.write(encrypt(b"".join(chunks)))

    paper = WorkingPaper(
        audit_id=audit_id,
        title=title,
        file_path=str(stored_path.relative_to(Path(settings.upload_dir))),
        version_number=version,
        uploaded_by=user.id,
        encrypted=True,
        sha256=digest.hexdigest(),
    )
    db.add(paper)
    db.flush()
    log_action(
        db,
        user_id=user.id,
        action=f"WORKING_PAPER_UPLOAD id={paper.id} audit={audit_id} title={title} v{version} sha256={paper.sha256}",
        request=request,
    )
    log_record_history(
        db,
        record_type="audit",
        record_id=audit_id,
        user_id=user.id,
        action=f"WORKING PAPER UPLOADED {title} v{version}",
        request=request,
    )
    db.commit()
    db.refresh(paper)
    return paper


def _download_name(paper: WorkingPaper) -> str:
    stored = Path(paper.file_path).name
    original = stored.split("_", 1)[1] if "_" in stored else stored
    if original.endswith(".enc"):
        original = original[: -len(".enc")]
    return f"{paper.title}_v{paper.version_number}_{original}"


@router.get("/api/working-papers/{paper_id}/download")
def download_working_paper(
    paper_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
):  # noqa: ANN201 - FileResponse or Response
    paper = db.get(WorkingPaper, paper_id)
    ensure_can_view(db, user, "working_paper", paper)
    root = Path(settings.upload_dir).resolve()
    absolute = (root / paper.file_path).resolve()
    if root not in absolute.parents or not absolute.exists():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="File is no longer available")
    name = _download_name(paper)
    log_action(db, user_id=user.id, action=f"WORKING_PAPER_DOWNLOAD id={paper.id}", request=request)
    db.commit()
    if not paper.encrypted:
        return FileResponse(path=absolute, filename=name)
    try:
        data = decrypt(absolute.read_bytes())
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File cannot be decrypted (encryption key changed?)",
        ) from exc
    if paper.sha256 and hashlib.sha256(data).hexdigest() != paper.sha256:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="File integrity check failed")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )


@router.delete("/api/working-papers/{paper_id}", response_model=MessageOut)
def withdraw_working_paper(
    paper_id: int,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin)),
) -> MessageOut:
    """Withdraw (soft-delete) a working paper. The file and record are kept."""
    paper = db.get(WorkingPaper, paper_id)
    if paper is None or paper.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Working paper not found")
    audit = _get_audit_or_404(db, paper.audit_id)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_LOCKED)
    paper.is_deleted = True
    paper.deleted_by = user.id
    paper.deleted_at = utcnow()
    log_action(db, user_id=user.id, action=f"WORKING_PAPER_WITHDRAW id={paper_id}", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=paper.audit_id,
        user_id=user.id,
        action=f"WORKING PAPER WITHDRAWN {paper.title} v{paper.version_number}",
        request=request,
    )
    db.commit()
    return MessageOut(message=f"Working paper {paper_id} withdrawn (retained for the audit trail)")
