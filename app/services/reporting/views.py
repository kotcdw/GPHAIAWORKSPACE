"""Report Views: the data sources reports, dashboards, presentations and AI Reporting are built from.

Every View returns only rows the requesting user may see (port/team audit scope; Risk Manager data needs a
risk & compliance permission). A shared report is always run with the *viewer's* access, never the author's.
Each row carries ``_audit_id`` (or ``None``) so stored facts can later be checked against a reader's access.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import utcnow
from app.platform.users.models import User

MAX_ROWS = 5000
OPS = ("eq", "ne", "contains", "gte", "lte", "in", "empty", "not_empty")


@dataclass(frozen=True)
class Col:
    key: str
    label: str
    type: str = "text"  # text | number | date


@dataclass(frozen=True)
class View:
    key: str
    label: str
    columns: tuple[Col, ...]
    rows: Callable[[DBSession, User], list[dict]]
    date_column: str | None = None
    perms: tuple[str, ...] = field(default_factory=tuple)  # any of these, beyond being audit staff


def _scope(db: DBSession, user: User) -> set[int] | None:
    from app.core.access import staff_audit_scope

    return staff_audit_scope(db, user)


def _ref(audit_id: int | None) -> str | None:
    return f"AUD-{audit_id:04d}" if audit_id else None


def _d(v):  # noqa: ANN001, ANN202
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _issues(db: DBSession, user: User) -> list[dict]:
    from app.domains.audit.audits.models import Audit, Finding

    scope = _scope(db, user)
    audits = {a.id: a for a in db.execute(select(Audit)).scalars() if scope is None or a.id in scope}
    out = []
    for f in db.execute(select(Finding).where(Finding.audit_id.in_(list(audits) or [0]))).scalars():
        a = audits[f.audit_id]
        out.append({"_audit_id": a.id, "issue": f"#{f.id}", "title": f.title, "audit": _ref(a.id),
                    "audit_title": a.title,
                    "audit_type": a.audit_type, "rating": f.risk_rating.value, "status": f.status.value,
                    "remediation_status": f.remediation_status, "published": "Yes" if f.published else "No",
                    "owner": f.assigned_owner_email, "target_date": _d(f.target_date),
                    "retest_result": f.retest_result, "raised": _d(f.created_at)})
    return out


def _actions(db: DBSession, user: User) -> list[dict]:
    from app.domains.audit.audits.models import Finding
    from app.domains.issues.capa.models import Capa

    scope = _scope(db, user)
    audit_of = dict(db.execute(select(Finding.id, Finding.audit_id)).all())
    today = date.today()
    out = []
    for c in db.execute(select(Capa)).scalars():
        audit_id = audit_of.get(c.source_id) if c.source_type == "finding" else None
        if scope is not None and (audit_id is None or audit_id not in scope):
            continue
        overdue = bool(c.due_date and c.status.value != "Closed" and c.due_date.date() < today)
        out.append({"_audit_id": audit_id, "action": c.capa_ref, "title": c.title, "severity": c.severity.value,
                    "status": c.status.value, "owner": c.owner_email, "due_date": _d(c.due_date),
                    "overdue": "Yes" if overdue else "No", "audit": _ref(audit_id),
                    "validation": c.validation_result.value if c.validation_result else None,
                    "raised": _d(c.created_at)})
    return out


def _audits(db: DBSession, user: User) -> list[dict]:
    from app.domains.audit.audits.models import Audit

    scope = _scope(db, user)
    return [{"_audit_id": a.id, "audit": _ref(a.id), "title": a.title, "audit_type": a.audit_type,
             "workflow": a.workflow, "status": a.status.value, "created": _d(a.created_at)}
            for a in db.execute(select(Audit)).scalars() if scope is None or a.id in scope]


def _controls(db: DBSession, user: User) -> list[dict]:
    from app.domains.audit.rcm.models import Control, ControlTest, Objective

    scope = _scope(db, user)
    objs = {o.id: o for o in db.execute(select(Objective)).scalars() if scope is None or o.audit_id in scope}
    latest: dict[int, ControlTest] = {}
    for t in db.execute(select(ControlTest).order_by(ControlTest.id)).scalars():
        latest[t.control_id] = t
    out = []
    for c in db.execute(select(Control).where(Control.objective_id.in_(list(objs) or [0]))).scalars():
        o = objs[c.objective_id]
        t = latest.get(c.id)
        out.append({"_audit_id": o.audit_id, "control": c.ref, "title": c.title, "objective": o.title,
                    "audit": _ref(o.audit_id), "key": "Yes" if c.is_key else "No",
                    "latest_test": t.test_type.value if t else None,
                    "conclusion": t.conclusion.value if t and t.conclusion else "Not tested"})
    return out


def _risks(db: DBSession, user: User) -> list[dict]:
    from app.domains.grc.common import band
    from app.domains.grc.risk.models import EnterpriseRisk

    names = {u.id: (u.full_name or u.username) for u in db.execute(select(User)).scalars()}
    out = []
    for r in db.execute(select(EnterpriseRisk)).scalars():
        target = (r.target_likelihood or 0) * (r.target_impact or 0)
        out.append({"_audit_id": None, "risk": r.ref, "title": r.title, "category": r.category, "status": r.status,
                    "owner": names.get(r.owner_id), "inherent_score": r.inherent_score,
                    "residual_score": r.residual_score, "residual_level": band(r.residual_score),
                    "above_target": "Yes" if target and r.residual_score > target else "No",
                    "next_review": _d(r.next_review_date)})
    return out


def _projects(db: DBSession, user: User) -> list[dict]:
    from app.domains.assurance.planning.coverage import engagement_progress
    from app.domains.assurance.planning.models import AssurancePlan, PlanEngagement
    from app.domains.audit.audits.models import Audit

    scope = _scope(db, user)
    plans = {p.id: p for p in db.execute(select(AssurancePlan)).scalars()}
    names = {u.id: (u.full_name or u.username) for u in db.execute(select(User)).scalars()}
    out = []
    for e in db.execute(select(PlanEngagement)).scalars():
        if scope is not None and e.audit_id not in scope:
            continue
        p = plans.get(e.plan_id)
        audit = db.get(Audit, e.audit_id) if e.audit_id else None
        out.append({"_audit_id": e.audit_id, "plan": p.plan_ref if p else None,
                    "fiscal_year": p.fiscal_year if p else None,
                    "project": e.title, "quarter": e.planned_quarter, "status": e.status.value,
                    "owner": names.get(e.lead_auditor_id), "budget_hours": e.budget_hours,
                    "progress": engagement_progress(db, audit), "audit": _ref(e.audit_id)})
    return out


VIEWS: dict[str, View] = {v.key: v for v in (
    View("issues", "Issues", (
        Col("issue", "Issue"), Col("title", "Title"), Col("audit", "Audit"), Col("audit_title", "Audit title"),
        Col("audit_type", "Audit type"), Col("rating", "Rating"), Col("status", "Status"),
        Col("remediation_status", "Remediation status"), Col("published", "Published"), Col("owner", "Owner"),
        Col("target_date", "Target date", "date"), Col("retest_result", "Retest result"),
        Col("raised", "Raised", "date")), _issues, "raised"),
    View("actions", "Remediation actions", (
        Col("action", "Action"), Col("title", "Title"), Col("severity", "Severity"), Col("status", "Status"),
        Col("owner", "Owner"), Col("due_date", "Due date", "date"), Col("overdue", "Overdue"), Col("audit", "Audit"),
        Col("validation", "Validation"), Col("raised", "Raised", "date")), _actions, "due_date"),
    View("audits", "Audits (projects)", (
        Col("audit", "Audit"), Col("title", "Title"), Col("audit_type", "Audit type"), Col("workflow", "Workflow"),
        Col("status", "Status"), Col("created", "Created", "date")), _audits, "created"),
    View("controls", "Controls and testing", (
        Col("control", "Control"), Col("title", "Title"), Col("objective", "Objective"), Col("audit", "Audit"),
        Col("key", "Key control"), Col("latest_test", "Latest test"), Col("conclusion", "Conclusion")), _controls),
    View("risks", "Strategic risks", (
        Col("risk", "Risk"), Col("title", "Title"), Col("category", "Category"), Col("status", "Status"),
        Col("owner", "Owner"), Col("inherent_score", "Inherent score", "number"),
        Col("residual_score", "Residual score", "number"), Col("residual_level", "Residual level"),
        Col("above_target", "Above target"), Col("next_review", "Next review", "date")), _risks, "next_review",
         perms=("grc.view", "grc.manage", "grc.risk")),
    View("projects", "Assurance plan projects", (
        Col("plan", "Plan"), Col("fiscal_year", "Fiscal year", "number"), Col("project", "Project"),
        Col("quarter", "Quarter"), Col("status", "Status"), Col("owner", "Owner"),
        Col("budget_hours", "Budget hours", "number"), Col("progress", "Progress %", "number"),
        Col("audit", "Audit")), _projects),
)}


class FilterIn(BaseModel):
    column: str = Field(max_length=60)
    op: str = Field(default="eq", max_length=12)
    value: str | float | int | list[str] | None = None


class PeriodIn(BaseModel):
    column: str | None = Field(default=None, max_length=60)
    date_from: date | None = None
    date_to: date | None = None


class DesignIn(BaseModel):
    """Report Builder › Design: font, size, borders and alignment of the report output."""

    font: Literal["Default", "Serif", "Monospace"] = "Default"
    size: Literal["Small", "Medium", "Large"] = "Medium"
    borders: Literal["Rows", "Grid", "None"] = "Rows"
    align: Literal["Left", "Center", "Right"] = "Left"
    page_layout: Literal["Portrait", "Landscape"] = "Portrait"


class SpecIn(BaseModel):
    view: str = Field(max_length=40)
    columns: list[str] = Field(default_factory=list, max_length=40)
    filters: list[FilterIn] = Field(default_factory=list, max_length=20)
    period: PeriodIn | None = None
    group_by: str | None = Field(default=None, max_length=60)
    chart: str | None = Field(default=None, pattern="^(bar|pie|line)$")
    sort: str | None = Field(default=None, max_length=60)
    sort_desc: bool = False
    limit: int = Field(default=500, ge=1, le=MAX_ROWS)
    # Table (rows) or Cross Tab: rows = group_by, columns = cross_column, cells = count or the sum of `measure`.
    layout: Literal["table", "crosstab"] = "table"
    cross_column: str | None = Field(default=None, max_length=60)
    measure: str | None = Field(default=None, max_length=60)
    # Sections: the table is split into one section per value of this column.
    section_by: str | None = Field(default=None, max_length=60)
    # Analysis Style: "drill" lets readers open the records behind a chart bar or a Cross Tab cell.
    analysis: Literal["none", "drill"] = "none"
    design: DesignIn = Field(default_factory=DesignIn)


def available(user: User) -> list[View]:
    from app.core.enums import Role
    from app.core.permissions import has_perm

    if user.role not in (Role.Admin, Role.Auditor):
        return []
    return [v for v in VIEWS.values() if not v.perms or has_perm(user, *v.perms)]


def view_for(user: User, key: str) -> View:
    v = VIEWS.get(key)
    if v is None or v not in available(user):
        raise HTTPException(status_code=422, detail=f"Unknown or unavailable view '{key}'")
    return v


def validate(user: User, spec: SpecIn) -> View:
    v = view_for(user, spec.view)
    keys = {c.key for c in v.columns}
    for name in [*spec.columns, *(f.column for f in spec.filters), spec.group_by, spec.sort,
                 spec.period.column if spec.period else None, spec.cross_column, spec.measure, spec.section_by]:
        if name and name not in keys:
            raise HTTPException(status_code=422, detail=f"'{name}' is not a column of {v.label}")
    kinds = {c.key: c.type for c in v.columns}
    if spec.measure and kinds[spec.measure] != "number":
        raise HTTPException(status_code=422, detail="The Cross Tab value must be a number column (or the count)")
    if spec.layout == "crosstab":
        if not spec.group_by or not spec.cross_column:
            raise HTTPException(status_code=422, detail="A Cross Tab needs a row field and a column field")
        if spec.group_by == spec.cross_column:
            raise HTTPException(status_code=422, detail="Choose different fields for the Cross Tab rows and columns")
    for f in spec.filters:
        if f.op not in OPS:
            raise HTTPException(status_code=422, detail=f"Unknown filter operator '{f.op}'")
    if spec.period and spec.period.date_from and spec.period.date_to and spec.period.date_from > spec.period.date_to:
        raise HTTPException(status_code=422, detail="The period starts after it ends")
    return v


def _match(row: dict, f: FilterIn, kinds: dict[str, str]) -> bool:
    have = row.get(f.column)
    if f.op == "empty":
        return have in (None, "")
    if f.op == "not_empty":
        return have not in (None, "")
    if f.op == "in":
        wanted = {str(x).lower() for x in (f.value if isinstance(f.value, list) else [f.value])}
        return str(have).lower() in wanted
    if have is None:
        return f.op == "ne"
    if kinds.get(f.column) == "number":
        try:
            a, b = float(have), float(f.value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    else:
        a, b = str(have).lower(), str(f.value if f.value is not None else "").lower()
    return {"eq": a == b, "ne": a != b, "contains": str(b) in str(a), "gte": a >= b, "lte": a <= b}[f.op]


def describe(v: View, spec: SpecIn) -> tuple[str, str]:
    """Plain-language filters and period, shown with every output."""
    labels = {c.key: c.label for c in v.columns}
    words = {"eq": "is", "ne": "is not", "contains": "contains", "gte": "≥", "lte": "≤", "in": "is one of",
             "empty": "is empty", "not_empty": "is not empty"}
    parts = []
    for f in spec.filters:
        val = ", ".join(map(str, f.value)) if isinstance(f.value, list) else ("" if f.value is None else str(f.value))
        parts.append(f"{labels[f.column]} {words[f.op]} {val}".strip())
    period = "All dates"
    p = spec.period
    if p and (p.date_from or p.date_to):
        col = labels.get(p.column or v.date_column or "", "Date")
        period = f"{col} {p.date_from or '…'} to {p.date_to or '…'}"
    return ("; ".join(parts) or "No filters"), period


def _label(value: object) -> str:
    return "(blank)" if value in (None, "") else str(value)


def _crosstab(rows: list[dict], spec: SpecIn) -> dict:
    """Rows x columns of counts (or sums of the measure), with row, column and grand totals."""
    def amount(r: dict) -> float:
        if not spec.measure:
            return 1
        try:
            return float(r.get(spec.measure) or 0)
        except (TypeError, ValueError):
            return 0

    cells: dict[tuple[str, str], float] = {}
    row_keys: dict[str, float] = {}
    col_keys: dict[str, float] = {}
    for r in rows:
        a, b, n = _label(r.get(spec.group_by)), _label(r.get(spec.cross_column)), amount(r)
        cells[(a, b)] = cells.get((a, b), 0) + n
        row_keys[a] = row_keys.get(a, 0) + n
        col_keys[b] = col_keys.get(b, 0) + n
    cols = sorted(col_keys)
    tidy = lambda x: int(x) if float(x).is_integer() else round(x, 2)  # noqa: E731
    return {"row_key": spec.group_by, "column_key": spec.cross_column, "measure": spec.measure or "count",
            "columns": cols,
            "rows": [{"value": a, "cells": [tidy(cells.get((a, b), 0)) for b in cols], "total": tidy(row_keys[a])}
                     for a in sorted(row_keys)],
            "totals": [tidy(col_keys[b]) for b in cols], "grand": tidy(sum(row_keys.values()))}


def run(db: DBSession, user: User, spec: SpecIn) -> dict:
    """Run a report definition with this user's access."""
    from app.core.access import staff_audit_scope

    v = validate(user, spec)
    kinds = {c.key: c.type for c in v.columns}
    rows = v.rows(db, user)
    for f in spec.filters:
        rows = [r for r in rows if _match(r, f, kinds)]
    p = spec.period
    col = (p.column or v.date_column) if p else None
    if p and col and (p.date_from or p.date_to):
        lo, hi = (p.date_from.isoformat() if p.date_from else None), (p.date_to.isoformat() if p.date_to else None)
        rows = [r for r in rows if r.get(col) and (lo is None or r[col] >= lo) and (hi is None or r[col] <= hi)]
    if spec.sort:
        rows.sort(key=lambda r: (r.get(spec.sort) is None, r.get(spec.sort) if r.get(spec.sort) is not None else ""),
                  reverse=spec.sort_desc)
    total = len(rows)
    groups = None
    if spec.group_by:
        counts = Counter("(blank)" if r.get(spec.group_by) in (None, "") else str(r.get(spec.group_by)) for r in rows)
        groups = [{"value": k, "count": n} for k, n in counts.most_common()]
    cols = [c for c in v.columns if c.key in spec.columns] if spec.columns else list(v.columns)
    if spec.columns:
        order = {k: i for i, k in enumerate(spec.columns)}
        cols.sort(key=lambda c: order[c.key])
    shown = [{c.key: r.get(c.key) for c in cols} for r in rows[: spec.limit]]
    sections = None
    if spec.section_by:
        sec: dict[str, list[dict]] = {}
        for r, out in zip(rows[: spec.limit], shown, strict=True):
            sec.setdefault(_label(r.get(spec.section_by)), []).append(out)
        sections = [{"value": k, "count": len(v_)} for k, v_ in sec.items()]
        for s_ in sections:
            s_["rows"] = sec[s_["value"]]
    crosstab = _crosstab(rows, spec) if spec.layout == "crosstab" else None
    filters_text, period_text = describe(v, spec)
    scope = staff_audit_scope(db, user)
    audit_ids = sorted({r["_audit_id"] for r in rows if r.get("_audit_id")})
    return {
        "view": v.key, "view_label": v.label,
        "columns": [{"key": c.key, "label": c.label, "type": c.type} for c in cols],
        "rows": shown,
        "total": total, "truncated": total > spec.limit, "groups": groups, "group_by": spec.group_by,
        "chart": spec.chart if spec.group_by and spec.layout == "table" else None,
        "layout": spec.layout, "crosstab": crosstab, "sections": sections, "section_by": spec.section_by,
        "analysis": spec.analysis, "design": spec.design.model_dump(),
        "filters_text": filters_text, "period_text": period_text,
        "source": f"{v.label} (GPHA INTERNAL AUDIT WORKSPACE live data)",
        "scope_text": "All audits" if scope is None else f"Audits you may see ({len(scope)})",
        "generated_at": utcnow().isoformat(timespec="seconds"),
        "audit_ids": audit_ids,
        "perms": list(v.perms),
    }


