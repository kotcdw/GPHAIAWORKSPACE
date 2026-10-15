"""Evidence requests: auditors request documents, the assigned auditee uploads and submits them,
the auditor accepts (optionally filing them as working papers) or returns them for more."""

from __future__ import annotations

import hashlib
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view, is_privileged
from app.core.audit import log_action
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import ensure_perm, require_active_user
from app.core.enums import AuditStatus, Role, utcnow
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.permissions import has_perm
from app.core.refs import next_reference
from app.domains.audit.audits.models import Audit, AuditAuditee, WorkingPaper
from app.domains.audit.evidence.models import EvidenceFile, EvidenceRequest
from app.platform.notifications.service import notify
from app.platform.users.models import User
from app.services.documents import storage

router = APIRouter(tags=["evidence requests"])
Active = Depends(require_active_user)
OPEN = ("Requested", "Returned")
_CHUNK = 1024 * 1024


class RequestIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field("", max_length=8000)
    assignee_id: int
    due_date: datetime | None = None


class SubmitIn(BaseModel):
    response: str = Field("", max_length=8000)


class ReviewIn(BaseModel):
    decision: str
    comment: str = Field("", max_length=4000)
    file_as_working_paper: bool = False


class FileOut(BaseModel):
    id: int
    filename: str
    size_bytes: int
    sha256: str
    uploaded_at: datetime


class RequestOut(BaseModel):
    id: int
    request_ref: str
    audit_id: int
    audit_ref: str | None = None
    audit_title: str | None = None
    title: str
    description: str
    assignee_id: int | None
    assignee_name: str | None
    due_date: datetime | None
    status: str
    overdue: bool
    response: str | None
    review_comment: str | None
    requested_by_name: str | None
    requested_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    files: list[FileOut]
    can_respond: bool
    can_review: bool


def _name(db: DBSession, uid: int | None) -> str | None:
    u = db.get(User, uid) if uid else None
    return (u.full_name or u.username) if u else None


def _out(db: DBSession, r: EvidenceRequest, user: User) -> RequestOut:
    audit = db.get(Audit, r.audit_id)
    return RequestOut(
        id=r.id, request_ref=r.request_ref, audit_id=r.audit_id, audit_ref=getattr(audit, "audit_ref", None),
        audit_title=audit.title if audit else None, title=r.title, description=r.description,
        assignee_id=r.assignee_id, assignee_name=_name(db, r.assignee_id), due_date=r.due_date, status=r.status,
        overdue=bool(r.due_date and r.status in OPEN and r.due_date < utcnow()), response=r.response,
        review_comment=r.review_comment, requested_by_name=_name(db, r.requested_by), requested_at=r.requested_at,
        submitted_at=r.submitted_at, reviewed_at=r.reviewed_at,
        files=[FileOut(id=f.id, filename=f.filename, size_bytes=f.size_bytes, sha256=f.sha256,
                       uploaded_at=f.uploaded_at) for f in r.files],
        can_respond=r.assignee_id == user.id and r.status in OPEN,
        can_review=is_privileged(user) and has_perm(user, "audit.evidence") and r.status == "Submitted",
    )


