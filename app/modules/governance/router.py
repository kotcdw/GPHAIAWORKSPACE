"""Governance portal (Audit Committee / executive reviewers) and port portfolio (PIA / GM Audit).

Everything here is read-only. The governance portal shows only *approved* plans and *issued*
reports; the port portfolio aggregates audits, findings and remediation per port.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.deps import require_perm
from app.core.enums import AuditStatus, CapaStatus, FindingStatus, PlanStatus, ReportStatus, utcnow
from app.core.permissions import has_perm
from app.modules.audits.models import Audit, Finding
from app.modules.capa.models import Capa
from app.modules.planning.models import AssurancePlan
from app.modules.reports.models import AuditReport
from app.modules.users.models import User

router = APIRouter(tags=["governance"])
Governance = Depends(require_perm("governance.view", "oversight.reporting", "oversight.portfolio"))
Portfolio = Depends(require_perm("oversight.port", "oversight.portfolio", "governance.view"))


class GovPlanEngagement(BaseModel):
    title: str
    planned_quarter: str
    status: str
    budget_hours: int


class GovPlan(BaseModel):
    id: int
    plan_ref: str
    fiscal_year: int
    title: str
    status: str
    approved_at: datetime | None
    committee_meeting_date: datetime | None
    committee_reference: str | None
    engagements: list[GovPlanEngagement]
    completed: int
    total: int


class GovReport(BaseModel):
    id: int
    report_ref: str
    title: str
    rating: str | None
    issued_at: datetime | None
    audit_id: int
    findings: dict[str, int]


class GovOverview(BaseModel):
    generated_at: datetime
    plans: list[GovPlan]
    reports: list[GovReport]
    kpis: dict[str, int | float]


@router.get("/api/governance/overview", response_model=GovOverview)
def overview(db: DBSession = Depends(get_db), user: User = Governance) -> GovOverview:
    plans = []
    for p in db.execute(select(AssurancePlan).where(AssurancePlan.status.in_((PlanStatus.Approved, PlanStatus.Closed)))
                        .order_by(AssurancePlan.fiscal_year.desc())).scalars():
        engs = [e for e in p.engagements if e.status.value != "Cancelled"]
        done = sum(1 for e in engs
                   if e.audit_id and (a := db.get(Audit, e.audit_id)) and a.status == AuditStatus.Closed)
        plans.append(GovPlan(id=p.id, plan_ref=p.plan_ref, fiscal_year=p.fiscal_year, title=p.title,
                             status=p.status.value, approved_at=p.approved_at,
                             committee_meeting_date=p.committee_meeting_date,
                             committee_reference=getattr(p, "committee_reference", None),
                             engagements=[GovPlanEngagement(title=e.title, planned_quarter=e.planned_quarter,
                                                            status=e.status.value, budget_hours=e.budget_hours)
                                          for e in engs], completed=done, total=len(engs)))
    reports = []
    for r in db.execute(select(AuditReport).where(AuditReport.status == ReportStatus.Issued)
                        .order_by(AuditReport.issued_at.desc())).scalars():
        ratings = Counter(f.risk_rating.value for f in db.execute(
            select(Finding).where(Finding.audit_id == r.audit_id)).scalars())
        reports.append(GovReport(id=r.id, report_ref=r.report_ref, title=r.title,
                                 rating=r.overall_rating.value if r.overall_rating else None, issued_at=r.issued_at,
                                 audit_id=r.audit_id, findings=dict(ratings)))
    now = utcnow()
    capas = list(db.execute(select(Capa)).scalars())
    open_capa = [c for c in capas if c.status != CapaStatus.Closed]
    overdue = [c for c in open_capa if c.due_date and c.due_date < now]
    closed = [c for c in capas if c.status == CapaStatus.Closed and c.due_date and c.closed_at]
    on_time = sum(1 for c in closed if c.closed_at <= c.due_date)
    open_findings = db.execute(select(Finding).where(Finding.status != FindingStatus.Closed)).scalars().all()
    current = plans[0] if plans else None
    kpis: dict[str, int | float] = {
        "plan_completion_pct": round(100 * current.completed / current.total) if current and current.total else 0,
        "reports_issued": len(reports),
        "open_findings": len(open_findings),
        "open_high_findings": sum(1 for f in open_findings if f.risk_rating.value in ("High", "Critical")),
        "open_actions": len(open_capa),
        "overdue_actions": len(overdue),
        "actions_closed_on_time_pct": round(100 * on_time / len(closed)) if closed else 0,
    }
    return GovOverview(generated_at=now, plans=plans, reports=reports, kpis=kpis)


# ------------------------------------------------------------------ port portfolio


class PortRow(BaseModel):
    port_id: int | None
    port_name: str
    audits: int
    audits_by_status: dict[str, int]
    open_findings: int
    open_high_findings: int
    open_actions: int
    overdue_actions: int
    reports_issued: int


class PortAudit(BaseModel):
    id: int
    title: str
    status: str
    audit_type: str | None
    open_findings: int


class PortDetail(PortRow):
    audits_list: list[PortAudit]


def _visible_ports(db: DBSession, user: User) -> int | None:
    """None = all ports; otherwise the only port this user oversees (their home port)."""
    if has_perm(user, "oversight.portfolio", "governance.view"):
        return None
    from app.modules.audits.router import _home_port

    port = _home_port(db, user)
    if port is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Set 'Where I work' on your profile to see your port's portfolio")
    return port


def _rows(db: DBSession, only: int | None) -> dict[int | None, PortDetail]:
    from app.modules.organizations.router import Index

    idx = Index(db)
    now = utcnow()
    audits = list(db.execute(select(Audit)).scalars())
    findings_by_audit: dict[int, list[Finding]] = defaultdict(list)
    for f in db.execute(select(Finding)).scalars():
        findings_by_audit[f.audit_id].append(f)
    capa_by_finding: dict[int, list[Capa]] = defaultdict(list)
    for c in db.execute(select(Capa).where(Capa.source_type == "finding")).scalars():
        if c.source_id:
            capa_by_finding[c.source_id].append(c)
    issued = {r.audit_id for r in db.execute(select(AuditReport).where(AuditReport.status == ReportStatus.Issued))
              .scalars()}
    out: dict[int | None, PortDetail] = {}
    for o in idx.rows.values():
        if idx.is_port(o) and (only is None or o.id == only):
            out[o.id] = PortDetail(port_id=o.id, port_name=o.name, audits=0, audits_by_status={}, open_findings=0,
                                   open_high_findings=0, open_actions=0, overdue_actions=0, reports_issued=0,
                                   audits_list=[])
    for a in audits:
        key = a.port_entity_id
        if only is not None and key != only:
            continue
        if key not in out:
            if key is not None:
                continue  # entity is no longer a port
            out[None] = out.get(None) or PortDetail(
                port_id=None, port_name="Not assigned to a port", audits=0, audits_by_status={}, open_findings=0,
                open_high_findings=0, open_actions=0, overdue_actions=0, reports_issued=0, audits_list=[])
        row = out[key]
        row.audits += 1
        row.audits_by_status[a.status.value] = row.audits_by_status.get(a.status.value, 0) + 1
        open_f = [f for f in findings_by_audit[a.id] if f.status != FindingStatus.Closed]
        row.open_findings += len(open_f)
        row.open_high_findings += sum(1 for f in open_f if f.risk_rating.value in ("High", "Critical"))
        for f in findings_by_audit[a.id]:
            for c in capa_by_finding[f.id]:
                if c.status != CapaStatus.Closed:
                    row.open_actions += 1
                    if c.due_date and c.due_date < now:
                        row.overdue_actions += 1
        row.reports_issued += 1 if a.id in issued else 0
        row.audits_list.append(PortAudit(id=a.id, title=a.title, status=a.status.value, audit_type=a.audit_type,
                                         open_findings=len(open_f)))
    return out


@router.get("/api/portfolio/ports", response_model=list[PortRow])
def port_portfolio(db: DBSession = Depends(get_db), user: User = Portfolio) -> list[PortRow]:
    rows = _rows(db, _visible_ports(db, user))
    return sorted((PortRow(**r.model_dump(exclude={"audits_list"})) for r in rows.values()),
                  key=lambda r: (r.port_id is None, r.port_name.lower()))


@router.get("/api/portfolio/ports/{port_id}", response_model=PortDetail)
def port_detail(port_id: int, db: DBSession = Depends(get_db), user: User = Portfolio) -> PortDetail:
    only = _visible_ports(db, user)
    if only is not None and only != port_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only see your own port")
    rows = _rows(db, port_id)
    if port_id not in rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Port not found")
    return rows[port_id]
