"""Frameworks & controls library: set up by the Audit Administrator, used by auditors when they build an
engagement's risk and control matrix (IIA GIAS 13.3-13.4: criteria and controls for the engagement)."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_perm, staff_or_perm
from app.core.enums import ControlFrequency, ControlNature, ControlType, TestType
from app.core.refs import next_reference
from app.domains.audit.frameworks.models import Framework, LibraryControl
from app.platform.users.models import User

router = APIRouter(tags=["frameworks & controls"])
Viewer = Depends(staff_or_perm("method.library"))
Editor = Depends(require_perm("method.library"))


class FrameworkIn(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9._-]+$")
    name: str = Field(min_length=3, max_length=200)
    framework_type: str = Field(default="", max_length=100)
    issuer: str = Field(default="", max_length=160)
    version: str = Field(default="", max_length=40)
    description: str = Field(default="", max_length=10000)
    active: bool = True


class ControlIn(BaseModel):
    framework_id: int
    ref: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(default="", max_length=20000)
    process_area: str = Field(default="", max_length=100)
    risk_statement: str = Field(default="", max_length=10000)
    control_type: ControlType = ControlType.Preventive
    nature: ControlNature = ControlNature.Manual
    frequency: ControlFrequency = ControlFrequency.Monthly
    is_key: bool = True
    test_procedure: str = Field(default="", max_length=20000)
    criterion_id: int | None = None
    active: bool = True


class ApplyIn(BaseModel):
    library_control_ids: list[int] = Field(min_length=1, max_length=50)
    risk_ids: list[int] = Field(default_factory=list, max_length=50)
    create_tests: bool = True
    test_type: TestType = TestType.Design


def _fw_out(db: DBSession, f: Framework) -> dict:
    count = db.execute(select(func.count()).select_from(LibraryControl).where(
        LibraryControl.framework_id == f.id, LibraryControl.active.is_(True))).scalar_one()
    return {"id": f.id, "code": f.code, "name": f.name, "framework_type": f.framework_type, "issuer": f.issuer,
            "version": f.version, "description": f.description, "active": f.active, "controls": count,
            "updated_at": f.updated_at}


def _ctl_out(c: LibraryControl, fw: Framework | None = None, used: int = 0) -> dict:
    return {"id": c.id, "framework_id": c.framework_id, "framework_code": fw.code if fw else None,
            "framework_name": fw.name if fw else None, "ref": c.ref, "title": c.title, "description": c.description,
            "process_area": c.process_area, "risk_statement": c.risk_statement, "control_type": c.control_type.value,
            "nature": c.nature.value, "frequency": c.frequency.value, "is_key": c.is_key,
            "test_procedure": c.test_procedure, "criterion_id": c.criterion_id, "active": c.active, "used_in": used}


def _framework(db: DBSession, framework_id: int) -> Framework:
    f = db.get(Framework, framework_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Framework not found")
    return f


def _check_criterion(db: DBSession, criterion_id: int | None) -> None:
    if criterion_id is None:
        return
    from app.domains.audit.methodology.models import Criterion

    if db.get(Criterion, criterion_id) is None:
        raise HTTPException(status_code=422, detail="Unknown criterion")


# ---------------------------------------------------------------- frameworks

@router.get("/api/library/frameworks")
def list_frameworks(include_inactive: bool = False, db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    q = select(Framework).order_by(Framework.code)
    if not include_inactive:
        q = q.where(Framework.active.is_(True))
    return {"types": cfg("framework_types"), "items": [_fw_out(db, f) for f in db.execute(q).scalars()]}


@router.post("/api/library/frameworks", status_code=201)
def create_framework(payload: FrameworkIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Editor) -> dict:
    code = payload.code.strip().upper()
    if db.execute(select(Framework.id).where(func.upper(Framework.code) == code)).first():
        raise HTTPException(status_code=409, detail=f"A framework with code {code} already exists")
    f = Framework(code=code, name=payload.name.strip(), framework_type=payload.framework_type.strip(),
                  issuer=payload.issuer.strip(), version=payload.version.strip(), description=payload.description,
                  active=payload.active, created_by=user.id)
    db.add(f)
    db.flush()
    log_action(db, user_id=user.id, action=f"FRAMEWORK_CREATE {code}", request=request)
    db.commit()
    return _fw_out(db, f)


@router.put("/api/library/frameworks/{framework_id}")
def update_framework(framework_id: int, payload: FrameworkIn, request: Request, db: DBSession = Depends(get_db),
                     user: User = Editor) -> dict:
    f = _framework(db, framework_id)
    code = payload.code.strip().upper()
    if code != f.code and db.execute(select(Framework.id).where(func.upper(Framework.code) == code)).first():
        raise HTTPException(status_code=409, detail=f"A framework with code {code} already exists")
    f.code, f.name, f.framework_type = code, payload.name.strip(), payload.framework_type.strip()
    f.issuer, f.version, f.description, f.active = payload.issuer.strip(), payload.version.strip(), \
        payload.description, payload.active
    log_action(db, user_id=user.id, action=f"FRAMEWORK_UPDATE {code} active={f.active}", request=request)
    db.commit()
    return _fw_out(db, f)


# ---------------------------------------------------------------- library controls

@router.get("/api/library/controls")
def list_controls(framework_id: int | None = None, process_area: str | None = None, q: str | None = None,
                  include_inactive: bool = False, db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    from app.domains.audit.rcm.models import Control

    stmt = select(LibraryControl, Framework).join(Framework, Framework.id == LibraryControl.framework_id)
    if not include_inactive:
        stmt = stmt.where(LibraryControl.active.is_(True), Framework.active.is_(True))
    if framework_id:
        stmt = stmt.where(LibraryControl.framework_id == framework_id)
    if process_area:
        stmt = stmt.where(LibraryControl.process_area == process_area)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(LibraryControl.title).like(like), func.lower(LibraryControl.ref).like(like),
                              func.lower(LibraryControl.description).like(like),
                              func.lower(LibraryControl.risk_statement).like(like)))
    rows = db.execute(stmt.order_by(Framework.code, LibraryControl.ref).limit(1000)).all()
    usage = dict(db.execute(select(Control.library_control_id, func.count()).where(
        Control.library_control_id.is_not(None)).group_by(Control.library_control_id)).all())
    areas = sorted({a for (a,) in db.execute(select(LibraryControl.process_area).distinct()) if a})
    return {"process_areas": areas, "control_types": [x.value for x in ControlType],
            "natures": [x.value for x in ControlNature], "frequencies": [x.value for x in ControlFrequency],
            "items": [_ctl_out(c, f, usage.get(c.id, 0)) for c, f in rows]}


def _apply(c: LibraryControl, payload: ControlIn) -> None:
    c.framework_id, c.ref, c.title = payload.framework_id, payload.ref.strip(), payload.title.strip()
    c.description, c.process_area, c.risk_statement = payload.description, payload.process_area.strip(), \
        payload.risk_statement
    c.control_type, c.nature, c.frequency, c.is_key = payload.control_type, payload.nature, payload.frequency, \
        payload.is_key
    c.test_procedure, c.criterion_id, c.active = payload.test_procedure, payload.criterion_id, payload.active


def _ref_taken(db: DBSession, framework_id: int, ref: str, exclude: int | None = None) -> bool:
    q = select(LibraryControl.id).where(LibraryControl.framework_id == framework_id,
                                        func.lower(LibraryControl.ref) == ref.strip().lower())
    if exclude:
        q = q.where(LibraryControl.id != exclude)
    return db.execute(q).first() is not None


@router.post("/api/library/controls", status_code=201)
def create_control(payload: ControlIn, request: Request, db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    fw = _framework(db, payload.framework_id)
    _check_criterion(db, payload.criterion_id)
    if _ref_taken(db, fw.id, payload.ref):
        raise HTTPException(status_code=409, detail=f"{payload.ref} already exists in {fw.code}")
    c = LibraryControl(created_by=user.id)
    _apply(c, payload)
    db.add(c)
    db.flush()
    log_action(db, user_id=user.id, action=f"LIBRARY_CONTROL_CREATE {fw.code}/{c.ref}", request=request)
    db.commit()
    return _ctl_out(c, fw)


@router.put("/api/library/controls/{control_id}")
def update_control(control_id: int, payload: ControlIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Editor) -> dict:
    c = db.get(LibraryControl, control_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Control not found")
    fw = _framework(db, payload.framework_id)
    _check_criterion(db, payload.criterion_id)
    if _ref_taken(db, fw.id, payload.ref, exclude=c.id):
        raise HTTPException(status_code=409, detail=f"{payload.ref} already exists in {fw.code}")
    _apply(c, payload)
    log_action(db, user_id=user.id, action=f"LIBRARY_CONTROL_UPDATE {fw.code}/{c.ref} active={c.active}",
               request=request)
    db.commit()
    return _ctl_out(c, fw)




@router.get("/api/library/controls/template.csv")
def csv_template(_: User = Viewer):  # noqa: ANN201
    from fastapi.responses import Response

    sample = ("ref,title,description,process_area,risk_statement,control_type,nature,frequency,is_key,test_procedure\n"
              "PR-01,Purchase orders are approved before goods are ordered,The approver checks budget and need,"
              "Procurement,Unauthorised purchases,Preventive,Manual,Daily,yes,"
              "Select a sample of purchase orders and inspect evidence of approval before the order date\n")
    return Response(content=sample, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=library-controls-template.csv"})


@router.post("/api/library/frameworks/{framework_id}/import")
async def import_controls(framework_id: int, request: Request, file: UploadFile = File(...),
                          db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    """Load or update controls from a CSV (columns as in template.csv). Existing refs are updated."""
    fw = _framework(db, framework_id)
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="The file is larger than 2 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in ("ref", "title") if c not in (reader.fieldnames or [])]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing column(s): {', '.join(missing)}")
    created = updated = 0
    errors: list[str] = []

    def enum_of(cls, value, default):  # noqa: ANN001, ANN202
        value = (value or "").strip()
        for member in cls:
            if member.value.lower() == value.lower():
                return member
        if value:
            raise ValueError(f"'{value}' is not one of: {', '.join(m.value for m in cls)}")
        return default

    for n, row in enumerate(reader, start=2):
        ref, title = (row.get("ref") or "").strip(), (row.get("title") or "").strip()
        if not ref or len(title) < 3:
            errors.append(f"Row {n}: ref and title are required")
            continue
        try:
            data = ControlIn(framework_id=fw.id, ref=ref[:40], title=title[:255],
                             description=row.get("description") or "",
                             process_area=(row.get("process_area") or "")[:100],
                             risk_statement=row.get("risk_statement") or "",
                             control_type=enum_of(ControlType, row.get("control_type"), ControlType.Preventive),
                             nature=enum_of(ControlNature, row.get("nature"), ControlNature.Manual),
                             frequency=enum_of(ControlFrequency, row.get("frequency"), ControlFrequency.Monthly),
                             is_key=(row.get("is_key") or "yes").strip().lower() in ("yes", "y", "true", "1"),
                             test_procedure=row.get("test_procedure") or "")
        except ValueError as exc:
            errors.append(f"Row {n}: {exc}")
            continue
        existing = db.execute(select(LibraryControl).where(
            LibraryControl.framework_id == fw.id, func.lower(LibraryControl.ref) == ref.lower())).scalars().first()
        if existing is None:
            c = LibraryControl(created_by=user.id)
            _apply(c, data)
            db.add(c)
            created += 1
        else:
            _apply(existing, data)
            updated += 1
        if n > 2001:
            errors.append("Stopped after 2000 rows")
            break
    log_action(db, user_id=user.id, request=request,
               action=f"LIBRARY_IMPORT {fw.code} created={created} updated={updated} errors={len(errors)}")
    db.commit()
    return {"created": created, "updated": updated, "errors": errors[:50]}


# ---------------------------------------------------------------- use in an engagement

@router.post("/api/objectives/{objective_id}/controls/from-library", status_code=201)
def apply_to_objective(objective_id: int, payload: ApplyIn, request: Request, db: DBSession = Depends(get_db),
                       user: User = Depends(staff_or_perm("audit.fieldwork"))) -> dict:
    """Copy standard controls into the engagement's matrix (linked back to the library), mapped to the chosen
    risks, each with a test pre-filled from the suggested procedure."""
    from app.core.history import log_record_history
    from app.domains.audit.rcm import router as rcm
    from app.domains.audit.rcm.models import Control, ControlTest

    obj = rcm._objective(db, objective_id)
    rcm._ensure_open(rcm._audit_of(db, obj))
    added = []
    for lib_id in dict.fromkeys(payload.library_control_ids):
        lib = db.get(LibraryControl, lib_id)
        if lib is None or not lib.active:
            raise HTTPException(status_code=422, detail=f"Library control {lib_id} is not available")
        fw = db.get(Framework, lib.framework_id)
        description = lib.description
        if lib.risk_statement:
            description = f"{description}\n\nRisk addressed: {lib.risk_statement}".strip()
        control = Control(objective_id=obj.id, ref=next_reference(db, "CTL"), title=lib.title[:255],
                          description=f"{description}\n\nSource: {fw.code} {lib.ref}".strip(),
                          control_type=lib.control_type, nature=lib.nature, frequency=lib.frequency,
                          is_key=lib.is_key, library_control_id=lib.id, created_by=user.id)
        db.add(control)
        db.flush()
        rcm._set_mapping(db, control, payload.risk_ids)
        if payload.create_tests and lib.test_procedure.strip():
            db.add(ControlTest(control_id=control.id, ref=next_reference(db, "TST"), test_type=payload.test_type,
                               procedure=lib.test_procedure, created_by=user.id))
        added.append(f"{control.ref} ({fw.code} {lib.ref})")
    log_action(db, user_id=user.id, action=f"LIBRARY_APPLY objective={obj.id} {len(added)} control(s)",
               request=request)
    log_record_history(db, record_type="audit", record_id=obj.audit_id, user_id=user.id,
                       action=f"CONTROLS FROM LIBRARY: {', '.join(added)}", request=request)
    db.commit()
    return {"added": added}
