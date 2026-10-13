"""Draft routes: autosave, restore and discard the current user's form drafts."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.schemas import MessageOut
from app.modules.drafts.models import FormDraft
from app.modules.drafts.schemas import DraftIn, DraftOut, DraftSummary
from app.modules.users.models import User

router = APIRouter(prefix="/api/drafts", tags=["drafts"])

MAX_DRAFT_BYTES = 256 * 1024
MAX_DRAFTS_PER_USER = 200
_KEY = re.compile(r"^[A-Za-z0-9:_.\-]{1,200}$")
# Never persist secrets, even if a client sends them.
_SECRET = re.compile(r"pass(word)?|secret|token", re.IGNORECASE)


def _check_key(form_key: str) -> None:
    if not _KEY.match(form_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid draft key")


def _out(draft: FormDraft) -> DraftOut:
    return DraftOut(
        form_key=draft.form_key,
        title=draft.title,
        record_type=draft.record_type,
        record_id=draft.record_id,
        payload=json.loads(draft.payload or "{}"),
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


def _mine(db: DBSession, user: User, form_key: str) -> FormDraft | None:
    return db.execute(
        select(FormDraft).where(FormDraft.user_id == user.id, FormDraft.form_key == form_key)
    ).scalar_one_or_none()


@router.get("", response_model=list[DraftSummary])
def list_drafts(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list[FormDraft]:
    return list(
        db.execute(
            select(FormDraft).where(FormDraft.user_id == user.id).order_by(FormDraft.updated_at.desc())
        ).scalars()
    )


@router.get("/{form_key}", response_model=DraftOut)
def get_draft(form_key: str, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> DraftOut:
    _check_key(form_key)
    draft = _mine(db, user, form_key)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No draft")
    return _out(draft)


@router.put("/{form_key}", response_model=DraftOut)
def save_draft(
    form_key: str, payload: DraftIn, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> DraftOut:
    """Create or replace the draft. Deliberately *not* validated: a draft holds
    whatever the user typed, complete or not, so nothing is ever lost."""
    _check_key(form_key)
    clean = {k: v for k, v in payload.payload.items() if not _SECRET.search(k)}
    body = json.dumps(clean, ensure_ascii=False, default=str)
    if len(body.encode("utf-8")) > MAX_DRAFT_BYTES:
        raise HTTPException(status_code=413, detail="Draft is too large (limit 256 KB)")
    draft = _mine(db, user, form_key)
    if draft is None:
        count = len(db.execute(select(FormDraft.id).where(FormDraft.user_id == user.id)).all())
        if count >= MAX_DRAFTS_PER_USER:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Too many open drafts; discard some")
        draft = FormDraft(user_id=user.id, form_key=form_key, payload=body)
        db.add(draft)
    draft.payload = body
    draft.title = payload.title
    draft.record_type = payload.record_type
    draft.record_id = payload.record_id
    db.commit()
    db.refresh(draft)
    return _out(draft)


@router.delete("/{form_key}", response_model=MessageOut)
def discard_draft(
    form_key: str, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> MessageOut:
    _check_key(form_key)
    draft = _mine(db, user, form_key)
    if draft is not None:
        db.delete(draft)
        db.commit()
    return MessageOut(message="Draft discarded")