def catalog(user: User) -> list[dict]:
    return [{"key": v.key, "label": v.label, "date_column": v.date_column,
             "columns": [{"key": c.key, "label": c.label, "type": c.type} for c in v.columns]} for v in available(user)]


# Report templates (Browse › Templates): ready-made definitions to copy and adapt.
TEMPLATES: tuple[dict, ...] = (
    {"key": "issues-owner-severity", "name": "Issues by Owner and Severity Bar Chart",
     "description": "Open issues grouped by severity, with their owners.",
     "definition": {"view": "issues", "columns": ["issue", "title", "owner", "rating", "status"],
                    "filters": [{"column": "status", "op": "ne", "value": "Closed"}], "group_by": "rating",
                    "chart": "bar", "sort": "rating"}},
    {"key": "issues-severity-pie", "name": "Issues by Severity",
     "description": "All issues by severity (pie chart).",
     "definition": {"view": "issues", "columns": ["issue", "title", "audit", "rating", "status"],
                    "group_by": "rating", "chart": "pie"}},
    {"key": "actions-due", "name": "Actions by due date",
     "description": "Open remediation actions with owner, due date and whether they are overdue.",
     "definition": {"view": "actions", "columns": ["action", "title", "owner", "due_date", "overdue", "status"],
                    "filters": [{"column": "status", "op": "ne", "value": "Closed"}], "group_by": "overdue",
                    "chart": "bar", "sort": "due_date"}},
    {"key": "plan-progress", "name": "Assurance plan progress",
     "description": "Plan projects with status, progress and budgeted hours.",
     "definition": {"view": "projects", "columns": ["plan", "project", "status", "progress", "budget_hours"],
                    "group_by": "status", "chart": "bar"}},
    {"key": "hours-owner", "name": "Project hours by owner",
     "description": "Budgeted project hours by owner (lead auditor).",
     "definition": {"view": "projects", "columns": ["project", "owner", "budget_hours", "status"],
                    "group_by": "owner", "chart": "bar", "sort": "owner"}},
    {"key": "control-results", "name": "Control testing results",
     "description": "Controls by latest test conclusion.",
     "definition": {"view": "controls", "columns": ["control", "title", "audit", "conclusion"],
                    "group_by": "conclusion", "chart": "pie"}},
    {"key": "risks-residual", "name": "Strategic risks by residual level",
     "description": "Strategic risks by residual level, and whether they are above target.",
     "definition": {"view": "risks", "columns": ["risk", "title", "category", "residual_score", "residual_level",
                                                 "above_target"], "group_by": "residual_level", "chart": "bar"}},
)


def with_context(v: View, spec: SpecIn, *, audit: str | None = None, date_from: date | None = None,
                 date_to: date | None = None) -> SpecIn:
    """Apply dashboard / presentation filters (Project, Period) to a report that supports them."""
    keys = {c.key for c in v.columns}
    out = spec.model_copy(deep=True)
    if audit and "audit" in keys:
        out.filters = [*out.filters, FilterIn(column="audit", op="eq", value=audit)]
    if (date_from or date_to) and v.date_column:
        out.period = PeriodIn(column=(spec.period.column if spec.period and spec.period.column else v.date_column),
                              date_from=date_from, date_to=date_to)
    return out
