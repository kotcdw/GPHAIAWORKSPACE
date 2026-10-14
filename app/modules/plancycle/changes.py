"""Plan change requests: the only way to change an approved Assurance Plan.

Each request records the reason, the affected plan items (engagements added, changed or cancelled), the
resource impact (hours, budget, quarters, leads) and the coverage impact (universe coverage, high-risk units),
the requester, an independent reviewer and the approver's e-signature. Approval applies the changes, logs each
one under Plan changes and freezes a new numbered version, which is re-distributed to the previous recipients.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.approvalsvc import sign
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import ensure_perm, require_role
from app.core.enums import EngagementStatus, PlanStatus, Role, risk_level, utcnow
from app.core.errors import field_error
from app.core.history import log_record_history
from app.core.permissions import has_perm
from app.core.refs import next_reference
from app.core.schemas import ESignRequest
from app.modules.notifications.service import notify, notify_many
from app.modules.plancycle.models import PlanChangeRequest, PlanCycleEvent, PlanDistribution, PlanVersion
from app.modules.planning.models import AssurancePlan, EntityUnit, PlanChange, PlanEngagement
from app.modules.users.models import User

router = APIRouter(tags=["plan change requests"])
Staff = Depends(require_role(Role.Admin, Role.Auditor))
OPEN = ("Submitted", "Endorsed")
COMMITTEE_DECISIONS = ("Approved", "Rejected", "Deferred")
REVIEWER_FLAG = "marked significant by the reviewer"


class Item(BaseModel):
    action: Literal["add", "change", "cancel"]
    engagement_id: int | None = None
    title: str | None = Field(None, max_length=255)
    entity_unit_id: int | None = None
    planned_quarter: str | None = Field(None, pattern=r"^Q[1-4]$")
    budget_hours: int | None = Field(None, ge=0, le=10000)
    lead_auditor_id: int | None = None
    site_entity_id: int | None = None  # responsible site: Head Office or a port
    rationale: str = Field("", max_length=5000)

    @model_validator(mode="after")
    def _shape(self) -> Item:
        if self.action == "add" and not (self.title or "").strip():
            raise ValueError("a new engagement needs a title")
        if self.action in ("change", "cancel") and self.engagement_id is None:
            raise ValueError("choose the engagement to change or cancel")
        return self


class RequestIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    reason: str = Field(..., min_length=10, max_length=8000)
    items: list[Item] = Field(..., min_length=1, max_length=50)


# ------------------------------------------------------------------ impact


def _units(db: DBSession) -> dict[int, EntityUnit]:
    return {u.id: u for u in db.execute(select(EntityUnit).where(EntityUnit.is_active.is_(True))).scalars()}


def _state(rows: list[dict], units: dict[int, EntityUnit]) -> dict:
    live = [r for r in rows if r["status"] != EngagementStatus.Cancelled.value]
    covered = {r["entity_unit_id"] for r in live if r["entity_unit_id"] in units}
    high = {uid for uid, u in units.items() if risk_level(u.risk_score) == "High"}
    return {
        "engagements": len(live),
        "hours": sum(r["budget_hours"] for r in live),
        "by_quarter": {
            q: sum(r["budget_hours"] for r in live if r["planned_quarter"] == q) for q in ("Q1", "Q2", "Q3", "Q4")
        },
        "by_lead": _by_lead(live),
        "covered_units": len(covered),
        "coverage_pct": round(100 * len(covered) / len(units), 1) if units else 0.0,
        "high_uncovered": sorted(high - covered),
    }


def _by_lead(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        key = str(r["lead_auditor_id"] or 0)
        out[key] = out.get(key, 0) + r["budget_hours"]
    return out


def _rows(plan: AssurancePlan) -> list[dict]:
    return [
        {
            "id": e.id,
            "title": e.title,
            "entity_unit_id": e.entity_unit_id,
            "planned_quarter": e.planned_quarter,
            "budget_hours": e.budget_hours,
            "lead_auditor_id": e.lead_auditor_id,
            "site_entity_id": e.site_entity_id,
            "status": e.status.value,
        }
        for e in plan.engagements
    ]


def _validate(db: DBSession, plan: AssurancePlan, items: list[Item]) -> None:
    engs = {e.id: e for e in plan.engagements}
    seen: set[int] = set()
    for i, it in enumerate(items, 1):
        if it.engagement_id is not None:
            e = engs.get(it.engagement_id)
            if e is None:
                raise field_error("items", f"item {i}: the engagement is not part of this plan")
            if it.engagement_id in seen:
                raise field_error("items", f"item {i}: the engagement appears twice in this request")
            seen.add(it.engagement_id)
            if e.status == EngagementStatus.Cancelled:
                raise field_error("items", f"item {i}: '{e.title}' is already cancelled")
            if it.action == "cancel" and e.status != EngagementStatus.Planned:
                raise field_error("items", f"item {i}: '{e.title}' has started and cannot be cancelled")
        if it.site_entity_id is not None:
            from app.modules.planning.router import check_site

            check_site(db, it.site_entity_id)
        if it.entity_unit_id is not None and db.get(EntityUnit, it.entity_unit_id) is None:
            raise field_error("items", f"item {i}: unknown auditable unit")
        if it.lead_auditor_id is not None:
            lead = db.get(User, it.lead_auditor_id)
            if lead is None or not lead.is_active:
                raise field_error("items", f"item {i}: the lead is not an active user")
        if it.action == "change" and not any(
            getattr(it, f) is not None
            for f in ("title", "entity_unit_id", "planned_quarter", "budget_hours", "lead_auditor_id", "site_entity_id")
        ):
            raise field_error("items", f"item {i}: nothing to change")


def compute_impact(db: DBSession, plan: AssurancePlan, items: list[Item]) -> dict:
    units = _units(db)
    before_rows = _rows(plan)
    after_rows = [dict(r) for r in before_rows]
    by_id = {r["id"]: r for r in after_rows}
    lines = []
    for it in items:
        if it.action == "add":
            row = {
                "id": None,
                "title": it.title.strip(),
                "entity_unit_id": it.entity_unit_id,
                "planned_quarter": it.planned_quarter or "Q1",
                "budget_hours": it.budget_hours or 0,
                "lead_auditor_id": it.lead_auditor_id,
                "site_entity_id": it.site_entity_id,
                "status": EngagementStatus.Planned.value,
            }
            after_rows.append(row)
            lines.append(f"Add '{row['title']}' ({row['planned_quarter']}, {row['budget_hours']}h)")
        elif it.action == "cancel":
            r = by_id[it.engagement_id]
            r["status"] = EngagementStatus.Cancelled.value
            lines.append(f"Cancel '{r['title']}' (-{r['budget_hours']}h)")
        else:
            r = by_id[it.engagement_id]
            parts = []
            for f in (
                "title",
                "entity_unit_id",
                "planned_quarter",
                "budget_hours",
                "lead_auditor_id",
                "site_entity_id",
            ):
                v = getattr(it, f)
                if v is not None and v != r[f]:
                    parts.append(f"{f.replace('_', ' ')} {r[f]} -> {v}")
                    r[f] = v
            lines.append(f"Change '{r['title']}': " + (", ".join(parts) or "no effective change"))
    before, after = _state(before_rows, units), _state(after_rows, units)
    names = {uid: f"{u.location.name} / {u.name}" for uid, u in units.items()}
    leads = {}
    for key in set(before["by_lead"]) | set(after["by_lead"]):
        delta = after["by_lead"].get(key, 0) - before["by_lead"].get(key, 0)
        if delta:
            u = db.get(User, int(key)) if key != "0" else None
            leads[(u.full_name or u.username) if u else "Unassigned"] = delta
    return {
        "changes": lines,
        "resource": {
            "hours_before": before["hours"],
            "hours_after": after["hours"],
            "hours_delta": after["hours"] - before["hours"],
            "budget_hours": plan.total_budget_hours,
            "over_budget": bool(plan.total_budget_hours and after["hours"] > plan.total_budget_hours),
            "by_quarter_before": before["by_quarter"],
            "by_quarter_after": after["by_quarter"],
            "lead_hours_delta": leads,
            "engagements_before": before["engagements"],
            "engagements_after": after["engagements"],
        },
        "coverage": {
            "coverage_before": before["coverage_pct"],
            "coverage_after": after["coverage_pct"],
            "covered_before": before["covered_units"],
            "covered_after": after["covered_units"],
            "high_risk_newly_uncovered": [
                names[u] for u in after["high_uncovered"] if u not in before["high_uncovered"]
            ],
            "high_risk_newly_covered": [names[u] for u in before["high_uncovered"] if u not in after["high_uncovered"]],
            "high_risk_uncovered_after": len(after["high_uncovered"]),
        },
    }


def significance(impact: dict, items: list[Item]) -> list[str]:
    """Why a change counts as significant (IIA GIAS 9.4: significant changes are approved by the board)."""
    from app.core.appconfig import cfg

    reasons = []
    if any(i.action == "add" for i in items):
        reasons.append("adds an engagement to the approved plan")
    if any(i.action == "cancel" for i in items):
        reasons.append("cancels an approved engagement")
    r = impact["resource"]
    pct = abs(r["hours_delta"]) * 100 / max(r["hours_before"], 1)
    if r["hours_delta"] and pct >= cfg("plan_change_significant_hours_pct"):
        reasons.append(f"moves planned hours by {pct:.0f}% (threshold {cfg('plan_change_significant_hours_pct')}%)")
    if r["over_budget"]:
        reasons.append("takes planned hours over the approved budget")
    if impact["coverage"]["high_risk_newly_uncovered"]:
        lost = ", ".join(impact["coverage"]["high_risk_newly_uncovered"])
        reasons.append(f"leaves high-risk units uncovered: {lost}")
    return reasons


def _assess(
    db: DBSession, plan: AssurancePlan, cr: PlanChangeRequest, items: list[Item], flagged: bool = False
) -> None:
    """Recompute the impact and whether the change is significant (the reviewer can also mark it so)."""
    impact = compute_impact(db, plan, items)
    reasons = significance(impact, items)
    previous = json.loads(cr.impact or "{}").get("significance", [])
    if flagged or REVIEWER_FLAG in previous:
        reasons.append(REVIEWER_FLAG)
    impact["significance"] = reasons
    cr.impact = json.dumps(impact)
    cr.significant = bool(reasons)


# ------------------------------------------------------------------ read


class CROut(BaseModel):
    id: int
    cr_ref: str
    plan_id: int
    base_version: int
    title: str
    reason: str
    items: list[dict]
    impact: dict
    status: str
    requested_by: str | None
    requested_at: str
    reviewer: str | None
    reviewed_at: str | None
    review_comment: str | None
    approver: str | None
    decided_at: str | None
    decision_comment: str | None
    new_version: int | None
    significant: bool
    committee_decision: str | None
    committee_meeting_date: str | None
    committee_reference: str | None
    committee_notes: str | None
    can_review: bool
    can_record_committee: bool
    can_approve: bool
    can_withdraw: bool
    can_resubmit: bool


def _name(db: DBSession, uid: int | None) -> str | None:
    u = db.get(User, uid) if uid else None
    return (u.full_name or u.username) if u else None


def _iso(v) -> str | None:  # noqa: ANN001
    return v.isoformat() if v else None


def _out(db: DBSession, cr: PlanChangeRequest, user: User) -> CROut:
    return CROut(
        id=cr.id,
        cr_ref=cr.cr_ref,
        plan_id=cr.plan_id,
        base_version=cr.base_version,
        title=cr.title,
        reason=cr.reason,
        items=json.loads(cr.items),
        impact=json.loads(cr.impact),
        status=cr.status,
        requested_by=_name(db, cr.requested_by),
        requested_at=cr.requested_at.isoformat(),
        reviewer=_name(db, cr.reviewer_id),
        reviewed_at=_iso(cr.reviewed_at),
        review_comment=cr.review_comment,
        approver=_name(db, cr.approver_id),
        decided_at=_iso(cr.decided_at),
        decision_comment=cr.decision_comment,
        new_version=cr.new_version,
        significant=cr.significant,
        committee_decision=cr.committee_decision,
        committee_meeting_date=_iso(cr.committee_meeting_date),
        committee_reference=cr.committee_reference,
        committee_notes=cr.committee_notes,
        can_record_committee=cr.status == "Awaiting Committee" and has_perm(user, "plan.amend"),
        can_review=cr.status == "Submitted"
        and cr.requested_by != user.id
        and has_perm(user, "plan.prepare", "oversight.port", "plan.approve"),
        can_approve=cr.status == "Endorsed" and cr.requested_by != user.id and has_perm(user, "plan.amend"),
        can_withdraw=cr.status in OPEN and cr.requested_by == user.id,
        can_resubmit=cr.status == "Returned" and cr.requested_by == user.id,
    )


def _plan(db: DBSession, plan_id: int) -> AssurancePlan:
    plan = db.get(AssurancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assurance Plan not found")
    return plan


def _approved(plan: AssurancePlan) -> None:
    if plan.status != PlanStatus.Approved or plan.current_version == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Change requests apply to an Audit Committee-approved plan; edit a draft directly",
        )


def _cr(db: DBSession, cr_id: int) -> PlanChangeRequest:
    cr = db.get(PlanChangeRequest, cr_id)
    if cr is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")
    return cr


def _history(db: DBSession, cr: PlanChangeRequest, user: User, text: str, request: Request) -> None:
    log_record_history(
        db,
        record_type="assurance_plan",
        record_id=cr.plan_id,
        user_id=user.id,
        action=f"CHANGE REQUEST {cr.cr_ref} {text}"[:490],
        request=request,
    )


@router.get("/api/assurance-plans/{plan_id}/change-requests", response_model=list[CROut])
def list_requests(plan_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> list[CROut]:
    _plan(db, plan_id)
    rows = db.execute(
        select(PlanChangeRequest).where(PlanChangeRequest.plan_id == plan_id).order_by(PlanChangeRequest.id.desc())
    ).scalars()
    return [_out(db, r, user) for r in rows]


@router.get("/api/plan-change-requests/{cr_id}", response_model=CROut)
def get_request(cr_id: int, db: DBSession = Depends(get_db), user: User = Staff) -> CROut:
    return _out(db, _cr(db, cr_id), user)


@router.post("/api/assurance-plans/{plan_id}/change-requests/impact")
def preview_impact(plan_id: int, payload: RequestIn, db: DBSession = Depends(get_db), user: User = Staff) -> dict:
    plan = _plan(db, plan_id)
    _approved(plan)
    _validate(db, plan, payload.items)
    return compute_impact(db, plan, payload.items)


# ------------------------------------------------------------------ workflow


@router.post(
    "/api/assurance-plans/{plan_id}/change-requests", response_model=CROut, status_code=status.HTTP_201_CREATED
)
def create_request(
    plan_id: int, payload: RequestIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> CROut:
    ensure_perm(user, "plan.prepare", "oversight.port", "audit.memo_approve")
    plan = _plan(db, plan_id)
    _approved(plan)
    _validate(db, plan, payload.items)
    cr = PlanChangeRequest(
        cr_ref=next_reference(db, "PCR"),
        plan_id=plan.id,
        base_version=plan.current_version,
        title=payload.title.strip(),
        reason=payload.reason.strip(),
        items=json.dumps([i.model_dump() for i in payload.items]),
        impact="{}",
        requested_by=user.id,
    )
    _assess(db, plan, cr, payload.items)
    db.add(cr)
    db.flush()
    reviewers = [
        u.id
        for u in db.execute(select(User).where(User.is_active.is_(True))).scalars()
        if u.id != user.id and has_perm(u, "oversight.port", "plan.approve")
    ]
    notify_many(
        db,
        reviewers,
        f"Plan change request {cr.cr_ref} to review",
        f"{cr.title}: {cr.reason[:200]}",
        link_type="assurance_plan",
        link_id=plan.id,
    )
    _history(db, cr, user, f"SUBMITTED: {cr.title}", request)
    log_action(db, user_id=user.id, action=f"PCR_SUBMIT {cr.cr_ref} plan={plan.id}", request=request)
    db.commit()
    return _out(db, cr, user)


class ReviewIn(BaseModel):
    decision: Literal["Endorse", "Return"]
    comment: str = Field("", max_length=4000)
    mark_significant: bool = False


@router.post("/api/plan-change-requests/{cr_id}/review", response_model=CROut)
def review_request(
    cr_id: int, payload: ReviewIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> CROut:
    ensure_perm(user, "plan.prepare", "oversight.port", "plan.approve")
    cr = _cr(db, cr_id)
    if cr.status != "Submitted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"The request is {cr.status}")
    if cr.requested_by == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Segregation of duties: the requester cannot review their own change request",
        )
    if payload.decision == "Return" and len(payload.comment.strip()) < 5:
        raise field_error("comment", "say what needs to change")
    plan = _plan(db, cr.plan_id)
    _assess(db, plan, cr, [Item(**i) for i in json.loads(cr.items)], flagged=payload.mark_significant)  # refresh
    cr.reviewer_id = user.id
    cr.reviewed_at = utcnow()
    cr.review_comment = payload.comment.strip() or None
    cr.status = "Endorsed" if payload.decision == "Endorse" else "Returned"
    if cr.status == "Endorsed":
        approvers = [
            u.id
            for u in db.execute(select(User).where(User.is_active.is_(True))).scalars()
            if u.id not in (cr.requested_by, user.id) and has_perm(u, "plan.amend")
        ]
        notify_many(
            db,
            approvers,
            f"Plan change request {cr.cr_ref} awaits approval",
            cr.title,
            link_type="assurance_plan",
            link_id=cr.plan_id,
        )
    else:
        notify(
            db,
            cr.requested_by,
            f"Plan change request {cr.cr_ref} returned",
            cr.review_comment or "",
            link_type="assurance_plan",
            link_id=cr.plan_id,
        )
    _history(db, cr, user, cr.status.upper(), request)
    db.commit()
    return _out(db, cr, user)


@router.post("/api/plan-change-requests/{cr_id}/approve", response_model=CROut)
def approve_request(
    cr_id: int, payload: ESignRequest, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> CROut:
    """GM Audit's e-signature: Approve applies the changes and freezes a new version; Reject closes the request."""
    ensure_perm(user, "plan.amend")
    cr = _cr(db, cr_id)
    if cr.status != "Endorsed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The change request must be reviewed and endorsed before approval",
        )
    plan = _plan(db, cr.plan_id)
    _approved(plan)
    items = [Item(**i) for i in json.loads(cr.items)]
    if payload.decision.value == "Approve":
        if cr.base_version != plan.current_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The plan moved from version {cr.base_version} to {plan.current_version}; "
                "raise a new change request against the current version",
            )
        _validate(db, plan, items)

    def _on_approve(_: DBSession) -> None:
        if cr.significant:  # GIAS 9.4: the Audit Committee approves significant changes
            cr.status = "Awaiting Committee"
        else:
            _apply(db, plan, cr, items, user)

    sign(
        db,
        record_type="plan_change_request",
        record_id=cr.id,
        user=user,
        password=payload.password,
        decision=payload.decision.value,
        comment=payload.comment,
        request=request,
        on_approve=_on_approve,
        preparer_id=cr.requested_by,
    )
    cr.approver_id = user.id
    cr.decided_at = utcnow()
    cr.decision_comment = payload.comment or None
    if payload.decision.value == "Reject":
        cr.status = "Rejected"
        notify(
            db,
            cr.requested_by,
            f"Plan change request {cr.cr_ref} rejected",
            payload.comment or "",
            link_type="assurance_plan",
            link_id=plan.id,
        )
    _history(db, cr, user, cr.status.upper() + (f" -> version {cr.new_version}" if cr.new_version else ""), request)
    log_action(db, user_id=user.id, action=f"PCR_{cr.status.upper()} {cr.cr_ref}", request=request)
    db.commit()
    return _out(db, cr, user)


