"""Integrated audit universe (Diligent One / HighBond Audit): Org Structure, Process library, Define audit universe,
auditable entities and audit risk assessments.

Data flow: Org Structure + Process library -> Define audit universe (auditable entities, coverage) -> Audit risk
assessment (factor scores, overall = average, prioritised entities, conclusion) -> Assurance Plan (engagements
generated for the prioritised entities) -> audits -> findings and actions shown on each entity.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm, require_role
from app.core.enums import EngagementStatus, FindingStatus, PlanStatus, Role, utcnow
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.core.validators import OptEmail
from app.domains.assurance.planning.models import AssurancePlan, EntityUnit, Location, PlanEngagement
from app.domains.assurance.universe.models import (
    SCALES,
    AraEntity,
    AraFactor,
    AraScore,
    AssessmentFactor,
    AuditEntity,
    AuditRiskAssessment,
    EntityOrgUnit,
    EntityProcess,
    Process,
    ProcessOrgUnit,
    scale_label,
)
from app.platform.organizations.models import Organization
from app.platform.users.models import User

router = APIRouter(tags=["audit universe"])
Staff = Depends(require_role(Role.Admin, Role.Auditor))
LIBRARY = ("method.library", "system.reference")
PLANNING = ("plan.prepare", "plan.amend", "method.library")
FREQUENCIES = {12: "Every year", 24: "Every 2 years", 36: "Every 3 years", 48: "Every 4 years", 60: "Every 5 years"}


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _names(db: DBSession, ids) -> dict[int, str]:  # noqa: ANN001
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.full_name or u.username for u in db.execute(select(User).where(User.id.in_(ids))).scalars()}


# ==================================================================== Org Structure


class OrgTree:
    """The internal organisation (types listed under Configuration > Organizations > Org Structure types)."""

    def __init__(self, db: DBSession, include_inactive: bool = False) -> None:
        types = {t.lower() for t in (cfg("org_structure_categories") or [])}
        rows = list(db.execute(select(Organization).order_by(Organization.name)).scalars())
        self.all = {o.id: o for o in rows}
        # Deactivated units leave the tree (coverage, pickers) but keep their names on the records that use them.
        self.typed = {o.id: o for o in rows if (o.category or "").lower() in types}
        self.nodes = {i: o for i, o in self.typed.items() if include_inactive or o.is_active}
        self.kids: dict[int | None, list[int]] = defaultdict(list)
        for o in self.nodes.values():
            parent = o.parent_id if o.parent_id in self.nodes else None
            self.kids[parent].append(o.id)

    def subtree(self, oid: int) -> list[int]:
        out, stack = [], [oid]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.append(cur)
            stack.extend(self.kids.get(cur, []))
        return out

    def parent(self, oid: int) -> int | None:
        o = self.nodes.get(oid)
        return o.parent_id if o and o.parent_id in self.nodes else None

    def path(self, oid: int) -> list[Organization]:
        out, cur, seen = [], oid, set()
        while cur and cur in self.typed and cur not in seen:
            seen.add(cur)
            out.append(self.typed[cur])
            cur = self.typed[cur].parent_id
        return list(reversed(out))

    def ordered(self) -> list[tuple[int, int]]:
        """(org id, depth) in tree order."""
        out: list[tuple[int, int]] = []

        def walk(pid: int | None, depth: int) -> None:
            for cid in sorted(self.kids.get(pid, []), key=lambda i: self.nodes[i].name.lower()):
                out.append((cid, depth))
                walk(cid, depth + 1)

        walk(None, 0)
        return out


def _pairs(db: DBSession, tree: OrgTree) -> dict[int, list[int]]:
    """Active processes linked to each org unit of the tree."""
    active = {p.id for p in db.execute(select(Process).where(Process.status == "Active")).scalars()}
    out: dict[int, list[int]] = defaultdict(list)
    for pid, oid in db.execute(select(ProcessOrgUnit.process_id, ProcessOrgUnit.org_id)).all():
        if pid in active and oid in tree.nodes:
            out[oid].append(pid)
    return out


@router.get("/api/org-structure")
def org_structure(include_inactive: bool = False, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    """Org Structure as a tree, with each unit's head, people, processes and auditable entities."""
    tree = OrgTree(db, include_inactive=include_inactive)
    people: dict[int, int] = defaultdict(int)
    for wid, in db.execute(select(User.work_entity_id).where(User.work_entity_id.is_not(None),
                                                             User.is_active.is_(True))).all():
        people[wid] += 1
    heads = _names(db, [o.head_user_id for o in tree.nodes.values()])
    pairs = _pairs(db, tree)
    entities: dict[int, int] = defaultdict(int)
    for oid, in db.execute(select(EntityOrgUnit.org_id).join(EntityUnit, EntityUnit.id == EntityOrgUnit.entity_id)
                           .where(EntityUnit.is_active.is_(True))).all():
        entities[oid] += 1
    procs = {p.id: p.name for p in db.execute(select(Process)).scalars()}
    rows = []
    for oid, depth in tree.ordered():
        o = tree.nodes[oid]
        rows.append({"id": o.id, "org_ref": o.org_ref, "name": o.name, "category": o.category, "depth": depth,
                     "parent_id": tree.parent(oid), "children": len(tree.kids.get(oid, [])),
                     "processes": [{"id": p, "name": procs.get(p, "")} for p in pairs.get(oid, [])],
                     "entities": entities.get(oid, 0), "status": o.status.value, "is_active": o.is_active,
                     "head_user_id": o.head_user_id, "head_name": heads.get(o.head_user_id),
                     "people": people.get(oid, 0)})
    inactive = sum(1 for o in tree.typed.values() if not o.is_active)
    return {"types": cfg("org_structure_categories"), "items": rows, "inactive_count": inactive}


# ==================================================================== Process library


class ProcessIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str = Field("", max_length=20000)
    parent_id: int | None = None
    owner_email: OptEmail = None
    org_ids: list[int] = Field(default_factory=list, max_length=500)


class ProcessUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = Field(None, max_length=20000)
    parent_id: int | None = None
    owner_email: OptEmail = None
    status: str | None = None
    org_ids: list[int] | None = Field(None, max_length=500)


def _process_out(p: Process, entity_counts: dict[int, int], parents: dict[int, str]) -> dict:
    return {"id": p.id, "ref": p.ref, "name": p.name, "description": p.description, "parent_id": p.parent_id,
            "parent": parents.get(p.parent_id), "owner_email": p.owner_email, "status": p.status,
            "org_units": [{"id": o.id, "name": o.name} for o in p.org_units],
            "entities": entity_counts.get(p.id, 0), "updated_at": p.updated_at.isoformat(),
            **_link_counts(p)}


def _link_counts(p: Process) -> dict:
    from sqlalchemy.orm import object_session

    from app.domains.grc.links import linked

    rows = linked(object_session(p), "process", p.id)
    return {"risk_count": sum(1 for r in rows if r["type"] == "risk"),
            "control_count": sum(1 for r in rows if r["type"] == "control")}


def _set_orgs(db: DBSession, p: Process, org_ids: list[int]) -> None:
    tree = OrgTree(db)
    kept = {o.id for o in p.org_units}  # a link to a unit deactivated since may stay; new links need an active unit
    bad = [i for i in org_ids if i not in tree.nodes and i not in kept]
    if bad:
        raise field_error("org_ids", f"not org units of the Org Structure: {bad}")
    db.execute(delete(ProcessOrgUnit).where(ProcessOrgUnit.process_id == p.id))
    for oid in dict.fromkeys(org_ids):
        db.add(ProcessOrgUnit(process_id=p.id, org_id=oid))
    db.flush()
    db.expire(p, ["org_units"])


def _check_process_parent(db: DBSession, pid: int | None, parent_id: int | None) -> None:
    if parent_id is None:
        return
    seen, cur = set(), parent_id
    while cur:
        if cur == pid:
            raise field_error("parent_id", "would create a loop")
        row = db.get(Process, cur)
        if row is None:
            raise field_error("parent_id", "is not a process")
        if cur in seen:
            break
        seen.add(cur)
        cur = row.parent_id


