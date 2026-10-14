"""Excel import (audit universe, findings) and Excel export of any list.

Imports are two-step: upload with ``commit=false`` to validate and preview, then
upload again with ``commit=true``. Nothing is written if any row has an error.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.access import ensure_can_view
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier, require_perm
from app.core.enums import AuditStatus, RiskRating, Role
from app.core.history import log_record_history
from app.domains.audit.audits.models import Audit, Finding
from app.platform.users.models import User

router = APIRouter(tags=["import / export"])
Staff = Depends(require_module_tier("import", Role.Admin, Role.Auditor))
AdminOnly = Depends(require_module_tier("audit universe import", Role.Admin))
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

TEMPLATES: dict[str, list[tuple[str, bool, str]]] = {
    # column, required, help
    "universe": [
        ("Location code", True, "Short code of the port / site, e.g. TEMA"),
        ("Location name", True, "e.g. Tema Port"),
        ("Unit code", True, "Short code of the auditable unit, unique within its location, e.g. GJT"),
        ("Unit name", True, "e.g. Golden Jubilee Terminal"),
        ("Description", False, ""),
        ("Owner email", False, "Head of the unit"),
        ("Likelihood", True, "Inherent risk likelihood, 1 (rare) to 5 (almost certain)"),
        ("Impact", True, "Inherent risk impact, 1 (minor) to 5 (severe)"),
    ],
    "findings": [
        ("Title", True, "Short statement of the issue"),
        ("Risk rating", True, "High, Medium or Low"),
        ("Description", False, ""),
        ("Criteria", False, "What should be (policy, law, standard)"),
        ("Condition", False, "What was found"),
        ("Cause", False, "Why it happened"),
        ("Effect", False, "Risk or impact"),
        ("Recommendation", False, ""),
        ("Owner email", False, "Management owner of the finding"),
    ],
}


def _workbook(title: str, headers: list[str], rows: list[list], notes: list[str] | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\[\]\*\?/\\:]", "", title)[:31] or "Sheet1"
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A68")
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        ws.append([_cell(v) for v in row])
    for i, h in enumerate(headers, start=1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows[:200] if i - 1 < len(r) and r[i - 1]])
        ws.column_dimensions[get_column_letter(i)].width = min(max(12, width + 2), 60)
    ws.freeze_panes = "A2"
    if notes:
        help_ws = wb.create_sheet("Instructions")
        for line in notes:
            help_ws.append([line])
        help_ws.column_dimensions["A"].width = 100
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(v):  # noqa: ANN001, ANN202
    if isinstance(v, (int, float, datetime, date)) or v is None:
        return v
    text = str(v)
    # Guard against formula injection when the file is opened in Excel.
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _xlsx_response(content: bytes, filename: str) -> Response:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "export.xlsx"
    return Response(content=content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


# ------------------------------------------------------------------ export


class ExportIn(BaseModel):
    title: str = Field("Export", max_length=100)
    columns: list[str] = Field(..., min_length=1, max_length=60)
    rows: list[list[str | int | float | None]] = Field(default_factory=list, max_length=20000)


@router.post("/api/export.xlsx")
def export_xlsx(
    payload: ExportIn, request: Request, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)
) -> Response:
    """Turn the rows a user is looking at into a formatted Excel workbook."""
    content = _workbook(payload.title, payload.columns, payload.rows)
    log_action(
        db, user_id=user.id, action=f"EXPORT_XLSX {payload.title[:60]} rows={len(payload.rows)}", request=request
    )
    db.commit()
    return _xlsx_response(content, f"{payload.title}-{date.today().isoformat()}.xlsx")


# ------------------------------------------------------------------ import


@router.get("/api/import/{kind}/template.xlsx")
def template(kind: str, user: User = Staff) -> Response:
    if kind not in TEMPLATES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown import type")
    cols = TEMPLATES[kind]
    example = {
        "universe": [
            [
                "TEMA",
                "Tema Port",
                "GJT",
                "Golden Jubilee Terminal",
                "Container terminal operations",
                "head.gjt@gpha.gov.gh",
                4,
                5,
            ]
        ],
        "findings": [
            [
                "Vessel calls not reconciled to invoices",
                "High",
                "",
                "Billing policy s.4.2",
                "No monthly reconciliation in 2026",
                "No assigned reviewer",
                "Revenue leakage",
                "Assign and evidence a monthly reconciliation",
                "finance.manager@gpha.gov.gh",
            ]
        ],
    }[kind]
    notes = (
        [f"How to fill the {kind} import sheet", ""]
        + [f"{c} ({'required' if req else 'optional'}){': ' + h if h else ''}" for c, req, h in cols]
        + [
            "",
            "Keep the header row exactly as provided. One record per row. Delete the example row first.",
            f"Up to {MAX_ROWS} rows per file.",
        ]
    )
    return _xlsx_response(
        _workbook(kind.title(), [c for c, _, _ in cols], example, notes), f"gpha-{kind}-import-template.xlsx"
    )


class RowIssue(BaseModel):
    row: int
    field: str
    message: str


class ImportResult(BaseModel):
    kind: str
    committed: bool
    total_rows: int
    to_create: int
    to_update: int
    errors: list[RowIssue]
    preview: list[dict]


def _read_rows(data: bytes, kind: str) -> tuple[list[dict], list[RowIssue]]:
    from openpyxl import load_workbook

    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="The file is larger than 5 MB")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The file is not a valid Excel workbook (.xlsx)"
        ) from exc
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(it, [])]
    expected = [c for c, _, _ in TEMPLATES[kind]]
    missing = [c for c, req, _ in TEMPLATES[kind] if req and c not in header]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing column(s): {', '.join(missing)}. Download the template to see the layout.",
        )
    idx = {c: header.index(c) for c in expected if c in header}
    rows, issues = [], []
    for n, raw in enumerate(it, start=2):
        if raw is None or all(v is None or str(v).strip() == "" for v in raw):
            continue
        rec = {c: (raw[i] if i < len(raw) else None) for c, i in idx.items()}
        rec = {c: (v.strip() if isinstance(v, str) else v) for c, v in rec.items()}
        rec["_row"] = n
        rows.append(rec)
        if len(rows) > MAX_ROWS:
            issues.append(RowIssue(row=n, field="file", message=f"More than {MAX_ROWS} rows; split the file"))
            break
    if not rows:
        issues.append(RowIssue(row=1, field="file", message="The sheet has no data rows"))
    return rows, issues


def _required(rec: dict, cols: list[tuple[str, bool, str]], issues: list[RowIssue]) -> None:
    for c, req, _ in cols:
        if req and (rec.get(c) is None or str(rec.get(c)).strip() == ""):
            issues.append(RowIssue(row=rec["_row"], field=c, message="is required"))


def _rating(v) -> int | None:  # noqa: ANN001
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 5 and float(v) == n else None


@router.post("/api/import/universe", response_model=ImportResult)
async def import_universe(
    request: Request,
    file: UploadFile = File(...),
    commit: bool = Query(False),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_perm("method.library", "system.reference")),
) -> ImportResult:
    from app.domains.assurance.planning.models import EntityUnit, Location

    rows, issues = _read_rows(await file.read(), "universe")
    cols = TEMPLATES["universe"]
    locations = {loc.code.upper(): loc for loc in db.execute(select(Location)).scalars()}
    units = {(u.location_id, u.code.upper()): u for u in db.execute(select(EntityUnit)).scalars()}
    seen: set[tuple[str, str]] = set()
    plan: list[tuple[dict, EntityUnit | None]] = []
    for rec in rows:
        _required(rec, cols, issues)
        r = rec["_row"]
        lcode, ucode = str(rec.get("Location code") or "").upper(), str(rec.get("Unit code") or "").upper()
        for field, val, limit in (
            ("Location code", lcode, 20),
            ("Unit code", ucode, 20),
            ("Unit name", str(rec.get("Unit name") or ""), 255),
            ("Location name", str(rec.get("Location name") or ""), 255),
        ):
            if len(val) > limit:
                issues.append(RowIssue(row=r, field=field, message=f"must be {limit} characters or fewer"))
        if (lcode, ucode) in seen and lcode and ucode:
            issues.append(RowIssue(row=r, field="Unit code", message="appears twice in the file for this location"))
        seen.add((lcode, ucode))
        for f in ("Likelihood", "Impact"):
            if rec.get(f) not in (None, "") and _rating(rec.get(f)) is None:
                issues.append(RowIssue(row=r, field=f, message="must be a whole number from 1 to 5"))
        email = rec.get("Owner email")
        if email and not _EMAIL.match(str(email)):
            issues.append(RowIssue(row=r, field="Owner email", message="is not a valid e-mail address"))
        loc = locations.get(lcode)
        plan.append((rec, units.get((loc.id, ucode)) if loc else None))
    to_update = sum(1 for _, u in plan if u is not None)
    result = ImportResult(
        kind="universe",
        committed=False,
        total_rows=len(rows),
        to_create=len(plan) - to_update,
        to_update=to_update,
        errors=issues,
        preview=[
            {
                "row": rec["_row"],
                "location": rec.get("Location code"),
                "unit": rec.get("Unit code"),
                "name": rec.get("Unit name"),
                "risk": (_rating(rec.get("Likelihood")) or 0) * (_rating(rec.get("Impact")) or 0),
                "action": "update" if u else "create",
            }
            for rec, u in plan[:50]
        ],
    )
    if not commit or issues:
        return result
    for rec, unit in plan:
        lcode = str(rec["Location code"]).upper()
        loc = locations.get(lcode)
        if loc is None:
            loc = Location(code=lcode, name=str(rec["Location name"]), description="")
            db.add(loc)
            db.flush()
            locations[lcode] = loc
        if unit is None:
            unit = EntityUnit(location_id=loc.id, code=str(rec["Unit code"]).upper())
            db.add(unit)
        unit.name = str(rec["Unit name"])
        unit.description = str(rec.get("Description") or "")
        unit.owner_email = str(rec["Owner email"]) if rec.get("Owner email") else None
        unit.risk_likelihood = _rating(rec["Likelihood"])
        unit.risk_impact = _rating(rec["Impact"])
    log_action(
        db, user_id=user.id, action=f"IMPORT_UNIVERSE created={result.to_create} updated={to_update}", request=request
    )
    db.commit()
    result.committed = True
    return result


@router.post("/api/audits/{audit_id}/import/findings", response_model=ImportResult)
async def import_findings(
    audit_id: int,
    request: Request,
    file: UploadFile = File(...),
    commit: bool = Query(False),
    db: DBSession = Depends(get_db),
    user: User = Staff,
) -> ImportResult:
    audit = db.get(Audit, audit_id)
    ensure_can_view(db, user, "audit", audit)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed")
    rows, issues = _read_rows(await file.read(), "findings")
    cols = TEMPLATES["findings"]
    ratings = {r.value.lower(): r for r in RiskRating}
    for rec in rows:
        _required(rec, cols, issues)
        r = rec["_row"]
        if rec.get("Title") and len(str(rec["Title"])) > 255:
            issues.append(RowIssue(row=r, field="Title", message="must be 255 characters or fewer"))
        if rec.get("Risk rating") and str(rec["Risk rating"]).lower() not in ratings:
            issues.append(RowIssue(row=r, field="Risk rating", message="must be High, Medium or Low"))
        email = rec.get("Owner email")
        if email and not _EMAIL.match(str(email)):
            issues.append(RowIssue(row=r, field="Owner email", message="is not a valid e-mail address"))
    result = ImportResult(
        kind="findings",
        committed=False,
        total_rows=len(rows),
        to_create=len(rows),
        to_update=0,
        errors=issues,
        preview=[
            {"row": rec["_row"], "title": rec.get("Title"), "rating": rec.get("Risk rating"), "action": "create"}
            for rec in rows[:50]
        ],
    )
    if not commit or issues:
        return result
    for rec in rows:
        f = Finding(
            audit_id=audit_id,
            title=str(rec["Title"]),
            description=str(rec.get("Description") or ""),
            risk_rating=ratings[str(rec["Risk rating"]).lower()],
            assigned_owner_email=str(rec["Owner email"]) if rec.get("Owner email") else None,
            criteria=str(rec.get("Criteria") or ""),
            condition=str(rec.get("Condition") or ""),
            cause=str(rec.get("Cause") or ""),
            effect=str(rec.get("Effect") or ""),
            recommendation=str(rec.get("Recommendation") or ""),
            created_by=user.id,
        )
        db.add(f)
    db.flush()
    log_action(db, user_id=user.id, action=f"IMPORT_FINDINGS audit={audit_id} rows={len(rows)}", request=request)
    log_record_history(
        db,
        record_type="audit",
        record_id=audit_id,
        user_id=user.id,
        action=f"IMPORTED {len(rows)} FINDING(S) FROM EXCEL",
        request=request,
    )
    db.commit()
    result.committed = True
    return result
