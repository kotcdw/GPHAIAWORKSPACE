"""Follow-up of a remediation action beyond implement/validate: timeline, evidence files, reopening,
risk acceptance and the aging report (IIA GIAS 15.2 - monitoring the implementation of action plans)."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.access import _same_email, ensure_can_view, is_privileged, visible
from app.core.audit import log_action
from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier, require_perm
from app.core.enums import CapaStatus, Role, utcnow
from app.core.history import log_record_history
from app.core.schemas import MessageOut
from app.domains.audit.audits.working_papers import _read_upload
from app.domains.issues.capa.models import Capa, CapaFile
from app.domains.issues.capa.schemas import CapaOut
from app.domains.issues.capa.status import PARTIALLY
from app.domains.issues.capa.timeline import add_event, events
from app.platform.notifications.service import notify_many, user_id_by_email
from app.platform.users.models import User

router = APIRouter(tags=["follow-up"])
Staff = Depends(require_module_tier("follow-up", Role.Admin, Role.Auditor))

KIND_LABELS = {
    "created": "Action raised", "progress": "Progress update", "implementation": "Implementation recorded",
    "evidence_file": "Evidence file", "validation": "Auditor validation", "extension": "Target date revised",
    "escalation": "Escalated", "reopened": "Reopened", "risk_accepted": "Risk accepted",
    "withdrawal": "Withdrawal", "closed": "Closed", "note": "Note",
}


def _load(db: DBSession, capa_id: int, user: User) -> Capa:
    capa = db.get(Capa, capa_id)
    if capa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remediation not found")
    ensure_can_view(db, user, "capa", capa)
    return capa


def _names(db: DBSession, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: (u.full_name or u.username) for u in db.execute(select(User).where(User.id.in_(ids))).scalars()}


# --------------------------------------------------------------------------- timeline

class EventOut(BaseModel):
    id: int
    kind: str
    label: str
    text: str | None
    user: str | None
    old_due_date: datetime | None
    new_due_date: datetime | None
    created_at: datetime


@router.get("/api/capa/{capa_id}/timeline", response_model=list[EventOut])
def timeline(capa_id: int, db: DBSession = Depends(get_db),
             user: User = Depends(require_active_user)) -> list[EventOut]:
    """Everything that happened to the action, oldest first. Append-only: nothing here can be edited."""
    _load(db, capa_id, user)
    rows = events(db, capa_id)
    names = _names(db, {e.user_id for e in rows})
    return [EventOut(id=e.id, kind=e.kind, label=KIND_LABELS.get(e.kind, e.kind.title()), text=e.text,
                     user=names.get(e.user_id) if e.user_id else ("System" if e.kind == "escalation" else None),
                     old_due_date=e.old_due_date, new_due_date=e.new_due_date, created_at=e.created_at)
            for e in rows]


# --------------------------------------------------------------------------- evidence files

class FileOut(BaseModel):
    id: int
    original_name: str
    size_bytes: int
    sha256: str
    uploaded_by: str | None
    uploaded_at: datetime


def _can_contribute(user: User, capa: Capa) -> bool:
    return is_privileged(user) or _same_email(capa.owner_email, user.email)


@router.get("/api/capa/{capa_id}/files", response_model=list[FileOut])
def list_files(capa_id: int, db: DBSession = Depends(get_db),
               user: User = Depends(require_active_user)) -> list[FileOut]:
    _load(db, capa_id, user)
    rows = list(db.execute(select(CapaFile).where(CapaFile.capa_id == capa_id, CapaFile.is_deleted.is_(False))
                           .order_by(CapaFile.uploaded_at)).scalars())
    names = _names(db, {f.uploaded_by for f in rows})
    return [FileOut(id=f.id, original_name=f.original_name, size_bytes=f.size_bytes, sha256=f.sha256,
                    uploaded_by=names.get(f.uploaded_by), uploaded_at=f.uploaded_at) for f in rows]


@router.post("/api/capa/{capa_id}/files", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(capa_id: int, request: Request, file: UploadFile = File(...), db: DBSession = Depends(get_db),
                      user: User = Depends(require_active_user)) -> FileOut:
    """The action owner (or audit staff) attaches evidence of implementation. Stored encrypted, with SHA-256."""
    capa = _load(db, capa_id, user)
    if not _can_contribute(user, capa):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the action owner or audit staff "
                                                                          "can attach evidence")
    if capa.status == CapaStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The action is closed")
    data, digest, original = await _read_upload(file)
    folder = Path(settings.upload_dir) / "remediation" / str(capa.id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}.enc"
    async with aiofiles.open(stored, "wb") as out:
        await out.write(encrypt(data))
    relative = str(stored.relative_to(Path(settings.upload_dir)))
    row = CapaFile(capa_id=capa.id, original_name=original, file_path=relative,
                   size_bytes=len(data), sha256=digest, uploaded_by=user.id, uploaded_at=utcnow())
    db.add(row)
    db.flush()
    add_event(db, capa, "evidence_file", user_id=user.id, request=request,
              text=f"{original} ({len(data) // 1024 or 1} KB, SHA-256 {digest[:12]}...)")
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user.id, request=request,
                       action=f"EVIDENCE FILE {original}")
    log_action(db, user_id=user.id, request=request,
               action=f"REMEDIATION_EVIDENCE_UPLOAD id={capa.id} file={row.id} name={original} sha256={digest}")
    db.commit()
    return FileOut(id=row.id, original_name=row.original_name, size_bytes=row.size_bytes, sha256=row.sha256,
                   uploaded_by=user.full_name or user.username, uploaded_at=row.uploaded_at)


@router.get("/api/capa-files/{file_id}/download")
def download_file(file_id: int, request: Request, db: DBSession = Depends(get_db),
                  user: User = Depends(require_active_user)) -> Response:
    row = db.get(CapaFile, file_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    _load(db, row.capa_id, user)
    path = Path(settings.upload_dir) / row.file_path
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The stored file is missing")
    data = decrypt(path.read_bytes())
    log_action(db, user_id=user.id, request=request, commit=True,
               action=f"REMEDIATION_EVIDENCE_DOWNLOAD id={row.capa_id} file={row.id} name={row.original_name}")
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.original_name)}"})


@router.delete("/api/capa-files/{file_id}", response_model=MessageOut)
def withdraw_file(file_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> MessageOut:
    """Withdraw a file uploaded by mistake: hidden from the action, kept on disk and in the trail."""
    row = db.get(CapaFile, file_id)
    if row is None or row.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    capa = _load(db, row.capa_id, user)
    if capa.status == CapaStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The action is closed; its evidence is kept")
    row.is_deleted, row.deleted_by, row.deleted_at = True, user.id, utcnow()
    add_event(db, capa, "evidence_file", user_id=user.id, request=request, text=f"Withdrawn: {row.original_name}")
    log_action(db, user_id=user.id, request=request,
               action=f"REMEDIATION_EVIDENCE_WITHDRAW id={capa.id} file={row.id} name={row.original_name}")
    db.commit()
    return MessageOut(message=f"{row.original_name} withdrawn")


# --------------------------------------------------------------------------- reopen and risk acceptance

class ReasonIn(BaseModel):
    reason: str = Field(min_length=20, max_length=5000)


class RiskAcceptIn(BaseModel):
    reason: str = Field(min_length=20, max_length=5000)
    accepted_by: str = Field(min_length=3, max_length=255,
                             description="The manager who accepts the residual risk (name and position)")


def _reopen_finding(db: DBSession, capa: Capa, user: User, request: Request) -> None:
    if capa.source_type == "finding":
        from app.domains.issues.capa.closure import sync_finding

        db.flush()
        sync_finding(db, capa.source_id, user.id, request)


@router.post("/api/capa/{capa_id}/reopen", response_model=CapaOut)
def reopen(capa_id: int, payload: ReasonIn, request: Request, db: DBSession = Depends(get_db),
           user: User = Depends(require_perm("followup.manage"))) -> Capa:
    """Reopen a closed action (for example the problem recurred, or the closure was based on wrong evidence)."""
    capa = _load(db, capa_id, user)
    if capa.status != CapaStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a closed action can be reopened")
    capa.status = CapaStatus.InProgress
    capa.implementation_status = PARTIALLY
    capa.reopen_count = (capa.reopen_count or 0) + 1
    capa.closed_by = capa.closed_at = None
    capa.validation_result = capa.validated_by = capa.validated_at = None
    capa.risk_accepted_by = capa.risk_accepted_at = None
    capa.escalation_level = 0
    reason = payload.reason.strip()
    add_event(db, capa, "reopened", user_id=user.id, text=reason, request=request)
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user.id, request=request,
                       action=f"REOPENED ({reason[:300]})")
    log_action(db, user_id=user.id, request=request, action=f"REMEDIATION_REOPEN id={capa.id} ref={capa.capa_ref}")
    notify_many(db, [user_id_by_email(db, capa.owner_email), capa.created_by], f"Action reopened: {capa.capa_ref}",
                reason, link_type="capa", link_id=capa.id)
    _reopen_finding(db, capa, user, request)
    db.commit()
    db.refresh(capa)
    return capa


@router.post("/api/capa/{capa_id}/accept-risk", response_model=CapaOut)
def accept_risk(capa_id: int, payload: RiskAcceptIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(require_perm("followup.manage"))) -> Capa:
    """Close the action because management formally accepts the residual risk instead of implementing it.
    Recorded with who accepted it, why, and who in Internal Audit approved the closure."""
    from app.domains.issues.capa.status import RISK_ACCEPTED

    capa = _load(db, capa_id, user)
    if capa.status == CapaStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The action is already closed")
    if capa.created_by == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Segregation of duties: the person who raised the action cannot approve "
                                   "its closure by risk acceptance")
    text = f"Accepted by {payload.accepted_by.strip()}: {payload.reason.strip()}"
    capa.status = CapaStatus.Closed
    capa.implementation_status = RISK_ACCEPTED
    capa.risk_acceptance = text
    capa.risk_accepted_by = user.id
    capa.risk_accepted_at = utcnow()
    capa.closed_by = user.id
    capa.closed_at = utcnow()
    add_event(db, capa, "risk_accepted", user_id=user.id, text=text, request=request)
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user.id, request=request,
                       action=f"CLOSED - RISK ACCEPTED by {payload.accepted_by.strip()[:120]}")
    log_action(db, user_id=user.id, request=request,
               action=f"REMEDIATION_ACCEPT_RISK id={capa.id} ref={capa.capa_ref}")
    _reopen_finding(db, capa, user, request)
    db.commit()
    db.refresh(capa)
    return capa


# --------------------------------------------------------------------------- aging report

BUCKETS = ("Not yet due", "1-30 days", "31-60 days", "61-90 days", "Over 90 days")


def _bucket(capa: Capa, now: datetime) -> str:
    if capa.due_date is None or capa.due_date >= now:
        return BUCKETS[0]
    days = (now - capa.due_date).days or 1
    return BUCKETS[1] if days <= 30 else BUCKETS[2] if days <= 60 else BUCKETS[3] if days <= 90 else BUCKETS[4]


class AgingRow(BaseModel):
    id: int
    capa_ref: str
    title: str
    owner_email: str | None
    severity: str
    status: str
    implementation_status: str
    original_due_date: datetime | None
    due_date: datetime | None
    extension_count: int
    days_open: int
    days_overdue: int
    bucket: str
    escalation_level: int


class AgingOut(BaseModel):
    buckets: dict[str, int]
    by_owner: list[dict]
    rows: list[AgingRow]


def _aging_rows(db: DBSession, user: User) -> list[AgingRow]:
    now = utcnow()
    open_actions = visible(db, user, "capa", list(db.execute(
        select(Capa).where(Capa.status != CapaStatus.Closed).order_by(Capa.due_date)).scalars()))
    rows = []
    for c in open_actions:
        overdue = max((now - c.due_date).days, 1) if c.due_date and c.due_date < now else 0
        rows.append(AgingRow(id=c.id, capa_ref=c.capa_ref, title=c.title, owner_email=c.owner_email,
                             severity=c.severity.value, status=c.status.value,
                             implementation_status=c.implementation_status, original_due_date=c.original_due_date,
                             due_date=c.due_date, extension_count=c.extension_count or 0,
                             days_open=(now - c.created_at).days, days_overdue=overdue, bucket=_bucket(c, now),
                             escalation_level=c.escalation_level or 0))
    return rows


@router.get("/api/followup/aging", response_model=AgingOut)
def aging(db: DBSession = Depends(get_db), user: User = Staff) -> AgingOut:
    """Open actions by how long they are overdue, and by owner."""
    rows = _aging_rows(db, user)
    buckets = {b: 0 for b in BUCKETS}
    owners: dict[str, dict] = {}
    for r in rows:
        buckets[r.bucket] += 1
        o = owners.setdefault(r.owner_email or "Not assigned",
                              {"owner": r.owner_email or "Not assigned", "open": 0, "overdue": 0, "extended": 0})
        o["open"] += 1
        o["overdue"] += 1 if r.days_overdue else 0
        o["extended"] += 1 if r.extension_count else 0
    by_owner = sorted(owners.values(), key=lambda o: (-o["overdue"], -o["open"], o["owner"]))
    return AgingOut(buckets=buckets, by_owner=by_owner, rows=rows)


@router.get("/api/followup/aging.csv")
def aging_csv(request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> Response:
    from app.core.deps import ensure_perm

    ensure_perm(user, "data.export")
    rows = _aging_rows(db, user)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Reference", "Action", "Owner", "Severity", "Status", "Implementation", "Original target date",
                     "Current target date", "Extensions", "Days open", "Days overdue", "Aging", "Escalation level"])
    for r in rows:
        writer.writerow([r.capa_ref, r.title, r.owner_email or "", r.severity, r.status, r.implementation_status,
                         f"{r.original_due_date:%Y-%m-%d}" if r.original_due_date else "",
                         f"{r.due_date:%Y-%m-%d}" if r.due_date else "", r.extension_count, r.days_open,
                         r.days_overdue, r.bucket, r.escalation_level])
    log_action(db, user_id=user.id, request=request, commit=True, action=f"FOLLOWUP_AGING_EXPORT rows={len(rows)}")
    return Response(content="﻿" + out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="followup-aging-{utcnow():%Y%m%d}.csv"'})