def _apply(db: DBSession, plan: AssurancePlan, cr: PlanChangeRequest, items: list[Item], user: User) -> None:
    from app.modules.plancycle.router import _snapshot

    why = f"{cr.cr_ref}: {cr.reason}"
    for it in items:
        if it.action == "add":
            eng = PlanEngagement(
                plan_id=plan.id,
                title=it.title.strip(),
                entity_unit_id=it.entity_unit_id,
                planned_quarter=it.planned_quarter or "Q1",
                budget_hours=it.budget_hours or 0,
                lead_auditor_id=it.lead_auditor_id,
                site_entity_id=it.site_entity_id,
                rationale=it.rationale,
                created_by=user.id,
            )
            db.add(eng)
            db.flush()
            db.add(
                PlanChange(
                    plan_id=plan.id,
                    engagement_id=eng.id,
                    change_type="Added",
                    reason=why,
                    description=f"{eng.title} ({eng.planned_quarter}, {eng.budget_hours}h) added",
                    changed_by=user.id,
                )
            )
            continue
        eng = db.get(PlanEngagement, it.engagement_id)
        if it.action == "cancel":
            eng.status = EngagementStatus.Cancelled
            db.add(
                PlanChange(
                    plan_id=plan.id,
                    engagement_id=eng.id,
                    change_type="Cancelled",
                    reason=why,
                    description=f"{eng.title} ({eng.planned_quarter}, {eng.budget_hours}h) cancelled",
                    changed_by=user.id,
                )
            )
            continue
        parts = []
        for f in ("title", "entity_unit_id", "planned_quarter", "budget_hours", "lead_auditor_id", "site_entity_id"):
            v = getattr(it, f)
            if v is not None and v != getattr(eng, f):
                parts.append(f"{f.replace('_', ' ')} {getattr(eng, f)} -> {v}")
                setattr(eng, f, v)
        if parts:
            db.add(
                PlanChange(
                    plan_id=plan.id,
                    engagement_id=eng.id,
                    change_type="Changed",
                    reason=why,
                    description=f"{eng.title}: {', '.join(parts)}",
                    changed_by=user.id,
                )
            )
    db.flush()
    db.refresh(plan)
    plan.current_version += 1
    db.add(
        PlanVersion(
            plan_id=plan.id,
            version=plan.current_version,
            snapshot=json.dumps(_snapshot(plan)),
            decision=f"Amended by {cr.cr_ref}"
            + (f" (Audit Committee {cr.committee_reference})" if cr.committee_reference else " (CAE, minor change)"),
            committee_reference=cr.committee_reference or plan.committee_reference,
            approved_at=utcnow(),
            created_by=user.id,
        )
    )
    cr.status = "Approved"
    cr.new_version = plan.current_version
    db.add(
        PlanCycleEvent(
            plan_id=plan.id,
            stage="approved",
            action=f"Version {plan.current_version} frozen",
            decision=f"Amended by {cr.cr_ref}",
            notes=cr.reason,
            user_id=user.id,
        )
    )
    # Controlled re-distribution: everyone who held the previous version receives the new one.
    previous = {
        d.user_id: d.site_entity_id
        for d in db.execute(
            select(PlanDistribution).where(
                PlanDistribution.plan_id == plan.id, PlanDistribution.version == cr.base_version
            )
        ).scalars()
    }
    for uid, site_id in previous.items():
        db.add(
            PlanDistribution(
                plan_id=plan.id,
                version=plan.current_version,
                user_id=uid,
                site_entity_id=site_id,
                sent_by=user.id,
                note=f"Amended by {cr.cr_ref}: {cr.title}",
            )
        )
    notify_many(
        db,
        [*previous, cr.requested_by],
        f"Assurance Plan FY{plan.fiscal_year} amended - version {plan.current_version}",
        f"{cr.cr_ref} {cr.title} was approved. Please acknowledge the new version.",
        link_type="assurance_plan",
        link_id=plan.id,
    )


