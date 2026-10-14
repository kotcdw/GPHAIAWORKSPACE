"""Compliance Maps API: obligations and their requirements, the standard controls that meet each requirement,
coverage gaps, compliance assessments and the impact of a new version of an obligation.

A new version of an obligation flags every one of its requirements "review required" until someone re-assesses
it, so a change in the law shows up as work rather than being missed.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import utcnow
from app.core.refs import next_reference
from app.domains.grc import links
from app.domains.grc.common import Viewer, can, check_entity, check_user, editor, entity_name, in_list, name_of
from app.domains.grc.compliance.models import COMPLIANCE_STATUSES, Regulation, Requirement
from app.platform.users.models import User

router = APIRouter(prefix="/api/grc", tags=["risk & compliance"])
Editor = editor("grc.compliance")


class RegulationIn(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9._/() -]+$")
    title: str = Field(min_length=3, max_length=255)
    reg_type: str = Field(default="", max_length=100)
    issuer: str = Field(default="", max_length=160)
    version: str = Field(default="", max_length=40)
    effective_date: date | None = None
    url: str = Field(default="", max_length=500, pattern=r"^(|https?://\S+)$")
    description: str = Field(default="", max_length=20000)
    owner_id: int | None = None
    active: bool = True


class RequirementIn(BaseModel):
    ref: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=3, max_length=255)
    text: str = Field(default="", max_length=20000)
    owner_id: int | None = None
    entity_id: int | None = None
    applicable: bool = True
    control_ids: list[int] | None = Field(default=None, max_length=200)
    policy_ids: list[int] | None = Field(default=None, max_length=200)


class AssessIn(BaseModel):
    status: str
    comment: str = Field(default="", max_length=10000)


def _req_out(db: DBSession, r: Requirement) -> dict:
    controls = links.linked(db, "requirement", r.id, "control")
    return {"id": r.id, "regulation_id": r.regulation_id, "ref": r.ref, "title": r.title, "text": r.text,
            "owner_id": r.owner_id, "owner": name_of(db, r.owner_id), "entity_id": r.entity_id,
            "entity": entity_name(db, r.entity_id), "status": r.status, "review_required": r.review_required,
            "last_assessed_at": r.last_assessed_at, "assessed_by": name_of(db, r.assessed_by),
            "assessment_comment": r.assessment_comment, "controls": controls,
            "policies": links.linked(db, "requirement", r.id, "policy"),
            "risks": links.linked(db, "requirement", r.id, "risk"),
            "covered": bool(controls) or r.status == "Not applicable"}


def _stats(reqs: list[dict]) -> dict:
    applicable = [r for r in reqs if r["status"] != "Not applicable"]
    covered = sum(1 for r in applicable if r["controls"])
    by_status = {s: sum(1 for r in reqs if r["status"] == s) for s in COMPLIANCE_STATUSES}
    return {"requirements": len(reqs), "applicable": len(applicable), "covered": covered,
            "gaps": len(applicable) - covered,
            "coverage_pct": round(100 * covered / len(applicable)) if applicable else None,
            "compliant_pct": round(100 * by_status["Compliant"] / len(applicable)) if applicable else None,
            "by_status": by_status, "review_required": sum(1 for r in reqs if r["review_required"])}


def _reg_out(db: DBSession, g: Regulation, with_reqs: bool = False) -> dict:
    reqs = [_req_out(db, r) for r in db.execute(select(Requirement).where(Requirement.regulation_id == g.id)
                                                .order_by(Requirement.ref)).scalars()]
    out = {"id": g.id, "ref": g.ref, "code": g.code, "title": g.title, "reg_type": g.reg_type, "issuer": g.issuer,
           "version": g.version, "effective_date": g.effective_date, "url": g.url, "description": g.description,
           "owner_id": g.owner_id, "owner": name_of(db, g.owner_id), "active": g.active, "stats": _stats(reqs)}
    if with_reqs:
        out["requirements"] = reqs
    return out


def _reg(db: DBSession, regulation_id: int) -> Regulation:
    g = db.get(Regulation, regulation_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Obligation not found")
    return g


def _req(db: DBSession, requirement_id: int) -> Requirement:
    r = db.get(Requirement, requirement_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return r


# ---------------------------------------------------------------- obligations

@router.get("/regulations")
def list_regulations(include_inactive: bool = False, db: DBSession = Depends(get_db), user: User = Viewer) -> dict:
    stmt = select(Regulation).order_by(Regulation.code)
    if not include_inactive:
        stmt = stmt.where(Regulation.active.is_(True))
    items = [_reg_out(db, g) for g in db.execute(stmt).scalars()]
    total = {"requirements": 0, "applicable": 0, "covered": 0, "compliant": 0, "review_required": 0}
    for i in items:
        s = i["stats"]
        total["requirements"] += s["requirements"]
        total["applicable"] += s["applicable"]
        total["covered"] += s["covered"]
        total["compliant"] += s["by_status"]["Compliant"]
        total["review_required"] += s["review_required"]
    return {"items": items, "types": cfg("regulation_types"), "statuses": list(COMPLIANCE_STATUSES),
            "totals": total, "can_edit": can(user, "grc.compliance")}


@router.post("/regulations", status_code=201)
def create_regulation(payload: RegulationIn, request: Request, db: DBSession = Depends(get_db),
                      user: User = Editor) -> dict:
    code = payload.code.strip().upper()
    if db.execute(select(Regulation.id).where(func.upper(Regulation.code) == code)).first():
        raise HTTPException(status_code=409, detail=f"An obligation with code {code} already exists")
    check_user(db, payload.owner_id)
    g = Regulation(ref=next_reference(db, "REG"), created_by=user.id, **payload.model_dump())
    g.code, g.reg_type = code, in_list(payload.reg_type, "regulation_types", "Kind")
    db.add(g)
    db.flush()
    log_action(db, user_id=user.id, action=f"REGULATION_CREATE {code}", request=request)
    db.commit()
    return _reg_out(db, g, with_reqs=True)


@router.get("/regulations/{regulation_id}")
def get_regulation(regulation_id: int, db: DBSession = Depends(get_db), user: User = Viewer) -> dict:
    return {**_reg_out(db, _reg(db, regulation_id), with_reqs=True), "can_edit": can(user, "grc.compliance")}


@router.put("/regulations/{regulation_id}")
def update_regulation(regulation_id: int, payload: RegulationIn, request: Request, db: DBSession = Depends(get_db),
                      user: User = Editor) -> dict:
    g = _reg(db, regulation_id)
    code = payload.code.strip().upper()
    clash = db.execute(select(Regulation.id).where(func.upper(Regulation.code) == code,
                                                    Regulation.id != g.id)).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"An obligation with code {code} already exists")
    check_user(db, payload.owner_id)
    new_version = payload.version.strip() != (g.version or "").strip() and bool(g.version)
    for k, v in payload.model_dump().items():
        setattr(g, k, v)
    g.code, g.reg_type = code, in_list(payload.reg_type, "regulation_types", "Kind")
    flagged = 0
    if new_version:
        for r in db.execute(select(Requirement).where(Requirement.regulation_id == g.id)).scalars():
            r.review_required = True
            flagged += 1
        from app.platform.notifications.service import notify_many

        owners = db.execute(select(Requirement.owner_id).where(Requirement.regulation_id == g.id)).scalars()
        notify_many(db, [g.owner_id, *owners], f"{g.code} changed to version {g.version}",
                    "Review the requirements you own: the mapping to controls and the compliance status need a "
                    "fresh look.", link_type="regulation", link_id=g.id)
    log_action(db, user_id=user.id, request=request,
               action=f"REGULATION_UPDATE {code}" + (f" new version, {flagged} requirement(s) flagged" if new_version
                                                     else ""))
    db.commit()
    return {**_reg_out(db, g, with_reqs=True), "flagged": flagged}


# ---------------------------------------------------------------- requirements

def _apply_req(db: DBSession, r: Requirement, p: RequirementIn, user: User) -> None:
    check_user(db, p.owner_id)
    check_entity(db, p.entity_id)
    r.ref, r.title, r.text = p.ref.strip(), p.title.strip(), p.text
    r.owner_id, r.entity_id = p.owner_id, p.entity_id
    if not p.applicable:
        r.status = "Not applicable"
    elif r.status == "Not applicable":
        r.status = "Not assessed"
    db.flush()
    if p.control_ids is not None:
        links.set_links(db, "requirement", r.id, "control", p.control_ids, user.id)
    if p.policy_ids is not None:
        links.set_links(db, "requirement", r.id, "policy", p.policy_ids, user.id)


@router.post("/regulations/{regulation_id}/requirements", status_code=201)
def create_requirement(regulation_id: int, payload: RequirementIn, request: Request,
                       db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    g = _reg(db, regulation_id)
    if db.execute(select(Requirement.id).where(Requirement.regulation_id == g.id,
                                               Requirement.ref == payload.ref.strip())).first():
        raise HTTPException(status_code=409, detail=f"{g.code} already has a requirement {payload.ref}")
    r = Requirement(regulation_id=g.id, ref=payload.ref.strip(), title=payload.title.strip())
    db.add(r)
    db.flush()
    _apply_req(db, r, payload, user)
    log_action(db, user_id=user.id, action=f"REQUIREMENT_CREATE {g.code} {r.ref}", request=request)
    db.commit()
    return _req_out(db, r)


@router.put("/requirements/{requirement_id}")
def update_requirement(requirement_id: int, payload: RequirementIn, request: Request,
                       db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    r = _req(db, requirement_id)
    clash = db.execute(select(Requirement.id).where(Requirement.regulation_id == r.regulation_id,
                                                    Requirement.ref == payload.ref.strip(),
                                                    Requirement.id != r.id)).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"Requirement {payload.ref} already exists")
    _apply_req(db, r, payload, user)
    log_action(db, user_id=user.id, action=f"REQUIREMENT_UPDATE {r.id}", request=request)
    db.commit()
    return _req_out(db, r)


@router.delete("/requirements/{requirement_id}")
def delete_requirement(requirement_id: int, request: Request, db: DBSession = Depends(get_db),
                       user: User = Editor) -> dict:
    r = _req(db, requirement_id)
    links.drop_links(db, "requirement", r.id)
    log_action(db, user_id=user.id, action=f"REQUIREMENT_DELETE {r.id} {r.ref}", request=request)
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.post("/requirements/{requirement_id}/assess")
def assess_requirement(requirement_id: int, payload: AssessIn, request: Request, db: DBSession = Depends(get_db),
                       user: User = Depends(require_active_user)) -> dict:
    r = _req(db, requirement_id)
    if not (can(user, "grc.compliance") or r.owner_id == user.id):
        raise HTTPException(status_code=403, detail="Only the requirement owner or the compliance team can assess it")
    if payload.status not in COMPLIANCE_STATUSES or payload.status == "Not assessed":
        raise HTTPException(status_code=422, detail="Choose Compliant, Partially compliant, Non-compliant or "
                                                    "Not applicable")
    if payload.status in ("Partially compliant", "Non-compliant") and not payload.comment.strip():
        raise HTTPException(status_code=422, detail="Explain the gap in the comment")
    r.status, r.assessment_comment = payload.status, payload.comment
    r.last_assessed_at, r.assessed_by, r.review_required = utcnow(), user.id, False
    log_action(db, user_id=user.id, action=f"REQUIREMENT_ASSESS {r.id} {r.status}", request=request)
    db.commit()
    return _req_out(db, r)


CSV_COLUMNS = ["ref", "title", "text", "owner_email", "applicable", "control_refs"]


@router.get("/requirements/template.csv")
def requirements_template(_: User = Viewer) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    w.writerow(["s.16(1)", "Internal audit unit in every covered entity", "Each covered entity shall have an "
                "internal audit unit...", "", "yes", "COSO2013 CA-10"])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="requirements-template.csv"'})


@router.post("/regulations/{regulation_id}/import")
async def import_requirements(regulation_id: int, request: Request, file: UploadFile = File(...),
                              db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    from app.domains.audit.frameworks.models import Framework, LibraryControl

    g = _reg(db, regulation_id)
    raw = await file.read(2_000_001)
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="The file is larger than 2 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="Save the file as CSV UTF-8") from None
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"ref", "title"} <= {f.strip().lower() for f in reader.fieldnames}:
        raise HTTPException(status_code=422, detail="The file needs at least the columns ref and title")
    controls = {f"{fw.code} {c.ref}".upper(): c.id for c, fw in
                db.execute(select(LibraryControl, Framework).join(Framework,
                                                                  Framework.id == LibraryControl.framework_id))}
    created = updated = 0
    errors: list[str] = []
    for n, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not row.get("ref") or len(row.get("title", "")) < 3:
            errors.append(f"Row {n}: ref and a title of at least 3 characters are required")
            continue
        owner_id = None
        if row.get("owner_email"):
            owner = db.execute(select(User).where(func.lower(User.email) == row["owner_email"].lower())).scalar()
            if owner is None:
                errors.append(f"Row {n}: no user with e-mail {row['owner_email']}")
                continue
            owner_id = owner.id
        ctl_ids = []
        for ref in filter(None, (x.strip() for x in row.get("control_refs", "").split(";"))):
            if ref.upper() not in controls:
                errors.append(f"Row {n}: unknown standard control '{ref}' (use FRAMEWORK REF, separated by ;)")
                break
            ctl_ids.append(controls[ref.upper()])
        else:
            existing = db.execute(select(Requirement).where(Requirement.regulation_id == g.id,
                                                            Requirement.ref == row["ref"][:40])).scalar_one_or_none()
            payload = RequirementIn(ref=row["ref"][:40], title=row["title"][:255], text=row.get("text", ""),
                                    owner_id=owner_id,
                                    applicable=row.get("applicable", "yes").lower() not in ("no", "n", "false", "0"),
                                    control_ids=ctl_ids or None)
            if existing:
                if owner_id is None:
                    payload.owner_id = existing.owner_id
                _apply_req(db, existing, payload, user)
                updated += 1
            else:
                r = Requirement(regulation_id=g.id, ref=payload.ref, title=payload.title)
                db.add(r)
                db.flush()
                _apply_req(db, r, payload, user)
                created += 1
    log_action(db, user_id=user.id, request=request,
               action=f"REQUIREMENTS_IMPORT {g.code} +{created} ~{updated} errors {len(errors)}")
    db.commit()
    return {"created": created, "updated": updated, "errors": errors[:50]}


# ---------------------------------------------------------------- the map

@router.get("/compliance/map")
def compliance_map(db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    """Common controls: each standard control with the obligations it helps meet, and every coverage gap."""
    from app.domains.audit.frameworks.models import Framework, LibraryControl
    from app.domains.grc.links import GrcLink

    rows = db.execute(select(GrcLink).where(
        ((GrcLink.a_type == "control") & (GrcLink.b_type == "requirement"))
        | ((GrcLink.a_type == "requirement") & (GrcLink.b_type == "control")))).scalars()
    by_control: dict[int, set[int]] = {}
    for link in rows:
        ctl, req = (link.a_id, link.b_id) if link.a_type == "control" else (link.b_id, link.a_id)
        by_control.setdefault(ctl, set()).add(req)
    controls = []
    for cid, req_ids in by_control.items():
        c = db.get(LibraryControl, cid)
        fw = db.get(Framework, c.framework_id) if c else None
        regs = {db.get(Requirement, rid).regulation_id for rid in req_ids if db.get(Requirement, rid)}
        controls.append({"id": cid, "ref": f"{fw.code if fw else ''} {c.ref if c else ''}".strip(),
                         "title": c.title if c else "?", "requirements": len(req_ids),
                         "obligations": sorted(db.get(Regulation, x).code for x in regs if db.get(Regulation, x))})
    controls.sort(key=lambda x: (-x["requirements"], x["ref"]))
    gaps = []
    for r in db.execute(select(Requirement).join(Regulation, Regulation.id == Requirement.regulation_id)
                        .where(Regulation.active.is_(True), Requirement.status != "Not applicable")
                        .order_by(Regulation.code, Requirement.ref)).scalars():
        if not links.linked(db, "requirement", r.id, "control"):
            g = db.get(Regulation, r.regulation_id)
            gaps.append({"id": r.id, "regulation_id": r.regulation_id, "regulation": g.code, "ref": r.ref,
                         "title": r.title, "owner": name_of(db, r.owner_id), "status": r.status})
    return {"common_controls": controls, "gaps": gaps}
