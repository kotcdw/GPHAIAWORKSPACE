"""Bulk import, part 2: users (created as awaiting approval), remediation actions (including external
recommendations) and enterprise risks; the import catalogue and the import history.

Every import is two-step (preview, then import) and all-or-nothing: rows are created with the same code as the
screens (same checks, notifications and history), inside one database transaction that is committed only when
every row succeeded.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable
from contextlib import contextmanager
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.deps import ensure_perm, require_active_user
from app.core.permissions import has_perm
from app.platform.dataio.router import (
    _EMAIL,
    TEMPLATES,
    ImportResult,
    RowIssue,
    _rating,
    _read_rows,
    _required,
    record_run,
)
from app.platform.users.models import User

router = APIRouter(tags=["import / export"])
_USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,64}$")

# kind -> label, permissions (any one), where it lands. Findings are imported inside an audit.
CATALOGUE = {
    "users": ("User accounts", ("system.users",), "Created as awaiting approval; approve them under Users & access"),
    "orgunits": ("Org units", ("system.reference", "method.library"), "Org Structure (created or updated by name)"),
    "processes": ("Processes", ("method.library", "system.reference"), "Process library"),
    "remediation": ("Remediation actions", ("followup.manage",), "Including external recommendations"),
    "risks": ("Enterprise risks", ("grc.risk",), "Risk register"),
}


@contextmanager
def _one_transaction(db: DBSession):  # noqa: ANN202
    """Run several 'create' calls that each commit, as one transaction: their commits become flushes, and the
    caller commits once at the end (or everything is rolled back)."""
    real_commit, real_refresh = db.commit, db.refresh
    db.commit = db.flush  # type: ignore[method-assign]
    db.refresh = lambda *a, **k: None  # type: ignore[method-assign]
    try:
        yield
    except Exception:
        db.commit, db.refresh = real_commit, real_refresh  # type: ignore[method-assign]
        db.rollback()
        raise
    db.commit, db.refresh = real_commit, real_refresh  # type: ignore[method-assign]


def _text(v) -> str:  # noqa: ANN001
    return "" if v is None else str(v).strip()


def _date(v) -> date | None:  # noqa: ANN001
    if v is None or _text(v) == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(_text(v)[:10])
    except ValueError:
        return None


def _units(db: DBSession) -> dict[str, object]:
    from app.platform.organizations.models import Organization

    out: dict[str, object] = {}
    for o in db.execute(select(Organization).where(Organization.is_active.is_(True))).scalars():
        out[o.name.strip().lower()] = o
        out[o.org_ref.upper()] = o
    return out


def _unit_of(units: dict, value: str):  # noqa: ANN202
    return units.get(value.lower()) or units.get(value.upper()) if value else None


def _pydantic_issues(row: int, exc: ValidationError, names: dict[str, str]) -> list[RowIssue]:
    out = []
    for e in exc.errors():
        loc = e.get("loc") or ("",)
        field = names.get(str(loc[0]), str(loc[0]) or "row")
        message = str(e.get("msg", "is not valid")).removeprefix("Value error, ")
        out.append(RowIssue(row=row, field=field, message=message))
    return out


def _run(db: DBSession, request: Request, user: User, kind: str, file: UploadFile, commit: bool,
         rows: list[dict], issues: list[RowIssue], plan: list, preview: list[dict],
         create: Callable[[object], None], updates: int = 0) -> ImportResult:
    result = ImportResult(kind=kind, committed=False, total_rows=len(rows), to_create=len(plan) - updates,
                          to_update=updates, errors=issues, preview=preview[:50])
    if not commit or issues:
        return record_run(db, user, kind, file.filename, result)
    try:
        with _one_transaction(db):
            for item in plan:
                create(item)
    except HTTPException as exc:  # a rule only the create step checks
        result.errors = [RowIssue(row=0, field="file", message=str(exc.detail))]
        return record_run(db, user, kind, file.filename, result)
    from app.core.audit import log_action

    log_action(db, user_id=user.id, request=request,
               action=f"IMPORT_{kind.upper()} rows={len(plan)}" + (f" updated={updates}" if updates else ""))
    db.commit()
    result.committed = True
    return record_run(db, user, kind, file.filename, result)


# ---------------------------------------------------------------- users (awaiting approval)

@router.post("/api/import/users", response_model=ImportResult)
async def import_users(request: Request, file: UploadFile = File(...), commit: bool = Query(False),
                       db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> ImportResult:
    """Create accounts as awaiting approval (they cannot sign in until approved under Users & access)."""
    from app.core import permissions as perms
    from app.core.security import hash_password
    from app.platform.roles import service as role_service

    ensure_perm(user, "system.users")
    rows, issues = _read_rows(await file.read(), "users", db=db, user=user, filename=file.filename)
    names = {r.name.lower(): r.code for r in perms.JOB_ROLES} | {r.code: r.code for r in perms.JOB_ROLES}
    levels = {"unit head": "Unit Head", "audit manager": "Manager", "manager": "Manager", "pia": "PIA",
              "gm audit (cae)": "CAE", "gm audit": "CAE", "cae": "CAE"}
    taken_u = {u.lower() for u in db.execute(select(User.username)).scalars()}
    taken_e = {(e or "").lower() for e in db.execute(select(User.email)).scalars()}
    units = _units(db)
    seen_u: set[str] = set()
    seen_e: set[str] = set()
    plan, preview = [], []
    for rec in rows:
        _required(rec, TEMPLATES["users"], issues)
        r = rec["_row"]
        uname, email, role_txt = _text(rec.get("Username")), _text(rec.get("Email")).lower(), _text(rec.get("Role"))
        if uname and not _USERNAME.match(uname):
            issues.append(RowIssue(row=r, field="Username", message="3-64 letters, digits, '.', '_' or '-'"))
        elif uname.lower() in taken_u or uname.lower() in seen_u:
            issues.append(RowIssue(row=r, field="Username", message="is already taken"))
        if email and not _EMAIL.match(email):
            issues.append(RowIssue(row=r, field="Email", message="is not a valid e-mail address"))
        elif email and (email in taken_e or email in seen_e):
            issues.append(RowIssue(row=r, field="Email", message="already belongs to an account"))
        code = names.get(role_txt.lower()) if role_txt else None
        if role_txt and code is None:
            issues.append(RowIssue(row=r, field="Role", message="Administrator, Manager, Auditor, Read-only User or "
                                                                "Audit Client"))
        elif code in role_service.ADMIN_ROLES and not perms.is_super_admin(user):
            issues.append(RowIssue(row=r, field="Role", message="only a Super Administrator can create administrators"))
        level_txt = _text(rec.get("Approval level"))
        level = levels.get(level_txt.lower()) if level_txt else None
        if level_txt and (level is None or code != "manager"):
            issues.append(RowIssue(row=r, field="Approval level",
                                   message="Managers only: Unit Head, Audit Manager, PIA or GM Audit (CAE)"))
        place_txt = _text(rec.get("Workplace"))
        place = _unit_of(units, place_txt)
        if place_txt and place is None:
            issues.append(RowIssue(row=r, field="Workplace", message="is not an active unit of the Org Structure"))
        seen_u.add(uname.lower())
        seen_e.add(email)
        plan.append((rec, code, level, place))
        preview.append({"row": r, "name": _text(rec.get("Full name")), "username": uname, "email": email,
                        "role": role_txt, "workplace": place_txt})

    def create(item) -> None:  # noqa: ANN001
        rec, code, level, place = item
        u = User(username=_text(rec["Username"]), email=_text(rec["Email"]).lower(),
                 full_name=_text(rec["Full name"]), password_hash=hash_password(secrets.token_urlsafe(24)),
                 is_active=False, work_entity_id=place.id if place else None)
        role_service.apply_role(u, code, level)
        db.add(u)
        db.flush()
        from app.core.audit import log_action

        log_action(db, user_id=user.id, request=request,
                   action=f"USER_CREATE username={u.username} role={u.role.value} [import, awaiting approval]")

    return _run(db, request, user, "users", file, commit, rows, issues, plan, preview, create)


# ---------------------------------------------------------------- remediation actions / external recommendations

@router.post("/api/import/remediation", response_model=ImportResult)
async def import_remediation(request: Request, file: UploadFile = File(...), commit: bool = Query(False),
                             db: DBSession = Depends(get_db),
                             user: User = Depends(require_active_user)) -> ImportResult:
    from app.core.appconfig import cfg
    from app.domains.issues.capa.router import create_capa
    from app.domains.issues.capa.schemas import CapaCreate

    ensure_perm(user, "followup.manage")
    rows, issues = _read_rows(await file.read(), "remediation", db=db, user=user, filename=file.filename)
    sources = {s.lower(): s for s in (cfg("recommendation_sources") or [])}
    frames = {t.lower(): t for t in (cfg("action_timeframes") or [])}
    sev = {"high": "High", "medium": "Medium", "low": "Low"}
    names = {"title": "Title", "severity": "Severity", "owner_email": "Owner email", "source_year": "Source year",
             "source_reference": "Source reference", "description": "Description",
             "corrective_action": "Recommended action"}
    plan, preview = [], []
    for rec in rows:
        _required(rec, TEMPLATES["remediation"], issues)
        r = rec["_row"]
        src = sources.get(_text(rec.get("Source")).lower())
        if _text(rec.get("Source")) and src is None:
            issues.append(RowIssue(row=r, field="Source", message=f"must be one of: {', '.join(sources.values())}"))
        frame_txt = _text(rec.get("Timeframe"))
        if frame_txt and frame_txt.lower() not in frames:
            issues.append(RowIssue(row=r, field="Timeframe", message=f"must be one of: {', '.join(frames.values())}"))
        due_raw = rec.get("Due date")
        due = _date(due_raw)
        if _text(due_raw) and due is None:
            issues.append(RowIssue(row=r, field="Due date", message="is not a date (use a date cell or YYYY-MM-DD)"))
        year = None
        if _text(rec.get("Source year")):
            try:
                year = int(float(_text(rec.get("Source year"))))
            except ValueError:
                issues.append(RowIssue(row=r, field="Source year", message="must be a year such as 2025"))
        severity = sev.get(_text(rec.get("Severity")).lower())
        if _text(rec.get("Severity")) and severity is None:
            issues.append(RowIssue(row=r, field="Severity", message="must be High, Medium or Low"))
        payload = None
        try:
            payload = CapaCreate(title=_text(rec.get("Title")) or "x", severity=severity or "Medium",
                                 owner_email=_text(rec.get("Owner email")) or None, source_body=src,
                                 source_reference=_text(rec.get("Source reference")) or None, source_year=year,
                                 timeframe=frames.get(frame_txt.lower()) if frame_txt else None,
                                 description=_text(rec.get("Description")),
                                 corrective_action=_text(rec.get("Recommended action")))
        except ValidationError as exc:
            issues.extend(_pydantic_issues(r, exc, names))
        plan.append((payload, due))
        preview.append({"row": r, "title": _text(rec.get("Title")), "source": src or _text(rec.get("Source")),
                        "severity": severity, "owner": _text(rec.get("Owner email")),
                        "due": due.isoformat() if due else ""})

    def create(item) -> None:  # noqa: ANN001
        payload, due = item
        capa = create_capa(payload, request, db, user)
        if due is not None:  # imported recommendations keep their real (possibly past) target date
            capa.due_date = capa.original_due_date = datetime.combine(due, datetime.min.time())

    return _run(db, request, user, "remediation", file, commit, rows, issues, plan, preview, create)


# ---------------------------------------------------------------- enterprise risks

@router.post("/api/import/risks", response_model=ImportResult)
async def import_risks(request: Request, file: UploadFile = File(...), commit: bool = Query(False),
                       db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> ImportResult:
    from app.core.appconfig import cfg
    from app.domains.grc.risk.router import RiskIn, create_risk

    ensure_perm(user, "grc.risk")
    rows, issues = _read_rows(await file.read(), "risks", db=db, user=user, filename=file.filename)
    lists = {"Category": "erm_risk_categories", "Appetite": "erm_appetite_levels", "Treatment": "erm_treatments"}
    allowed = {col: {v.lower(): v for v in (cfg(key) or [])} for col, key in lists.items()}
    owners = {(u.email or "").lower(): u for u in db.execute(select(User).where(User.is_active.is_(True))).scalars()}
    units = _units(db)
    names = {"title": "Title", "inherent_likelihood": "Inherent likelihood", "inherent_impact": "Inherent impact",
             "residual_likelihood": "Residual likelihood", "residual_impact": "Residual impact"}
    plan, preview = [], []
    for rec in rows:
        _required(rec, TEMPLATES["risks"], issues)
        r = rec["_row"]
        values = {}
        for col in lists:
            txt = _text(rec.get(col))
            if txt and txt.lower() not in allowed[col]:
                issues.append(RowIssue(row=r, field=col, message=f"must be one of: {', '.join(allowed[col].values())}"))
            values[col] = allowed[col].get(txt.lower(), "") if txt else ""
        scores = {}
        for col in ("Inherent likelihood", "Inherent impact", "Residual likelihood", "Residual impact"):
            txt = _text(rec.get(col))
            scores[col] = _rating(rec.get(col)) if txt else None
            if txt and scores[col] is None:
                issues.append(RowIssue(row=r, field=col, message="must be a whole number from 1 to 5"))
        owner_txt = _text(rec.get("Owner email")).lower()
        owner = owners.get(owner_txt) if owner_txt else None
        if owner_txt and owner is None:
            issues.append(RowIssue(row=r, field="Owner email", message="is not an active account"))
        unit_txt = _text(rec.get("Org unit"))
        unit = _unit_of(units, unit_txt)
        if unit_txt and unit is None:
            issues.append(RowIssue(row=r, field="Org unit", message="is not an active unit of the Org Structure"))
        payload = None
        il, ii = scores["Inherent likelihood"] or 3, scores["Inherent impact"] or 3
        try:
            payload = RiskIn(title=_text(rec.get("Title")) or "xxx", category=values["Category"],
                             description=_text(rec.get("Description")), cause=_text(rec.get("Cause")),
                             consequence=_text(rec.get("Consequence")), owner_id=owner.id if owner else None,
                             entity_id=unit.id if unit else None, inherent_likelihood=il, inherent_impact=ii,
                             residual_likelihood=scores["Residual likelihood"] or il,
                             residual_impact=scores["Residual impact"] or ii, appetite=values["Appetite"],
                             treatment=values["Treatment"], treatment_plan=_text(rec.get("Treatment plan")))
        except ValidationError as exc:
            issues.extend(_pydantic_issues(r, exc, names))
        plan.append(payload)
        preview.append({"row": r, "title": _text(rec.get("Title")), "category": values["Category"],
                        "inherent": f"{il} x {ii}", "owner": owner_txt, "unit": unit_txt})

    def create(payload) -> None:  # noqa: ANN001
        create_risk(payload, request, db, user)

    return _run(db, request, user, "risks", file, commit, rows, issues, plan, preview, create)


# ---------------------------------------------------------------- catalogue and history

@router.get("/api/import/catalogue")
def import_catalogue(user: User = Depends(require_active_user)) -> list[dict]:
    """The imports this user may run, with their columns."""
    return [{"kind": kind, "label": label, "where": where,
             "columns": [{"name": c, "required": req, "help": h} for c, req, h in TEMPLATES[kind]]}
            for kind, (label, need, where) in CATALOGUE.items() if has_perm(user, *need)]


def _runs_visible(user: User):  # noqa: ANN202
    from app.platform.dataio.models import ImportRun

    stmt = select(ImportRun)
    if not has_perm(user, "system.technical"):
        stmt = stmt.where(ImportRun.user_id == user.id)  # everyone sees their own; administrators see all
    return stmt


@router.get("/api/import/history")
def import_history(limit: int = Query(default=100, ge=1, le=500), outcome: str | None = Query(default=None),
                   db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    from app.platform.dataio.models import ImportRun

    stmt = _runs_visible(user)
    if outcome in ("imported", "rejected"):
        stmt = stmt.where(ImportRun.outcome == outcome)
    rows = db.execute(stmt.order_by(ImportRun.at.desc(), ImportRun.id.desc()).limit(limit)).scalars().all()
    labels = {k: v[0] for k, v in CATALOGUE.items()} | {"findings": "Findings"}
    total = db.execute(select(func.count()).select_from(_runs_visible(user).subquery())).scalar_one()
    return {"total": total, "items": [
        {"id": r.id, "kind": r.kind, "label": labels.get(r.kind, r.kind), "filename": r.filename,
         "outcome": r.outcome, "rows": r.total_rows, "created": r.created, "updated": r.updated,
         "problems": r.error_count, "context": r.context, "by": r.user_name, "at": r.at.isoformat()} for r in rows]}


@router.get("/api/import/history/{run_id}")
def import_run(run_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    from app.platform.dataio.models import ImportRun

    run = db.execute(_runs_visible(user).where(ImportRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return {"id": run.id, "kind": run.kind, "filename": run.filename, "outcome": run.outcome, "rows": run.total_rows,
            "created": run.created, "updated": run.updated, "by": run.user_name, "at": run.at.isoformat(),
            "problems": json.loads(run.errors or "[]"), "problem_count": run.error_count}
