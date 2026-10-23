"""The analytics a robot task can run. Each one is a fixed, read-only query over GPHA INTERNAL AUDIT WORKSPACE data
with a few numeric
parameters, so robots never execute free-form scripts on the server.

An analytic returns rows of (record_key, data, priority). ``record_key`` is stable across runs, so a later run
updates the same record instead of adding a duplicate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import utcnow

Row = tuple[str, dict, str]


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    default: int
    min: int = 0
    max: int = 3650


@dataclass(frozen=True)
class Analytic:
    key: str
    name: str
    description: str
    columns: list[str]
    run: Callable[[DBSession, dict], list[Row]]
    params: list[Param] = field(default_factory=list)


def _sev(value: str) -> str:
    return {"High": "High", "Critical": "Critical", "Low": "Low"}.get(value, "Medium")


def _open_high_issues(db: DBSession, p: dict) -> list[Row]:
    from app.core.enums import FindingStatus, RiskRating
    from app.domains.audit.audits.models import Audit, Finding

    days = p.get("min_days_open", 0)
    cutoff = utcnow() - timedelta(days=days)
    rows = db.execute(select(Finding, Audit.title).join(Audit, Audit.id == Finding.audit_id).where(
        Finding.status != FindingStatus.Closed, Finding.risk_rating == RiskRating.High,
        Finding.created_at <= cutoff)).all()
    now = utcnow()
    return [(f"finding:{f.id}", {"Issue": f.title, "Audit": title, "Severity": f.risk_rating.value,
                                 "Status": f.status.value, "Owner": f.assigned_owner_email or "",
                                 "Days open": (now - f.created_at).days}, "High") for f, title in rows]


def _overdue_actions(db: DBSession, p: dict) -> list[Row]:
    from app.core.enums import CapaStatus
    from app.domains.issues.capa.models import Capa

    grace = p.get("grace_days", 0)
    cutoff = utcnow() - timedelta(days=grace)
    rows = db.execute(select(Capa).where(Capa.status != CapaStatus.Closed, Capa.due_date.is_not(None),
                                         Capa.due_date < cutoff)).scalars()
    now = utcnow()
    return [(f"capa:{c.id}", {"Action": c.capa_ref, "Title": c.title, "Severity": c.severity.value,
                              "Owner": c.owner_email or "", "Due": c.due_date.date().isoformat(),
                              "Days overdue": (now - c.due_date).days}, _sev(c.severity.value)) for c in rows]


def _tests_with_exceptions(db: DBSession, p: dict) -> list[Row]:
    from app.domains.audit.audits.models import Audit
    from app.domains.audit.rcm.models import Control, ControlTest, Objective

    least = p.get("min_exceptions", 1)
    rows = db.execute(select(ControlTest, Control, Audit.title).join(Control, Control.id == ControlTest.control_id)
                      .join(Objective, Objective.id == Control.objective_id).join(Audit, Audit.id == Objective.audit_id)
                      .where(ControlTest.exceptions_found >= max(1, least))).all()
    return [(f"test:{t.id}", {"Test": t.ref, "Control": c.title, "Audit": title, "Sample": t.sample_size or 0,
                              "Exceptions": t.exceptions_found, "Conclusion": t.conclusion.value},
             "High" if t.sample_size and t.exceptions_found * 10 >= t.sample_size else "Medium")
            for t, c, title in rows]


def _overdue_requests(db: DBSession, p: dict) -> list[Row]:
    from app.domains.audit.audits.models import Audit
    from app.domains.audit.evidence.models import EvidenceRequest

    grace = p.get("grace_days", 0)
    cutoff = utcnow() - timedelta(days=grace)
    rows = db.execute(select(EvidenceRequest, Audit.title).join(Audit, Audit.id == EvidenceRequest.audit_id).where(
        EvidenceRequest.status.in_(("Requested", "Returned")), EvidenceRequest.due_date.is_not(None),
        EvidenceRequest.due_date < cutoff)).all()
    now = utcnow()
    return [(f"request:{r.id}", {"Request": r.title, "Audit": title, "Status": r.status,
                                 "Due": r.due_date.date().isoformat(), "Days overdue": (now - r.due_date).days},
             "High" if (now - r.due_date).days > 14 else "Medium") for r, title in rows]


def _audits_over_budget(db: DBSession, p: dict) -> list[Row]:
    from app.domains.assurance.planning.models import PlanEngagement
    from app.domains.audit.audits.models import Audit
    from app.domains.audit.capacity.models import TimeEntry

    margin = p.get("margin_percent", 0)
    spent = dict(db.execute(select(TimeEntry.audit_id, func.sum(TimeEntry.hours)).where(
        TimeEntry.audit_id.is_not(None)).group_by(TimeEntry.audit_id)).all())
    out = []
    for e, title in db.execute(select(PlanEngagement, Audit.title).join(Audit, Audit.id == PlanEngagement.audit_id)
                               .where(PlanEngagement.budget_hours > 0)).all():
        used = float(spent.get(e.audit_id) or 0)
        if used > e.budget_hours * (1 + margin / 100):
            over = round(100 * (used - e.budget_hours) / e.budget_hours)
            out.append((f"audit:{e.audit_id}", {"Audit": title, "Budget": e.budget_hours, "Time spent": used,
                                                "Over budget %": over}, "High" if over >= 25 else "Medium"))
    return out


def _entities_overdue(db: DBSession, p: dict) -> list[Row]:
    from app.domains.assurance.planning.models import EntityUnit

    months_default = p.get("default_frequency_months", 36)
    now = utcnow()
    out = []
    for u in db.execute(select(EntityUnit).where(EntityUnit.is_active.is_(True))).scalars():
        months = u.audit_frequency_months or months_default
        last = u.last_audited_at
        due = (last + timedelta(days=round(months * 30.44))) if last else None
        if due is None or due < now:
            out.append((f"entity:{u.id}", {"Auditable entity": u.name, "Last audited":
                                           last.date().isoformat() if last else "Never",
                                           "Audit frequency (months)": months,
                                           "Next due": due.date().isoformat() if due else "Now",
                                           "Risk rating": u.assessed_rating or ""},
                        "High" if last is None else "Medium"))
    return out


def _unpublished_issues(db: DBSession, p: dict) -> list[Row]:
    from app.core.enums import FindingStatus
    from app.domains.audit.audits.models import Audit, Finding

    days = p.get("older_than_days", 30)
    cutoff = utcnow() - timedelta(days=days)
    rows = db.execute(select(Finding, Audit.title).join(Audit, Audit.id == Finding.audit_id).where(
        Finding.published.is_(False), Finding.status != FindingStatus.Closed, Finding.created_at <= cutoff)).all()
    return [(f"finding:{f.id}", {"Issue": f.title, "Audit": title, "Severity": f.risk_rating.value,
                                 "Raised": f.created_at.date().isoformat()}, _sev(f.risk_rating.value))
            for f, title in rows]


CATALOG: dict[str, Analytic] = {a.key: a for a in [
    Analytic("open_high_issues", "Open High issues", "Issues rated High that are not closed.",
             ["Issue", "Audit", "Severity", "Status", "Owner", "Days open"], _open_high_issues,
             [Param("min_days_open", "Open for at least (days)", 0)]),
    Analytic("overdue_actions", "Overdue remediation actions", "Agreed actions past their due date.",
             ["Action", "Title", "Severity", "Owner", "Due", "Days overdue"], _overdue_actions,
             [Param("grace_days", "Grace period (days)", 0, 0, 365)]),
    Analytic("tests_with_exceptions", "Control tests with exceptions", "Tests that found exceptions.",
             ["Test", "Control", "Audit", "Sample", "Exceptions", "Conclusion"], _tests_with_exceptions,
             [Param("min_exceptions", "At least (exceptions)", 1, 1, 1000)]),
    Analytic("overdue_requests", "Overdue evidence requests", "Requests the auditee has not answered in time.",
             ["Request", "Audit", "Status", "Due", "Days overdue"], _overdue_requests,
             [Param("grace_days", "Grace period (days)", 0, 0, 365)]),
    Analytic("audits_over_budget", "Audits over budget", "Audits whose logged time exceeds the budget hours.",
             ["Audit", "Budget", "Time spent", "Over budget %"], _audits_over_budget,
             [Param("margin_percent", "Tolerance (%)", 0, 0, 200)]),
    Analytic("entities_overdue", "Auditable entities overdue for audit",
             "Active entities never audited or past their audit frequency.",
             ["Auditable entity", "Last audited", "Audit frequency (months)", "Next due", "Risk rating"],
             _entities_overdue, [Param("default_frequency_months", "Frequency when not set (months)", 36, 1, 120)]),
    Analytic("unpublished_issues", "Issues not yet published", "Open issues the auditee still cannot see.",
             ["Issue", "Audit", "Severity", "Raised"], _unpublished_issues,
             [Param("older_than_days", "Older than (days)", 30, 0, 3650)]),
]}


def clean_params(analytic: Analytic, raw: dict | None) -> dict:
    from app.core.errors import field_error

    raw = raw or {}
    out = {}
    for prm in analytic.params:
        value = raw.get(prm.key, prm.default)
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise field_error(f"param_{prm.key}", f"{prm.label} must be a whole number") from None
        if not prm.min <= value <= prm.max:
            raise field_error(f"param_{prm.key}", f"{prm.label} must be between {prm.min} and {prm.max}")
        out[prm.key] = value
    return out


def next_run(frequency: str | None, starting_at: str, beginning_on, after: datetime | None = None):  # noqa: ANN001,ANN201
    """The next scheduled time on or after ``after`` (None when the task is not scheduled)."""
    if not frequency:
        return None
    now = after or utcnow()
    hh, mm = (int(x) for x in (starting_at or "06:00").split(":"))
    base = datetime.combine(beginning_on or now.date(), datetime.min.time()).replace(hour=hh, minute=mm)
    step = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}.get(frequency)
    t = base
    while t <= now:
        if step:
            t += step
        else:  # monthly
            month = t.month % 12 + 1
            year = t.year + (t.month == 12)
            day = min(t.day, 28)
            t = t.replace(year=year, month=month, day=day)
    return t
