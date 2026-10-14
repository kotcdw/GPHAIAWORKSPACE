"""System Configuration routes (Admin): read and change the business rules."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.core import appconfig
from app.core.appconfig import RULES, RULES_BY_KEY, AppConfig, cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.errors import FieldValidationError
from app.modules.users.models import User

router = APIRouter(prefix="/api/config", tags=["configuration"])

# Who may change which group of rules (job-role permissions, see app.core.permissions).
GROUP_PERMS = {
    "Audit workflow": "system.workflow", "Action plans": "system.workflow", "Security": "system.config",
    "Organizations": "system.reference", "Reports": "method.reporting", "KPI targets": "method.reporting",
    "Audit methodology": "method.audit_types", "Plan configuration": "method.plan_config",
}


def _editable_groups(user: User) -> set[str]:
    from app.core.permissions import permissions_of

    have = permissions_of(user)
    return {g for g, perm in GROUP_PERMS.items() if perm in have}


def _config_user(user: User = Depends(require_active_user)) -> User:
    if not _editable_groups(user):
        raise HTTPException(status_code=403, detail="Insufficient permissions for configuration")
    return user


Admin = Depends(_config_user)


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


def _rules(user: User | None = None) -> list[RuleOut]:
    appconfig.invalidate()
    groups = _editable_groups(user) if user is not None else set(GROUP_PERMS)
    out = []
    for rule in RULES:
        if rule.group not in groups:
            continue
        value = cfg(rule.key)
        default = rule.default_value()
        out.append(RuleOut(key=rule.key, label=rule.label, group=rule.group, kind=rule.kind, help=rule.help,
                           value=value, default=default, is_default=value == default,
                           min=rule.min, max=rule.max, options=rule.options))
    return out


@router.get("", response_model=list[RuleOut])
def get_config(user: User = Admin) -> list[RuleOut]:
    return _rules(user)


@router.put("", response_model=list[RuleOut])
def update_config(payload: ConfigUpdate, request: Request, db: DBSession = Depends(get_db),
                  user: User = Admin) -> list[RuleOut]:
    errors, clean = [], {}
    for key, value in payload.values.items():
        rule = RULES_BY_KEY.get(key)
        if rule is None:
            errors.append({"field": key, "message": "unknown setting"})
            continue
        if rule.group not in _editable_groups(user):
            errors.append({"field": key, "message": "your role cannot change this setting"})
            continue
        try:
            clean[key] = appconfig.validate(rule, value)
        except ValueError as exc:
            errors.append({"field": key, "message": str(exc)})
    merged = {**{k: cfg(k) for k in RULES_BY_KEY}, **clean}
    if merged["risk_high_threshold"] <= merged["risk_medium_threshold"]:
        errors.append({"field": "risk_high_threshold", "message": "must be above the Medium threshold"})
    missing = [c for c in merged["port_categories"] if c not in merged["organization_categories"]]
    if missing:
        errors.append({"field": "port_categories", "message": f"not in the entity types: {', '.join(missing)}"})
    if merged["escalate_committee_days"] <= merged["escalate_cae_days"]:
        errors.append({"field": "escalate_committee_days", "message": "must be later than the CAE escalation"})
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
    return _rules(user)


@router.post("/{key}/reset", response_model=list[RuleOut])
def reset_rule(key: str, request: Request, db: DBSession = Depends(get_db), user: User = Admin) -> list[RuleOut]:
    if key not in RULES_BY_KEY:
        raise FieldValidationError([{"field": key, "message": "unknown setting"}])
    if RULES_BY_KEY[key].group not in _editable_groups(user):
        raise HTTPException(status_code=403, detail="Your role cannot change this setting")
    row = db.get(AppConfig, key)
    if row is not None:
        db.delete(row)
        log_action(db, user_id=user.id, action=f"CONFIG_RESET {key}", request=request)
        db.commit()
    appconfig.invalidate()
    return _rules(user)
