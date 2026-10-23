"""Videos on presentation slides (Present Builder › Images / Video).

Videos are uploaded (MP4 or WebM, within the attachment size limit), checked by content and stored with the other
uploads under a random name. They are served from this application only, to their uploader or to anyone who can
open an item that shows them.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.upload_policy import max_bytes, max_mb, safe_name
from app.platform.users.models import User
from app.services.reporting.models import ReportItem, ReportMedia
from app.services.reporting.router import _visible
from app.services.reporting.sharing import ensure_staff

router = APIRouter(prefix="/api/reporting", tags=["reporting"])

VIDEO_TYPES = {".mp4": "video/mp4", ".webm": "video/webm"}
_CHUNK = 1024 * 1024


def media_dir() -> Path:
    d = Path(settings.upload_dir) / "reporting"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_video(data: bytes, suffix: str) -> bool:
    if suffix == ".mp4":
        return data[4:8] == b"ftyp"
    return data[:4] == b"\x1a\x45\xdf\xa3"  # WebM / Matroska (EBML)


def media_path(m: ReportMedia) -> Path:
    return media_dir() / m.stored_name


def video_ids(definition: dict) -> set[int]:
    pages = definition.get("tabs") or definition.get("slides") or []
    return {w["video_id"] for p in pages for w in p.get("widgets", [])
            if w.get("type") == "video" and w.get("video_id")}


def can_see(db: DBSession, user: User, m: ReportMedia) -> bool:
    if m.owner_id == user.id:
        return True
    for it in db.execute(select(ReportItem).where(ReportItem.kind.in_(("dashboard", "presentation")),
                                                  ReportItem.archived.is_(False))).scalars():
        if m.id in video_ids(json.loads(it.definition or "{}")) and _visible(db, user, it):
            return True
    return False


@router.post("/media", status_code=201)
async def upload_video(request: Request, file: UploadFile = File(...), db: DBSession = Depends(get_db),
                       user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    name = safe_name(file.filename)
    suffix = Path(name).suffix.lower()
    if suffix not in VIDEO_TYPES:
        raise HTTPException(status_code=415, detail="Choose an MP4 or WebM video")
    limit, size, digest, chunks = max_bytes(), 0, hashlib.sha256(), []
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"The video exceeds the {max_mb()} MB limit")
        digest.update(chunk)
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data or not _is_video(data, suffix):
        raise HTTPException(status_code=415, detail=f"The file's content is not a {suffix[1:].upper()} video")
    stored = f"{uuid.uuid4().hex}{suffix}"
    (media_dir() / stored).write_bytes(data)
    m = ReportMedia(owner_id=user.id, filename=name, content_type=VIDEO_TYPES[suffix], size=size, stored_name=stored,
                    sha256=digest.hexdigest())
    db.add(m)
    db.flush()
    log_action(db, user_id=user.id, request=request, action=f"REPORTING_MEDIA_UPLOAD id={m.id} bytes={size}")
    db.commit()
    return {"id": m.id, "filename": m.filename, "size": m.size, "content_type": m.content_type,
            "url": f"/api/reporting/media/{m.id}"}


@router.get("/media/{media_id}")
def get_video(media_id: int, db: DBSession = Depends(get_db),
              user: User = Depends(require_active_user)) -> FileResponse:
    ensure_staff(user)
    m = db.get(ReportMedia, media_id)
    if m is None or not can_see(db, user, m) or not media_path(m).is_file():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(media_path(m), media_type=m.content_type, filename=m.filename,
                        content_disposition_type="inline", headers={"Cache-Control": "private, max-age=3600"})