def _load(db: DBSession, request_id: int, user: User) -> EvidenceRequest:
    r = db.get(EvidenceRequest, request_id)
    if r is None or not (is_privileged(user) or r.assignee_id == user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence request not found")
    return r


def _audit(db: DBSession, audit_id: int) -> Audit:
    audit = db.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


@router.get("/api/audits/{audit_id}/evidence-requests", response_model=list[RequestOut])
def list_for_audit(audit_id: int, db: DBSession = Depends(get_db), user: User = Active) -> list[RequestOut]:
    ensure_can_view(db, user, "audit", db.get(Audit, audit_id))
    stmt = select(EvidenceRequest).where(EvidenceRequest.audit_id == audit_id).order_by(EvidenceRequest.id.desc())
    if not is_privileged(user):
        stmt = stmt.where(EvidenceRequest.assignee_id == user.id)
    return [_out(db, r, user) for r in db.execute(stmt).scalars()]


@router.get("/api/evidence-requests", response_model=list[RequestOut])
def my_requests(scope: str = Query("mine", pattern="^(mine|open|overdue)$"), db: DBSession = Depends(get_db),
                user: User = Active) -> list[RequestOut]:
    """mine: requests assigned to me (auditee) or raised by me (staff); open / overdue: all open (staff)."""
    stmt = select(EvidenceRequest).order_by(EvidenceRequest.due_date.is_(None), EvidenceRequest.due_date)
    if scope == "mine" or not is_privileged(user):
        if is_privileged(user):
            stmt = stmt.where(EvidenceRequest.requested_by == user.id, EvidenceRequest.status != "Cancelled")
        else:
            stmt = stmt.where(EvidenceRequest.assignee_id == user.id, EvidenceRequest.status != "Cancelled")
    else:
        stmt = stmt.where(EvidenceRequest.status.in_((*OPEN, "Submitted")))
    found = list(db.execute(stmt).scalars())
    if is_privileged(user):  # staff: only requests of audits in their port/team scope
        from app.core.access import staff_audit_scope

        allowed = staff_audit_scope(db, user)
        if allowed is not None:
            found = [r for r in found if r.audit_id in allowed]
    rows = [_out(db, r, user) for r in found]
    if scope == "overdue":
        rows = [r for r in rows if r.overdue]
    return rows


@router.get("/api/evidence-requests/{request_id}", response_model=RequestOut)
def get_request(request_id: int, db: DBSession = Depends(get_db), user: User = Active) -> RequestOut:
    return _out(db, _load(db, request_id, user), user)


@router.post("/api/audits/{audit_id}/evidence-requests", response_model=RequestOut,
             status_code=status.HTTP_201_CREATED)
def create_request(audit_id: int, payload: RequestIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Active) -> RequestOut:
    if not is_privileged(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    ensure_perm(user, "audit.evidence")
    audit = _audit(db, audit_id)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed")
    assignee = db.get(User, payload.assignee_id)
    if assignee is None or not assignee.is_active:
        raise field_error("assignee_id", "is not an active user")
    if assignee.role == Role.Auditee and db.get(AuditAuditee, (audit_id, assignee.id)) is None:
        raise field_error("assignee_id", "must be an auditee assigned to this audit")
    if assignee.role == Role.Committee:
        raise field_error("assignee_id", "cannot be an Audit Committee member")
    if payload.due_date and payload.due_date.date() < utcnow().date():
        raise field_error("due_date", "cannot be in the past")
    r = EvidenceRequest(request_ref=next_reference(db, "ER"), audit_id=audit_id, title=payload.title.strip(),
                        description=payload.description, assignee_id=assignee.id, due_date=payload.due_date,
                        requested_by=user.id)
    db.add(r)
    db.flush()
    due = f" by {payload.due_date:%d %b %Y}" if payload.due_date else ""
    notify(db, assignee.id, f"Evidence requested: {r.title}",
           f"{_name(db, user.id)} requested evidence for audit {audit.title}{due}.", link_type="evidence",
           link_id=r.id)
    log_action(db, user_id=user.id, action=f"EVIDENCE_REQUEST {r.request_ref} audit={audit_id}", request=request)
    log_record_history(db, record_type="audit", record_id=audit_id, user_id=user.id,
                       action=f"EVIDENCE REQUESTED {r.request_ref} {r.title}", request=request)
    db.commit()
    return _out(db, r, user)


@router.post("/api/evidence-requests/{request_id}/files", response_model=RequestOut)
async def upload_file(request_id: int, request: Request, file: UploadFile = File(...),
                      db: DBSession = Depends(get_db), user: User = Active) -> RequestOut:
    r = _load(db, request_id, user)
    if r.assignee_id != user.id and not has_perm(user, "audit.evidence"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assignee can add files")
    if r.status not in OPEN:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"The request is {r.status}")
    original = storage.safe_name(file.filename)
    storage.check_extension(original)
    limit = settings.max_upload_mb * 1024 * 1024
    digest, chunks, size = hashlib.sha256(), [], 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"File exceeds the {settings.max_upload_mb} MB limit")
        digest.update(chunk)
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty")
    path, sha = storage.store_encrypted(b"".join(chunks), f"{r.audit_id}/evidence", original)
    f = EvidenceFile(request_id=r.id, filename=original, file_path=path, sha256=sha, size_bytes=size,
                     uploaded_by=user.id)
    db.add(f)
    log_action(db, user_id=user.id, action=f"EVIDENCE_FILE {r.request_ref} {original} sha256={f.sha256}",
               request=request)
    db.commit()
    db.refresh(r)
    return _out(db, r, user)


@router.get("/api/evidence-files/{file_id}/download")
def download_file(file_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Active) -> Response:
    f = db.get(EvidenceFile, file_id)
    if f is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    _load(db, f.request_id, user)
    data = storage.read_verified(f.file_path, f.sha256)
    log_action(db, user_id=user.id, action=f"EVIDENCE_DOWNLOAD file={f.id}", request=request)
    db.commit()
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f.filename)}"})


