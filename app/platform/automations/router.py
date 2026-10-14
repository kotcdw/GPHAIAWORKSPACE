"""Automation rules: catalogue, create / edit / switch off, preview, run now and the run log."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_perm
from app.core.permissions import JOB_ROLES, PERMISSIONS
from app.platform.automations import engine
from app.platform.automations.models import AutomationRule, AutomationRun
from app.platform.users.models import User

router = APIRouter(prefix="/api/automations", tags=["automations"])
Manage = Depends(require_perm("system.automation"))


class Condition(BaseModel):
    field: str = Field(min_length=1, max_length=40)
    op: str = "eq"
    value: str = Field(default="", max_length=200)

    @field_validator("op")
    @classmethod
    def _op(cls, v: str) -> str:
        if v not in engine.OPS:
            raise ValueError(f"must be one of: {', '.join(engine.OPS)}")
        return v


class Action(BaseModel):
    type: str = "notify"
    to: list[str] = Field(min_length=1, max_length=20)
    title: str = Field(min_length=3, max_length=255)
    body: str = Field(default="", max_length=4000)
    email: bool = True
    due_days: int = Field(default=7, ge=0, le=365)

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in ("notify", "task"):
            raise ValueError("must be notify or task")
        return v

    @field_validator("to")
    @classmethod
    def _to(cls, v: list[str]) -> list[str]:
        roles = {r.code for r in JOB_ROLES}
        for token in v:
            kind, _, value = token.partition(":")
            ok = (token in engine.RECIPIENT_TOKENS or (kind == "role" and value in roles)
                  or (kind == "perm" and value in PERMISSIONS) or (kind == "user" and value.isdigit())
                  or (kind == "tier" and value in ("Admin", "Auditor", "Auditee", "Committee")))
            if not ok:
                raise ValueError(f"unknown recipient '{token}'")
        return v


class RuleIn(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=2000)
    trigger: str
    offset_days: int = Field(default=0, ge=0, le=730)
    conditions: list[Condition] = Field(default_factory=list, max_length=10)
    actions: list[Action] = Field(min_length=1, max_length=5)
    active: bool = True

    @field_validator("trigger")
    @classmethod
    def _trigger(cls, v: str) -> str:
        if v not in engine.TRIGGERS:
            raise ValueError("unknown trigger")
        return v


def _out(r: AutomationRule) -> dict:
    trig = engine.TRIGGERS.get(r.trigger)
    return {"id": r.id, "name": r.name, "description": r.description, "trigger": r.trigger,
            "trigger_label": trig.label if trig else r.trigger, "kind": trig.kind if trig else "",
            "offset_days": r.offset_days, "conditions": json.loads(r.conditions or "[]"),
            "actions": json.loads(r.actions or "[]"), "active": r.active, "builtin": bool(r.builtin_key),
            "last_run_at": r.last_run_at, "updated_at": r.updated_at}


def _rule(db: DBSession, rule_id: int) -> AutomationRule:
    r = db.get(AutomationRule, rule_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return r


@router.get("/catalog")
def catalog(_: User = Manage) -> dict:
    return {
        "triggers": [{"key": t.key, "label": t.label, "kind": t.kind, "record_type": t.record_type,
                      "fields": t.fields, "offset_help": t.offset_help, "people": list(t.people)}
                     for t in engine.TRIGGERS.values()],
        "ops": engine.OPS,
        "people": engine.RECIPIENT_TOKENS,
        "roles": [{"code": r.code, "name": r.name} for r in JOB_ROLES],
        "permissions": {k: v[1] for k, v in PERMISSIONS.items()},
    }


@router.get("")
def list_rules(db: DBSession = Depends(get_db), _: User = Manage) -> list[dict]:
    engine.ensure_builtins(db)
    rows = db.execute(select(AutomationRule).order_by(AutomationRule.active.desc(), AutomationRule.name)).scalars()
    return [_out(r) for r in rows]


@router.post("", status_code=201)
def create_rule(payload: RuleIn, request: Request, db: DBSession = Depends(get_db), user: User = Manage) -> dict:
    r = AutomationRule(name=payload.name.strip(), description=payload.description.strip(), trigger=payload.trigger,
                       offset_days=payload.offset_days,
                       conditions=json.dumps([c.model_dump() for c in payload.conditions]),
                       actions=json.dumps([a.model_dump() for a in payload.actions]), active=payload.active,
                       created_by=user.id)
    db.add(r)
    db.flush()
    log_action(db, user_id=user.id, action=f"AUTOMATION_CREATE id={r.id} trigger={r.trigger}", request=request)
    db.commit()
    return _out(r)


@router.put("/{rule_id}")
def update_rule(rule_id: int, payload: RuleIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Manage) -> dict:
    r = _rule(db, rule_id)
    r.name, r.description, r.trigger = payload.name.strip(), payload.description.strip(), payload.trigger
    r.offset_days, r.active = payload.offset_days, payload.active
    r.conditions = json.dumps([c.model_dump() for c in payload.conditions])
    r.actions = json.dumps([a.model_dump() for a in payload.actions])
    log_action(db, user_id=user.id, action=f"AUTOMATION_UPDATE id={r.id} active={r.active}", request=request)
    db.commit()
    return _out(r)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Manage) -> dict:
    r = _rule(db, rule_id)
    if r.builtin_key:
        raise HTTPException(status_code=409, detail="A built-in rule can be switched off but not deleted")
    db.delete(r)
    log_action(db, user_id=user.id, action=f"AUTOMATION_DELETE id={rule_id}", request=request)
    db.commit()
    return {"message": "Rule deleted"}


@router.get("/{rule_id}/preview")
def preview_rule(rule_id: int, db: DBSession = Depends(get_db), _: User = Manage) -> dict:
    r = _rule(db, rule_id)
    trig = engine.TRIGGERS.get(r.trigger)
    if trig is None or trig.kind != "schedule":
        return {"kind": "event", "matches": [], "note": "This rule runs when the event happens."}
    return {"kind": "schedule", "matches": engine.preview(db, r)}


@router.post("/run")
def run_now(request: Request, rule_id: int | None = Query(default=None), db: DBSession = Depends(get_db),
            user: User = Manage) -> dict:
    fired = engine.run_scheduled(db, rule_id=rule_id)
    log_action(db, user_id=user.id, action=f"AUTOMATION_RUN fired={fired}", request=request, commit=True)
    return {"fired": fired}


@router.get("/runs")
def runs(rule_id: int | None = Query(default=None), limit: int = Query(default=100, le=500),
         db: DBSession = Depends(get_db), _: User = Manage) -> list[dict]:
    q = select(AutomationRun, AutomationRule.name).join(AutomationRule, AutomationRule.id == AutomationRun.rule_id)
    if rule_id is not None:
        q = q.where(AutomationRun.rule_id == rule_id)
    rows = db.execute(q.order_by(AutomationRun.fired_at.desc()).limit(limit)).all()
    return [{"id": run.id, "rule_id": run.rule_id, "rule": name, "record_type": run.record_type,
             "record_id": run.record_id, "period": run.period_key, "outcome": run.outcome, "fired_at": run.fired_at}
            for run, name in rows]
