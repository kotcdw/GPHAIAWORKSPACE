"""System Configuration routes (Admin): read and change the business rules."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core import appconfig
from app.core.appconfig import RULES, RULES_BY_KEY, AppConfig, AppConfigHistory, cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.errors import FieldValidationError
from app.platform.users.models import User


def regional_values() -> dict:
    """The regional settings plus the languages a person may choose for their own screens."""
    return {**{key: cfg(key) for key in REGIONAL}, "languages": list(RULES_BY_KEY["language"].options)}


router = APIRouter(prefix="/api/config", tags=["configuration"])

# Who may change which group of rules (job-role permissions, see app.core.permissions).
GROUP_PERMS = {
    "Audit workflow": "system.workflow", "Action plans": "system.workflow", "Security": "system.config",
    "Organizations": "system.reference", "Reports": "method.reporting", "KPI targets": "method.reporting",
    "Audit methodology": "method.audit_types", "Plan configuration": "method.plan_config",
    "AI": "system.config",
    "Follow-up & reporting": "system.workflow",
    "Professional practice": "governance.charter",
    "Risk & compliance": "grc.manage",
    "Regional": "system.config",
    "Data & attachments": "system.config",
    "Backups": "system.technical",
    "Users & licenses": "system.users",
}

# Regional settings every signed-in screen needs to show dates and times (nothing secret).
REGIONAL = ("time_zone", "date_format", "time_format", "fiscal_year_start_month", "working_days", "language")

# Admin-maintained lists every signed-in user's forms need (drop-down choices); nothing secret.
PUBLIC_LISTS = ("recommendation_sources", "action_timeframes", "report_statutory_recipients",
                "quarterly_report_recipients", "annual_statement_recipients", "audit_types")


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
    updated_at: str | None = None
    updated_by: str | None = None


class ConfigUpdate(BaseModel):
    values: dict[str, Any]
    reason: str | None = Field(default=None, max_length=500)


def _rules(user: User | None = None, db: DBSession | None = None) -> list[RuleOut]:
    appconfig.invalidate()
    groups = _editable_groups(user) if user is not None else set(GROUP_PERMS)
    saved: dict[str, AppConfig] = {}
    names: dict[int, str] = {}
    if db is not None:
        saved = {r.key: r for r in db.execute(select(AppConfig)).scalars()}
        ids = {r.updated_by for r in saved.values() if r.updated_by}
        names = {u.id: u.full_name or u.username for u in db.execute(
            select(User).where(User.id.in_(ids))).scalars()} if ids else {}
    out = []
    for rule in RULES:
        if rule.group not in groups:
            continue
        value = cfg(rule.key)
        default = rule.default_value()
        row = saved.get(rule.key)
        out.append(RuleOut(key=rule.key, label=rule.label, group=rule.group, kind=rule.kind, help=rule.help,
                           value=value, default=default, is_default=value == default,
                           min=rule.min, max=rule.max, options=rule.options,
                           updated_at=row.updated_at.isoformat() if row else None,
                           updated_by=names.get(row.updated_by) if row and row.updated_by else None))
    return out


def _history(db: DBSession, user: User, key: str, action: str, old: Any, new: Any, reason: str | None) -> None:
    db.add(AppConfigHistory(key=key, action=action, old_value=json.dumps(old), new_value=json.dumps(new),
                            reason=(reason or "").strip()[:500] or None, changed_by=user.id,
                            changed_by_name=user.full_name or user.username))


@router.get("", response_model=list[RuleOut])
def get_config(db: DBSession = Depends(get_db), user: User = Admin) -> list[RuleOut]:
    return _rules(user, db)


@router.get("/regional")
def regional(_: User = Depends(require_active_user)) -> dict:
    """Time zone, date and time format, fiscal year and working days: every screen formats dates with these."""
    return regional_values()


@router.get("/history")
def config_history(key: str | None = Query(default=None, max_length=64),
                   limit: int = Query(default=50, ge=1, le=500),
                   db: DBSession = Depends(get_db), user: User = Admin) -> list[dict]:
    """Changes to the settings the caller may manage, newest first (append-only record)."""
    from app.core.permissions import has_perm
    from app.platform.apps.registry import KEY as APPS_KEY

    groups = _editable_groups(user)
    keys = [r.key for r in RULES if r.group in groups and (key is None or r.key == key)]
    if has_perm(user, "system.superadmin") and key in (None, APPS_KEY):
        keys.append(APPS_KEY)  # Apps & branding (Super Administrator)
    if not keys:
        return []
    rows = db.execute(select(AppConfigHistory).where(AppConfigHistory.key.in_(keys))
                      .order_by(AppConfigHistory.changed_at.desc(), AppConfigHistory.id.desc())
                      .limit(limit)).scalars().all()

    def val(raw: str | None) -> Any:
        try:
            return json.loads(raw) if raw is not None else None
        except ValueError:
            return raw

    def meta(k: str) -> tuple[str, str]:
        rule = RULES_BY_KEY.get(k)
        return (rule.label, rule.group) if rule else ("Apps and branding", "Apps & customization")

    return [{"key": r.key, "label": meta(r.key)[0], "group": meta(r.key)[1],
             "action": r.action, "old": val(r.old_value), "new": val(r.new_value), "reason": r.reason,
             "by": r.changed_by_name or "-", "at": r.changed_at.isoformat()} for r in rows]


@router.get("/lists")
def public_lists(_: User = Depends(require_active_user)) -> dict:
    return {key: cfg(key) for key in PUBLIC_LISTS if key in appconfig.RULES_BY_KEY}


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
    from app.core.config import settings as server

    if merged["attachment_max_mb"] > server.max_upload_mb:
        errors.append({"field": "attachment_max_mb",
                       "message": f"cannot exceed the server limit of {server.max_upload_mb} MB"})
    if merged["escalate_committee_days"] <= merged["escalate_cae_days"]:
        errors.append({"field": "escalate_committee_days", "message": "must be later than the CAE escalation"})
    if merged["escalate_cae_days"] <= merged["escalate_manager_days"]:
        errors.append({"field": "escalate_cae_days", "message": "must be later than the Audit Manager escalation"})
    if errors:
        raise FieldValidationError(errors)
    changed = []
    for key, value in clean.items():
        old = cfg(key)
        if value == old:
            continue
        _history(db, user, key, "update", old, value, payload.reason)
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
    return _rules(user, db)


@router.post("/{key}/reset", response_model=list[RuleOut])
def reset_rule(key: str, request: Request, reason: str | None = Query(default=None, max_length=500),
               db: DBSession = Depends(get_db), user: User = Admin) -> list[RuleOut]:
    if key not in RULES_BY_KEY:
        raise FieldValidationError([{"field": key, "message": "unknown setting"}])
    if RULES_BY_KEY[key].group not in _editable_groups(user):
        raise HTTPException(status_code=403, detail="Your role cannot change this setting")
    row = db.get(AppConfig, key)
    if row is not None:
        _history(db, user, key, "reset", cfg(key), RULES_BY_KEY[key].default_value(), reason)
        db.delete(row)
        log_action(db, user_id=user.id, action=f"CONFIG_RESET {key}", request=request)
        db.commit()
    appconfig.invalidate()
    return _rules(user, db)