@router.post("/api/plan-change-requests/{cr_id}/withdraw", response_model=CROut)
def withdraw_request(cr_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Staff) -> CROut:
    cr = _cr(db, cr_id)
    if cr.requested_by != user.id or cr.status not in OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only the requester can withdraw an open request"
        )
    cr.status = "Withdrawn"
    _history(db, cr, user, "WITHDRAWN", request)
    db.commit()
    return _out(db, cr, user)


@router.post("/api/plan-change-requests/{cr_id}/resubmit", response_model=CROut)
def resubmit_request(
    cr_id: int, payload: RequestIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> CROut:
    """Rework a returned request and send it back for review."""
    cr = _cr(db, cr_id)
    if cr.requested_by != user.id or cr.status != "Returned":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a returned request can be resubmitted")
    plan = _plan(db, cr.plan_id)
    _approved(plan)
    _validate(db, plan, payload.items)
    cr.title, cr.reason = payload.title.strip(), payload.reason.strip()
    cr.items = json.dumps([i.model_dump() for i in payload.items])
    _assess(db, plan, cr, payload.items)
    cr.base_version = plan.current_version
    cr.status = "Submitted"
    cr.reviewer_id = cr.reviewed_at = None
    _history(db, cr, user, "RESUBMITTED", request)
    db.commit()
    return _out(db, cr, user)


class CommitteeIn(BaseModel):
    decision: Literal["Approved", "Rejected", "Deferred"]
    meeting_date: datetime
    reference: str = Field(..., min_length=2, max_length=100)
    notes: str = Field("", max_length=8000)


@router.post("/api/plan-change-requests/{cr_id}/committee-decision", response_model=CROut)
def committee_decision(
    cr_id: int, payload: CommitteeIn, request: Request, db: DBSession = Depends(get_db), user: User = Staff
) -> CROut:
    """Record the Audit Committee's decision on a significant change (IIA GIAS 9.4); approval applies it."""
    ensure_perm(user, "plan.amend")
    cr = _cr(db, cr_id)
    if cr.status != "Awaiting Committee":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The request is not awaiting the Committee")
    meeting = payload.meeting_date.replace(tzinfo=None)
    if meeting > utcnow():
        raise field_error("meeting_date", "cannot be in the future")
    if cr.decided_at and meeting.date() < cr.decided_at.date():
        raise field_error("meeting_date", "is before the CAE approved the change")
    plan = _plan(db, cr.plan_id)
    cr.committee_decision = payload.decision
    cr.committee_meeting_date = meeting
    cr.committee_reference = payload.reference.strip()
    cr.committee_notes = payload.notes.strip() or None
    cr.committee_recorded_by = user.id
    if payload.decision == "Approved":
        _approved(plan)
        if cr.base_version != plan.current_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The plan moved from version {cr.base_version} to {plan.current_version}; "
                "raise a new change request against the current version",
            )
        items = [Item(**i) for i in json.loads(cr.items)]
        _validate(db, plan, items)
        _apply(db, plan, cr, items, user)
    elif payload.decision == "Rejected":
        cr.status = "Rejected"
        notify(
            db,
            cr.requested_by,
            f"Plan change request {cr.cr_ref} rejected by the Audit Committee",
            cr.committee_notes or cr.committee_reference,
            link_type="assurance_plan",
            link_id=plan.id,
        )
    _history(
        db,
        cr,
        user,
        f"AUDIT COMMITTEE {payload.decision.upper()} (ref {cr.committee_reference})"
        + (f" -> version {cr.new_version}" if cr.new_version else ""),
        request,
    )
    log_action(db, user_id=user.id, action=f"PCR_COMMITTEE_{payload.decision.upper()} {cr.cr_ref}", request=request)
    db.commit()
    return _out(db, cr, user)
