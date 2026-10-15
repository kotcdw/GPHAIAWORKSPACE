"""Issue Tracker (HighBond Results > Issues): one register of findings across every audit the user may read.

Columns as in HighBond: Issue | Status | Severity | Owner | Remediation Deadline | Issue Type | Published | Sign-offs,
plus the project (audit). Filters: search, status, severity, owner, issue type, audit, published, overdue. The KPI
tab counts issues by project, by issue type and by severity with the same filters.

Publishing releases a finding to the auditee (unpublished findings are visible to audit staff only) and notifies its
owner. Sending the draft report to management publishes the audit's findings. Review sign-offs follow the working
paper review chain (Configuration > Audit workflow); the preparer never signs.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core import review_chain
from app.core.access import ensure_can_view, staff_audit_scope
from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm, require_role
from app.core.enums import AuditStatus, FindingStatus, ReviewLevel, RiskRating, Role, utcnow
from app.core.history import log_record_history
from app.core.paging import Page, PageParams, matches, page_params, paginate_rows
from app.core.permissions import has_perm
from app.domains.audit.audits.models import Audit, Finding
from app.platform.notifications.service import notify, user_id_by_email
from app.platform.users.models import User

router = APIRouter(tags=["issue tracker"])
StaffUser = Depends(require_role(Role.Admin, Role.Auditor))


def publish(db: DBSession, finding: Finding, user: User, request: Request | None = None) -> bool:
    """Release a finding to the auditee and notify its owner. Returns False when it was already published."""
    if finding.published:
        return False
    finding.published, finding.published_at, finding.published_by = True, utcnow(), user.id
    owner = user_id_by_email(db, finding.assigned_owner_email)
    if owner:
        notify(db, owner, f"Audit issue for your response: {finding.title}",
               "Internal Audit has published an issue assigned to you. Please record the management response "
               "(action plan, responsible officer and target date).", link_type="finding", link_id=finding.id)
    log_record_history(db, record_type="audit", record_id=finding.audit_id, user_id=user.id,
                       action=f"FINDING PUBLISHED #{finding.id} {finding.title}", request=request)
    return True


def publish_audit(db: DBSession, audit_id: int, user: User, request: Request | None = None) -> int:
    rows = db.execute(select(Finding).where(Finding.audit_id == audit_id, Finding.published.is_(False))).scalars()
    return sum(1 for f in rows if publish(db, f, user, request))


def signoffs(f: Finding, names: dict[int, str]) -> list[dict]:
    """HighBond sign-off dots: the preparer, then each configured review level (done or pending)."""
    dots = [{"label": "Prepared", "done": True, "by": names.get(f.created_by), "at": f.created_at.isoformat()}]
    trail = review_chain.trail(f.review_trail)
    levels = review_chain.chain("workpaper")
    if not levels:
        dots.append({"label": "Reviewed", "done": bool(f.reviewed_at), "by": trail[0]["name"] if trail else None,
                     "at": f.reviewed_at.isoformat() if f.reviewed_at else None})
        return dots
    signed = {t["level"]: t for t in trail}
    for lvl in levels:
        t = signed.get(review_chain.label(lvl))
        dots.append({"label": review_chain.label(lvl), "done": t is not None, "by": t["name"] if t else None,
                     "at": t["at"] if t else None})
    return dots


def _row(f: Finding, audit: Audit, owners: dict[str, str], names: dict[int, str]) -> dict:
    now = utcnow()
    deadline = f.target_date
    return {
        "id": f.id, "ref": f"ISS-{f.id:04d}", "title": f.title, "status": f.status.value,
        "severity": f.risk_rating.value, "owner_email": f.assigned_owner_email,
        "owner": owners.get((f.assigned_owner_email or "").lower()) or f.assigned_owner_email,
        "remediation_deadline": deadline.date().isoformat() if deadline else None,
        "overdue": bool(deadline and deadline < now and f.status != FindingStatus.Closed),
        "issue_type": f.issue_type, "published": f.published,
        "published_at": f.published_at.isoformat() if f.published_at else None,
        "signoffs": signoffs(f, names), "reviewed": bool(f.reviewed_at),
        "review_stage": review_chain.label(f.review_stage) if f.review_stage else None,
        "audit_id": audit.id, "audit": audit.title, "audit_status": audit.status.value,
        "source": "Procedure" if f.procedure_id else ("Control test" if f.test_id else "Manual"),
        "created_at": f.created_at.isoformat(), "updated_at": f.updated_at.isoformat(),
    }


def _rows(db: DBSession, user: User, params: PageParams | None, *, status_f: str | None, severity: str | None,
          owner: str | None, issue_type: str | None, audit_id: int | None, published: bool | None,
          overdue: bool, entity_id: int | None = None) -> list[dict]:
    stmt = select(Finding, Audit).join(Audit, Audit.id == Finding.audit_id)
    scope = staff_audit_scope(db, user) if user.role == Role.Auditor else None
    if scope is not None:
        stmt = stmt.where(Finding.audit_id.in_(scope or {0}))
    if status_f:
        stmt = stmt.where(Finding.status == FindingStatus(status_f))
    if severity:
        stmt = stmt.where(Finding.risk_rating == RiskRating(severity))
    if owner:
        stmt = stmt.where(Finding.assigned_owner_email == owner)
    if issue_type:
        stmt = stmt.where(Finding.issue_type == issue_type) if issue_type != "(none)" else \
            stmt.where(Finding.issue_type.is_(None))
    if audit_id:
        stmt = stmt.where(Finding.audit_id == audit_id)
    if entity_id:  # issues inherit the auditable entities of their audit
        from app.domains.assurance.universe.models import AuditEntity

        covered = select(AuditEntity.audit_id).where(AuditEntity.entity_id == entity_id)
        stmt = stmt.where(Finding.audit_id.in_(covered) | (Audit.entity_unit_id == entity_id))
    if published is not None:
        stmt = stmt.where(Finding.published.is_(published))
    pairs = db.execute(stmt).all()
    emails = {(f.assigned_owner_email or "").lower() for f, _ in pairs} - {""}
    owners = {}
    if emails:
        for u in db.execute(select(User).where(User.email.in_(emails))).scalars():
            owners[u.email.lower()] = u.full_name or u.username
    ids = {f.created_by for f, _ in pairs} - {None}
    names = {u.id: u.full_name or u.username for u in db.execute(select(User).where(User.id.in_(ids))).scalars()} \
        if ids else {}
    rows = [_row(f, a, owners, names) for f, a in pairs]
    q = params.q if params else None
    return [r for r in rows if (not overdue or r["overdue"])
            and matches(q, r["ref"], r["title"], r["owner"], r["audit"], r["issue_type"], r["status"])]


@router.get("/api/findings/issue-types")
def issue_types(_: User = StaffUser) -> list[str]:
    """The configured issue types (Configuration > Audit methodology)."""
    return list(cfg("finding_issue_types") or [])


def issue_filters(
    status_f: str | None = Query(None, alias="status", pattern="^(Open|Remediating|Closed)$"),
    severity: str | None = Query(None, pattern="^(Low|Medium|High)$"),
    owner: str | None = Query(None, max_length=255),
    issue_type: str | None = Query(None, max_length=60),
    audit_id: int | None = None,
    published: bool | None = None,
    overdue: bool = False,
    entity_id: int | None = None,
) -> dict:
    return {"status_f": status_f, "severity": severity, "owner": owner, "issue_type": issue_type,
            "audit_id": audit_id, "published": published, "overdue": overdue, "entity_id": entity_id}


@router.get("/api/findings/register", response_model=Page[dict])
def issue_register(db: DBSession = Depends(get_db), user: User = StaffUser, params: PageParams = Depends(page_params),
                   filters: dict = Depends(issue_filters)) -> Page[dict]:
    rows = _rows(db, user, params, **filters)
    sortable = {k: (lambda r, k=k: r[k]) for k in ("id", "title", "status", "owner", "remediation_deadline",
                                                   "issue_type", "audit", "updated_at")}
    sortable["severity"] = lambda r: {"High": 3, "Medium": 2, "Low": 1}[r["severity"]]
    sortable["published"] = lambda r: int(r["published"])
    page, total, sort = paginate_rows(rows, params, sortable, "-updated_at")
    if page:
        from app.domains.issues.capa.closure import remediation_summary

        found = {f.id: f for f in db.execute(select(Finding).where(Finding.id.in_([r["id"] for r in page])))
                 .scalars()}
        for r in page:
            r["remediation"] = remediation_summary(db, found[r["id"]])["state"]
    return Page(items=page, total=total, page=params.page, page_size=params.page_size, sort=sort)


@router.get("/api/findings/register/summary")
def issue_summary(db: DBSession = Depends(get_db), user: User = StaffUser, q: str | None = Query(None, max_length=120),
                  filters: dict = Depends(issue_filters)) -> dict:
    """KPIs for the donuts (By Issue Type, By Severity) and the KPI tab (Issue Count by Project)."""
    params = PageParams(page=1, page_size=1, sort=None, q=(q or "").strip() or None)
    rows = _rows(db, user, params, **filters)
    types = list(cfg("finding_issue_types") or [])
    by_type = Counter(r["issue_type"] or "(none)" for r in rows)
    projects = Counter((r["audit_id"], r["audit"]) for r in rows)
    owners = sorted({(r["owner_email"], r["owner"]) for r in rows if r["owner_email"]}, key=lambda x: x[1].lower())
    return {
        "total": len(rows), "open": sum(1 for r in rows if r["status"] != "Closed"),
        "overdue": sum(1 for r in rows if r["overdue"]), "unpublished": sum(1 for r in rows if not r["published"]),
        "by_issue_type": [{"label": t, "count": by_type.get(t, 0)} for t in types]
        + [{"label": t, "count": n} for t, n in by_type.items() if t not in types],
        "by_severity": [{"label": s, "count": sum(1 for r in rows if r["severity"] == s)}
                        for s in ("High", "Medium", "Low")],
        "by_status": [{"label": s, "count": sum(1 for r in rows if r["status"] == s)}
                      for s in ("Open", "Remediating", "Closed")],
        "by_project": [{"audit_id": aid, "label": title, "count": n} for (aid, title), n in projects.most_common()],
        "issue_types": types, "owners": [{"email": e, "name": n} for e, n in owners],
    }


# ---------------------------------------------------------------- per-finding actions


def _finding(db: DBSession, finding_id: int, user: User) -> tuple[Finding, Audit]:
    f = db.get(Finding, finding_id)
    ensure_can_view(db, user, "finding", f)
    return f, db.get(Audit, f.audit_id)


@router.post("/api/findings/{finding_id}/publish")
def publish_finding(finding_id: int, request: Request, db: DBSession = Depends(get_db),
                    user: User = StaffUser) -> dict:
    ensure_perm(user, "audit.findings")
    f, audit = _finding(db, finding_id, user)
    if audit.status == AuditStatus.Closed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The audit is closed")
    if not publish(db, f, user, request):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The issue is already published")
    log_action(db, user_id=user.id, action=f"FINDING_PUBLISH id={f.id}", request=request)
    db.commit()
    return {"id": f.id, "published": True, "published_at": f.published_at.isoformat()}


@router.post("/api/findings/{finding_id}/review")
def review_finding(finding_id: int, request: Request, db: DBSession = Depends(get_db),
                   user: User = StaffUser) -> dict:
    """Reviewer sign-off on an issue, through the working paper review chain (never by its preparer)."""
    f, audit = _finding(db, finding_id, user)
    if not has_perm(user, "review.workpapers"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role does not sign off audit work")
    if f.created_by == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The preparer cannot review their own issue")
    if f.reviewed_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already signed off")
    levels = review_chain.chain("workpaper")
    if not levels:
        f.review_trail = review_chain.sign(f.review_trail, user, user.review_level or ReviewLevel.UnitHead)
        f.reviewed_at = utcnow()
        what = "REVIEWED"
    else:
        try:
            stage = ReviewLevel(f.review_stage) if f.review_stage else levels[0]
        except ValueError:
            stage = levels[0]
        allowed, why = review_chain.may_sign(user, stage, f.review_trail, f.created_by)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=why)
        f.review_trail = review_chain.sign(f.review_trail, user, stage)
        following = review_chain.next_stage("workpaper", stage)
        if following is None:
            f.review_stage, f.reviewed_at = None, utcnow()
            what = f"REVIEWED ({review_chain.label(stage)}, final)"
        else:
            f.review_stage = following.value
            what = f"SIGNED OFF by {review_chain.label(stage)}; next {review_chain.label(following)}"
    log_record_history(db, record_type="audit", record_id=audit.id, user_id=user.id,
                       action=f"ISSUE #{f.id} {what}", request=request)
    log_action(db, user_id=user.id, action=f"FINDING_REVIEW id={f.id}", request=request)
    db.commit()
    names = {f.created_by: (db.get(User, f.created_by).full_name if f.created_by and db.get(User, f.created_by)
                            else None)}
    return {"id": f.id, "reviewed": bool(f.reviewed_at), "signoffs": signoffs(f, names),
            "review_stage": review_chain.label(f.review_stage) if f.review_stage else None}
