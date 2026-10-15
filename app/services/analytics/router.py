"""Analytics for the CAE (risk heat map, finding trends, repeat findings, KPIs) and global search."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.access import is_privileged, visible
from app.core.appconfig import cfg
from app.core.database import get_db
from app.core.deps import require_active_user, require_module_tier, staff_or_perm
from app.core.enums import CapaStatus, EngagementStatus, ReportStatus, Role, utcnow
from app.domains.audit.audits.models import Audit, Finding
from app.domains.issues.capa.models import Capa
from app.platform.users.models import User

router = APIRouter(tags=["insights"])
Staff = Depends(require_module_tier("analytics", Role.Admin, Role.Auditor))
Governance = Depends(staff_or_perm("governance.view"))

_STOP = {
    "the",
    "a",
    "an",
    "of",
    "for",
    "and",
    "to",
    "in",
    "on",
    "not",
    "no",
    "is",
    "are",
    "was",
    "were",
    "be",
    "with",
    "by",
    "at",
    "from",
    "lack",
    "missing",
    "inadequate",
    "weak",
    "poor",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w.rstrip("s") for w in words if w not in _STOP and len(w) > 2}


def _similar(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


# ------------------------------------------------------------------ analytics


class Kpi(BaseModel):
    key: str
    label: str
    actual: float | None
    target: float
    unit: str
    better: str  # "higher" | "lower"
    status: str  # ok | warn | bad | none
    detail: str = ""


class Analytics(BaseModel):
    fiscal_year: int
    heat_map: list[dict]
    findings_trend: list[dict]
    open_by_rating: dict[str, int]
    repeat_findings: list[dict]
    kpis: list[Kpi]
    themes: list[dict]


def _status(actual: float | None, target: float, better: str) -> str:
    if actual is None:
        return "none"
    if (better == "higher" and actual >= target) or (better == "lower" and actual <= target):
        return "ok"
    gap = abs(actual - target) / (target or 1)
    return "warn" if gap <= 0.15 else "bad"


def repeat_findings(findings: list[Finding], audits: dict[int, Audit], threshold: float = 0.6) -> list[dict]:
    """Findings that recur across different audits of the same unit / organisation, or by near-identical title."""
    toks = {f.id: _tokens(f"{f.title} {f.criteria or ''}"[:400]) for f in findings}
    groups: list[list[Finding]] = []
    used: set[int] = set()
    ordered = sorted(findings, key=lambda f: f.created_at)
    for i, f in enumerate(ordered[:1500]):
        if f.id in used:
            continue
        group = [f]
        for g in ordered[i + 1 : 1500]:
            if g.id in used or g.audit_id == f.audit_id:
                continue
            af, ag = audits.get(f.audit_id), audits.get(g.audit_id)
            same_area = (
                af
                and ag
                and (
                    (af.entity_unit_id and af.entity_unit_id == ag.entity_unit_id)
                    or (af.organization_id and af.organization_id == ag.organization_id)
                )
            )
            score = _similar(toks[f.id], toks[g.id])
            if score >= threshold or (same_area and score >= threshold - 0.2):
                group.append(g)
        if len(group) > 1:
            used.update(x.id for x in group)
            groups.append(group)
    out = []
    for group in sorted(groups, key=len, reverse=True)[:25]:
        out.append(
            {
                "title": group[-1].title,
                "occurrences": len(group),
                "audits": [
                    {
                        "audit_id": x.audit_id,
                        "audit_title": audits[x.audit_id].title if x.audit_id in audits else "",
                        "finding_id": x.id,
                        "rating": x.risk_rating.value,
                        "status": x.status.value,
                        "date": x.created_at.date().isoformat(),
                    }
                    for x in group
                ],
            }
        )
    return out


def _fieldwork_start(db: DBSession, audit_id: int) -> datetime | None:
    from app.platform.history.models import RecordHistory

    row = db.execute(
        select(RecordHistory.timestamp)
        .where(
            RecordHistory.record_type == "audit",
            RecordHistory.record_id == audit_id,
            RecordHistory.action.like("%status=In Progress%"),
        )
        .order_by(RecordHistory.timestamp)
    ).first()
    return row[0] if row else None


def analytics(db: DBSession, fy: int) -> Analytics:
    from app.domains.assurance.planning.models import AssurancePlan, EntityUnit, PlanEngagement
    from app.domains.assurance.qaip.models import AuditSurvey
    from app.domains.audit.capacity.router import capacity_summary
    from app.domains.audit.reports.models import AuditReport

    start, end = datetime(fy, 1, 1), datetime(fy + 1, 1, 1)
    # Heat map: 5x5 likelihood x impact over active auditable units.
    cells: dict[tuple[int, int], list[str]] = defaultdict(list)
    units = db.execute(select(EntityUnit).where(EntityUnit.is_active.is_(True))).scalars().all()
    for u in units:
        cells[(u.risk_likelihood, u.risk_impact)].append(u.name)
    heat = [
        {"likelihood": lk, "impact": im, "score": lk * im, "count": len(cells[(lk, im)]), "units": cells[(lk, im)][:12]}
        for lk in range(1, 6)
        for im in range(1, 6)
    ]

    audits = {a.id: a for a in db.execute(select(Audit)).scalars()}
    findings = db.execute(select(Finding)).scalars().all()
    # 12-month trend ending at the fiscal year end (or today, whichever is earlier).
    anchor = min(end, utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    months = []
    y, m = anchor.year, anchor.month
    for _ in range(12):
        months.append((y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    months.reverse()
    trend = {k: {"High": 0, "Medium": 0, "Low": 0} for k in months}
    for f in findings:
        key = (f.created_at.year, f.created_at.month)
        if key in trend:
            trend[key][f.risk_rating.value] += 1
    findings_trend = [{"month": f"{yy}-{mm:02d}", **trend[(yy, mm)]} for yy, mm in months]
    open_by = {"High": 0, "Medium": 0, "Low": 0}
    for f in findings:
        if f.status.value != "Closed":
            open_by[f.risk_rating.value] += 1

    # Themes: most common significant words in this year's finding titles.
    words: dict[str, int] = defaultdict(int)
    for f in findings:
        if start <= f.created_at < end:
            for w in _tokens(f.title):
                words[w] += 1
    themes = [{"word": w, "count": c} for w, c in sorted(words.items(), key=lambda x: -x[1])[:12] if c > 1]

    # KPIs
    kpis: list[Kpi] = []
    plan = db.execute(select(AssurancePlan).where(AssurancePlan.fiscal_year == fy)).scalar_one_or_none()
    if plan:
        engs = db.execute(select(PlanEngagement).where(PlanEngagement.plan_id == plan.id)).scalars().all()
        live = [e for e in engs if e.status != EngagementStatus.Cancelled]
        started = [e for e in live if e.status == EngagementStatus.Started]
        pct = round(100 * len(started) / len(live), 1) if live else None
        kpis.append(
            Kpi(
                key="plan",
                label="Assurance Plan delivery",
                actual=pct,
                target=cfg("kpi_plan_completion_pct"),
                unit="%",
                better="higher",
                status=_status(pct, cfg("kpi_plan_completion_pct"), "higher"),
                detail=f"{len(started)} of {len(live)} engagements started",
            )
        )
    else:
        kpis.append(
            Kpi(
                key="plan",
                label="Assurance Plan delivery",
                actual=None,
                target=cfg("kpi_plan_completion_pct"),
                unit="%",
                better="higher",
                status="none",
                detail=f"No Assurance Plan for FY{fy}",
            )
        )

    closed = (
        db.execute(select(Capa).where(Capa.status == CapaStatus.Closed, Capa.closed_at >= start, Capa.closed_at < end))
        .scalars()
        .all()
    )
    with_due = [c for c in closed if c.due_date]
    on_time = [c for c in with_due if c.closed_at <= c.due_date.replace(hour=23, minute=59)]
    pct = round(100 * len(on_time) / len(with_due), 1) if with_due else None
    kpis.append(
        Kpi(
            key="actions_on_time",
            label="Remediation closed on time",
            actual=pct,
            target=cfg("kpi_actions_on_time_pct"),
            unit="%",
            better="higher",
            status=_status(pct, cfg("kpi_actions_on_time_pct"), "higher"),
            detail=f"{len(on_time)} of {len(with_due)} closed by the due date",
        )
    )

    overdue = (
        db.execute(
            select(Capa).where(Capa.status != CapaStatus.Closed, Capa.due_date.is_not(None), Capa.due_date < utcnow())
        )
        .scalars()
        .all()
    )
    kpis.append(
        Kpi(
            key="overdue",
            label="Overdue remediation",
            actual=len(overdue),
            target=0,
            unit="",
            better="lower",
            status="ok" if not overdue else ("warn" if len(overdue) <= 3 else "bad"),
            detail="open actions past their due date",
        )
    )

    reports = (
        db.execute(
            select(AuditReport).where(
                AuditReport.status == ReportStatus.Issued, AuditReport.issued_at >= start, AuditReport.issued_at < end
            )
        )
        .scalars()
        .all()
    )
    spans = []
    for r in reports:
        begun = _fieldwork_start(db, r.audit_id)
        if begun and r.issued_at:
            spans.append((r.issued_at - begun).days)
    avg_days = round(sum(spans) / len(spans), 1) if spans else None
    kpis.append(
        Kpi(
            key="report_days",
            label="Fieldwork start to report issued",
            actual=avg_days,
            target=cfg("kpi_report_days"),
            unit="days",
            better="lower",
            status=_status(avg_days, cfg("kpi_report_days"), "lower"),
            detail=f"average over {len(spans)} issued report(s)",
        )
    )

    surveys = (
        db.execute(select(AuditSurvey).where(AuditSurvey.submitted_at >= start, AuditSurvey.submitted_at < end))
        .scalars()
        .all()
    )
    avg = round(sum(s.average for s in surveys) / len(surveys), 2) if surveys else None
    target = cfg("kpi_survey_score") / 10
    kpis.append(
        Kpi(
            key="survey",
            label="Auditee satisfaction",
            actual=avg,
            target=target,
            unit="/ 5",
            better="higher",
            status=_status(avg, target, "higher"),
            detail=f"{len(surveys)} survey response(s)",
        )
    )

    cap = capacity_summary(db, fy)
    util = cap.totals["utilisation_pct"] if cap.totals["logged_hours"] else None
    kpis.append(
        Kpi(
            key="utilisation",
            label="Time charged to audit work",
            actual=util,
            target=cfg("kpi_utilisation_pct"),
            unit="%",
            better="higher",
            status=_status(util, cfg("kpi_utilisation_pct"), "higher"),
            detail=f"{cap.totals['audit_hours']:g} of {cap.totals['logged_hours']:g} hours logged",
        )
    )

    return Analytics(
        fiscal_year=fy,
        heat_map=heat,
        findings_trend=findings_trend,
        open_by_rating=open_by,
        repeat_findings=repeat_findings(findings, audits),
        kpis=kpis,
        themes=themes,
    )


@router.get("/api/analytics", response_model=Analytics)
def get_analytics(
    fiscal_year: int | None = None, db: DBSession = Depends(get_db), user: User = Governance
) -> Analytics:
    return analytics(db, fiscal_year or utcnow().year)


# ------------------------------------------------------------------ global search


class Hit(BaseModel):
    type: str
    type_label: str
    id: int
    ref: str | None = None
    title: str
    subtitle: str = ""
    status: str | None = None


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%"


@router.get("/api/search", response_model=list[Hit])
def search(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(8, ge=1, le=25),
    db: DBSession = Depends(get_db),
    user: User = Depends(require_active_user),
) -> list[Hit]:
    from app.domains.assurance.planning.models import AssurancePlan, EntityUnit
    from app.domains.audit.reports.models import AuditReport
    from app.domains.audit.service_feedback.models import ServiceFeedback
    from app.domains.issues.nonconformances.models import Nonconformance
    from app.platform.organizations.models import Organization
    from app.platform.stakeholders.models import Stakeholder

    pat = _like(q.strip())
    staff = is_privileged(user)

    def st(r) -> str | None:  # noqa: ANN001
        value = getattr(r, "status", None)
        return getattr(value, "value", value)

    # (record_type for access checks, label, model, columns searched, ref attr, title attr, subtitle fn, staff only)
    sources = [
        ("audit", "Audit", Audit, (Audit.title, Audit.scope), None, "title", lambda r: (r.scope or "")[:90], False),
        (
            "finding",
            "Finding",
            Finding,
            (Finding.title, Finding.condition),
            None,
            "title",
            lambda r: f"{r.risk_rating.value} risk",
            False,
        ),
        (
            "capa",
            "Remediation",
            Capa,
            (Capa.capa_ref, Capa.title),
            "capa_ref",
            "title",
            lambda r: r.owner_email or "",
            False,
        ),
        (
            "nonconformance",
            "Nonconformance",
            Nonconformance,
            (Nonconformance.nc_ref, Nonconformance.title),
            "nc_ref",
            "title",
            lambda r: "",
            False,
        ),
        (
            "audit_report",
            "Report",
            AuditReport,
            (AuditReport.report_ref, AuditReport.title),
            "report_ref",
            "title",
            lambda r: "",
            False,
        ),
        (
            "service_feedback",
            "Service feedback",
            ServiceFeedback,
            (ServiceFeedback.sf_ref, ServiceFeedback.subject),
            "sf_ref",
            "subject",
            lambda r: "",
            False,
        ),
        (
            "organization",
            "Organization",
            Organization,
            (Organization.org_ref, Organization.name),
            "org_ref",
            "name",
            lambda r: r.contact_name or "",
            True,
        ),
        (
            "stakeholder",
            "Stakeholder",
            Stakeholder,
            (Stakeholder.sh_ref, Stakeholder.name),
            "sh_ref",
            "name",
            lambda r: r.contact_name or "",
            True,
        ),
        (
            "assurance_plan",
            "Assurance Plan",
            AssurancePlan,
            (AssurancePlan.plan_ref, AssurancePlan.title),
            "plan_ref",
            "title",
            lambda r: f"FY{r.fiscal_year}",
            True,
        ),
        (
            "entity_unit",
            "Auditable unit",
            EntityUnit,
            (EntityUnit.code, EntityUnit.name),
            "code",
            "name",
            lambda r: f"Risk {r.risk_likelihood * r.risk_impact}",
            True,
        ),
    ]
    hits: list[Hit] = []
    for rtype, label, model, cols, ref_attr, title_attr, sub, staff_only in sources:
        if staff_only and not staff:
            continue
        rows = (
            db.execute(
                select(model)
                .where(or_(*(c.ilike(pat) for c in cols)))
                .order_by(model.id.desc())
                .limit(limit * (1 if staff else 4))
            )
            .scalars()
            .all()
        )
        if rtype != "entity_unit":
            rows = visible(db, user, rtype, rows)
        for r in rows[:limit]:
            hits.append(
                Hit(
                    type=rtype,
                    type_label=label,
                    id=r.id,
                    ref=getattr(r, ref_attr) if ref_attr else None,
                    title=getattr(r, title_attr),
                    subtitle=sub(r),
                    status=st(r),
                )
            )
    # Exact reference matches first, then title-starts-with, keeping type grouping otherwise.
    ql = q.strip().lower()
    hits.sort(key=lambda h: 0 if (h.ref or "").lower() == ql else 1 if h.title.lower().startswith(ql) else 2)
    return hits
