"""Audit universe workspace: Overview, Units, Processes and Entities.

Org units (Org Structure) and processes (Process library) are the sources; they are read here, never copied. An
auditor reviews each unit (Included / Not included, with a reason), maps processes to the units that perform them,
and defines auditable entities deliberately (a unit, a process, or a process within units). Ready entities go to the
existing audit risk assessment; no risk score is produced here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm
from app.core.enums import FindingStatus, utcnow
from app.core.errors import field_error
from app.core.history import list_record_history, log_record_history
from app.core.refs import next_reference
from app.core.validators import OptEmail
from app.domains.assurance.planning.models import EntityUnit, PlanEngagement
from app.domains.assurance.universe.models import (
    AraEntity,
    AuditEntity,
    AuditRiskAssessment,
    EntityOrgUnit,
    EntityProcess,
    Process,
    ProcessOrgUnit,
    UniverseReview,
)
from app.domains.assurance.universe.router import (
    LIBRARY,
    OrgTree,
    Staff,
    _entity,
    _entity_audit_ids,
    _location_for,
    _names,
    _pairs,
    _set_orgs,
)
from app.platform.users.models import User

router = APIRouter(tags=["audit universe"])

DEFINITION_STATUSES = ("Draft", "Needs review", "Ready", "Retired")
DECISIONS = ("Included", "Not included")
HISTORY_TYPE = "auditable_entity"


# ==================================================================== shared facts


def _risk_control_counts(db: DBSession, kind: str, ids: list[int]) -> dict[int, dict[str, int]]:
    """Linked enterprise risks and standard controls per record (grc_links is stored in canonical order)."""
    from app.domains.grc.links import GrcLink

    out: dict[int, dict[str, int]] = defaultdict(lambda: {"risks": 0, "controls": 0})
    if not ids:
        return out
    rows = db.execute(select(GrcLink).where(or_(
        and_(GrcLink.a_type == kind, GrcLink.a_id.in_(ids), GrcLink.b_type.in_(("risk", "control"))),
        and_(GrcLink.b_type == kind, GrcLink.b_id.in_(ids), GrcLink.a_type.in_(("risk", "control")))))).scalars()
    for r in rows:
        rec, other = (r.a_id, r.b_type) if r.a_type == kind else (r.b_id, r.a_type)
        out[rec]["risks" if other == "risk" else "controls"] += 1
    return out


def _active_entity_links(db: DBSession) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """Active entities per org unit and per process."""
    by_org: dict[int, set[int]] = defaultdict(set)
    by_proc: dict[int, set[int]] = defaultdict(set)
    active = select(EntityUnit.id).where(EntityUnit.is_active.is_(True))
    for eid, oid in db.execute(select(EntityOrgUnit.entity_id, EntityOrgUnit.org_id)
                               .where(EntityOrgUnit.entity_id.in_(active))).all():
        by_org[oid].add(eid)
    for eid, pid in db.execute(select(EntityProcess.entity_id, EntityProcess.process_id)
                               .where(EntityProcess.entity_id.in_(active))).all():
        by_proc[pid].add(eid)
    return by_org, by_proc


def _reviews(db: DBSession, kind: str) -> dict[int, UniverseReview]:
    return {r.object_id: r for r in db.execute(select(UniverseReview).where(UniverseReview.object_type == kind))
            .scalars()}


def _unit_status(oid: int, by_org: dict[int, set[int]], reviews: dict[int, UniverseReview]) -> str:
    if by_org.get(oid):
        return "Included"
    review = reviews.get(oid)
    return review.decision if review else "Needs review"


def _location_names(db: DBSession, tree: OrgTree) -> dict[int, str]:
    """The port or office each unit sits in (the top of its branch when it is not under a port)."""
    from app.platform.organizations.router import Index

    idx = Index(db)
    out = {}
    for oid, org in tree.nodes.items():
        top = idx.port_of(org)
        if top is None:
            path = tree.path(oid)
            top = path[0] if path else org
        out[oid] = top.name
    return out


def _owner_names(db: DBSession, emails) -> dict[str, str]:  # noqa: ANN001
    emails = {e.lower() for e in emails if e}
    if not emails:
        return {}
    return {u.email.lower(): u.full_name or u.username for u in db.execute(
        select(User).where(func.lower(User.email).in_(emails))).scalars() if u.email}


# ==================================================================== overview


@router.get("/api/audit-universe/overview")
def overview(db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    tree = OrgTree(db)
    pairs = _pairs(db, tree)
    by_org, by_proc = _active_entity_links(db)
    reviews = _reviews(db, "unit")
    states = [_unit_status(oid, by_org, reviews) for oid in tree.nodes]
    processes = list(db.execute(select(Process).where(Process.status == "Active")).scalars())
    mapped = {p for ps in pairs.values() for p in ps}
    entities = list(db.execute(select(EntityUnit.definition_status, EntityUnit.is_active)).all())
    by_status = {s: 0 for s in DEFINITION_STATUSES}
    for st, active in entities:
        by_status["Retired" if not active else (st if st in by_status else "Ready")] += 1
    open_aras = db.execute(select(func.count()).select_from(AuditRiskAssessment)
                           .where(AuditRiskAssessment.status != "Completed")).scalar_one()
    latest = db.execute(select(AuditRiskAssessment).order_by(AuditRiskAssessment.created_at.desc()).limit(1))\
        .scalar_one_or_none()
    units = {"total": len(tree.nodes), "included": states.count("Included"),
             "not_included": states.count("Not included"), "needs_review": states.count("Needs review"),
             "with_processes": sum(1 for oid in tree.nodes if pairs.get(oid))}
    procs = {"total": len(processes), "mapped": sum(1 for p in processes if p.id in mapped),
             "unmapped": sum(1 for p in processes if p.id not in mapped),
             "in_entities": sum(1 for p in processes if by_proc.get(p.id))}
    active_entities = sum(v for k, v in by_status.items() if k != "Retired")
    return {
        "units": units, "processes": procs,
        "entities": {"active": active_entities, "by_status": by_status},
        "needs_review": units["needs_review"] + procs["unmapped"] + by_status["Needs review"],
        "assessments": {"open": open_aras, "latest": {"id": latest.id, "ref": latest.ref, "name": latest.name,
                                                      "status": latest.status} if latest else None},
        # Setup flow: each step is done when there is something to review and nothing left to review.
        "steps": {"units": units["total"] > 0 and units["needs_review"] == 0,
                  "processes": procs["total"] > 0 and procs["unmapped"] == 0,
                  "entities": by_status["Ready"] > 0 and by_status["Draft"] + by_status["Needs review"] == 0,
                  "assessment": latest is not None and latest.status == "Completed"},
    }


# ==================================================================== units


def _unit_rows(db: DBSession, tree: OrgTree) -> list[dict]:
    pairs = _pairs(db, tree)
    by_org, _ = _active_entity_links(db)
    reviews = _reviews(db, "unit")
    locations = _location_names(db, tree)
    heads = _names(db, [o.head_user_id for o in tree.nodes.values()])
    rows = []
    for oid, _depth in tree.ordered():
        o = tree.nodes[oid]
        parent = tree.parent(oid)
        review = reviews.get(oid)
        rows.append({
            "id": oid, "code": o.org_ref, "name": o.name, "type": o.category,
            "parent": {"id": parent, "name": tree.nodes[parent].name} if parent else None,
            "location": locations.get(oid), "owner": heads.get(o.head_user_id),
            "processes": len(pairs.get(oid, [])), "entities": len(by_org.get(oid, ())),
            "status": _unit_status(oid, by_org, reviews), "reason": review.reason if review else "",
            "updated_at": o.updated_at.isoformat() if getattr(o, "updated_at", None) else None,
        })
    return rows


@router.get("/api/audit-universe/units")
def list_units(db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    rows = _unit_rows(db, OrgTree(db))
    return {"items": rows, "summary": {
        "total": len(rows), "included": sum(1 for r in rows if r["status"] == "Included"),
        "with_processes": sum(1 for r in rows if r["processes"]),
        "needs_review": sum(1 for r in rows if r["status"] == "Needs review")}}


@router.get("/api/audit-universe/units/{org_id}")
def unit_detail(org_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    from app.core.access import visible
    from app.domains.audit.audits.models import Audit, Finding

    tree = OrgTree(db)
    if org_id not in tree.nodes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Org unit not found")
    row = next(r for r in _unit_rows(db, tree) if r["id"] == org_id)
    org = tree.nodes[org_id]
    pids = _pairs(db, tree).get(org_id, [])
    procs = list(db.execute(select(Process).where(Process.id.in_(pids or [0])).order_by(Process.name)).scalars())
    counts = _risk_control_counts(db, "process", pids)
    entity_ids = select(EntityOrgUnit.entity_id).where(EntityOrgUnit.org_id == org_id)
    entities = list(db.execute(select(EntityUnit).where(EntityUnit.id.in_(entity_ids))
                               .order_by(EntityUnit.is_active.desc(), EntityUnit.name)).scalars())
    audit_ids = set(db.execute(select(Audit.id).where(Audit.organization_id == org_id)).scalars())
    for e in entities:
        audit_ids |= _entity_audit_ids(db, e.id)
    audits = visible(db, user, "audit", list(db.execute(select(Audit).where(Audit.id.in_(audit_ids or {0}))
                                                         .order_by(Audit.created_at.desc())).scalars()))
    seen = [a.id for a in audits]
    open_findings = db.execute(select(func.count()).select_from(Finding).where(
        Finding.audit_id.in_(seen or [0]), Finding.status != FindingStatus.Closed)).scalar_one()
    reviews = _reviews(db, "unit")
    review = reviews.get(org_id)
    return {
        **row, "address": org.address, "category": org.category,
        "path": " / ".join(n.name for n in tree.path(org_id)),
        "process_list": [{"id": p.id, "ref": p.ref, "name": p.name, **counts.get(p.id, {"risks": 0, "controls": 0})}
                         for p in procs],
        "risks": sum(c["risks"] for c in counts.values()), "controls": sum(c["controls"] for c in counts.values()),
        "entity_list": [{"id": e.id, "code": e.code, "name": e.name,
                         "status": e.definition_status if e.is_active else "Retired"} for e in entities],
        "audits": [{"id": a.id, "ref": f"AUD-{a.id:04d}", "title": a.title, "status": a.status.value}
                   for a in audits[:10]],
        "audit_count": len(audits), "open_findings": open_findings,
        "review": {"decision": review.decision, "reason": review.reason,
                   "by": _names(db, [review.reviewed_by]).get(review.reviewed_by),
                   "at": review.reviewed_at.isoformat()} if review else None,
    }


class ReviewIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    decision: str
    reason: str = Field("", max_length=2000)


@router.post("/api/audit-universe/units/review")
def review_units(payload: ReviewIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Include units in the universe, mark them Not included (with a reason) or send them back for review."""
    ensure_perm(user, *LIBRARY)
    if payload.decision not in (*DECISIONS, "Needs review"):
        raise field_error("decision", "must be Included, Not included or Needs review")
    reason = payload.reason.strip()
    if payload.decision == "Not included" and len(reason) < 5:
        raise field_error("reason", "give the reason the unit is not part of the audit universe")
    tree = OrgTree(db)
    ids = list(dict.fromkeys(payload.ids))
    bad = [i for i in ids if i not in tree.nodes]
    if bad:
        raise field_error("ids", "choose active org units of the Org Structure")
    by_org, _ = _active_entity_links(db)
    if payload.decision != "Included":
        used = [tree.nodes[i].name for i in ids if by_org.get(i)]
        if used:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail=f"Used by an auditable entity, so it stays included: {', '.join(used[:5])}")
    existing = _reviews(db, "unit")
    now = utcnow()
    for oid in ids:
        row = existing.get(oid)
        if payload.decision == "Needs review":
            if row is not None:
                db.delete(row)
            continue
        if row is None:
            db.add(UniverseReview(object_type="unit", object_id=oid, decision=payload.decision, reason=reason,
                                  reviewed_by=user.id, reviewed_at=now))
        else:
            row.decision, row.reason, row.reviewed_by, row.reviewed_at = payload.decision, reason, user.id, now
    log_action(db, user_id=user.id, request=request, entity_type="organization",
               action=f"UNIVERSE_UNITS {payload.decision} units={len(ids)}"
                      + (f" reason={reason[:120]}" if reason else ""))
    db.commit()
    return {"updated": len(ids)}