@router.post("/api/evidence-requests/{request_id}/submit", response_model=RequestOut)
def submit(request_id: int, payload: SubmitIn, request: Request, db: DBSession = Depends(get_db),
           user: User = Active) -> RequestOut:
    r = _load(db, request_id, user)
    if r.assignee_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assignee can submit")
    if user.role == Role.Auditee:
        ensure_perm(user, "auditee.respond")
    if r.status not in OPEN:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"The request is {r.status}")
    if not r.files and len(payload.response.strip()) < 5:
        raise field_error("response", "attach at least one file or explain why the evidence is not available")
    r.response = payload.response.strip()
    r.status = "Submitted"
    r.submitted_at = utcnow()
    notify(db, r.requested_by, f"Evidence submitted: {r.title}", f"{_name(db, user.id)} responded to {r.request_ref}.",
           link_type="evidence", link_id=r.id)
    log_action(db, user_id=user.id, action=f"EVIDENCE_SUBMIT {r.request_ref}", request=request)
    db.commit()
    return _out(db, r, user)


@router.post("/api/evidence-requests/{request_id}/review", response_model=RequestOut)
def review(request_id: int, payload: ReviewIn, request: Request, db: DBSession = Depends(get_db),
           user: User = Active) -> RequestOut:
    r = _load(db, request_id, user)
    if not is_privileged(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    ensure_perm(user, "audit.evidence")
    if r.status != "Submitted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only submitted evidence can be reviewed")
    if payload.decision not in ("Accepted", "Returned"):
        raise field_error("decision", "must be Accepted or Returned")
    if payload.decision == "Returned" and len(payload.comment.strip()) < 5:
        raise field_error("comment", "say what is missing when returning evidence")
    r.status = payload.decision
    r.review_comment = payload.comment.strip() or None
    r.reviewed_by = user.id
    r.reviewed_at = utcnow()
    filed = 0
    if payload.decision == "Accepted" and payload.file_as_working_paper:
        audit = _audit(db, r.audit_id)
        if audit.status != AuditStatus.Closed:
            for f in r.files:
                title = f"{r.request_ref} {f.filename}"[:255]
                version = (db.execute(select(func.max(WorkingPaper.version_number)).where(
                    WorkingPaper.audit_id == r.audit_id, WorkingPaper.title == title)).scalar_one_or_none() or 0) + 1
                db.add(WorkingPaper(audit_id=r.audit_id, title=title, file_path=f.file_path, version_number=version,
                                    uploaded_by=f.uploaded_by, encrypted=True, sha256=f.sha256))
                filed += 1
    notify(db, r.assignee_id, f"Evidence {payload.decision.lower()}: {r.title}",
           r.review_comment or f"{r.request_ref} was {payload.decision.lower()}.", link_type="evidence", link_id=r.id)
    log_action(db, user_id=user.id, action=f"EVIDENCE_{payload.decision.upper()} {r.request_ref} filed={filed}",
               request=request)
    log_record_history(db, record_type="audit", record_id=r.audit_id, user_id=user.id,
                       action=f"EVIDENCE {payload.decision.upper()} {r.request_ref}"
                              + (f" ({filed} filed as working papers)" if filed else ""), request=request)
    db.commit()
    return _out(db, r, user)


@router.post("/api/evidence-requests/{request_id}/cancel", response_model=RequestOut)
def cancel(request_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Active) -> RequestOut:
    r = _load(db, request_id, user)
    if not is_privileged(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    ensure_perm(user, "audit.evidence")
    if r.status in ("Accepted", "Cancelled"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"The request is already {r.status}")
    r.status = "Cancelled"
    log_action(db, user_id=user.id, action=f"EVIDENCE_CANCEL {r.request_ref}", request=request)
    db.commit()
    return _out(db, r, user)


def overdue_count(db: DBSession, user: User) -> int:
    """Open requests past due assigned to (auditee) or raised by (staff) ``user``."""
    col = EvidenceRequest.requested_by if is_privileged(user) else EvidenceRequest.assignee_id
    return db.execute(select(func.count()).select_from(EvidenceRequest).where(
        col == user.id, EvidenceRequest.status.in_(OPEN), EvidenceRequest.due_date < utcnow())).scalar_one()

