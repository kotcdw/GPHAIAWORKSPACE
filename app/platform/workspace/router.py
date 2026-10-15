"""Workspace (home page) that hosts the apps.

* **Favourite apps**: each person pins apps and orders them; new users start from the defaults for their role.
* **Recently opened**: the last apps a person opened (kept on the server, so it follows them across browsers).
* **Defaults per role**: the Super Administrator chooses which apps are pinned for new users of each role
  (Configuration > Apps & customization > Workspace defaults). Apps switched off never show.
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import AppConfig, invalidate
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_perm
from app.core.enums import Role, utcnow
from app.core.errors import field_error
from app.platform.users.models import User
from app.platform.workspace.models import UserWorkspace

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

KEY = "workspace_defaults"
MAX_FAVORITES = 16
MAX_RECENT = 8
_VIEW = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
TIERS = (Role.Admin.value, Role.Auditor.value, Role.Auditee.value, Role.Committee.value)
BUILT_IN = {
    Role.Admin.value: ["audits", "issues", "plans", "configuration", "profile", "roles"],
    Role.Auditor.value: ["audits", "issues", "portal", "tasks", "plans", "capacity"],
    Role.Auditee.value: ["portal", "issues", "evidence"],
    Role.Committee.value: ["committee", "governance", "storyboards"],
}


def _views(values: list[str], limit: int, field: str) -> list[str]:
    out: list[str] = []
    for v in values:
        v = str(v).strip()
        if not _VIEW.match(v):
            raise field_error(field, f"'{v}' is not an app")
        if v not in out:
            out.append(v)
    if len(out) > limit:
        raise field_error(field, f"at most {limit} apps")
    return out


def role_defaults(db: DBSession) -> dict[str, list[str]]:
    row = db.get(AppConfig, KEY)
    saved = json.loads(row.value) if row else {}
    return {t: list(saved.get(t, BUILT_IN[t])) for t in TIERS}


def _row(db: DBSession, user: User) -> UserWorkspace:
    row = db.get(UserWorkspace, user.id)
    if row is None:
        tier = user.role.value if user.role.value in TIERS else Role.Auditor.value
        row = UserWorkspace(user_id=user.id, favorites=json.dumps(role_defaults(db)[tier]), recent="[]",
                            updated_at=utcnow())
        db.add(row)
        db.flush()
    return row


def _out(row: UserWorkspace) -> dict:
    return {"favorites": json.loads(row.favorites or "[]"), "recent": json.loads(row.recent or "[]")}


class FavoritesIn(BaseModel):
    favorites: list[str] = Field(default_factory=list, max_length=MAX_FAVORITES)


class RecentIn(BaseModel):
    view: str = Field(..., min_length=2, max_length=40)


class DefaultsIn(BaseModel):
    defaults: dict[str, list[str]] = Field(default_factory=dict)


@router.get("/me")
def my_workspace(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    row = _row(db, user)
    db.commit()
    return _out(row)


@router.put("/me/favorites")
def save_favorites(payload: FavoritesIn, db: DBSession = Depends(get_db),
                   user: User = Depends(require_active_user)) -> dict:
    row = _row(db, user)
    row.favorites = json.dumps(_views(payload.favorites, MAX_FAVORITES, "favorites"))
    row.updated_at = utcnow()
    db.commit()
    return _out(row)


@router.post("/me/recent")
def add_recent(payload: RecentIn, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    view = _views([payload.view], 1, "view")[0]
    row = _row(db, user)
    recent = [v for v in json.loads(row.recent or "[]") if v != view]
    row.recent = json.dumps([view, *recent][:MAX_RECENT])
    row.updated_at = utcnow()
    db.commit()
    return _out(row)


@router.post("/me/reset")
def reset_mine(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    row = _row(db, user)
    tier = user.role.value if user.role.value in TIERS else Role.Auditor.value
    row.favorites = json.dumps(role_defaults(db)[tier])
    db.commit()
    return _out(row)


@router.get("/defaults")
def get_defaults(db: DBSession = Depends(get_db), _: User = Depends(require_active_user)) -> dict:
    return {"defaults": role_defaults(db), "roles": list(TIERS)}


@router.put("/defaults")
def save_defaults(payload: DefaultsIn, request: Request, db: DBSession = Depends(get_db),
                  user: User = Depends(require_perm("system.superadmin"))) -> dict:
    current = role_defaults(db)
    for tier, views in payload.defaults.items():
        if tier not in TIERS:
            raise field_error("defaults", f"unknown role '{tier}'")
        current[tier] = _views(views, MAX_FAVORITES, f"defaults_{tier}")
    row = db.get(AppConfig, KEY)
    if row is None:
        db.add(AppConfig(key=KEY, value=json.dumps(current), updated_by=user.id))
    else:
        row.value, row.updated_by = json.dumps(current), user.id
    log_action(db, user_id=user.id, action="WORKSPACE_DEFAULTS", request=request)
    db.commit()
    invalidate()
    return {"defaults": current, "roles": list(TIERS)}
