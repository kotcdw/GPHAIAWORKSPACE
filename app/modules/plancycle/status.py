"""Keeps ``AssurancePlan.lifecycle_status`` in step with the plan, its cycle stage and its engagements.

Draft -> In Review -> Submitted -> Approved -> Distributed -> In Execution -> Closed -> Archived, with
Returned (sent back by the internal reviewer or the Audit Committee) and Revised (an approved version
reopened for revision). The status is recomputed before every flush that touches a plan or an engagement,
so no endpoint can leave it stale.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.enums import EngagementStatus, PlanLifecycle, PlanStatus
from app.modules.planning.models import AssurancePlan, PlanEngagement


def compute(plan: AssurancePlan) -> str:
    if plan.archived_at is not None:
        return PlanLifecycle.Archived.value
    status = plan.status or PlanStatus.Draft  # defaults are applied at INSERT, after this runs
    if status == PlanStatus.Closed:
        return PlanLifecycle.Closed.value
    stage = plan.cycle_stage or "preparation"
    if stage == "internal_review":
        return PlanLifecycle.InReview.value
    if stage in ("submission", "committee"):
        return PlanLifecycle.Submitted.value
    if status == PlanStatus.Draft:
        if plan.lifecycle_status == PlanLifecycle.Returned.value:
            return PlanLifecycle.Returned.value  # stays Returned until it is resubmitted
        return PlanLifecycle.Revised.value if (plan.current_version or 0) > 0 else PlanLifecycle.Draft.value
    if stage == "execution":
        started = any(e.status == EngagementStatus.Started for e in plan.engagements)
        return PlanLifecycle.InExecution.value if started else PlanLifecycle.Distributed.value
    return PlanLifecycle.Approved.value


def mark_returned(plan: AssurancePlan) -> None:
    plan.lifecycle_status = PlanLifecycle.Returned.value


@event.listens_for(Session, "before_flush")
def _sync_lifecycle(session: Session, flush_context, instances) -> None:  # noqa: ANN001
    plans: set[AssurancePlan] = set()
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, AssurancePlan):
            plans.add(obj)
        elif isinstance(obj, PlanEngagement) and obj.plan is not None:
            plans.add(obj.plan)
    for plan in plans:
        value = compute(plan)
        if plan.lifecycle_status != value:
            plan.lifecycle_status = value
