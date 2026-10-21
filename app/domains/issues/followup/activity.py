"""Activity Center › Issues & Actions (Issue follow-up walkthrough, steps 1 and 8).

One monitoring view over every issue and remediation action the user may see: open issues, actions by due date
(overdue, due soon, completed), issues by due date, open issues, actions by priority and the follow-up status of
each issue (remediation status and retest). Data comes from the projects; filters narrow by project and owner.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.enums import CapaStatus, FindingStatus, Role
from app.platform.users.models import User

router = APIRouter(tags=["follow-up"])
Staff = Depends(require_role(Role.Admin, Role.Auditor))
DUE_SOON_DAYS = 14


def _retest_state(f) -> str:  # noqa: ANN001
    if f.retest_result:
        return f"Retested: {f.retest_result}"
    if f.retest_deadline:
        return "Scheduled"
    return "Not started"


def _day(v) -> date | None:  # noqa: ANN001
    return v.date() if v is not None and hasattr(v, "date") else v


@router.get("/api/activity-center/issues-actions")
def issues_actions(audit_id: int | None = None, owner: str | None = Query(None, max_length=255),
                   db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    from app.core.access import staff_audit_scope
    from app.domains.audit.audits.models import Audit, Finding
    from app.domains.issues.capa.models import Capa

    scope = staff_audit_scope(db, user)
    audits = {a.id: a for a in db.execute(select(Audit)).scalars() if scope is None or a.id in scope}
    if audit_id is not None:
        audits = {k: v for k, v in audits.items() if k == audit_id}
    who = (owner or "").strip().lower()
    findings = [f for f in db.execute(select(Finding).where(Finding.audit_id.in_(list(audits) or [0]))).scalars()
                if not who or (f.assigned_owner_email or "").lower() == who]
    by_id = {f.id: f for f in findings}
    actions = [c for c in db.execute(select(Capa).where(Capa.source_type == "finding",
                                                        Capa.source_id.in_(list(by_id) or [0]))).scalars()
               if not who or (c.owner_email or "").lower() == who
               or (by_id[c.source_id].assigned_owner_email or "").lower() == who]
    today = date.today()
    soon = today + timedelta(days=DUE_SOON_DAYS)
    open_issues = [f for f in findings if f.status != FindingStatus.Closed]
    open_actions = [c for c in actions if c.status != CapaStatus.Closed]
    overdue = [c for c in open_actions if c.due_date and _day(c.due_date) < today]
    due_soon = [c for c in open_actions if c.due_date and today <= _day(c.due_date) <= soon]

    def issue_due(f):  # noqa: ANN001, ANN202
        return _day(f.remediation_deadline or f.target_date)

    def issue_row(f):  # noqa: ANN001, ANN202
        due = issue_due(f)
        return {"id": f.id, "title": f.title, "audit_id": f.audit_id, "project": audits[f.audit_id].title,
                "owner": f.assigned_owner_email or f.responsible_officer, "rating": f.risk_rating.value,
                "status": f.status.value, "remediation_status": f.remediation_status, "deadline": due,
                "due_state": ("overdue" if due and due < today else "due soon" if due and due <= soon else None),
                "retest": _retest_state(f), "published": f.published}

    dated = sorted((f for f in open_issues if issue_due(f)), key=issue_due)
    prio = Counter(c.severity.value for c in open_actions)
    return {
        "filters": {"audit_id": audit_id, "owner": owner or None},
        "projects": [{"id": a.id, "title": a.title} for a in sorted(audits.values(), key=lambda a: a.title.lower())],
        "open_issues": len(open_issues),
        "closed_issues": len(findings) - len(open_issues),
        "actions": {"overdue": len(overdue), "due_soon": len(due_soon),
                    "completed": sum(1 for c in actions if c.status == CapaStatus.Closed), "open": len(open_actions)},
        "issues_by_due_date": [issue_row(f) for f in dated if issue_row(f)["due_state"]][:20],
        "open_issue_list": [issue_row(f) for f in open_issues][:20],
        "actions_by_priority": {k: prio.get(k, 0) for k in ("High", "Medium", "Low")},
        "follow_up": [issue_row(f) for f in sorted(open_issues, key=lambda f: f.id, reverse=True)][:100],
        "note": f"Due soon = within {DUE_SOON_DAYS} days. Issues and actions from projects you may see.",
    }
