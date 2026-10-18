"""Working paper routes: upload with automatic versioning, the GPHA template form, download, withdraw.

Evidence handling:

* uploads are streamed in chunks and rejected as soon as they exceed the size
  limit; only allow-listed file extensions are accepted;
* every file gets a SHA-256 integrity hash and is stored encrypted at rest
  (``app.core.crypto``); legacy plaintext files remain downloadable;
* a paper may be the GPHA template form alone (no file) or a file with the form; a new version carries the
  previous version's form forward;
* papers are never physically deleted - an Admin can *withdraw* one, which
  hides it from normal views but keeps the file, the row and the trail.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import quote

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, is_privileged
from app.core.audit import log_action
from app.core.config import settings
from app.core.crypto import encrypt
from app.core.database import get_db
from app.core.deps import require_active_user, require_role
from app.core.enums import AuditStatus, Role, utcnow
from app.core.history import log_record_history
from app.core.schemas import MessageOut
from app.domains.audit.audits import wp_template
from app.domains.audit.audits.models import Audit, Finding, WorkingPaper
from app.domains.audit.audits.schemas import WorkingPaperOut
from app.platform.users.models import User
from app.services.documents import storage

router = APIRouter(tags=["working-papers"])

_CHUNK = 1024 * 1024
_LOCKED = "The audit is closed; working papers are locked"


async def _read_upload(file: UploadFile) -> tuple[bytes, str, str]:
    """Read an upload under the upload policy (type, size, content). Returns (data, sha256, safe original name)."""
    from app.core.upload_policy import read_upload

    return await read_upload(file)


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
    file: UploadFile | None = File(None),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> WorkingPaper:
    from app.core.deps import ensure_perm

    ensure_perm(user, "audit.workpapers", "audit.fieldwork")
    audit = _get_audit_or_404(db, audit_id)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_LOCKED)

    data, digest_hex, original = (await _read_upload(file)) if file is not None and file.filename else (None, None, "")
    # Determine the next version for this (audit, title).
    current_max = db.execute(
        select(func.max(WorkingPaper.version_number)).where(
            WorkingPaper.audit_id == audit_id, WorkingPaper.title == title
        )
    ).scalar_one_or_none()
    version = (current_max or 0) + 1
    previous = db.execute(
        select(WorkingPaper).where(WorkingPaper.audit_id == audit_id, WorkingPaper.title == title,
                                   WorkingPaper.version_number == current_max)
    ).scalars().first() if current_max else None

    stored = ""
    if data is not None:
        folder = Path(settings.upload_dir) / str(audit_id)
        folder.mkdir(parents=True, exist_ok=True)
        stored_path = folder / f"{uuid.uuid4().hex}_{original}.enc"
        async with aiofiles.open(stored_path, "wb") as out:
            await out.write(encrypt(data))
        stored = str(stored_path.relative_to(Path(settings.upload_dir)))

    paper = WorkingPaper(
        audit_id=audit_id,
        title=title,
        file_path=stored,
        version_number=version,
        uploaded_by=user.id,
        encrypted=data is not None,
        sha256=digest_hex,
        template=previous.template if previous is not None else None,
        wp_ref=previous.wp_ref if previous is not None else None,
        test_id=previous.test_id if previous is not None else None,
        finding_id=previous.finding_id if previous is not None else None,
    )
    db.add(paper)
    db.flush()
    log_action(
        db,
        user_id=user.id,
        action=f"WORKING_PAPER_UPLOAD id={paper.id} audit={audit_id} title={title} v{version} "
        f"sha256={paper.sha256 or 'no file'}",
        request=request,
    )
    log_record_history(
        db,
        record_type="audit",
        record_id=audit_id,
        user_id=user.id,
        action=f"WORKING PAPER {'UPLOADED' if data is not None else 'CREATED (template form)'} {title} v{version}",
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
    if not paper.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="This working paper is a template form with no attached file")
    data = storage.read_verified(paper.file_path, paper.sha256, encrypted=paper.encrypted)
    name = _download_name(paper)
    log_action(db, user_id=user.id, action=f"WORKING_PAPER_DOWNLOAD id={paper.id}", request=request)
    db.commit()
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


# --------------------------------------------------------------------------- GPHA working paper template


class TemplateIn(BaseModel):
    values: dict[str, str | None]


def _person(db: DBSession, uid: int | None) -> str | None:
    u = db.get(User, uid) if uid else None
    return (u.full_name or u.username) if u else None


def _template_out(db: DBSession, paper: WorkingPaper, user: User) -> dict:
    from app.core import permissions as perms
    from app.core.review_chain import label, trail

    audit = db.get(Audit, paper.audit_id)
    values = wp_template.load(paper.template)
    done, total = wp_template.completeness(values)
    signs = trail(paper.review_trail)
    latest = db.execute(
        select(func.max(WorkingPaper.version_number)).where(
            WorkingPaper.audit_id == paper.audit_id, WorkingPaper.title == paper.title)
    ).scalar_one()
    finding = db.get(Finding, paper.finding_id) if paper.finding_id else None
    can_edit = (
        not paper.is_deleted and paper.version_number == latest and audit.status != AuditStatus.Closed
        and (paper.uploaded_by == user.id or perms.has_perm(user, "audit.workpapers"))
        and user.role in (Role.Admin, Role.Auditor)
    )
    return {
        "id": paper.id,
        "admin": {
            "audit_title": audit.title,
            "audit_reference": paper.wp_ref or "",
            "title": paper.title,
            "version": paper.version_number,
            "prepared_by": _person(db, paper.uploaded_by),
            "date_prepared": paper.uploaded_at.isoformat(),
            "reviewed_by": [{"level": t.get("level"), "name": t.get("name"), "at": t.get("at"),
                             "acting_as": t.get("acting_as")} for t in signs]
            or ([{"level": "Reviewer", "name": _person(db, paper.reviewed_by),
                  "at": paper.reviewed_at.isoformat() if paper.reviewed_at else None, "acting_as": None}]
                if paper.reviewed_by else []),
            "date_reviewed": paper.reviewed_at.isoformat() if paper.reviewed_at else None,
            "review_stage": label(paper.review_stage) if paper.review_stage else None,
            "has_file": bool(paper.file_path),
            "linked_finding": {"id": finding.id, "title": finding.title} if finding else None,
        },
        "fields": [{"key": k, "label": lbl, "kind": kind, "help": hlp,
                    "section": "admin" if (k, lbl, kind, hlp) in wp_template.ADMIN_FIELDS else "body"}
                   for k, lbl, kind, hlp in wp_template.FIELDS],
        "values": values,
        "locations": wp_template.locations(),
        "complete": done,
        "total": total,
        "can_edit": can_edit,
        "signed": bool(signs or paper.reviewed_at),
    }


@router.get("/api/working-papers/{paper_id}/template")
def get_template(paper_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    paper = db.get(WorkingPaper, paper_id)
    ensure_can_view(db, user, "working_paper", paper)
    return _template_out(db, paper, user)


@router.put("/api/working-papers/{paper_id}/template")
def save_template(
    paper_id: int,
    payload: TemplateIn,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(require_role(Role.Admin, Role.Auditor)),
) -> dict:
    """Fill in the GPHA working paper template. Changing a signed paper restarts its review chain."""
    paper = db.get(WorkingPaper, paper_id)
    ensure_can_view(db, user, "working_paper", paper)
    current = _template_out(db, paper, user)
    if not current["can_edit"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the latest version of a paper in an open audit can be edited, by its preparer or "
                   "working-paper staff",
        )
    values = wp_template.clean(payload.values)
    if values == current["values"]:
        return current
    changed = sorted(k for k in wp_template.KEYS if values.get(k) != current["values"].get(k))
    paper.template = wp_template.dump(values)
    restarted = current["signed"]
    if restarted:
        paper.review_trail, paper.review_stage, paper.reviewed_by, paper.reviewed_at = "[]", None, None, None
    log_action(db, user_id=user.id, request=request,
               action=f"WORKING_PAPER_TEMPLATE id={paper.id} [{','.join(changed)}]"[:490])
    log_record_history(
        db, record_type="audit", record_id=paper.audit_id, user_id=user.id, request=request,
        action=(f"WORKING PAPER FORM UPDATED {paper.wp_ref or ''} {paper.title} v{paper.version_number}"
                + ("; review sign-offs cleared, review restarts" if restarted else "")).replace("  ", " "),
    )
    db.commit()
    db.refresh(paper)
    out = _template_out(db, paper, user)
    out["review_restarted"] = restarted
    return out
