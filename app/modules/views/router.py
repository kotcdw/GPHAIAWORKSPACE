"""Saved list views (per user, per module)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.errors import field_error
from app.modules.users.models import User
from app.modules.views.models import SavedView

router = APIRouter(prefix="/api/views", tags=["saved views"])


class ViewIn(BaseModel):
    module: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(..., min_length=1, max_length=100)
    params: dict[str, str] = Field(default_factory=dict)

    @field_validator("params")
    @classmethod
    def _small(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20 or any(len(k) > 50 or len(str(x)) > 200 for k, x in v.items()):
            raise ValueError("too many or too long filter values")
        return {k: str(x) for k, x in v.items() if str(x) != ""}


class ViewOut(BaseModel):
    id: int
    module: str
    name: str
    params: dict[str, str]


def _out(v: SavedView) -> ViewOut:
    return ViewOut(id=v.id, module=v.module, name=v.name, params=json.loads(v.params or "{}"))


@router.get("", response_model=list[ViewOut])
def list_views(
    module: str, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> list[ViewOut]:
    rows = db.execute(
        select(SavedView).where(SavedView.user_id == user.id, SavedView.module == module).order_by(SavedView.name)
    ).scalars()
    return [_out(v) for v in rows]


@router.post("", response_model=ViewOut, status_code=status.HTTP_201_CREATED)
def save_view(
    payload: ViewIn, request: Request, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> ViewOut:
    name = payload.name.strip()
    if not name:
        raise field_error("name", "must not be empty")
    v = db.execute(
        select(SavedView).where(
            SavedView.user_id == user.id, SavedView.module == payload.module, SavedView.name == name
        )
    ).scalar_one_or_none()
    if v is None:
        count = len(
            db.execute(
                select(SavedView.id).where(SavedView.user_id == user.id, SavedView.module == payload.module)
            ).all()
        )
        if count >= 25:
            raise field_error("name", "you can keep up to 25 saved views per list")
        v = SavedView(user_id=user.id, module=payload.module, name=name)
        db.add(v)
    v.params = json.dumps(payload.params)
    db.flush()
    log_action(db, user_id=user.id, action=f"VIEW_SAVE module={payload.module} name={name[:40]}", request=request)
    db.commit()
    return _out(v)


@router.delete("/{view_id}")
def delete_view(
    view_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> dict:
    v = db.get(SavedView, view_id)
    if v is None or v.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
    db.delete(v)
    log_action(db, user_id=user.id, action=f"VIEW_DELETE id={view_id}", request=request)
    db.commit()
    return {"message": "Saved view deleted"}