# ==================================================================== processes


def _process_rows(db: DBSession, tree: OrgTree, include_archived: bool = False) -> list[dict]:
    stmt = select(Process).order_by(Process.name)
    if not include_archived:
        stmt = stmt.where(Process.status == "Active")
    procs = list(db.execute(stmt).scalars())
    all_procs = {p.id: p for p in db.execute(select(Process)).scalars()}
    units: dict[int, list[int]] = defaultdict(list)
    for pid, oid in db.execute(select(ProcessOrgUnit.process_id, ProcessOrgUnit.org_id)).all():
        if oid in tree.nodes:
            units[pid].append(oid)
    _, by_proc = _active_entity_links(db)
    counts = _risk_control_counts(db, "process", [p.id for p in procs])
    owners = _owner_names(db, [p.owner_email for p in procs])

    def top(p: Process) -> Process:
        seen = set()
        while p.parent_id and p.parent_id in all_procs and p.id not in seen:
            seen.add(p.id)
            p = all_procs[p.parent_id]
        return p

    rows = []
    for p in procs:
        group = top(p)
        unit_ids = sorted(units.get(p.id, []), key=lambda i: tree.nodes[i].name.lower())
        rows.append({
            "id": p.id, "ref": p.ref, "name": p.name, "status": p.status,
            "group": group.name if group.id != p.id else None, "parent_id": p.parent_id,
            "units": [{"id": i, "name": tree.nodes[i].name} for i in unit_ids],
            "owner_email": p.owner_email,
            "owner": owners.get((p.owner_email or "").lower()) or p.owner_email,
            "risks": counts.get(p.id, {}).get("risks", 0), "controls": counts.get(p.id, {}).get("controls", 0),
            "entities": len(by_proc.get(p.id, ())),
            "mapping": "Mapped" if unit_ids else "Unmapped",
        })
    return rows


