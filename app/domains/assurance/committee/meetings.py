"""Register of Audit Committee meetings, minutes and decisions on recommendations.

PFM Act 2016 (Act 921) s.88 and the MoF follow-up instructions (s.6.3, s.7.7): the Audit Committee considers the
quarterly follow-up report at each meeting, pursues implementation, and closes internal audit recommendations
once the evidence is sufficient (external recommendations are closed by the external body). A decision recorded
here is applied to the action, so the register, the Committee pack and the statutory returns stay consistent.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_perm
from app.core.enums import CapaStatus, ValidationResult, utcnow
from app.core.history import log_record_history
from app.core.refs import next_reference
from app.domains.assurance.committee.models import (
    DECISIONS,
    MEETING_STATUSES,
    MEETING_TYPES,
    CommitteeDecision,
    CommitteeMeeting,
)
from app.domains.issues.capa.models import Capa
from app.domains.issues.capa.status import FULLY, WITHDRAWN, is_internal
from app.platform.notifications.service import notify_many, user_id_by_email
from app.platform.users.models import User
from app.services.documents import add_table, docx_response, new_document

router = APIRouter(prefix="/api/committee", tags=["audit committee"])
Viewer = Depends(require_perm("committee.record", "governance.view"))
Recorder = Depends(require_perm("committee.record"))


class MeetingIn(BaseModel):
    meeting_date: datetime
    meeting_type: str = "Ordinary"
    venue: str = Field(default="", max_length=160)
    agenda: str = Field(default="", max_length=20000)


class MeetingPatch(BaseModel):
    meeting_date: datetime | None = None
    meeting_type: str | None = None
    venue: str | None = Field(default=None, max_length=160)
    agenda: str | None = Field(default=None, max_length=20000)
    attendees: str | None = Field(default=None, max_length=10000)
    apologies: str | None = Field(default=None, max_length=10000)
    quorum: bool | None = None
    minutes: str | None = Field(default=None, max_length=100000)
    followup_report_considered: bool | None = None
    status: str | None = None


class DecisionIn(BaseModel):
    subject_type: str = "capa"
    subject_id: int | None = None
    decision: str
    new_due_date: datetime | None = None
    reference: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=10000)


def _meeting(db: DBSession, meeting_id: int) -> CommitteeMeeting:
    m = db.get(CommitteeMeeting, meeting_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return m


def _decision_out(db: DBSession, d: CommitteeDecision) -> dict:
    subject = ""
    if d.subject_type == "capa" and d.subject_id:
        capa = db.get(Capa, d.subject_id)
        subject = f"{capa.capa_ref} {capa.title}" if capa else f"Action #{d.subject_id}"
    return {"id": d.id, "subject_type": d.subject_type, "subject_id": d.subject_id, "subject": subject,
            "decision": d.decision, "new_due_date": d.new_due_date, "reference": d.reference, "notes": d.notes,
            "recorded_by": d.recorded_by, "created_at": d.created_at}


def _out(db: DBSession, m: CommitteeMeeting, full: bool = True) -> dict:
    out = {"id": m.id, "meeting_ref": m.meeting_ref, "meeting_date": m.meeting_date, "meeting_type": m.meeting_type,
           "venue": m.venue, "status": m.status, "quorum": m.quorum,
           "followup_report_considered": m.followup_report_considered, "decisions_count": len(m.decisions),
           "minutes_approved_at": m.minutes_approved_at}
    if full:
        out.update({"agenda": m.agenda, "attendees": m.attendees, "apologies": m.apologies, "minutes": m.minutes,
                    "decisions": [_decision_out(db, d) for d in m.decisions]})
    return out


@router.get("/meetings")
def list_meetings(db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    rows = db.execute(select(CommitteeMeeting).order_by(CommitteeMeeting.meeting_date.desc())).scalars()
    return {"types": MEETING_TYPES, "statuses": MEETING_STATUSES, "decisions": DECISIONS,
            "items": [_out(db, m, full=False) for m in rows]}


@router.post("/meetings", status_code=201)
def create_meeting(payload: MeetingIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Recorder) -> dict:
    if payload.meeting_type not in MEETING_TYPES:
        raise HTTPException(status_code=422, detail=f"Type must be one of: {', '.join(MEETING_TYPES)}")
    m = CommitteeMeeting(meeting_ref=next_reference(db, "ACM"), meeting_date=payload.meeting_date.replace(tzinfo=None),
                         meeting_type=payload.meeting_type, venue=payload.venue.strip(), agenda=payload.agenda,
                         created_by=user.id)
    db.add(m)
    db.flush()
    log_action(db, user_id=user.id, action=f"COMMITTEE_MEETING_CREATE {m.meeting_ref}", request=request)
    db.commit()
    return _out(db, m)


@router.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: int, db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    return _out(db, _meeting(db, meeting_id))


@router.patch("/meetings/{meeting_id}")
def update_meeting(meeting_id: int, payload: MeetingPatch, request: Request, db: DBSession = Depends(get_db),
                   user: User = Recorder) -> dict:
    m = _meeting(db, meeting_id)
    if m.status == "Minutes approved":
        raise HTTPException(status_code=409, detail="The minutes are approved; the meeting record is locked")
    sent = payload.model_fields_set
    if "meeting_type" in sent and payload.meeting_type not in MEETING_TYPES:
        raise HTTPException(status_code=422, detail="Unknown meeting type")
    if "status" in sent and payload.status not in ("Scheduled", "Held", "Cancelled"):
        raise HTTPException(status_code=422, detail="Status can be Scheduled, Held or Cancelled "
                                                    "(minutes are approved separately)")
    if payload.status == "Held" and (payload.meeting_date or m.meeting_date) > utcnow():
        raise HTTPException(status_code=422, detail="A meeting in the future cannot be marked as held")
    for name in sent:
        value = getattr(payload, name)
        if name == "meeting_date" and value is not None:
            value = value.replace(tzinfo=None)
        if value is not None:
            setattr(m, name, value)
    log_action(db, user_id=user.id, action=f"COMMITTEE_MEETING_UPDATE {m.meeting_ref} [{', '.join(sent)}]",
               request=request)
    db.commit()
    return _out(db, m)


@router.post("/meetings/{meeting_id}/approve-minutes")
def approve_minutes(meeting_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Recorder) -> dict:
    m = _meeting(db, meeting_id)
    if m.status != "Held":
        raise HTTPException(status_code=409, detail="Only a meeting marked as held can have its minutes approved")
    if len(m.minutes.strip()) < 20 or not m.attendees.strip():
        raise HTTPException(status_code=422, detail="Record the attendees and the minutes first")
    m.status = "Minutes approved"
    m.minutes_approved_at = utcnow()
    m.minutes_approved_by = user.id
    log_action(db, user_id=user.id, action=f"COMMITTEE_MINUTES_APPROVED {m.meeting_ref}", request=request)
    db.commit()
    return _out(db, m)


def _apply_to_capa(db: DBSession, m: CommitteeMeeting, d: CommitteeDecision, user: User, request: Request) -> None:
    capa = db.get(Capa, d.subject_id or 0)
    if capa is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if capa.status == CapaStatus.Closed and d.decision != "Noted":
        raise HTTPException(status_code=409, detail=f"{capa.capa_ref} is already closed")
    note = f"Audit Committee {m.meeting_ref} ({m.meeting_date:%d %b %Y}): {d.decision}"
    if d.decision == "Close":
        if is_internal(capa):
            if capa.validation_result != ValidationResult.Effective:
                raise HTTPException(status_code=409, detail="Internal Audit must validate the implementation as "
                                                            "Effective before the Committee closes it")
        else:
            ref = d.reference.strip() if d.reference else (capa.external_closure_ref or "")
            if not ref:
                raise HTTPException(status_code=422, detail=f"Give {capa.source_body}'s closure reference")
            capa.external_closure_ref = ref
        capa.status = CapaStatus.Closed
        capa.implementation_status = FULLY
        capa.closed_by = user.id
        capa.closed_at = utcnow()
    elif d.decision == "Withdraw":
        if len((d.notes or capa.withdrawal_reason or "").strip()) < 10:
            raise HTTPException(status_code=422, detail="Give the reason the recommendation is withdrawn")
        capa.status = CapaStatus.Closed
        capa.implementation_status = WITHDRAWN
        capa.withdrawal_reason = capa.withdrawal_reason or d.notes
        capa.closed_by = user.id
        capa.closed_at = utcnow()
    elif d.decision == "Extend deadline":
        if d.new_due_date is None or d.new_due_date <= utcnow():
            raise HTTPException(status_code=422, detail="Give a new due date in the future")
        capa.due_date = d.new_due_date
        capa.escalation_level = 0
        note += f" to {d.new_due_date:%d %b %Y}"
    elif d.decision == "Escalate to management":
        from app.core.permissions import job_role_of
        from app.platform.users.models import User as U

        heads = [u.id for u in db.execute(select(U).where(U.is_active.is_(True))).scalars()
                 if job_role_of(u) == "gm_audit"]
        notify_many(db, [user_id_by_email(db, capa.owner_email), *heads],
                    f"Audit Committee escalation: {capa.capa_ref}", f"{capa.title}\n{d.notes}",
                    link_type="capa", link_id=capa.id)
    log_record_history(db, record_type="capa", record_id=capa.id, user_id=user.id, action=note, request=request)


@router.post("/meetings/{meeting_id}/decisions", status_code=201)
def record_decision(meeting_id: int, payload: DecisionIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = Recorder) -> dict:
    m = _meeting(db, meeting_id)
    if m.status != "Held":
        raise HTTPException(status_code=409, detail="Decisions are recorded for a meeting marked as held, before its "
                                                    "minutes are approved")
    if payload.decision not in DECISIONS:
        raise HTTPException(status_code=422, detail=f"Decision must be one of: {', '.join(DECISIONS)}")
    if payload.subject_type not in ("capa", "other"):
        raise HTTPException(status_code=422, detail="Subject must be an action (capa) or other")
    if payload.subject_type == "other" and payload.decision not in ("Noted",):
        raise HTTPException(status_code=422, detail="Only 'Noted' applies to other matters")
    if payload.subject_type == "other" and len(payload.notes.strip()) < 5:
        raise HTTPException(status_code=422, detail="Describe the matter decided")
    d = CommitteeDecision(meeting_id=m.id, subject_type=payload.subject_type, subject_id=payload.subject_id,
                          decision=payload.decision,
                          new_due_date=payload.new_due_date.replace(tzinfo=None) if payload.new_due_date else None,
                          reference=payload.reference.strip() or None, notes=payload.notes.strip(),
                          recorded_by=user.id)
    if d.subject_type == "capa":
        _apply_to_capa(db, m, d, user, request)
    db.add(d)
    log_action(db, user_id=user.id, request=request,
               action=f"COMMITTEE_DECISION {m.meeting_ref} {d.subject_type}={d.subject_id} {d.decision}")
    db.commit()
    return _out(db, m)


@router.get("/for-decision")
def for_decision(db: DBSession = Depends(get_db), _: User = Viewer) -> list[dict]:
    """Actions the Committee needs to consider: proposed withdrawals, actions validated and awaiting closure,
    recommendations from external bodies with a closure reference, and actions escalated to the Committee."""
    rows = db.execute(select(Capa).where(Capa.status != CapaStatus.Closed, or_(
        Capa.withdrawal_proposed_at.is_not(None), Capa.validation_result == ValidationResult.Effective,
        Capa.escalation_level >= 4, Capa.external_closure_ref.is_not(None)))).scalars()
    out = []
    for c in rows:
        reasons = []
        if c.withdrawal_proposed_at:
            reasons.append("Withdrawal proposed")
        if c.validation_result == ValidationResult.Effective:
            reasons.append("Validated - ready to close" if is_internal(c) else "Validated by Internal Audit")
        if c.escalation_level >= 4:
            reasons.append("Overdue - escalated to the Committee")
        if c.external_closure_ref:
            reasons.append(f"Closed by {c.source_body} ({c.external_closure_ref})")
        out.append({"id": c.id, "capa_ref": c.capa_ref, "title": c.title, "source_body": c.source_body,
                    "owner_email": c.owner_email, "due_date": c.due_date, "implementation_status":
                    c.implementation_status, "reasons": reasons, "withdrawal_reason": c.withdrawal_reason})
    return out


@router.get("/meetings/{meeting_id}/minutes.docx")
def minutes_docx(meeting_id: int, db: DBSession = Depends(get_db), _: User = Viewer):  # noqa: ANN201
    m = _meeting(db, meeting_id)
    doc = new_document()
    doc.add_heading(f"Minutes of the {m.meeting_type.lower()} meeting of the Audit Committee", level=1)
    doc.add_paragraph(f"Ref: {m.meeting_ref}    Date: {m.meeting_date:%d %B %Y %H:%M}    Venue: {m.venue or '-'}")
    doc.add_paragraph(f"Status: {m.status}" + (f" (approved {m.minutes_approved_at:%d %B %Y})"
                                               if m.minutes_approved_at else ""))
    for title, text in (("Present", m.attendees), ("Apologies", m.apologies), ("Agenda", m.agenda),
                        ("Proceedings", m.minutes)):
        doc.add_heading(title, level=2)
        doc.add_paragraph(text or "-")
    doc.add_paragraph(f"Quorum: {'Yes' if m.quorum else 'No'}.  Quarterly follow-up report considered: "
                      f"{'Yes' if m.followup_report_considered else 'No'}.")
    if m.decisions:
        doc.add_heading("Decisions on audit recommendations and other matters", level=2)
        add_table(doc, ["Subject", "Decision", "New due date", "Reference", "Notes"],
                  [[x["subject"] or "Other", x["decision"], f"{x['new_due_date']:%d %b %Y}" if x["new_due_date"]
                    else "", x["reference"] or "", x["notes"]] for x in (_decision_out(db, d) for d in m.decisions)])
    doc.add_paragraph("\nChairperson: ____________________    Secretary: ____________________")
    return docx_response(doc, f"{m.meeting_ref}-minutes.docx")


def latest_meetings(db: DBSession, limit: int = 4) -> list[dict]:
    rows = db.execute(select(CommitteeMeeting).where(CommitteeMeeting.status != "Cancelled")
                      .order_by(CommitteeMeeting.meeting_date.desc()).limit(limit)).scalars()
    return [_out(db, m, full=False) for m in rows]


def committee_closes() -> bool:
    return bool(cfg("committee_closes_recommendations"))
