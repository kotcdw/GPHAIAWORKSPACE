"""Custom fields: Admin defines extra inputs per module; values are validated and stored as JSON on the record."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier
from app.core.enums import Role
from app.core.errors import FieldValidationError, field_error
from app.modules.customfields.models import FIELD_TYPES, CustomField
from app.modules.users.models import User

router = APIRouter(prefix="/api/custom-fields", tags=["custom fields"])
Admin = Depends(require_module_tier("custom fields", Role.Admin))
MODULES = ("organizations",)  # modules whose records carry custom fields
_MODULE_PATTERN = "^(" + "|".join(MODULES) + ")$"


class FieldIn(BaseModel):
    module: str = Field(..., pattern=_MODULE_PATTERN)
    label: str = Field(..., min_length=1, max_length=100)
    field_type: str = "text"
    options: list[str] = Field(default_factory=list, max_length=50)
    required: bool = False
    help: str = Field("", max_length=255)
    sort_order: int = Field(0, ge=0, le=999)

    @field_validator("field_type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in FIELD_TYPES:
            raise ValueError(f"must be one of: {', '.join(FIELD_TYPES)}")
        return v

    @field_validator("options")
    @classmethod
    def _opts(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v:
            item = item.strip()
            if len(item) > 100:
                raise ValueError("each choice must be 100 characters or fewer")
            if item and item not in out:
                out.append(item)
        return out

    @model_validator(mode="after")
    def _select_needs_options(self) -> FieldIn:
        if self.field_type == "select" and len(self.options) < 2:
            raise ValueError("A drop-down needs at least two choices")
        return self


class FieldPatch(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=100)
    options: list[str] | None = Field(None, max_length=50)
    required: bool | None = None
    help: str | None = Field(None, max_length=255)
    sort_order: int | None = Field(None, ge=0, le=999)
    active: bool | None = None


class FieldOut(BaseModel):
    id: int
    module: str
    key: str
    label: str
    field_type: str
    options: list[str]
    required: bool
    help: str
    sort_order: int
    active: bool


def _out(f: CustomField) -> FieldOut:
    return FieldOut(id=f.id, module=f.module, key=f.field_key, label=f.label, field_type=f.field_type,
                    options=json.loads(f.options or "[]"), required=f.required, help=f.help,
                    sort_order=f.sort_order, active=f.active)


def definitions(db: DBSession, module: str, include_inactive: bool = False) -> list[CustomField]:
    q = select(CustomField).where(CustomField.module == module)
    if not include_inactive:
        q = q.where(CustomField.active.is_(True))
    return list(db.execute(q.order_by(CustomField.sort_order, CustomField.id)).scalars())


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:50]
    return s or "field"


def clean_values(db: DBSession, module: str, values: dict[str, Any] | None,
                 existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate submitted custom values against the module's active definitions.

    Unknown keys are refused; inactive fields keep their stored value. Errors name ``cf_<key>`` so
    the form can show them under the right input.
    """
    values = values or {}
    defs = {d.field_key: d for d in definitions(db, module, include_inactive=True)}
    errors: list[dict[str, str]] = []
    out = dict(existing or {})
    for key in values:
        if key not in defs or not defs[key].active:
            errors.append({"field": f"cf_{key}", "message": "is not a configured field"})
    for key, d in defs.items():
        if not d.active:
            continue
        raw = values.get(key, out.get(key))
        name = f"cf_{key}"
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            if d.required:
                errors.append({"field": name, "message": f"{d.label} is required"})
            out.pop(key, None)
            continue
        try:
            if d.field_type in ("text", "longtext"):
                text = str(raw).strip()
                limit = 255 if d.field_type == "text" else 5000
                if len(text) > limit:
                    raise ValueError(f"must be {limit} characters or fewer")
                out[key] = text
            elif d.field_type == "number":
                num = float(raw)
                out[key] = int(num) if num.is_integer() else num
            elif d.field_type == "date":
                out[key] = date.fromisoformat(str(raw)[:10]).isoformat()
            elif d.field_type == "select":
                if str(raw) not in json.loads(d.options or "[]"):
                    raise ValueError("is not one of the choices")
                out[key] = str(raw)
            elif d.field_type == "yesno":
                if isinstance(raw, bool):
                    out[key] = raw
                elif str(raw).lower() in ("true", "yes", "1", "false", "no", "0"):
                    out[key] = str(raw).lower() in ("true", "yes", "1")
                else:
                    raise ValueError("must be yes or no")
        except (TypeError, ValueError) as exc:
            msg = str(exc) if "must" in str(exc) or "choices" in str(exc) else f"is not a valid {d.field_type}"
            errors.append({"field": name, "message": f"{d.label} {msg}"})
    if errors:
        raise FieldValidationError(errors)
    return out


@router.get("", response_model=list[FieldOut])
def list_fields(module: str = Query(..., pattern=_MODULE_PATTERN), include_inactive: bool = False,
                db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list[FieldOut]:
    show_all = include_inactive and user.role == Role.Admin
    return [_out(f) for f in definitions(db, module, include_inactive=show_all)]


@router.post("", response_model=FieldOut, status_code=status.HTTP_201_CREATED)
def create_field(payload: FieldIn, request: Request, db: DBSession = Depends(get_db), user: User = Admin) -> FieldOut:
    existing = {f.field_key for f in definitions(db, payload.module, include_inactive=True)}
    if any(f.label.lower() == payload.label.strip().lower() for f in definitions(db, payload.module)):
        raise field_error("label", "a field with this name already exists")
    key, n = _slug(payload.label), 2
    base = key
    while key in existing:
        key, n = f"{base}_{n}", n + 1
    f = CustomField(module=payload.module, field_key=key, label=payload.label.strip(), field_type=payload.field_type,
                    options=json.dumps(payload.options), required=payload.required, help=payload.help.strip(),
                    sort_order=payload.sort_order, created_by=user.id)
    db.add(f)
    db.flush()
    log_action(db, user_id=user.id, action=f"CUSTOM_FIELD_CREATE {payload.module}.{key}", request=request)
    db.commit()
    return _out(f)


@router.patch("/{field_id}", response_model=FieldOut)
def update_field(field_id: int, payload: FieldPatch, request: Request, db: DBSession = Depends(get_db),
                 user: User = Admin) -> FieldOut:
    f = db.get(CustomField, field_id)
    if f is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field not found")
    if payload.label is not None:
        f.label = payload.label.strip()
    if payload.options is not None:
        opts = FieldIn._opts(payload.options)
        if f.field_type == "select" and len(opts) < 2:
            raise field_error("options", "A drop-down needs at least two choices")
        f.options = json.dumps(opts)
    for attr in ("required", "sort_order", "active"):
        if getattr(payload, attr) is not None:
            setattr(f, attr, getattr(payload, attr))
    if payload.help is not None:
        f.help = payload.help.strip()
    log_action(db, user_id=user.id, action=f"CUSTOM_FIELD_UPDATE {f.module}.{f.field_key}", request=request)
    db.commit()
    return _out(f)
