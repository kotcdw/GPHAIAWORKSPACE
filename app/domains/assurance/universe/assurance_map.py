"""Assurance map: other providers of assurance per auditable entity and the reliance placed on them (IIA GIAS 9.5).

Providers (management functions, risk and compliance, external auditors, regulators) are grouped by the lines set in
``assurance_lines``. A coverage row says what a provider covers on an entity, when it last gave assurance, its result
and how far Internal Audit relies on it. Reliance needs a recorded basis (competence, objectivity and due care of the
provider). Internal Audit's own column is the entity's last assurance audit.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm
from app.core.enums import utcnow
from app.core.errors import field_error
from app.core.history import log_record_history
from app.domains.assurance.planning.models import EntityUnit
from app.domains.assurance.universe.models import AssuranceCoverage, AssuranceProvider
from app.domains.assurance.universe.router import Staff
from app.platform.users.models import User

router = APIRouter(tags=["assurance map"])

RELIANCE = ("None", "Partial", "Full")
EDIT_PERMS = ("plan.prepare", "method.library")
HISTORY_TYPE = "auditable_entity"


class ProviderIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    line: str = Field(min_length=2, max_length=60)
    contact: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=5000)


class ProviderPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    line: str | None = Field(default=None, min_length=2, max_length=60)
    contact: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None


class CoverageIn(BaseModel):
    entity_id: int
    provider_id: int
    scope: str = Field(default="", max_length=5000)
    last_assurance_on: date | None = None
    next_planned_on: date | None = None
    result: str = Field(min_length=1, max_length=40)
    reliance: str = "None"
    reliance_basis: str = Field(default="", max_length=5000)
    evidence_ref: str = Field(default="", max_length=255)


class CoveragePatch(BaseModel):
    scope: str | None = Field(default=None, max_length=5000)
    last_assurance_on: date | None = None
    next_planned_on: date | None = None
    result: str | None = Field(default=None, max_length=40)
    reliance: str | None = None
    reliance_basis: str | None = Field(default=None, max_length=5000)
    evidence_ref: str | None = Field(default=None, max_length=255)


def _pick(value: str, options: list[str] | tuple[str, ...], field: str) -> str:
    match = next((o for o in options if o.lower() == value.strip().lower()), None)
    if match is None:
        raise field_error(field, f"choose one of: {', '.join(options)}")
    return match


def _provider_out(p: AssuranceProvider, used: int = 0) -> dict:
    return {"id": p.id, "name": p.name, "line": p.line, "contact": p.contact, "description": p.description or "",
            "is_active": p.is_active, "entities": used}


def _coverage_out(c: AssuranceCoverage, p: AssuranceProvider) -> dict:
    return {"id": c.id, "entity_id": c.entity_id, "provider_id": p.id, "provider": p.name, "line": p.line,
            "scope": c.scope or "", "last_assurance_on": c.last_assurance_on, "next_planned_on": c.next_planned_on,
            "result": c.result, "reliance": c.reliance, "reliance_basis": c.reliance_basis or "",
            "evidence_ref": c.evidence_ref}


def _check(c: AssuranceCoverage) -> None:
    if c.reliance != "None":
        if len((c.reliance_basis or "").strip()) < 20:
            raise field_error("reliance_basis", "record how the provider's competence, objectivity and due care were "
                                                "evaluated before relying on it")
        if c.last_assurance_on is None:
            raise field_error("last_assurance_on", "give the date of the assurance relied on")
    if c.last_assurance_on and c.last_assurance_on > utcnow().date():
        raise field_error("last_assurance_on", "cannot be in the future")


# ---------------------------------------------------------------- providers


@router.get("/api/assurance-providers")
def list_providers(db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    used = dict(db.execute(select(AssuranceCoverage.provider_id, func.count(AssuranceCoverage.id))
                           .group_by(AssuranceCoverage.provider_id)).all())
    rows = db.execute(select(AssuranceProvider).order_by(AssuranceProvider.line, AssuranceProvider.name)).scalars()
    return {"lines": cfg("assurance_lines"), "items": [_provider_out(p, used.get(p.id, 0)) for p in rows]}


@router.post("/api/assurance-providers", status_code=status.HTTP_201_CREATED)
def create_provider(payload: ProviderIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    ensure_perm(user, *EDIT_PERMS)
    name = payload.name.strip()
    if db.execute(select(AssuranceProvider.id).where(func.lower(AssuranceProvider.name) == name.lower())).first():
        raise field_error("name", "a provider with this name exists")
    p = AssuranceProvider(name=name, line=_pick(payload.line, cfg("assurance_lines"), "line"),
                          contact=payload.contact.strip(), description=payload.description.strip() or None,
                          created_by=user.id)
    db.add(p)
    db.flush()
    log_action(db, user_id=user.id, request=request, action=f"ASSURANCE_PROVIDER_CREATE id={p.id} name={p.name}")
    db.commit()
    return _provider_out(p)


@router.patch("/api/assurance-providers/{provider_id}")
def update_provider(provider_id: int, payload: ProviderPatch, request: Request, db: DBSession = Depends(get_db),
                    user: User = Staff) -> dict:
    ensure_perm(user, *EDIT_PERMS)
    p = db.get(AssuranceProvider, provider_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    if payload.name is not None and payload.name.strip().lower() != p.name.lower():
        if db.execute(select(AssuranceProvider.id).where(
                func.lower(AssuranceProvider.name) == payload.name.strip().lower())).first():
            raise field_error("name", "a provider with this name exists")
        p.name = payload.name.strip()
    if payload.line is not None:
        p.line = _pick(payload.line, cfg("assurance_lines"), "line")
    if payload.contact is not None:
        p.contact = payload.contact.strip()
    if payload.description is not None:
        p.description = payload.description.strip() or None
    if payload.is_active is not None:
        p.is_active = payload.is_active
    log_action(db, user_id=user.id, request=request, action=f"ASSURANCE_PROVIDER_UPDATE id={p.id}")
    db.commit()
    return _provider_out(p)


# ---------------------------------------------------------------- coverage


def _entity_or_404(db: DBSession, entity_id: int) -> EntityUnit:
    e = db.get(EntityUnit, entity_id)
    if e is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auditable entity not found")
    return e


@router.get("/api/auditable-entities/{entity_id}/assurance")
def entity_assurance(entity_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    e = _entity_or_404(db, entity_id)
    rows = db.execute(select(AssuranceCoverage, AssuranceProvider)
                      .join(AssuranceProvider, AssuranceProvider.id == AssuranceCoverage.provider_id)
                      .where(AssuranceCoverage.entity_id == e.id).order_by(AssuranceProvider.line)).all()
    return {"internal_audit": {"last_audited_at": e.last_audited_at}, "items": [_coverage_out(c, p) for c, p in rows]}


@router.post("/api/assurance-coverage", status_code=status.HTTP_201_CREATED)
def add_coverage(payload: CoverageIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    ensure_perm(user, *EDIT_PERMS)
    e = _entity_or_404(db, payload.entity_id)
    p = db.get(AssuranceProvider, payload.provider_id)
    if p is None or not p.is_active:
        raise field_error("provider_id", "choose an active provider")
    if db.execute(select(AssuranceCoverage.id).where(AssuranceCoverage.entity_id == e.id,
                                                     AssuranceCoverage.provider_id == p.id)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{p.name} is already on this entity")
    c = AssuranceCoverage(entity_id=e.id, provider_id=p.id, scope=payload.scope.strip() or None,
                          last_assurance_on=payload.last_assurance_on, next_planned_on=payload.next_planned_on,
                          result=_pick(payload.result, cfg("assurance_results"), "result"),
                          reliance=_pick(payload.reliance, RELIANCE, "reliance"),
                          reliance_basis=payload.reliance_basis.strip() or None,
                          evidence_ref=payload.evidence_ref.strip(), recorded_by=user.id)
    _check(c)
    db.add(c)
    db.flush()
    log_record_history(db, record_type=HISTORY_TYPE, record_id=e.id, user_id=user.id, request=request,
                       action=f"Assurance: {p.name} added ({c.result}, reliance {c.reliance})")
    log_action(db, user_id=user.id, request=request,
               action=f"ASSURANCE_COVERAGE_CREATE id={c.id} entity={e.id} provider={p.id} reliance={c.reliance}")
    db.commit()
    return _coverage_out(c, p)


@router.patch("/api/assurance-coverage/{coverage_id}")
def update_coverage(coverage_id: int, payload: CoveragePatch, request: Request, db: DBSession = Depends(get_db),
                    user: User = Staff) -> dict:
    ensure_perm(user, *EDIT_PERMS)
    c = db.get(AssuranceCoverage, coverage_id)
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    p = db.get(AssuranceProvider, c.provider_id)
    fields = payload.model_fields_set
    if "scope" in fields:
        c.scope = (payload.scope or "").strip() or None
    if "last_assurance_on" in fields:
        c.last_assurance_on = payload.last_assurance_on
    if "next_planned_on" in fields:
        c.next_planned_on = payload.next_planned_on
    if payload.result is not None:
        c.result = _pick(payload.result, cfg("assurance_results"), "result")
    if payload.reliance is not None:
        c.reliance = _pick(payload.reliance, RELIANCE, "reliance")
    if "reliance_basis" in fields:
        c.reliance_basis = (payload.reliance_basis or "").strip() or None
    if payload.evidence_ref is not None:
        c.evidence_ref = payload.evidence_ref.strip()
    _check(c)
    log_record_history(db, record_type=HISTORY_TYPE, record_id=c.entity_id, user_id=user.id, request=request,
                       action=f"Assurance: {p.name} updated ({c.result}, reliance {c.reliance})")
    log_action(db, user_id=user.id, request=request,
               action=f"ASSURANCE_COVERAGE_UPDATE id={c.id} reliance={c.reliance}")
    db.commit()
    return _coverage_out(c, p)


@router.delete("/api/assurance-coverage/{coverage_id}")
def remove_coverage(coverage_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    ensure_perm(user, *EDIT_PERMS)
    c = db.get(AssuranceCoverage, coverage_id)
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    p = db.get(AssuranceProvider, c.provider_id)
    log_record_history(db, record_type=HISTORY_TYPE, record_id=c.entity_id, user_id=user.id, request=request,
                       action=f"Assurance: {p.name} removed")
    log_action(db, user_id=user.id, request=request, action=f"ASSURANCE_COVERAGE_DELETE id={c.id}")
    db.delete(c)
    db.commit()
    return {"message": "Removed"}


# ---------------------------------------------------------------- the map


@router.get("/api/assurance-map")
def assurance_map(db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    """Entities (not retired) by line: who gives assurance, the latest result and the reliance placed on it."""
    lines = list(cfg("assurance_lines") or [])
    entities = db.execute(select(EntityUnit).where(EntityUnit.definition_status != "Retired")
                          .order_by(EntityUnit.name)).scalars().all()
    cover: dict[int, list[dict]] = {}
    for c, p in db.execute(select(AssuranceCoverage, AssuranceProvider)
                           .join(AssuranceProvider, AssuranceProvider.id == AssuranceCoverage.provider_id)).all():
        cover.setdefault(c.entity_id, []).append(_coverage_out(c, p))
    rows, others, relied, bare = [], 0, 0, 0
    for e in entities:
        items = cover.get(e.id, [])
        cells = {line: [i for i in items if i["line"] == line] for line in lines}
        extra = [i for i in items if i["line"] not in lines]  # a provider whose line was removed from the setting
        if extra:
            cells.setdefault("Other", []).extend(extra)
        others += bool(items)
        relied += any(i["reliance"] != "None" for i in items)
        bare += not items and e.last_audited_at is None
        rows.append({"id": e.id, "code": e.code, "name": e.name, "entity_type": e.entity_type,
                     "rating": e.assessed_rating, "definition_status": e.definition_status,
                     "internal_audit": e.last_audited_at, "cells": cells})
    if any("Other" in r["cells"] for r in rows):
        lines.append("Other")
    return {"lines": lines, "results": cfg("assurance_results"), "reliance": RELIANCE, "rows": rows,
            "summary": {"entities": len(entities), "covered_by_others": others, "relied_on": relied,
                        "no_assurance": bare}}
