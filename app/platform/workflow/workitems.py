"""Work items: every hand-off is a task in someone's inbox, with a working-day due date.

Work items are *derived* from the records: who must act next on a procedure, a test, an evidence request, a review
note, a working paper, a report, a finding or a remediation action follows from that record's status, assignee,
next reviewer and deadlines. ``sync_records`` re-derives them whenever a record changes, so the inbox never drifts
from the work; ``full_resync`` rebuilds them all (at start-up and nightly).

The SLA clock (``run_sla_clock``) warns the assignee before the due date and, once it has passed, notifies them
again and escalates to the audit's Lead auditor. Remediation actions keep their own escalation ladder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import utcnow

logger = logging.getLogger("gpha")

# kind -> (label shown in the inbox, SLA policy key, group used for the inbox filters)
KINDS: dict[str, tuple[str, str, str]] = {
    "prepare": ("Prepare and sign off", "prepare", "prepare"),
    "review": ("Review and sign off", "review", "review"),
    "review_paper": ("Review working paper", "review", "review"),
    "answer_note": ("Answer review note", "note_answer", "respond"),
    "clear_note": ("Clear review note", "note_clear", "review"),
    "provide_evidence": ("Provide requested evidence", "evidence_provide", "respond"),
    "accept_evidence": ("Check submitted evidence", "evidence_accept", "review"),
    "review_report": ("Review audit report", "report_review", "review"),
    "approve_report": ("Approve and issue report", "report_approve", "review"),
    "respond_finding": ("Respond to finding", "client_response", "respond"),
    "implement_action": ("Implement remediation action", "implement", "action"),
    "validate_action": ("Validate remediation action", "validate", "action"),
}

# key -> (label, working days, warn before (working days)). Defaults agreed for Phase 1.
SLA_DEFAULTS: dict[str, tuple[str, int, int]] = {
    "prepare": ("Prepare a procedure or test", 5, 1),
    "review": ("Review and sign off fieldwork", 3, 1),
    "note_answer": ("Answer a review note", 3, 1),
    "note_clear": ("Clear an answered review note", 3, 1),
    "evidence_provide": ("Provide requested evidence (when the request has no due date)", 5, 1),
    "evidence_accept": ("Check submitted evidence", 3, 1),
    "report_review": ("Review a report at a review-chain level", 3, 1),
    "report_approve": ("CAE approval of a report", 3, 1),
    "client_response": ("Client response to a finding (when the report has no deadline)", 10, 2),
    "implement": ("Implement a remediation action (when it has no target date)", 30, 10),
    "validate": ("Validate an implemented remediation action", 10, 2),
}

# Record type -> link type understood by the web app's openLink().
LINK = {"audit_report": "audit_report", "finding": "finding", "capa": "capa"}


@dataclass(frozen=True)
class Want:
    kind: str
    assignee_id: int
    title: str
    audit_id: int | None
    due: datetime | None = None  # from the record (target date, deadline); else the SLA policy


# ---------------------------------------------------------------- SLA policies

def ensure_policies(db: DBSession) -> None:
    from app.platform.workflow.models import SlaPolicy

    have = set(db.execute(select(SlaPolicy.key)).scalars())
    for key, (label, days, warn) in SLA_DEFAULTS.items():
        if key not in have:
            db.add(SlaPolicy(key=key, label=label, working_days=days, warn_before_days=warn))
    db.flush()


def policy(db: DBSession, key: str):  # noqa: ANN201
    from app.platform.workflow.models import SlaPolicy

    row = db.get(SlaPolicy, key)
    if row is None and key in SLA_DEFAULTS:
        label, days, warn = SLA_DEFAULTS[key]
        row = SlaPolicy(key=key, label=label, working_days=days, warn_before_days=warn)
        db.add(row)
        db.flush()
    return row


def due_for(db: DBSession, sla_key: str, start: datetime) -> datetime | None:
    from app.core.workdays import add_working_days

    pol = policy(db, sla_key)
    if pol is None or not pol.active:
        return None
    return add_working_days(start, pol.working_days)


# ---------------------------------------------------------------- record helpers

def _get(db: DBSession, model, rid: int):  # noqa: ANN001, ANN202
    try:
        return db.get(model, rid)
    except Exception:  # noqa: BLE001 - table missing in an old schema
        return None


def audit_id_for(db: DBSession, rt: str, obj) -> int | None:  # noqa: ANN001, C901, PLR0911
    from app.domains.audit.rcm.models import Control, ControlTest, Objective

    try:
        if rt == "audit":
            return obj.id
        if rt in ("finding", "evidence_request", "review_note", "audit_report", "working_paper", "rcm"):
            return obj.audit_id
        if rt in ("procedure", "narrative"):
            o = db.get(Objective, obj.objective_id)
            return o.audit_id if o else None
        if rt == "test_plan":
            o = db.get(Objective, obj.objective_id)
            return o.audit_id if o else None
        if rt == "control_test":
            c = db.get(Control, obj.control_id)
            o = db.get(Objective, c.objective_id) if c else None
            return o.audit_id if o else None
        if rt == "capa":
            if obj.source_type == "finding" and obj.source_id:
                from app.domains.audit.audits.models import Finding

                f = db.get(Finding, obj.source_id)
                return f.audit_id if f else None
            return None
        if isinstance(obj, ControlTest):  # pragma: no cover - defensive
            return None
    except Exception:  # noqa: BLE001
        return None
    return None


def _lead_ids(db: DBSession, audit_id: int | None) -> list[int]:
    from app.domains.audit.audits.models import Audit, AuditTeamMember

    if audit_id is None:
        return []
    leads = list(db.execute(select(AuditTeamMember.user_id).where(AuditTeamMember.audit_id == audit_id,
                                                                  AuditTeamMember.team_role == "Lead auditor"))
                 .scalars())
    if leads:
        return leads
    audit = db.get(Audit, audit_id)
    return [audit.created_by] if audit is not None and audit.created_by else []


def _user_by_email(db: DBSession, email: str | None) -> int | None:
    from app.platform.notifications.service import user_id_by_email

    return user_id_by_email(db, email) if email else None


def _active(db: DBSession, user_id: int | None) -> bool:
    from app.platform.users.models import User

    if not user_id:
        return False
    u = db.get(User, user_id)
    return u is not None and u.is_active


def _signoff_page(db: DBSession, rt: str, rid: int):  # noqa: ANN202
    from app.domains.audit.audits.models import Finding
    from app.domains.audit.rcm.models import Control, ControlTest, Narrative, Objective, Procedure

    model = {"procedure": Procedure, "control_test": ControlTest, "test_plan": Control, "narrative": Narrative,
             "rcm": Objective, "finding": Finding}.get(rt)
    return _get(db, model, rid) if model else None


SIGNOFF_TARGET = {"procedure": "procedure", "control_test": "test", "test_plan": "test_plan",
                  "narrative": "narrative", "rcm": "rcm", "finding": "finding"}


def _title(rt: str, obj) -> str:  # noqa: ANN001
    ref = getattr(obj, "ref", None) or getattr(obj, "capa_ref", None) or getattr(obj, "report_ref", None) \
        or getattr(obj, "request_ref", None) or getattr(obj, "wp_ref", None)
    name = getattr(obj, "title", None) or ""
    if rt == "control_test":
        name = f"Control test ({obj.test_type.value})" if getattr(obj, "test_type", None) else "Control test"
    if rt == "review_note":
        name = f"{obj.target_label or 'Review note'}: {(obj.note or '')[:120]}"
    text = f"{ref} · {name}" if ref and name else (ref or name or rt.replace("_", " ").title())
    return text[:255]


# ---------------------------------------------------------------- what should be open for a record

def _review_from_next_reviewer(db: DBSession, rt: str, rid: int, obj, audit_id: int | None) -> list[Want]:  # noqa: ANN001
    from app.domains.audit.rcm.models import SignoffReviewer

    target = SIGNOFF_TARGET.get(rt)
    if target is None:
        return []
    nxt = _get(db, SignoffReviewer, (target, rid))
    if nxt is None or not _active(db, nxt.reviewer_id):
        return []
    return [Want("review", nxt.reviewer_id, _title(rt, obj), audit_id)]


def desired(db: DBSession, rt: str, rid: int) -> tuple[Any, list[Want]]:  # noqa: C901, PLR0911, PLR0912, PLR0915
    """The record (or None if it no longer exists) and the work items that should be open for it."""
    from app.core.enums import CapaStatus, FindingStatus, ReportStatus, ReviewLevel, TestStatus

    if rt in ("procedure", "control_test", "test_plan", "narrative", "rcm"):
        obj = _signoff_page(db, rt, rid)
        if obj is None:
            return None, []
        aid = audit_id_for(db, rt, obj)
        wants: list[Want] = []
        status = getattr(obj, "status", None)
        status_v = status.value if hasattr(status, "value") else status
        done = status_v in ("Reviewed",)
        if rt == "procedure" and status_v in ("Not Started", "In Progress") and _active(db, obj.assigned_to):
            wants.append(Want("prepare", obj.assigned_to, _title(rt, obj), aid, obj.due_date))
        if rt == "control_test" and status in (TestStatus.NotStarted, TestStatus.InProgress) \
                and _active(db, obj.assigned_to):
            wants.append(Want("prepare", obj.assigned_to, _title(rt, obj), aid))
        if not done:
            wants += _review_from_next_reviewer(db, rt, rid, obj, aid)
        return obj, wants

    if rt == "finding":
        from app.domains.audit.audits.models import Finding
        from app.domains.audit.reports.models import AuditReport

        f = _get(db, Finding, rid)
        if f is None or getattr(f, "is_deleted", False):
            return None, []
        wants = []
        if f.reviewed_at is None:
            wants += _review_from_next_reviewer(db, rt, rid, f, f.audit_id)
        if f.published and f.status == FindingStatus.Open and not (f.management_response or "").strip():
            report = db.execute(select(AuditReport).where(AuditReport.audit_id == f.audit_id)).scalar_one_or_none()
            owner = _user_by_email(db, f.assigned_owner_email)
            if report is not None and report.status == ReportStatus.ManagementReview and _active(db, owner):
                wants.append(Want("respond_finding", owner, _title(rt, f), f.audit_id, report.response_due_at))
        return f, wants

    if rt == "evidence_request":
        from app.domains.audit.evidence.models import EvidenceRequest

        r = _get(db, EvidenceRequest, rid)
        if r is None:
            return None, []
        if r.status in ("Requested", "Returned") and _active(db, r.assignee_id):
            return r, [Want("provide_evidence", r.assignee_id, _title(rt, r), r.audit_id, r.due_date)]
        if r.status == "Submitted" and _active(db, r.requested_by):
            return r, [Want("accept_evidence", r.requested_by, _title(rt, r), r.audit_id)]
        return r, []

    if rt == "review_note":
        from app.domains.audit.methodology.models import ReviewNote

        n = _get(db, ReviewNote, rid)
        if n is None:
            return None, []
        if n.status == "Open":
            responders = _note_responders(db, n)
            return n, [Want("answer_note", u, _title(rt, n), n.audit_id) for u in responders]
        if n.status == "Responded" and _active(db, n.raised_by):
            return n, [Want("clear_note", n.raised_by, _title(rt, n), n.audit_id)]
        return n, []

    if rt == "working_paper":
        from app.core import review_chain
        from app.domains.audit.audits.models import WorkingPaper

        wp = _get(db, WorkingPaper, rid)
        if wp is None or wp.is_deleted:
            return None, []
        if wp.reviewed_at is not None:
            return wp, []
        levels = review_chain.chain("workpaper")
        if not levels:
            return wp, []
        try:
            stage = ReviewLevel(wp.review_stage) if wp.review_stage else levels[0]
        except ValueError:
            stage = levels[0]
        signed = review_chain.signer_ids(wp.review_trail)
        ids = [u for u in review_chain.reviewers_for(db, stage) if u != wp.uploaded_by and u not in signed]
        title = f"{wp.wp_ref or wp.title} v{wp.version_number} ({review_chain.label(stage)})"
        return wp, [Want("review_paper", u, title, wp.audit_id) for u in ids]

    if rt == "audit_report":
        from app.core import review_chain
        from app.domains.audit.reports.models import AuditReport

        r = _get(db, AuditReport, rid)
        if r is None:
            return None, []
        signed = review_chain.signer_ids(r.review_trail)
        if r.status == ReportStatus.ManagerReview and r.review_stage:
            try:
                stage = ReviewLevel(r.review_stage)
            except ValueError:
                return r, []
            ids = [u for u in review_chain.reviewers_for(db, stage) if u != r.created_by and u not in signed]
            return r, [Want("review_report", u, f"{_title(rt, r)} ({review_chain.label(stage)})", r.audit_id)
                       for u in ids]
        if r.status == ReportStatus.CAEApproval:
            ids = [u for u in review_chain.reviewers_for(db, ReviewLevel.CAE) if u not in signed]
            return r, [Want("approve_report", u, _title(rt, r), r.audit_id) for u in ids]
        return r, []

    if rt == "capa":
        from app.domains.issues.capa.models import Capa

        c = _get(db, Capa, rid)
        if c is None:
            return None, []
        aid = audit_id_for(db, rt, c)
        if c.status in (CapaStatus.Open, CapaStatus.InProgress):
            owner = _user_by_email(db, c.owner_email)
            if _active(db, owner):
                return c, [Want("implement_action", owner, _title(rt, c), aid, c.due_date)]
            return c, []
        if c.status == CapaStatus.Review:
            validators = [c.created_by] if _active(db, c.created_by) else _lead_ids(db, aid)
            owner = _user_by_email(db, c.owner_email)
            return c, [Want("validate_action", u, _title(rt, c), aid) for u in validators if u != owner]
        return c, []

    if rt == "audit":
        from app.domains.audit.audits.models import Audit

        return _get(db, Audit, rid), []
    return None, []


def _note_responders(db: DBSession, note) -> list[int]:  # noqa: ANN001
    from app.domains.audit.audits.models import Finding, WorkingPaper
    from app.domains.audit.rcm.models import ControlTest

    who: int | None = None
    if note.target_type == "control_test" and note.target_id:
        t = _get(db, ControlTest, note.target_id)
        who = t.assigned_to if t else None
    elif note.target_type == "working_paper" and note.target_id:
        wp = _get(db, WorkingPaper, note.target_id)
        who = wp.uploaded_by if wp else None
    elif note.target_type == "finding" and note.target_id:
        f = _get(db, Finding, note.target_id)
        who = f.created_by if f else None
    ids = [who] if _active(db, who) else [u for u in _lead_ids(db, note.audit_id) if _active(db, u)]
    return [u for u in ids if u != note.raised_by]


# ---------------------------------------------------------------- reconcile

def _reconcile(db: DBSession, rt: str, rid: int, obj, wants: list[Want], now: datetime) -> None:  # noqa: ANN001
    from app.platform.workflow.models import WorkItem

    existing = list(db.execute(select(WorkItem).where(WorkItem.record_type == rt, WorkItem.record_id == rid,
                                                      WorkItem.status == "open")).scalars())
    want_by_key = {(w.kind, w.assignee_id): w for w in wants}
    have_by_key = {(i.kind, i.assignee_id): i for i in existing}
    for key, item in have_by_key.items():
        if key not in want_by_key:
            item.status = "done" if obj is not None else "cancelled"
            item.closed_at = now
    for key, w in want_by_key.items():
        item = have_by_key.get(key)
        sla_key = KINDS[w.kind][1]
        if item is None:
            due = w.due or due_for(db, sla_key, now)
            db.add(WorkItem(kind=w.kind, record_type=rt, record_id=rid, audit_id=w.audit_id, title=w.title,
                            assignee_id=w.assignee_id, status="open", sla_key=sla_key, opened_at=now, due_at=due,
                            due_from_record=w.due is not None))
            continue
        item.title, item.audit_id = w.title, w.audit_id
        if w.due is not None and item.due_at != w.due:
            item.due_at, item.due_from_record = w.due, True
            if w.due > now:  # a later target date restarts the clock
                item.sla_state, item.priority = "ok", "normal"


def sync_records(db: DBSession, keys: set[tuple[str, int]]) -> None:
    """Re-derive the work items of the given records (called by the engine before every commit)."""
    if not keys:
        return
    keys = set(keys)
    for rt, rid in list(keys):  # dependants: a report's state decides its findings' response tasks
        if rt == "audit_report":
            from app.domains.audit.audits.models import Finding
            from app.domains.audit.reports.models import AuditReport

            r = _get(db, AuditReport, rid)
            if r is not None:
                keys |= {("finding", fid) for fid in db.execute(select(Finding.id).where(
                    Finding.audit_id == r.audit_id)).scalars()}
        elif rt == "audit_team":
            from app.domains.audit.methodology.models import ReviewNote

            keys.discard((rt, rid))
            keys |= {("review_note", nid) for nid in db.execute(select(ReviewNote.id).where(
                ReviewNote.audit_id == rid, ReviewNote.status == "Open")).scalars()}
    now = utcnow()
    for rt, rid in keys:
        obj, wants = desired(db, rt, rid)
        _reconcile(db, rt, rid, obj, wants, now)


def full_resync(db: DBSession) -> int:
    """Rebuild every open work item from the records. Returns the number of records examined."""
    from app.core.enums import CapaStatus, FindingStatus, ReportStatus, TestStatus
    from app.domains.audit.audits.models import Finding, WorkingPaper
    from app.domains.audit.evidence.models import EvidenceRequest
    from app.domains.audit.methodology.models import ReviewNote
    from app.domains.audit.rcm.models import ControlTest, Procedure, SignoffReviewer
    from app.domains.audit.reports.models import AuditReport
    from app.domains.issues.capa.models import Capa
    from app.platform.workflow.models import WorkItem

    ensure_policies(db)
    keys: set[tuple[str, int]] = set()
    keys |= {("procedure", i) for i in db.execute(select(Procedure.id).where(
        Procedure.status.in_(("Not Started", "In Progress")), Procedure.assigned_to.is_not(None))).scalars()}
    keys |= {("control_test", i) for i in db.execute(select(ControlTest.id).where(
        ControlTest.status.in_((TestStatus.NotStarted, TestStatus.InProgress)),
        ControlTest.assigned_to.is_not(None))).scalars()}
    reverse = {v: k for k, v in SIGNOFF_TARGET.items()}
    keys |= {(reverse[t], i) for t, i in db.execute(select(SignoffReviewer.target_type, SignoffReviewer.target_id))
             if t in reverse}
    keys |= {("evidence_request", i) for i in db.execute(select(EvidenceRequest.id).where(
        EvidenceRequest.status.in_(("Requested", "Returned", "Submitted")))).scalars()}
    keys |= {("review_note", i) for i in db.execute(select(ReviewNote.id).where(
        ReviewNote.status.in_(("Open", "Responded")))).scalars()}
    keys |= {("working_paper", i) for i in db.execute(select(WorkingPaper.id).where(
        WorkingPaper.is_deleted.is_(False), WorkingPaper.reviewed_at.is_(None))).scalars()}
    keys |= {("audit_report", i) for i in db.execute(select(AuditReport.id).where(
        AuditReport.status.in_((ReportStatus.ManagementReview, ReportStatus.ManagerReview,
                                ReportStatus.CAEApproval)))).scalars()}
    keys |= {("finding", i) for i in db.execute(select(Finding.id).where(
        Finding.status == FindingStatus.Open)).scalars()}
    keys |= {("capa", i) for i in db.execute(select(Capa.id).where(Capa.status != CapaStatus.Closed)).scalars()}
    keys |= {(rt, i) for rt, i in db.execute(select(WorkItem.record_type, WorkItem.record_id).where(
        WorkItem.status == "open")).all()}
    sync_records(db, keys)
    return len(keys)


# ---------------------------------------------------------------- SLA clock

def _link(item) -> tuple[str, int]:  # noqa: ANN001
    if item.record_type in LINK:
        return LINK[item.record_type], item.record_id
    return ("audit", item.audit_id) if item.audit_id else ("task", item.id)


def run_sla_clock(db: DBSession, now: datetime | None = None) -> dict[str, int]:
    """Warn before the due date and escalate after it. Commits. Returns counts."""
    from app.core.workdays import working_days_between
    from app.platform.notifications.service import notify
    from app.platform.workflow.models import SlaPolicy, WorkItem

    now = now or utcnow()
    policies = {p.key: p for p in db.execute(select(SlaPolicy)).scalars()}
    warned = breached = 0
    items = db.execute(select(WorkItem).where(WorkItem.status == "open", WorkItem.due_at.is_not(None))).scalars()
    for item in items:
        pol = policies.get(item.sla_key or "")
        warn_days = pol.warn_before_days if pol else 1
        label = KINDS.get(item.kind, (item.kind,))[0]
        link_type, link_id = _link(item)
        if now > item.due_at:
            if item.sla_state != "breached":
                item.sla_state, item.breached_at, item.priority = "breached", now, "high"
                notify(db, item.assignee_id, f"Overdue: {label}", f"{item.title} was due {item.due_at:%d %b %Y}.",
                       link_type=link_type, link_id=link_id)
                if item.kind not in ("implement_action",) and (pol is None or pol.escalate_on_breach):
                    for lead in _lead_ids(db, item.audit_id):
                        if lead != item.assignee_id:
                            notify(db, lead, f"Overdue in your audit: {label}",
                                   f"{item.title} (due {item.due_at:%d %b %Y}) is overdue.",
                                   link_type=link_type, link_id=link_id)
                _emit(db, "workitem.sla_breached", item, label)
                breached += 1
        elif item.sla_state == "ok" and working_days_between(now, item.due_at) <= warn_days:
            item.sla_state, item.warned_at = "warning", now
            notify(db, item.assignee_id, f"Due soon: {label}", f"{item.title} is due {item.due_at:%d %b %Y}.",
                   link_type=link_type, link_id=link_id)
            _emit(db, "workitem.sla_warning", item, label)
            warned += 1
    db.commit()
    return {"warned": warned, "breached": breached}


def _emit(db: DBSession, trigger: str, item, label: str) -> None:  # noqa: ANN001
    from app.platform.automations.engine import emit

    emit(db, trigger, "work_item", item.id, {
        "id": item.id, "task": label, "title": item.title, "kind": item.kind,
        "due_date": f"{item.due_at:%d %b %Y}" if item.due_at else "", "audit_id": item.audit_id,
        "_people": {"subject_user": [item.assignee_id]},
    }, period=trigger)