@router.get("/api/processes")
def list_processes(db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    rows = list(db.execute(select(Process).order_by(Process.name)).scalars())
    counts = dict(db.execute(select(EntityProcess.process_id, func.count()).join(
        EntityUnit, EntityUnit.id == EntityProcess.entity_id).where(EntityUnit.is_active.is_(True))
        .group_by(EntityProcess.process_id)).all())
    parents = {p.id: p.name for p in rows}
    return [_process_out(p, counts, parents) for p in rows]


@router.post("/api/processes", status_code=status.HTTP_201_CREATED)
def create_process(payload: ProcessIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    ensure_perm(user, *LIBRARY)
    _check_process_parent(db, None, payload.parent_id)
    if db.execute(select(Process.id).where(func.lower(Process.name) == payload.name.strip().lower())).first():
        raise field_error("name", "a process with this name already exists")
    p = Process(ref=next_reference(db, "PROC"), name=payload.name.strip(), description=payload.description,
                parent_id=payload.parent_id, owner_email=str(payload.owner_email) if payload.owner_email else None,
                status="Active", created_by=user.id)
    db.add(p)
    db.flush()
    _set_orgs(db, p, payload.org_ids)
    log_action(db, user_id=user.id, action=f"PROCESS_CREATE {p.ref} {p.name}", request=request)
    db.commit()
    return _process_out(p, {}, {})


@router.patch("/api/processes/{process_id}")
def update_process(process_id: int, payload: ProcessUpdate, request: Request, db: DBSession = Depends(get_db),
                   user: User = Staff) -> dict:
    ensure_perm(user, *LIBRARY)
    p = db.get(Process, process_id)
    if p is None:
        raise _not_found("Process")
    sent = payload.model_fields_set
    if payload.name is not None:
        p.name = payload.name.strip()
    if payload.description is not None:
        p.description = payload.description
    if "parent_id" in sent:
        _check_process_parent(db, p.id, payload.parent_id)
        p.parent_id = payload.parent_id
    if "owner_email" in sent:
        p.owner_email = str(payload.owner_email) if payload.owner_email else None
    if payload.status is not None:
        if payload.status not in ("Active", "Archived"):
            raise field_error("status", "must be Active or Archived")
        p.status = payload.status
    if payload.org_ids is not None:
        _set_orgs(db, p, payload.org_ids)
    log_action(db, user_id=user.id, action=f"PROCESS_UPDATE {p.ref} [{', '.join(sorted(sent))}]", request=request)
    db.commit()
    return _process_out(p, {}, {})


def entity_processes(db: DBSession, e: EntityUnit) -> list[Process]:
    """The processes an entity covers: those selected with it, or else every active process performed in its
    org units or below (an org-unit entity covers the processes of that unit)."""
    if e.processes:
        return list(e.processes)
    tree = OrgTree(db)
    orgs = {o for oid in [x.id for x in e.org_units] if oid in tree.nodes for o in tree.subtree(oid)}
    if not orgs:
        return []
    ids = {pid for (pid,) in db.execute(select(ProcessOrgUnit.process_id).where(ProcessOrgUnit.org_id.in_(orgs)))
           .all()}
    return list(db.execute(select(Process).where(Process.id.in_(ids or {0}), Process.status == "Active")
                           .order_by(Process.name)).scalars())


class ProcessLinksIn(BaseModel):
    risk_ids: list[int] = Field(default_factory=list, max_length=500)
    control_ids: list[int] = Field(default_factory=list, max_length=500)


def _object_links(db: DBSession, kind: str, rec_id: int) -> dict:
    from app.domains.grc.links import linked

    rows = linked(db, kind, rec_id)
    return {"risks": [r for r in rows if r["type"] == "risk"], "controls": [r for r in rows if r["type"] == "control"]}


@router.get("/api/object-library/options")
def object_library_options(db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    """Enterprise risks (Risk Manager) and standard controls (Frameworks & controls) for linking."""
    from app.domains.audit.frameworks.models import Framework, LibraryControl
    from app.domains.grc.risk.models import EnterpriseRisk

    fws = {f.id: f.code for f in db.execute(select(Framework)).scalars()}
    return {
        "risks": [{"id": r.id, "label": f"{r.ref} {r.title}", "category": r.category}
                  for r in db.execute(select(EnterpriseRisk).where(EnterpriseRisk.status != "Closed")
                                      .order_by(EnterpriseRisk.ref)).scalars()],
        "controls": [{"id": c.id, "label": f"{fws.get(c.framework_id, '')} {c.ref} {c.title}".strip(),
                      "process_area": c.process_area}
                     for c in db.execute(select(LibraryControl).where(LibraryControl.active.is_(True))
                                         .order_by(LibraryControl.framework_id, LibraryControl.ref)).scalars()],
    }


@router.get("/api/processes/{process_id}/links")
def process_links(process_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    if db.get(Process, process_id) is None:
        raise _not_found("Process")
    return _object_links(db, "process", process_id)


@router.put("/api/processes/{process_id}/links")
def set_process_links(process_id: int, payload: ProcessLinksIn, request: Request, db: DBSession = Depends(get_db),
                      user: User = Staff) -> dict:
    """Object library: the enterprise risks of a process and the standard controls that address them."""
    from app.domains.grc.links import set_links

    ensure_perm(user, *LIBRARY)
    p = db.get(Process, process_id)
    if p is None:
        raise _not_found("Process")
    set_links(db, "process", p.id, "risk", payload.risk_ids, user.id)
    set_links(db, "process", p.id, "control", payload.control_ids, user.id)
    log_action(db, user_id=user.id, action=f"PROCESS_LINKS {p.ref} risks={len(payload.risk_ids)} "
                                          f"controls={len(payload.control_ids)}", request=request)
    db.commit()
    return _object_links(db, "process", p.id)


@router.put("/api/auditable-entities/{entity_id}/links")
def set_entity_links(entity_id: int, payload: ProcessLinksIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Staff) -> dict:
    """Risks and controls linked to the entity itself (in addition to those of its processes)."""
    from app.domains.grc.links import set_links

    ensure_perm(user, *LIBRARY)
    e = _entity(db, entity_id)
    set_links(db, "unit", e.id, "risk", payload.risk_ids, user.id)
    set_links(db, "unit", e.id, "control", payload.control_ids, user.id)
    log_action(db, user_id=user.id, action=f"ENTITY_LINKS {e.code}", request=request)
    db.commit()
    return _object_links(db, "unit", e.id)


# ==================================================================== audit universe


def _key_objects(key: str, tree: OrgTree, pairs: dict[int, list[int]]) -> tuple[set[int], set[tuple[int, int]]]:
    """Org units and (org, process) pairs a selection key covers."""
    kind, _, rest = key.partition(":")
    if kind == "o":
        oid = int(rest)
        orgs = set(tree.subtree(oid))
        return orgs, {(o, p) for o in orgs for p in pairs.get(o, [])}
    if kind == "p":
        o, _, p = rest.partition(":")
        return set(), {(int(o), int(p))}
    raise ValueError(key)


def _entity_keys(db: DBSession, entity_ids: list[int]) -> dict[int, list[str]]:
    keys: dict[int, list[str]] = defaultdict(list)
    proc_orgs: dict[int, set[int]] = defaultdict(set)
    for eid, pid, oid in db.execute(select(EntityProcess.entity_id, EntityProcess.process_id, EntityProcess.org_id)
                                    .where(EntityProcess.entity_id.in_(entity_ids or [0]))).all():
        keys[eid].append(f"p:{oid}:{pid}")
        proc_orgs[eid].add(oid)
    for eid, oid in db.execute(select(EntityOrgUnit.entity_id, EntityOrgUnit.org_id)
                               .where(EntityOrgUnit.entity_id.in_(entity_ids or [0]))).all():
        if oid not in proc_orgs[eid]:
            keys[eid].append(f"o:{oid}")
    return {k: sorted(v) for k, v in keys.items()}


def _coverage(db: DBSession, tree: OrgTree, pairs: dict[int, list[int]], keys: list[str]) -> dict:
    orgs, prs = set(), set()
    for k in keys:
        try:
            o, p = _key_objects(k, tree, pairs)
        except (ValueError, KeyError):
            continue
        orgs |= o
        # an org unit selected through one of its processes counts as partly covered, not covered
        prs |= p
    all_pairs = {(o, p) for o, ps in pairs.items() for p in ps}
    total = len(tree.nodes) + len(all_pairs)
    done = len(orgs & set(tree.nodes)) + len(prs & all_pairs)
    state: dict[int, str] = {}
    for oid in tree.nodes:
        sub = tree.subtree(oid)
        objs = [("o", o) for o in sub] + [("p", (o, p)) for o in sub for p in pairs.get(o, [])]
        hit = [x for x in objs if (x[0] == "o" and x[1] in orgs) or (x[0] == "p" and x[1] in prs)]
        state[oid] = "Covered" if objs and len(hit) == len(objs) else ("Partially covered" if hit else "Not covered")
    return {"percent": round(100 * done / total) if total else 0, "covered": done, "total": total,
            "org_units": len(tree.nodes), "org_units_covered": len(orgs & set(tree.nodes)),
            "processes": len(all_pairs), "processes_covered": len(prs & all_pairs), "by_org": state}


def _next_due(e: EntityUnit) -> str | None:
    months = e.audit_frequency_months or _default_frequency(e)
    if not months:
        return None
    base = e.last_audited_at or e.defined_at or e.created_at
    return (base + timedelta(days=round(months * 30.44))).date().isoformat()


def _default_frequency(e: EntityUnit) -> int:
    years = {"High": cfg("audit_cycle_high_years"), "Medium": cfg("audit_cycle_medium_years"),
             "Low": cfg("audit_cycle_low_years")}.get(e.effective_rating, 3)
    return int(years) * 12


def _entity_row(e: EntityUnit, tree: OrgTree, procs: dict[int, str], links: dict, planned: dict,
                findings: dict) -> dict:
    org_ids = links["orgs"].get(e.id, [])
    proc_ids = links["procs"].get(e.id, [])
    months = e.audit_frequency_months or _default_frequency(e)
    return {
        "id": e.id, "code": e.code, "name": e.name, "status": "Active" if e.is_active else "Archived",
        "org_units": [{"id": o, "name": tree.all[o].name if o in tree.all else f"#{o}",
                       "path": " / ".join(n.name for n in tree.path(o))} for o in org_ids],
        "processes": [{"id": p, "name": procs.get(p, "")} for p in proc_ids],
        "category": e.location.name if e.location else None,
        "rating": e.assessed_rating, "score": round(e.assessed_score, 2) if e.assessed_score is not None else None,
        "assessed_at": e.assessed_at.isoformat() if e.assessed_at else None,
        "effective_rating": e.effective_rating, "inherent_score": e.risk_score,
        "frequency_months": months, "frequency": FREQUENCIES.get(months, f"Every {months} months"),
        "frequency_is_default": e.audit_frequency_months is None,
        "last_audited_at": e.last_audited_at.isoformat() if e.last_audited_at else None,
        "next_due": _next_due(e) if e.is_active else None,
        "planned_audits": planned.get(e.id, 0), "open_findings": findings.get(e.id, 0),
        "mapped": bool(org_ids), "archived_at": e.archived_at.isoformat() if e.archived_at else None,
        "owner_email": e.owner_email, "description": e.description,
        "entity_type": _type_of(e, org_ids, proc_ids),
        "definition_status": "Retired" if not e.is_active else (e.definition_status or "Ready"),
        "scope": e.scope or "", "objectives": e.objectives or "", "rationale": e.rationale or "",
        "effective_from": e.effective_from.isoformat() if e.effective_from else None,
        "effective_to": e.effective_to.isoformat() if e.effective_to else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _type_of(e: EntityUnit, org_ids: list[int], proc_ids: list[int]) -> str:
    if e.entity_type:
        return e.entity_type
    return "Process + unit" if proc_ids and org_ids else ("Process" if proc_ids else "Org unit")


def _links(db: DBSession, ids: list[int]) -> dict:
    orgs, procs = defaultdict(list), defaultdict(list)
    for eid, oid in db.execute(select(EntityOrgUnit.entity_id, EntityOrgUnit.org_id)
                               .where(EntityOrgUnit.entity_id.in_(ids or [0]))).all():
        orgs[eid].append(oid)
    for eid, pid in db.execute(select(EntityProcess.entity_id, EntityProcess.process_id)
                               .where(EntityProcess.entity_id.in_(ids or [0]))).all():
        procs[eid].append(pid)
    return {"orgs": orgs, "procs": procs}


def _planned_and_findings(db: DBSession, ids: list[int]) -> tuple[dict, dict]:
    from app.domains.audit.audits.models import Finding

    planned = dict(db.execute(select(PlanEngagement.entity_unit_id, func.count()).where(
        PlanEngagement.entity_unit_id.in_(ids or [0]), PlanEngagement.status == EngagementStatus.Planned)
        .group_by(PlanEngagement.entity_unit_id)).all())
    findings = dict(db.execute(select(AuditEntity.entity_id, func.count()).join(
        Finding, Finding.audit_id == AuditEntity.audit_id).where(
        AuditEntity.entity_id.in_(ids or [0]), Finding.status != FindingStatus.Closed)
        .group_by(AuditEntity.entity_id)).all())
    return planned, findings


def _entity_audit_ids(db: DBSession, entity_id: int) -> set[int]:
    """Audits covering the entity (entity tagging); their issues inherit the entity."""
    from app.domains.audit.audits.models import Audit

    tagged = {a for (a,) in db.execute(select(AuditEntity.audit_id).where(AuditEntity.entity_id == entity_id)).all()}
    primary = {a for (a,) in db.execute(select(Audit.id).where(Audit.entity_unit_id == entity_id)).all()}
    return tagged | primary


@router.get("/api/audit-universe")
def audit_universe(db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    """Coverage plus the auditable entities (HighBond: Auditable entity | Status | Org unit | Process)."""
    tree = OrgTree(db)
    pairs = _pairs(db, tree)
    entities = list(db.execute(select(EntityUnit).order_by(EntityUnit.is_active.desc(), EntityUnit.name)).scalars())
    ids = [e.id for e in entities]
    active_ids = [e.id for e in entities if e.is_active]
    keys = [k for ks in _entity_keys(db, active_ids).values() for k in ks]
    procs = {p.id: p.name for p in db.execute(select(Process)).scalars()}
    links = _links(db, ids)
    planned, findings = _planned_and_findings(db, ids)
    cov = _coverage(db, tree, pairs, keys)
    cov.pop("by_org")
    return {"defined": any(e.defined_at for e in entities), "coverage": cov,
            "entities": [_entity_row(e, tree, procs, links, planned, findings) for e in entities],
            "frequencies": [{"value": k, "label": v} for k, v in FREQUENCIES.items()]}


def _location_for(db: DBSession, tree: OrgTree, oid: int) -> Location:
    """Entity category: the port / office the org unit sits in (kept in step as the plan's entity category)."""
    from app.platform.organizations.router import Index

    idx = Index(db)
    org = tree.all.get(oid)
    top = idx.port_of(org) if org else None
    if top is None:
        path = tree.path(oid)
        top = path[0] if path else org
    code = (top.org_ref or f"ORG{top.id}")[:20].upper()
    loc = db.execute(select(Location).where(Location.code == code)).scalar_one_or_none()
    if loc is None:
        loc = Location(code=code, name=top.name, description="Org Structure: " + top.name, is_active=True)
        db.add(loc)
        db.flush()
    elif loc.name != top.name:
        loc.name = top.name
    return loc


# ---- auditable entity page


def _entity(db: DBSession, eid: int) -> EntityUnit:
    e = db.get(EntityUnit, eid)
    if e is None:
        raise _not_found("Auditable entity")
    return e


@router.get("/api/auditable-entities/{entity_id}")
def get_entity(entity_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    e = _entity(db, entity_id)
    tree = OrgTree(db)
    procs = {p.id: p.name for p in db.execute(select(Process)).scalars()}
    planned, findings = _planned_and_findings(db, [e.id])
    row = _entity_row(e, tree, procs, _links(db, [e.id]), planned, findings)
    own = _object_links(db, "unit", e.id)
    via = [{"process": pr.name, **_object_links(db, "process", pr.id)} for pr in entity_processes(db, e)]
    row["links"] = {"own": own, "processes": via}
    from app.domains.assurance.universe.workspace import entity_risk_counts, entity_usage

    row["usage"] = entity_usage(db, e)
    row["risk_counts"] = entity_risk_counts(db, [e.id], {e.id: [p["id"] for p in row["processes"]]})[e.id]
    owner = db.execute(select(User).where(func.lower(User.email) == (e.owner_email or "").lower())).scalars().first() \
        if e.owner_email else None
    row["owner"] = (owner.full_name or owner.username) if owner else e.owner_email
    open_ara = db.execute(select(AuditRiskAssessment).join(AraEntity, AraEntity.ara_id == AuditRiskAssessment.id)
                          .where(AraEntity.entity_id == e.id, AuditRiskAssessment.status != "Completed")
                          .order_by(AuditRiskAssessment.created_at.desc())).scalars().first()
    row["open_assessment"] = {"id": open_ara.id, "ref": open_ara.ref, "name": open_ara.name,
                              "status": open_ara.status} if open_ara else None
    row.update({"created_at": e.created_at.isoformat(),
                "defined_at": e.defined_at.isoformat() if e.defined_at else None,
                "risk_likelihood": e.risk_likelihood, "risk_impact": e.risk_impact,
                "frequencies": [{"value": k, "label": v} for k, v in FREQUENCIES.items()]})
    return row


class EntityUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    audit_frequency_months: int | None = None  # 0 = back to the default for its rating
    owner_email: OptEmail = None
    description: str | None = Field(None, max_length=20000)
    status: str | None = None  # Active | Archived (kept for older screens: Ready | Retired)
    org_ids: list[int] | None = Field(None, max_length=200)
    process_ids: list[int] | None = Field(None, max_length=200)
    entity_type: str | None = Field(None, max_length=40)
    definition_status: str | None = None
    scope: str | None = Field(None, max_length=20000)
    objectives: str | None = Field(None, max_length=20000)
    rationale: str | None = Field(None, max_length=20000)
    effective_from: date | None = None
    effective_to: date | None = None
    allow_duplicate: bool = False


LABELS = {"name": "Name", "entity_type": "Type", "definition_status": "Status", "owner_email": "Business owner",
          "audit_frequency_months": "Audit frequency", "effective_from": "Effective from",
          "effective_to": "Effective to"}
TEXTS = {"scope": "Scope", "objectives": "Objectives", "rationale": "Rationale", "description": "Description"}


@router.patch("/api/auditable-entities/{entity_id}")
def update_entity(entity_id: int, payload: EntityUpdate, request: Request, db: DBSession = Depends(get_db),
                  user: User = Staff) -> dict:
    from app.domains.assurance.universe.workspace import (
        check_definition,
        check_duplicate,
        history,
        resolve_links,
        write_links,
    )

    ensure_perm(user, *LIBRARY)
    e = _entity(db, entity_id)
    sent = payload.model_fields_set - {"allow_duplicate"}
    before = {k: getattr(e, k) for k in (*LABELS, *TEXTS)}
    before["definition_status"] = e.definition_status if e.is_active else "Retired"
    was_active = e.is_active
    if payload.status is not None:  # older screens: Active / Archived
        if payload.status not in ("Active", "Archived"):
            raise field_error("status", "must be Active or Archived")
        payload.definition_status = "Draft" if payload.status == "Active" else "Retired"
        sent = sent | {"definition_status"}
    links_before = _links(db, [e.id])
    old_orgs, old_procs = links_before["orgs"].get(e.id, []), links_before["procs"].get(e.id, [])
    name = payload.name.strip() if payload.name is not None else e.name
    etype = payload.entity_type if payload.entity_type is not None else _type_of(e, old_orgs, old_procs)
    status_ = payload.definition_status if "definition_status" in sent else before["definition_status"]
    owner = (str(payload.owner_email) if payload.owner_email else None) if "owner_email" in sent else e.owner_email
    scope = payload.scope if payload.scope is not None else (e.scope or "")
    eff_from = payload.effective_from if "effective_from" in sent else e.effective_from
    eff_to = payload.effective_to if "effective_to" in sent else e.effective_to
    if sent & {"name", "entity_type", "definition_status", "owner_email", "scope", "effective_from", "effective_to"}:
        check_definition(db, name=name, entity_type=etype, status_=status_, owner=owner, scope=scope,
                         effective_from=eff_from, effective_to=eff_to, exclude_id=e.id,
                         check_name=name.lower() != (e.name or "").lower() or (not was_active and status_ != "Retired"),
                         check_type=payload.entity_type is not None and payload.entity_type != e.entity_type)
    if "audit_frequency_months" in sent:
        m = payload.audit_frequency_months or None
        if m is not None and m not in FREQUENCIES:
            raise field_error("audit_frequency_months", "choose every 1, 2, 3, 4 or 5 years")
        e.audit_frequency_months = m
    e.name, e.owner_email = name, owner
    if payload.entity_type is not None:
        e.entity_type = etype
    for key in ("scope", "objectives", "rationale", "description"):
        value = getattr(payload, key)
        if value is not None:
            setattr(e, key, value.strip() if key != "description" else value)
    e.effective_from, e.effective_to = eff_from, eff_to
    if "definition_status" in sent:
        e.definition_status = status_
        e.is_active = status_ != "Retired"
        e.archived_at = None if e.is_active else (e.archived_at or utcnow())
    if payload.org_ids is not None or payload.process_ids is not None:
        tree = OrgTree(db)
        orgs_in = payload.org_ids if payload.org_ids is not None else old_orgs
        procs_in = payload.process_ids if payload.process_ids is not None else old_procs
        orgs, pairs = resolve_links(db, tree, orgs_in, procs_in, keep_orgs=set(old_orgs), keep_procs=set(old_procs))
        if e.is_active:
            check_duplicate(db, orgs, pairs, payload.allow_duplicate, exclude_id=e.id)
        write_links(db, e, orgs, pairs)
        if orgs[0] in tree.nodes:  # the entity category follows its first unit's port or office
            e.location_id = _location_for(db, tree, orgs[0]).id
        names = {o.id: o.name for o in db.execute(select(Organization).where(
            Organization.id.in_(set(orgs) | set(old_orgs) or {0}))).scalars()}
        pnames = {p.id: p.name for p in db.execute(select(Process).where(
            Process.id.in_({p for p, _ in pairs} | set(old_procs) or {0}))).scalars()}
        added = [names.get(o, "") for o in orgs if o not in old_orgs] + \
            [pnames.get(p, "") for p, _ in pairs if p not in old_procs]
        removed = [names.get(o, "") for o in old_orgs if o not in orgs] + \
            [pnames.get(p, "") for p in old_procs if p not in {x for x, _ in pairs}]
        if added or removed:
            history(db, e, user, "Links: " + "; ".join(
                ([f"added {', '.join(added)}"] if added else []) + ([f"removed {', '.join(removed)}"] if removed
                                                                    else []))[:480], request)
    elif e.is_active and not was_active:  # reactivated: must not duplicate an active entity
        check_duplicate(db, old_orgs, [(p, 0) for p in old_procs], payload.allow_duplicate, exclude_id=e.id)
    if not before["entity_type"]:
        before["entity_type"] = _type_of(e, old_orgs, old_procs)
    changes = []
    for key, label in LABELS.items():
        now_val = e.definition_status if key == "definition_status" and e.is_active else (
            "Retired" if key == "definition_status" else getattr(e, key))
        if key in sent and before[key] != now_val:
            old_txt, new_txt = before[key], now_val
            if key == "owner_email":
                names = {(u.email or "").lower(): u.full_name or u.username for u in db.execute(select(User).where(
                    func.lower(User.email).in_([(x or "").lower() for x in (old_txt, new_txt)]))).scalars()}
                old_txt, new_txt = (names.get((x or "").lower(), x) for x in (old_txt, new_txt))
            changes.append(f"{label}: {old_txt or '-'} -> {new_txt or '-'}")
    changes += [f"Changed {label.lower()}" for key, label in TEXTS.items()
                if key in sent and (before[key] or "") != (getattr(e, key) or "")]
    if changes:
        history(db, e, user, "; ".join(changes)[:490], request)
    log_action(db, user_id=user.id, action=f"ENTITY_UPDATE {e.code} [{', '.join(sorted(sent))}]", request=request,
               entity_type="auditable_entity", entity_id=e.id)
    db.commit()
    return get_entity(entity_id, db, user)


@router.get("/api/auditable-entities/{entity_id}/assessments")
def entity_assessments(entity_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    _entity(db, entity_id)
    out = []
    for ara in db.execute(select(AuditRiskAssessment).join(AraEntity, AraEntity.ara_id == AuditRiskAssessment.id)
                          .where(AraEntity.entity_id == entity_id).order_by(AuditRiskAssessment.created_at.desc()))\
            .scalars():
        scores = [s for (s,) in db.execute(select(AraScore.score).where(AraScore.ara_id == ara.id,
                                                                       AraScore.entity_id == entity_id)).all()]
        overall = sum(scores) / len(scores) if scores else None
        prio = db.get(AraEntity, (ara.id, entity_id))
        out.append({"id": ara.id, "ref": ara.ref, "name": ara.name, "status": ara.status, "scale": ara.scale,
                    "overall": round(overall, 2) if overall is not None else None,
                    "rating": scale_label(ara.scale, overall), "priority": prio.priority if prio else None,
                    "completed_at": ara.completed_at.isoformat() if ara.completed_at else None})
    return out


@router.get("/api/auditable-entities/{entity_id}/audits")
def entity_audits(entity_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> list[dict]:
    from app.core.access import visible
    from app.domains.audit.audits.models import Audit

    _entity(db, entity_id)
    audits = visible(db, user, "audit", list(db.execute(select(Audit).where(
        Audit.id.in_(_entity_audit_ids(db, entity_id) or {0}))
                                                        .order_by(Audit.created_at.desc())).scalars()))
    plans = {e.audit_id: e for e in db.execute(select(PlanEngagement).where(
        PlanEngagement.entity_unit_id == entity_id)).scalars()}
    rows = [{"id": a.id, "ref": f"AUD-{a.id:04d}", "title": a.title, "status": a.status.value,
             "audit_type": a.audit_type, "quarter": plans[a.id].planned_quarter if a.id in plans else None,
             "created_at": a.created_at.isoformat()} for a in audits]
    for eng in plans.values():  # planned engagements not started yet
        if not eng.audit_id:
            rows.append({"id": None, "ref": None, "title": eng.title, "status": f"Planned ({eng.status.value})",
                         "audit_type": None, "quarter": eng.planned_quarter, "created_at": eng.created_at.isoformat()})
    return rows


@router.get("/api/auditable-entities/{entity_id}/findings")
def entity_findings(entity_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    from app.core.access import staff_audit_scope
    from app.domains.audit.audits.models import Audit, Finding
    from app.domains.issues.capa.closure import remediation_summary

    _entity(db, entity_id)
    stmt = select(Finding, Audit).join(Audit, Audit.id == Finding.audit_id).where(
        Audit.id.in_(_entity_audit_ids(db, entity_id) or {0}))
    scope = staff_audit_scope(db, user) if user.role == Role.Auditor else None
    if scope is not None:
        stmt = stmt.where(Audit.id.in_(scope or {0}))
    rows = []
    for f, a in db.execute(stmt.order_by(Finding.created_at.desc())).all():
        rem = remediation_summary(db, f)
        rows.append({"id": f.id, "title": f.title, "severity": f.risk_rating.value, "status": f.status.value,
                     "audit_id": a.id, "audit": a.title, "remediation": rem["state"], "actions": rem["actions"],
                     "open_actions": rem["open_actions"]})
    return {"summary": {"findings": len(rows), "open": sum(1 for r in rows if r["status"] != "Closed"),
                        "high": sum(1 for r in rows if r["severity"] == "High" and r["status"] != "Closed"),
                        "open_actions": sum(r["open_actions"] for r in rows)}, "items": rows}


# ==================================================================== settings: assessment factors and scale


AUTO_SOURCES = {
    "time_since_audit": "Time since last audit (from the last audit and the entity's audit frequency)",
    "prior_results": "Prior audit results (open findings and overdue actions on the entity)",
}


class FactorIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str = Field("", max_length=5000)
    auto_source: str | None = None


def _check_auto(source: str | None) -> str | None:
    if source and source not in AUTO_SOURCES:
        raise field_error("auto_source", f"choose one of: {', '.join(AUTO_SOURCES)}")
    return source or None


@router.get("/api/assessment-factors")
def list_factors(db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    used = dict(db.execute(select(AraFactor.factor_id, func.count()).group_by(AraFactor.factor_id)).all())
    rows = db.execute(select(AssessmentFactor).where(AssessmentFactor.is_active.is_(True))
                      .order_by(AssessmentFactor.ref)).scalars()
    return {"scale": cfg("audit_risk_scale"), "scales": [{"name": k, "levels": v} for k, v in SCALES.items()],
            "auto_sources": [{"value": k, "label": v} for k, v in AUTO_SOURCES.items()],
            "items": [{"id": f.id, "ref": f.ref, "name": f.name, "description": f.description,
                       "auto_source": f.auto_source, "used_in": used.get(f.id, 0)} for f in rows]}


@router.post("/api/assessment-factors", status_code=status.HTTP_201_CREATED)
def create_factor(payload: FactorIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    ensure_perm(user, *PLANNING)
    f = AssessmentFactor(ref=next_reference(db, "AF"), name=payload.name.strip(), description=payload.description,
                         auto_source=_check_auto(payload.auto_source), created_by=user.id)
    db.add(f)
    db.flush()
    log_action(db, user_id=user.id, action=f"FACTOR_CREATE {f.ref} {f.name}", request=request)
    db.commit()
    return {"id": f.id, "ref": f.ref, "name": f.name, "description": f.description, "used_in": 0}


@router.patch("/api/assessment-factors/{factor_id}")
def update_factor(factor_id: int, payload: FactorIn, request: Request, db: DBSession = Depends(get_db),
                  user: User = Staff) -> dict:
    ensure_perm(user, *PLANNING)
    f = db.get(AssessmentFactor, factor_id)
    if f is None or not f.is_active:
        raise _not_found("Assessment factor")
    f.name, f.description = payload.name.strip(), payload.description
    f.auto_source = _check_auto(payload.auto_source)
    log_action(db, user_id=user.id, action=f"FACTOR_UPDATE {f.ref}", request=request)
    db.commit()
    return {"id": f.id, "ref": f.ref, "name": f.name, "description": f.description}


@router.delete("/api/assessment-factors/{factor_id}")
def delete_factor(factor_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Delete a factor. A factor used in a completed assessment is retired instead, so the record stays whole."""
    ensure_perm(user, *PLANNING)
    f = db.get(AssessmentFactor, factor_id)
    if f is None or not f.is_active:
        raise _not_found("Assessment factor")
    in_completed = db.execute(select(func.count()).select_from(AraFactor).join(
        AuditRiskAssessment, AuditRiskAssessment.id == AraFactor.ara_id).where(
        AraFactor.factor_id == f.id, AuditRiskAssessment.status == "Completed")).scalar_one()
    if in_completed:
        f.is_active = False
        what = "retired"
    else:
        db.delete(f)
        what = "deleted"
    log_action(db, user_id=user.id, action=f"FACTOR_{what.upper()} {f.ref}", request=request)
    db.commit()
    return {"message": f"Assessment factor {what}"}


# ==================================================================== audit risk assessments


class AraIn(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    entity_ids: list[int] = Field(min_length=1, max_length=2000)
    factor_ids: list[int] = Field(min_length=1, max_length=100)
    scale: str | None = None


class AraConfig(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=255)
    entity_ids: list[int] | None = Field(None, min_length=1, max_length=2000)
    factor_ids: list[int] | None = Field(None, min_length=1, max_length=100)


class ScoreIn(BaseModel):
    entity_id: int
    factor_id: int
    score: int | None = None


class PriorityIn(BaseModel):
    entity_ids: list[int] = Field(default_factory=list, max_length=2000)


class NoteIn(BaseModel):
    note: str | None = Field(None, max_length=5000)


class ConclusionIn(BaseModel):
    conclusion: str = Field("", max_length=50000)


class PlanningIn(BaseModel):
    plan_id: int | None = None
    fiscal_year: int | None = Field(None, ge=2000, le=2100)
    title: str | None = Field(None, max_length=255)
    entity_ids: list[int] | None = None  # default: every prioritised entity


def _ara(db: DBSession, ara_id: int) -> AuditRiskAssessment:
    a = db.get(AuditRiskAssessment, ara_id)
    if a is None:
        raise _not_found("Audit risk assessment")
    return a


def _editable(a: AuditRiskAssessment) -> None:
    if a.status == "Completed":
        raise _conflict("The assessment is completed; it is a permanent record")


def _members(db: DBSession, a: AuditRiskAssessment) -> tuple[list[EntityUnit], list[AssessmentFactor]]:
    ents = list(db.execute(select(EntityUnit).join(AraEntity, AraEntity.entity_id == EntityUnit.id)
                           .where(AraEntity.ara_id == a.id).order_by(EntityUnit.name)).scalars())
    facs = list(db.execute(select(AssessmentFactor).join(AraFactor, AraFactor.factor_id == AssessmentFactor.id)
                           .where(AraFactor.ara_id == a.id).order_by(AssessmentFactor.ref)).scalars())
    return ents, facs


def _scores(db: DBSession, a: AuditRiskAssessment) -> dict[tuple[int, int], int]:
    return {(s.entity_id, s.factor_id): s.score for s in db.execute(select(AraScore).where(AraScore.ara_id == a.id))
            .scalars()}


def _ara_out(db: DBSession, a: AuditRiskAssessment, full: bool = False) -> dict:
    ents, facs = _members(db, a)
    sc = _scores(db, a)
    cells = len(ents) * len(facs)
    scored = sum(1 for e in ents for f in facs if (e.id, f.id) in sc)
    out = {"id": a.id, "ref": a.ref, "name": a.name, "status": a.status, "scale": a.scale,
           "levels": SCALES.get(a.scale, []), "entities": len(ents), "factors": len(facs),
           "scored": scored, "cells": cells, "complete": cells > 0 and scored == cells, "plan_id": a.plan_id,
           "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat(),
           "completed_at": a.completed_at.isoformat() if a.completed_at else None}
    names = _names(db, [a.created_by, a.completed_by])
    out["created_by"] = names.get(a.created_by)
    out["completed_by"] = names.get(a.completed_by)
    if a.plan_id:
        plan = db.get(AssurancePlan, a.plan_id)
        out["plan"] = f"{plan.plan_ref} FY{plan.fiscal_year}" if plan else None
    if not full:
        return out
    meta = {m.entity_id: m for m in db.execute(select(AraEntity).where(AraEntity.ara_id == a.id)).scalars()}
    note_names = _names(db, [m.note_by for m in meta.values()])
    tree = OrgTree(db)
    rows = []
    for e in ents:
        vals = [sc[(e.id, f.id)] for f in facs if (e.id, f.id) in sc]
        overall = sum(vals) / len(vals) if vals and len(vals) == len(facs) else None
        m = meta.get(e.id)
        rows.append({"entity_id": e.id, "code": e.code, "name": e.name,
                     "org_unit": " / ".join(o.name for o in tree.path(e.org_unit_id)) if e.org_unit_id else None,
                     "status": "Active" if e.is_active else "Archived",
                     "scores": {str(f.id): sc.get((e.id, f.id)) for f in facs},
                     "overall": round(overall, 2) if overall is not None else None,
                     "rating": scale_label(a.scale, overall), "priority": m.priority if m else None,
                     "note": m.note if m else None, "note_by": note_names.get(m.note_by) if m else None,
                     "note_at": m.note_at.isoformat() if m and m.note_at else None,
                     "last_audited_at": e.last_audited_at.isoformat() if e.last_audited_at else None})
    out.update({"conclusion": a.conclusion, "factor_list": [{"id": f.id, "ref": f.ref, "name": f.name,
                                                             "auto": bool(f.auto_source)} for f in facs],
                "rows": rows})
    return out


def _check_members(db: DBSession, entity_ids: list[int] | None, factor_ids: list[int] | None,
                   current: set[int] | None = None) -> None:
    if entity_ids is not None:
        found = {e for (e,) in db.execute(select(EntityUnit.id).where(
            EntityUnit.id.in_(entity_ids), EntityUnit.is_active.is_(True),
            EntityUnit.definition_status == "Ready")).all()}
        if set(entity_ids) - found - (current or set()):
            raise field_error("entity_ids", "include Ready auditable entities only (Audit universe > Entities)")
    if factor_ids is not None:
        found = {f for (f,) in db.execute(select(AssessmentFactor.id).where(
            AssessmentFactor.id.in_(factor_ids), AssessmentFactor.is_active.is_(True))).all()}
        if set(factor_ids) - found:
            raise field_error("factor_ids", "include current assessment factors only")


def _set_members(db: DBSession, a: AuditRiskAssessment, entity_ids: list[int] | None,
                 factor_ids: list[int] | None) -> None:
    if entity_ids is not None:
        keep = set(entity_ids)
        for m in db.execute(select(AraEntity).where(AraEntity.ara_id == a.id)).scalars():
            if m.entity_id not in keep:
                db.delete(m)
        have = {m for (m,) in db.execute(select(AraEntity.entity_id).where(AraEntity.ara_id == a.id)).all()}
        for eid in dict.fromkeys(entity_ids):
            if eid not in have:
                db.add(AraEntity(ara_id=a.id, entity_id=eid))
    if factor_ids is not None:
        db.execute(delete(AraFactor).where(AraFactor.ara_id == a.id))
        for fid in dict.fromkeys(factor_ids):
            db.add(AraFactor(ara_id=a.id, factor_id=fid))
    db.flush()


def _auto_fraction(db: DBSession, e: EntityUnit, source: str) -> float:
    """0 (lowest risk) to 1 (highest) for an automatic factor; mapped onto the assessment's scale."""
    if source == "time_since_audit":
        if e.last_audited_at is None:
            return 1.0
        months = (utcnow() - e.last_audited_at).days / 30.44
        cycle = e.audit_frequency_months or _default_frequency(e)
        return max(0.0, min(1.0, months / cycle if cycle else 1.0))
    if source == "prior_results":
        from app.core.enums import CapaStatus
        from app.domains.audit.audits.models import Finding
        from app.domains.issues.capa.models import Capa

        audit_ids = _entity_audit_ids(db, e.id)
        if not audit_ids:
            return 0.0
        open_f = list(db.execute(select(Finding).where(Finding.audit_id.in_(audit_ids),
                                                       Finding.status != FindingStatus.Closed)).scalars())
        overdue = 0
        if open_f:
            overdue = db.execute(select(func.count()).select_from(Capa).where(
                Capa.source_type == "finding", Capa.source_id.in_([f.id for f in open_f]),
                Capa.status != CapaStatus.Closed, Capa.due_date < utcnow())).scalar_one()
        ratings = {f.risk_rating.value for f in open_f}
        if overdue or "High" in ratings:
            return 1.0
        if "Medium" in ratings:
            return 0.66
        if "Low" in ratings:
            return 0.33
        return 0.0
    return 0.0


def _auto_score(db: DBSession, a: AuditRiskAssessment, user: User, overwrite: bool) -> int:
    """Fill the cells of automatic factors from GIAW records (only empty cells unless ``overwrite``)."""
    ents, facs = _members(db, a)
    autos = [f for f in facs if f.auto_source]
    if not autos:
        return 0
    n = len(SCALES.get(a.scale, [])) or 3
    have = {(s.entity_id, s.factor_id): s for s in db.execute(select(AraScore).where(AraScore.ara_id == a.id))
            .scalars()}
    filled = 0
    for e in ents:
        for f in autos:
            cell = have.get((e.id, f.id))
            if cell is not None and not overwrite:
                continue
            score = 1 + int(_auto_fraction(db, e, f.auto_source) * (n - 1) + 0.5)
            if cell is None:
                db.add(AraScore(ara_id=a.id, entity_id=e.id, factor_id=f.id, score=score, scored_by=user.id))
            else:
                cell.score, cell.scored_by, cell.scored_at = score, user.id, utcnow()
            filled += 1
    if filled and a.status == "Draft":
        a.status = "In progress"
    db.flush()
    return filled


class AutoScoreIn(BaseModel):
    overwrite: bool = False


@router.post("/api/audit-risk-assessments/{ara_id}/auto-score")
def auto_score(ara_id: int, payload: AutoScoreIn, request: Request, db: DBSession = Depends(get_db),
               user: User = Staff) -> dict:
    """Score the automatic factors (time since last audit, prior audit results) from the entities' records."""
    ensure_perm(user, *PLANNING)
    a = _ara(db, ara_id)
    _editable(a)
    filled = _auto_score(db, a, user, payload.overwrite)
    log_action(db, user_id=user.id, action=f"ARA_AUTOSCORE {a.ref} filled={filled}", request=request)
    db.commit()
    return {"filled": filled, **_ara_out(db, a, True)}


@router.get("/api/audit-risk-assessments")
def list_aras(db: DBSession = Depends(get_db), _: User = Staff) -> list[dict]:
    return [_ara_out(db, a) for a in db.execute(select(AuditRiskAssessment)
                                                .order_by(AuditRiskAssessment.created_at.desc())).scalars()]


@router.post("/api/audit-risk-assessments", status_code=status.HTTP_201_CREATED)
def create_ara(payload: AraIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    ensure_perm(user, *PLANNING)
    if not db.execute(select(EntityUnit.id).where(EntityUnit.is_active.is_(True))).first():
        raise _conflict("Define the audit universe first")
    scale = payload.scale or cfg("audit_risk_scale")
    if scale not in SCALES:
        raise field_error("scale", f"choose {' or '.join(SCALES)}")
    if db.execute(select(AuditRiskAssessment.id).where(AuditRiskAssessment.name == payload.name.strip())).first():
        raise field_error("name", "another assessment already has this name")
    _check_members(db, payload.entity_ids, payload.factor_ids)
    a = AuditRiskAssessment(ref=next_reference(db, "ARA"), name=payload.name.strip(), scale=scale, status="Draft",
                            conclusion="", created_by=user.id)
    db.add(a)
    db.flush()
    _set_members(db, a, payload.entity_ids, payload.factor_ids)
    _auto_score(db, a, user, overwrite=False)
    log_action(db, user_id=user.id, action=f"ARA_CREATE {a.ref} {a.name}", request=request)
    db.commit()
    return _ara_out(db, a, True)


@router.get("/api/audit-risk-assessments/{ara_id}")
def get_ara(ara_id: int, db: DBSession = Depends(get_db), _: User = Staff) -> dict:
    return _ara_out(db, _ara(db, ara_id), True)


@router.patch("/api/audit-risk-assessments/{ara_id}")
def configure_ara(ara_id: int, payload: AraConfig, request: Request, db: DBSession = Depends(get_db),
                  user: User = Staff) -> dict:
    """Configure: include or exclude entities and factors, rename. Earlier scores are kept."""
    ensure_perm(user, *PLANNING)
    a = _ara(db, ara_id)
    _editable(a)
    if payload.name is not None and payload.name.strip() != a.name:
        if db.execute(select(AuditRiskAssessment.id).where(AuditRiskAssessment.name == payload.name.strip())).first():
            raise field_error("name", "another assessment already has this name")
        a.name = payload.name.strip()
    current = {e for (e,) in db.execute(select(AraEntity.entity_id).where(AraEntity.ara_id == a.id)).all()}
    _check_members(db, payload.entity_ids, payload.factor_ids, current)
    _set_members(db, a, payload.entity_ids, payload.factor_ids)
    log_action(db, user_id=user.id, action=f"ARA_CONFIGURE {a.ref}", request=request)
    db.commit()
    return _ara_out(db, a, True)


@router.put("/api/audit-risk-assessments/{ara_id}/scores")
def score_cell(ara_id: int, payload: ScoreIn, request: Request, db: DBSession = Depends(get_db),
               user: User = Staff) -> dict:
    """Score one entity on one factor (saved at once). Higher scores mean higher risk."""
    ensure_perm(user, *PLANNING)
    a = _ara(db, ara_id)
    _editable(a)
    if db.get(AraEntity, (a.id, payload.entity_id)) is None or db.get(AraFactor, (a.id, payload.factor_id)) is None:
        raise field_error("entity_id", "the entity or factor is not part of this assessment")
    levels = SCALES.get(a.scale, [])
    row = db.execute(select(AraScore).where(AraScore.ara_id == a.id, AraScore.entity_id == payload.entity_id,
                                            AraScore.factor_id == payload.factor_id)).scalar_one_or_none()
    if payload.score is None:
        if row is not None:
            db.delete(row)
    else:
        if not 1 <= payload.score <= len(levels):
            raise field_error("score", f"choose a score from 1 to {len(levels)}")
        if row is None:
            db.add(AraScore(ara_id=a.id, entity_id=payload.entity_id, factor_id=payload.factor_id,
                            score=payload.score, scored_by=user.id))
        else:
            row.score, row.scored_by, row.scored_at = payload.score, user.id, utcnow()
    if a.status == "Draft":
        a.status = "In progress"
    a.updated_at = utcnow()
    log_action(db, user_id=user.id, request=request,
               action=f"ARA_SCORE {a.ref} id={a.id} entity={payload.entity_id} factor={payload.factor_id} "
                      f"score={payload.score if payload.score is not None else 'cleared'}")
    db.commit()
    out = _ara_out(db, a, True)
    row_out = next(r for r in out["rows"] if r["entity_id"] == payload.entity_id)
    return {"status": out["status"], "scored": out["scored"], "cells": out["cells"], "complete": out["complete"],
            "row": row_out}


def _require_complete(db: DBSession, a: AuditRiskAssessment) -> None:
    out = _ara_out(db, a)
    if not out["complete"]:
        raise _conflict(f"Score every entity on every factor first ({out['scored']} of {out['cells']} scored)")


@router.put("/api/audit-risk-assessments/{ara_id}/priorities")
def set_priorities(ara_id: int, payload: PriorityIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Staff) -> dict:
    """Prioritised auditable entities for audit, in rank order. Removing one deletes its note."""
    ensure_perm(user, *PLANNING)
    a = _ara(db, ara_id)
    _editable(a)
    _require_complete(db, a)
    rank = {eid: n for n, eid in enumerate(dict.fromkeys(payload.entity_ids), start=1)}
    for m in db.execute(select(AraEntity).where(AraEntity.ara_id == a.id)).scalars():
        if m.entity_id in rank:
            m.priority = rank.pop(m.entity_id)
        elif m.priority is not None:
            m.priority, m.note, m.note_by, m.note_at = None, None, None, None
    if rank:
        raise field_error("entity_ids", "prioritise entities included in this assessment")
    log_action(db, user_id=user.id, request=request,
               action=f"ARA_PRIORITIES {a.ref} id={a.id} order={','.join(map(str, payload.entity_ids))[:300]}")
    db.commit()
    return _ara_out(db, a, True)


@router.put("/api/audit-risk-assessments/{ara_id}/notes/{entity_id}")
def set_note(ara_id: int, entity_id: int, payload: NoteIn, request: Request, db: DBSession = Depends(get_db),
             user: User = Staff) -> dict:
    ensure_perm(user, *PLANNING)
    a = _ara(db, ara_id)
    _editable(a)
    m = db.get(AraEntity, (a.id, entity_id))
    if m is None or m.priority is None:
        raise _conflict("Notes are kept on prioritised entities")
    text = (payload.note or "").strip() or None
    m.note, m.note_by, m.note_at = text, (user.id if text else None), (utcnow() if text else None)
    log_action(db, user_id=user.id, request=request, action=f"ARA_NOTE {a.ref} id={a.id} entity={entity_id}")
    db.commit()
    return _ara_out(db, a, True)


@router.put("/api/audit-risk-assessments/{ara_id}/conclusion")
def set_conclusion(ara_id: int, payload: ConclusionIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Staff) -> dict:
    ensure_perm(user, *PLANNING)
    a = _ara(db, ara_id)
    _editable(a)
    a.conclusion = payload.conclusion.strip()
    log_action(db, user_id=user.id, request=request, action=f"ARA_CONCLUSION {a.ref} id={a.id}")
    db.commit()
    return _ara_out(db, a, True)


def _refresh_entity_ratings(db: DBSession, entity_ids: list[int]) -> None:
    """Each entity carries the result of its latest completed assessment."""
    for eid in entity_ids:
        e = db.get(EntityUnit, eid)
        latest = db.execute(select(AuditRiskAssessment).join(AraEntity, AraEntity.ara_id == AuditRiskAssessment.id)
                            .where(AraEntity.entity_id == eid, AuditRiskAssessment.status == "Completed")
                            .order_by(AuditRiskAssessment.completed_at.desc())).scalars().first()
        if latest is None:
            e.assessed_score = e.assessed_rating = e.assessed_at = e.assessment_id = None
            continue
        vals = [s for (s,) in db.execute(select(AraScore.score).join(
            AraFactor, (AraFactor.ara_id == AraScore.ara_id) & (AraFactor.factor_id == AraScore.factor_id))
            .where(AraScore.ara_id == latest.id, AraScore.entity_id == eid)).all()]
        overall = sum(vals) / len(vals) if vals else None
        e.assessed_score, e.assessed_rating = overall, scale_label(latest.scale, overall)
        e.assessed_at, e.assessment_id = latest.completed_at, latest.id


@router.post("/api/audit-risk-assessments/{ara_id}/complete")
def complete_ara(ara_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Mark as completed: the assessment becomes a permanent record and rates its entities."""
    ensure_perm(user, *PLANNING)
    a = _ara(db, ara_id)
    _editable(a)
    _require_complete(db, a)
    a.status, a.completed_by, a.completed_at = "Completed", user.id, utcnow()
    db.flush()
    ents, _ = _members(db, a)
    _refresh_entity_ratings(db, [e.id for e in ents])
    log_action(db, user_id=user.id, action=f"ARA_COMPLETE {a.ref}", request=request)
    db.commit()
    return _ara_out(db, a, True)


@router.post("/api/audit-risk-assessments/{ara_id}/revert")
def revert_ara(ara_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    """Revert to in progress (notes and conclusion are kept). Not once the assessment feeds an audit plan."""
    ensure_perm(user, *PLANNING)
    a = _ara(db, ara_id)
    if a.status != "Completed":
        raise _conflict("Only a completed assessment can be reverted")
    if a.plan_id:
        raise _conflict("The assessment is linked to an audit plan and stays completed")
    a.status, a.completed_by, a.completed_at = "In progress", None, None
    db.flush()
    ents, _ = _members(db, a)
    _refresh_entity_ratings(db, [e.id for e in ents])
    log_action(db, user_id=user.id, action=f"ARA_REVERT {a.ref}", request=request)
    db.commit()
    return _ara_out(db, a, True)


@router.delete("/api/audit-risk-assessments/{ara_id}")
def delete_ara(ara_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    ensure_perm(user, *PLANNING)
    a = _ara(db, ara_id)
    _editable(a)
    ref = a.ref
    db.delete(a)
    log_action(db, user_id=user.id, action=f"ARA_DELETE {ref}", request=request)
    db.commit()
    return {"message": f"{ref} deleted"}


@router.post("/api/audit-risk-assessments/{ara_id}/start-planning")
def start_planning(ara_id: int, payload: PlanningIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Staff) -> dict:
    """Start planning: add an audit plan or link an existing draft plan, and generate an engagement for each
    prioritised entity not yet in the plan (named after the entity, budget from configuration)."""
    ensure_perm(user, "plan.prepare", "plan.amend")
    a = _ara(db, ara_id)
    if a.status != "Completed":
        raise _conflict("Complete the assessment before planning from it")
    if payload.plan_id:
        plan = db.get(AssurancePlan, payload.plan_id)
        if plan is None:
            raise _not_found("Assurance Plan")
    else:
        if not payload.fiscal_year:
            raise field_error("fiscal_year", "choose the plan year, or an existing plan")
        if db.execute(select(AssurancePlan.id).where(AssurancePlan.fiscal_year == payload.fiscal_year)).first():
            raise field_error("fiscal_year", "a plan for this year already exists; link to it instead")
        from pydantic import ValidationError

        from app.domains.assurance.planning.schemas import PlanIn

        try:
            spec = PlanIn(fiscal_year=payload.fiscal_year,
                          title=(payload.title or f"Assurance Plan FY{payload.fiscal_year}").strip(),
                          description=f"Scope from audit risk assessment {a.ref} {a.name}.")
        except ValidationError as exc:
            raise field_error("fiscal_year", exc.errors()[0]["msg"]) from None
        plan = AssurancePlan(plan_ref=next_reference(db, "AP"), created_by=user.id, **spec.model_dump())
        db.add(plan)
        db.flush()
    if plan.status != PlanStatus.Draft:
        raise _conflict("Engagements are added to a draft plan; use a change request for an approved plan")
    from app.domains.assurance.planning.projects import max_projects
    prioritised = [m for m in db.execute(select(AraEntity).where(AraEntity.ara_id == a.id,
                                                                 AraEntity.priority.is_not(None))
                                         .order_by(AraEntity.priority)).scalars()]
    wanted = set(payload.entity_ids) if payload.entity_ids is not None else {m.entity_id for m in prioritised}
    in_plan = {e.entity_unit_id for e in plan.engagements if e.status != EngagementStatus.Cancelled}
    from app.platform.organizations.router import Index

    idx = Index(db)
    hours = int(cfg("default_engagement_hours"))
    added = []
    for n, m in enumerate(prioritised):
        if m.entity_id not in wanted or m.entity_id in in_plan:
            continue
        if sum(1 for x in plan.engagements if x.status != EngagementStatus.Cancelled) + len(added) >= max_projects():
            break  # the plan is full; the remaining entities are reported as not added
        e = db.get(EntityUnit, m.entity_id)
        org = idx.rows.get(e.org_unit_id) if e.org_unit_id else None
        site = idx.port_of(org) if org else None
        eng = PlanEngagement(plan_id=plan.id, entity_unit_id=e.id, title=f"{e.name} audit"[:255],
                             rationale=f"Priority {m.priority} in {a.ref} ({e.assessed_rating or 'rated'})."
                                       + (f" {m.note}" if m.note else ""),
                             planned_quarter=["Q1", "Q2", "Q3", "Q4"][min(3, n * 4 // max(1, len(prioritised)))],
                             budget_hours=hours, site_entity_id=site.id if site else None,
                             status=EngagementStatus.Planned, created_by=user.id)
        db.add(eng)
        added.append(e.name)
    a.plan_id = plan.id
    log_action(db, user_id=user.id, action=f"ARA_PLAN {a.ref} plan={plan.plan_ref} added={len(added)}",
               request=request)
    log_record_history(db, record_type="assurance_plan", record_id=plan.id, user_id=user.id,
                       action=f"PLANNED FROM {a.ref}: {len(added)} engagement(s) generated", request=request)
    db.commit()
    return {"plan_id": plan.id, "plan_ref": plan.plan_ref, "added": len(added), "engagements": added}


__all__ = ["router", "OrgTree"]
