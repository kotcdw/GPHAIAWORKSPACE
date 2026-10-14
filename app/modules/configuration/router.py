"""System Configuration routes (Admin): read and change the business rules."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.core import appconfig
from app.core.appconfig import RULES, RULES_BY_KEY, AppConfig, cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_module_tier
from app.core.enums import Role
from app.core.errors import FieldValidationError
from app.modules.users.models import User

router = APIRouter(prefix="/api/config", tags=["configuration"])

Admin = Depends(require_module_tier("configuration", Role.Admin))


class RuleOut(BaseModel):
    key: str
    label: str
    group: str
    kind: str
    help: str
    value: Any
    default: Any
    is_default: bool
    min: int | None = None
    max: int | None = None
    options: list[str] = []


class ConfigUpdate(BaseModel):
    values: dict[str, Any]


def _rules() -> list[RuleOut]:
    appconfig.invalidate()
    out = []
    for rule in RULES:
        value = cfg(rule.key)
        default = rule.default_value()
        out.append(RuleOut(key=rule.key, label=rule.label, group=rule.group, kind=rule.kind, help=rule.help,
                           value=value, default=default, is_default=value == default,
                           min=rule.min, max=rule.max, options=rule.options))
    return out


@router.get("", response_model=list[RuleOut])
def get_config(_: User = Admin) -> list[RuleOut]:
    return _rules()


@router.put("", response_model=list[RuleOut])
def update_config(payload: ConfigUpdate, request: Request, db: DBSession = Depends(get_db),
                  user: User = Admin) -> list[RuleOut]:
    errors, clean = [], {}
    for key, value in payload.values.items():
        rule = RULES_BY_KEY.get(key)
        if rule is None:
            errors.append({"field": key, "message": "unknown setting"})
            continue
        try:
            clean[key] = appconfig.validate(rule, value)
        except ValueError as exc:
            errors.append({"field": key, "message": str(exc)})
    merged = {**{k: cfg(k) for k in RULES_BY_KEY}, **clean}
    missing = [c for c in merged["port_categories"] if c not in merged["organization_categories"]]
    if missing:
        errors.append({"field": "port_categories", "message": f"not in the entity types: {', '.join(missing)}"})
    if merged["escalate_cae_days"] <= merged["escalate_manager_days"]:
        errors.append({"field": "escalate_cae_days", "message": "must be later than the Audit Manager escalation"})
    if errors:
        raise FieldValidationError(errors)
    changed = []
    for key, value in clean.items():
        if value == cfg(key):
            continue
        row = db.get(AppConfig, key)
        if row is None:
            db.add(AppConfig(key=key, value=json.dumps(value), updated_by=user.id))
        else:
            row.value = json.dumps(value)
            row.updated_by = user.id
        changed.append(f"{key}={value}")
    if changed:
        log_action(db, user_id=user.id, action=f"CONFIG_UPDATE {'; '.join(changed)}"[:490], request=request)
    db.commit()
    appconfig.invalidate()
    return _rules()


@router.post("/{key}/reset", response_model=list[RuleOut])
def reset_rule(key: str, request: Request, db: DBSession = Depends(get_db), user: User = Admin) -> list[RuleOut]:
    if key not in RULES_BY_KEY:
        raise FieldValidationError([{"field": key, "message": "unknown setting"}])
    row = db.get(AppConfig, key)
    if row is not None:
        db.delete(row)
        log_action(db, user_id=user.id, action=f"CONFIG_RESET {key}", request=request)
        db.commit()
    appconfig.invalidate()
    return _rules()
