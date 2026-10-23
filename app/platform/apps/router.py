"""Apps & customization: every signed-in user reads which apps are on and what they are called; only the Super
Administrator changes them."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.core import appconfig
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_perm
from app.platform.apps import registry
from app.platform.users.models import User

router = APIRouter(prefix="/api/apps", tags=["apps & customization"])


class AppSetting(BaseModel):
    enabled: bool = True
    label: str = Field(default="", max_length=60)


class CustomizationIn(BaseModel):
    apps: dict[str, AppSetting] = Field(default_factory=dict)
    branding: dict[str, str] = Field(default_factory=dict)
    # The organisation's default home pad (screen keys in order); omit to keep it, [] to go back to built-in.
    home: list[str] | None = Field(default=None, max_length=60)


@router.get("")
def get_apps(_: User = Depends(require_active_user)) -> dict:
    return registry.catalogue()


@router.put("")
def save_apps(payload: CustomizationIn, request: Request, db: DBSession = Depends(get_db),
              user: User = Depends(require_perm("system.superadmin"))) -> dict:
    before = {a["key"]: a["enabled"] for a in registry.catalogue()["apps"]}
    registry.save(db, {k: v.model_dump() for k, v in payload.apps.items()},
                  {k: v for k, v in payload.branding.items() if k in registry.DEFAULT_BRANDING}, user.id,
                  home=False if "home" not in payload.model_fields_set else payload.home)
    db.commit()
    appconfig.invalidate()
    after = registry.catalogue()
    off = [a["key"] for a in after["apps"] if before.get(a["key"]) and not a["enabled"]]
    on = [a["key"] for a in after["apps"] if not before.get(a["key"]) and a["enabled"]]
    log_action(db, user_id=user.id, request=request, commit=True,
               action=f"APPS_CUSTOMIZE off=[{','.join(off)}] on=[{','.join(on)}]"[:490])
    return after
