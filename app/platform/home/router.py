"""The home pad of Workspace Apps: the person's own tiles, or the organisation's default."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.permissions import has_perm
from app.platform.users.models import User

router = APIRouter(tags=["home"])


class PadIn(BaseModel):
    tiles: list[str] | None = Field(default=None, max_length=60)


@router.get("/api/home/pad")
def get_pad(user: User = Depends(require_active_user)) -> dict:
    """The person's home pad, the organisation's default, and whether they may change the default."""
    from app.platform.apps import registry

    mine = None
    if user.home_pad:
        try:
            mine = registry.clean_home(json.loads(user.home_pad))
        except ValueError:
            mine = None
    return {"mine": mine, "default": registry.settings()["home"],
            "can_set_default": has_perm(user, "system.superadmin")}


@router.put("/api/home/pad")
def put_pad(payload: PadIn, request: Request, db: DBSession = Depends(get_db),
            user: User = Depends(require_active_user)) -> dict:
    """Save the person's own arrangement; ``tiles: null`` returns to the organisation's default."""
    from app.core.audit import log_action
    from app.platform.apps import registry

    tiles = registry.clean_home(payload.tiles)
    user.home_pad = json.dumps(tiles) if tiles else None
    log_action(db, user_id=user.id, request=request, action=f"HOME_PAD tiles={len(tiles or [])}")
    db.commit()
    return get_pad(user)