@router.get("/api/audit-universe/processes")
def list_processes(include_archived: bool = False, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    tree = OrgTree(db)
    rows = _process_rows(db, tree, include_archived)
    pairs = _pairs(db, tree)
    active = [r for r in rows if r["status"] == "Active"]
    return {"items": rows, "summary": {
        "total": len(active), "mapped": sum(1 for r in active if r["mapping"] == "Mapped"),
        "unmapped": sum(1 for r in active if r["mapping"] == "Unmapped"),
        "units_without_processes": [{"id": oid, "name": tree.nodes[oid].name}
                                    for oid, _d in tree.ordered() if not pairs.get(oid)]}}


class MapIn(BaseModel):
    process_ids: list[int] = Field(min_length=1, max_length=500)
    org_ids: list[int] = Field(default_factory=list, max_length=500)
    mode: str = "add"  # add: the units are added to each process | replace: they become its only units


@router.post("/api/audit-universe/processes/map")
def map_processes(payload: MapIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Record which org units perform the processes (the Process library mapping itself, not a copy)."""
    ensure_perm(user, *LIBRARY)
    if payload.mode not in ("add", "replace"):
        raise field_error("mode", "must be add or replace")
    if payload.mode == "add" and not payload.org_ids:
        raise field_error("org_ids", "choose at least one org unit")
    procs = list(db.execute(select(Process).where(Process.id.in_(payload.process_ids))).scalars())
    if len(procs) != len(set(payload.process_ids)):
        raise field_error("process_ids", "one or more processes were not found")
    for p in procs:
        current = [o.id for o in p.org_units]
        wanted = list(dict.fromkeys(current + payload.org_ids)) if payload.mode == "add" else payload.org_ids
        _set_orgs(db, p, wanted)
        p.updated_at = utcnow()
    log_action(db, user_id=user.id, request=request, entity_type="process",
               action=f"PROCESS_MAP {payload.mode} processes={len(procs)} units={len(payload.org_ids)}")
    db.commit()
    return {"updated": len(procs)}


# ==================================================================== entities


def entity_usage(db: DBSession, e: EntityUnit) -> dict:
    assessments = db.execute(select(func.count()).select_from(AraEntity).where(AraEntity.entity_id == e.id))\
        .scalar_one()
    plans = db.execute(select(func.count()).select_from(PlanEngagement).where(PlanEngagement.entity_unit_id == e.id))\
        .scalar_one()
    return {"audits": len(_entity_audit_ids(db, e.id)), "assessments": assessments, "plans": plans}


def entity_risk_counts(db: DBSession, ids: list[int], procs_by_entity: dict[int, list[int]]) -> dict[int, dict]:
    own = _risk_control_counts(db, "unit", ids)
    all_procs = sorted({p for ps in procs_by_entity.values() for p in ps})
    via = _risk_control_counts(db, "process", all_procs)
    out = {}
    for eid in ids:
        risks = own.get(eid, {}).get("risks", 0) + sum(via.get(p, {}).get("risks", 0)
                                                        for p in procs_by_entity.get(eid, []))
        controls = own.get(eid, {}).get("controls", 0) + sum(via.get(p, {}).get("controls", 0)
                                                              for p in procs_by_entity.get(eid, []))
        out[eid] = {"risks": risks, "controls": controls}
    return out


@router.get("/api/audit-universe/entity-options")
def entity_options(db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    """What the New entity form offers: entity types, org units, processes (with their units), people."""
    tree = OrgTree(db)
    pairs = _pairs(db, tree)
    units_of: dict[int, list[int]] = defaultdict(list)
    for oid, ps in pairs.items():
        for p in ps:
            units_of[p].append(oid)
    people = [{"email": u.email, "name": u.full_name or u.username}
              for u in db.execute(select(User).where(User.is_active.is_(True), User.email.is_not(None))
                                  .order_by(User.full_name, User.username)).scalars()]
    return {
        "types": cfg("universe_entity_types") or ["Org unit", "Process", "Process + unit"],
        "statuses": [s for s in DEFINITION_STATUSES if s != "Retired"],
        "units": [{"id": oid, "name": tree.nodes[oid].name, "code": tree.nodes[oid].org_ref, "depth": d,
                   "type": tree.nodes[oid].category} for oid, d in tree.ordered()],
        "processes": [{"id": p.id, "ref": p.ref, "name": p.name, "units": units_of.get(p.id, [])}
                      for p in db.execute(select(Process).where(Process.status == "Active")
                                          .order_by(Process.name)).scalars()],
        "people": people,
    }


class EntityIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    entity_type: str = Field(min_length=2, max_length=40)
    org_ids: list[int] = Field(default_factory=list, max_length=200)
    process_ids: list[int] = Field(default_factory=list, max_length=200)
    owner_email: OptEmail = None
    scope: str = Field("", max_length=20000)
    objectives: str = Field("", max_length=20000)
    rationale: str = Field("", max_length=20000)
    definition_status: str = "Draft"
    effective_from: date | None = None
    effective_to: date | None = None
    risk_ids: list[int] | None = Field(None, max_length=500)
    control_ids: list[int] | None = Field(None, max_length=500)
    allow_duplicate: bool = False


def check_definition(db: DBSession, *, name: str, entity_type: str, status_: str, owner: str | None, scope: str,
                     effective_from: date | None, effective_to: date | None, exclude_id: int | None = None,
                     check_name: bool = True, check_type: bool = True) -> None:
    types = cfg("universe_entity_types") or []
    if check_type and entity_type not in types:
        raise field_error("entity_type", "choose one of the entity types under Configuration")
    if status_ not in DEFINITION_STATUSES:
        raise field_error("definition_status", "must be Draft, Needs review, Ready or Retired")
    if status_ == "Ready":
        if not owner:
            raise field_error("owner_email", "a Ready entity needs a business owner")
        if len(scope.strip()) < 10:
            raise field_error("scope", "a Ready entity needs a scope statement")
    if effective_from and effective_to and effective_to < effective_from:
        raise field_error("effective_to", "must be on or after the start date")
    if not check_name or status_ == "Retired":  # older universes may already share names; only new names are checked
        return
    clash = db.execute(select(EntityUnit).where(func.lower(EntityUnit.name) == name.strip().lower(),
                                                EntityUnit.is_active.is_(True),
                                                EntityUnit.id != (exclude_id or 0))).scalars().first()
    if clash is not None:
        raise field_error("name", f"{clash.code} already has this name")


def resolve_links(db: DBSession, tree: OrgTree, org_ids: list[int], process_ids: list[int],
                  keep_orgs: set[int] | None = None, keep_procs: set[int] | None = None,
                  ) -> tuple[list[int], list[tuple[int, int]]]:
    """Validated org units and (process, org unit) pairs. A process with no unit chosen takes the units that
    perform it. Links an entity already has to a deactivated unit or an archived process may stay."""
    keep_orgs = keep_orgs or set()
    keep_procs = keep_procs or set()
    orgs = list(dict.fromkeys(org_ids))
    bad = [o for o in orgs if o not in tree.nodes and o not in keep_orgs]
    if bad:
        raise field_error("org_ids", "choose active org units of the Org Structure")
    pairs = _pairs(db, tree)
    performed: dict[int, list[int]] = defaultdict(list)
    for oid, ps in pairs.items():
        for p in ps:
            performed[p].append(oid)
    procs = list(dict.fromkeys(process_ids))
    active = {p for (p,) in db.execute(select(Process.id).where(Process.id.in_(procs or [0]),
                                                                Process.status == "Active")).all()}
    if set(procs) - active - keep_procs:
        raise field_error("process_ids", "choose active processes of the Process library")
    if not orgs:
        orgs = list(dict.fromkeys(o for p in procs for o in performed.get(p, [])))
    if not orgs:
        raise field_error("org_ids", "choose at least one org unit (the processes chosen are not mapped to a unit)")
    links = []
    for p in procs:
        where = next((o for o in orgs if o in performed.get(p, [])), orgs[0])
        links.append((p, where))
    return orgs, links


def write_links(db: DBSession, e: EntityUnit, orgs: list[int], links: list[tuple[int, int]]) -> None:
    db.execute(delete(EntityOrgUnit).where(EntityOrgUnit.entity_id == e.id))
    db.execute(delete(EntityProcess).where(EntityProcess.entity_id == e.id))
    db.flush()
    for oid in orgs:
        db.add(EntityOrgUnit(entity_id=e.id, org_id=oid))
    for pid, oid in links:
        db.add(EntityProcess(entity_id=e.id, process_id=pid, org_id=oid))
    e.org_unit_id = orgs[0]


def _signature(db: DBSession, exclude_id: int | None = None) -> dict[tuple, EntityUnit]:
    ents = {e.id: e for e in db.execute(select(EntityUnit).where(EntityUnit.is_active.is_(True),
                                                                 EntityUnit.id != (exclude_id or 0))).scalars()}
    orgs: dict[int, set[int]] = defaultdict(set)
    procs: dict[int, set[int]] = defaultdict(set)
    for eid, oid in db.execute(select(EntityOrgUnit.entity_id, EntityOrgUnit.org_id)
                               .where(EntityOrgUnit.entity_id.in_(list(ents) or [0]))).all():
        orgs[eid].add(oid)
    for eid, pid in db.execute(select(EntityProcess.entity_id, EntityProcess.process_id)
                               .where(EntityProcess.entity_id.in_(list(ents) or [0]))).all():
        procs[eid].add(pid)
    return {(tuple(sorted(orgs[i])), tuple(sorted(procs[i]))): e for i, e in ents.items()}


def check_duplicate(db: DBSession, orgs: list[int], links: list[tuple[int, int]], allow: bool,
                    exclude_id: int | None = None) -> None:
    sig = (tuple(sorted(orgs)), tuple(sorted(p for p, _ in links)))
    twin = _signature(db, exclude_id).get(sig)
    if twin is not None and not allow:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Possible duplicate: {twin.code} {twin.name} already covers the same units and "
                                   "processes")


def history(db: DBSession, e: EntityUnit, user: User, action: str, request: Request | None = None) -> None:
    log_record_history(db, record_type=HISTORY_TYPE, record_id=e.id, user_id=user.id, action=action, request=request)


@router.post("/api/auditable-entities", status_code=status.HTTP_201_CREATED)
def create_entity(payload: EntityIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    from app.domains.assurance.universe.router import get_entity
    from app.domains.grc.links import set_links

    ensure_perm(user, *LIBRARY)
    owner = str(payload.owner_email) if payload.owner_email else None
    if payload.definition_status == "Retired":
        raise field_error("definition_status", "a new entity cannot be retired")
    check_definition(db, name=payload.name, entity_type=payload.entity_type, status_=payload.definition_status,
                     owner=owner, scope=payload.scope, effective_from=payload.effective_from,
                     effective_to=payload.effective_to)
    tree = OrgTree(db)
    orgs, links = resolve_links(db, tree, payload.org_ids, payload.process_ids)
    check_duplicate(db, orgs, links, payload.allow_duplicate)
    loc = _location_for(db, tree, orgs[0])
    e = EntityUnit(location_id=loc.id, code=next_reference(db, "AE"), name=payload.name.strip(), description="",
                   owner_email=owner, defined_at=utcnow(), is_active=True, risk_likelihood=3, risk_impact=3,
                   entity_type=payload.entity_type, definition_status=payload.definition_status,
                   scope=payload.scope.strip(), objectives=payload.objectives.strip(),
                   rationale=payload.rationale.strip(), effective_from=payload.effective_from,
                   effective_to=payload.effective_to, org_unit_id=orgs[0])
    db.add(e)
    db.flush()
    write_links(db, e, orgs, links)
    if payload.risk_ids is not None:
        set_links(db, "unit", e.id, "risk", payload.risk_ids, user.id)
    if payload.control_ids is not None:
        set_links(db, "unit", e.id, "control", payload.control_ids, user.id)
    history(db, e, user, f"Created as {payload.definition_status}: {payload.entity_type}, {len(orgs)} unit(s), "
                         f"{len(links)} process(es)", request)
    log_action(db, user_id=user.id, request=request, entity_type="auditable_entity", entity_id=e.id,
               action=f"ENTITY_CREATE {e.code} status={e.definition_status}")
    db.commit()
    return get_entity(e.id, db, user)


@router.delete("/api/auditable-entities/{entity_id}")
def delete_entity(entity_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Remove an entity that was never used. One used by an audit, assessment or plan is retired instead."""
    ensure_perm(user, *LIBRARY)
    e = _entity(db, entity_id)
    usage = entity_usage(db, e)
    if any(usage.values()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Used by audits, assessments or plans; retire it instead so its history stays")
    from app.domains.grc.links import drop_links

    code = e.code
    db.execute(delete(AuditEntity).where(AuditEntity.entity_id == e.id))
    drop_links(db, "unit", e.id)
    db.delete(e)
    log_action(db, user_id=user.id, request=request, entity_type="auditable_entity", entity_id=entity_id,
               action=f"ENTITY_DELETE {code}")
    db.commit()
    return {"message": f"{code} deleted"}


@router.get("/api/auditable-entities/{entity_id}/history")
def entity_history(entity_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    _entity(db, entity_id)
    rows = list_record_history(db, HISTORY_TYPE, entity_id)
    names = _names(db, [r.user_id for r in rows])
    return [{"at": r.timestamp.isoformat(), "by": names.get(r.user_id, "System"), "action": r.action}
            for r in reversed(rows)]



@router.get("/api/audit-universe/entities")
def list_entities(db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """The entity register: the universe rows plus business owner names and linked risk and control counts."""
    from app.domains.assurance.universe.router import audit_universe

    data = audit_universe(db, user)
    rows = data["entities"]
    owners = _owner_names(db, [r["owner_email"] for r in rows])
    counts = entity_risk_counts(db, [r["id"] for r in rows], {r["id"]: [p["id"] for p in r["processes"]]
                                                               for r in rows})
    by_status = {s: 0 for s in DEFINITION_STATUSES}
    for r in rows:
        r["owner"] = owners.get((r["owner_email"] or "").lower()) or r["owner_email"]
        r["risks"] = counts[r["id"]]["risks"]
        r["controls"] = counts[r["id"]]["controls"]
        by_status[r["definition_status"]] = by_status.get(r["definition_status"], 0) + 1
    return {"items": rows, "summary": by_status, "types": cfg("universe_entity_types") or []}
