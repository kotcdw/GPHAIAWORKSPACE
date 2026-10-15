"""Policy Manager API: policy records, versioned drafts with an optional document, review and approval by someone
other than the author, publication (superseding the previous version), periodic review dates, and attestation
campaigns in which staff confirm they have read and will comply with a published version.
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import utcnow
from app.core.refs import next_reference
from app.domains.grc import links
from app.domains.grc.common import (
    Viewer,
    add_months,
    audience_user_ids,
    can,
    check_entity,
    check_user,
    editor,
    entity_name,
    in_list,
    name_of,
    read_upload,
)
from app.domains.grc.policies.models import Attestation, AttestationCampaign, Policy, PolicyVersion
from app.platform.notifications.service import notify, notify_many
from app.platform.users.models import User
from app.services.documents import storage

router = APIRouter(prefix="/api/grc", tags=["risk & compliance"])
Editor = editor("grc.policy")


class PolicyIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    category: str = Field(default="", max_length=100)
    summary: str = Field(default="", max_length=10000)
    owner_id: int | None = None
    approver_id: int | None = None
    entity_id: int | None = None
    review_months: int | None = Field(default=None, ge=1, le=120)
    requirement_ids: list[int] | None = Field(default=None, max_length=200)


class NewPolicyIn(PolicyIn):
    content: str = Field(default="", max_length=500_000)


class DraftIn(BaseModel):
    content: str = Field(default="", max_length=500_000)
    change_summary: str = Field(default="", max_length=5000)


class ReviewIn(BaseModel):
    decision: Literal["approve", "return"]
    comment: str = Field(default="", max_length=5000)


class PublishIn(BaseModel):
    effective_date: date | None = None


class CampaignIn(BaseModel):
    title: str = Field(default="", max_length=255)
    statement: str = Field(default="", max_length=5000)
    due_date: date | None = None
    user_ids: list[int] = Field(default_factory=list, max_length=5000)
    job_roles: list[str] = Field(default_factory=list, max_length=50)
    tiers: list[str] = Field(default_factory=list, max_length=4)
    entity_ids: list[int] = Field(default_factory=list, max_length=200)


class AttestIn(BaseModel):
    status: Literal["Attested", "Declined"]
    comment: str = Field(default="", max_length=5000)


DEFAULT_STATEMENT = ("I confirm that I have read and understood this policy and will comply with it. I will ask my "
                     "supervisor or the policy owner where anything is unclear.")


def _policy(db: DBSession, policy_id: int) -> Policy:
    p = db.get(Policy, policy_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return p


def _versions(db: DBSession, policy_id: int) -> list[PolicyVersion]:
    return list(db.execute(select(PolicyVersion).where(PolicyVersion.policy_id == policy_id)
                           .order_by(PolicyVersion.version.desc())).scalars())


def _working(db: DBSession, p: Policy) -> PolicyVersion | None:
    """The version being drafted or reviewed (not yet published), if any."""
    for v in _versions(db, p.id):
        if v.status in ("Draft", "Returned", "In review", "Approved"):
            return v
    return None


def _campaign_out(db: DBSession, c: AttestationCampaign, with_people: bool = False) -> dict:
    rows = list(db.execute(select(Attestation).where(Attestation.campaign_id == c.id)).scalars())
    done = sum(1 for a in rows if a.status == "Attested")
    out = {"id": c.id, "policy_id": c.policy_id, "version": c.version, "title": c.title, "statement": c.statement,
           "due_date": c.due_date, "status": c.status, "created_at": c.created_at, "total": len(rows),
           "attested": done, "declined": sum(1 for a in rows if a.status == "Declined"),
           "pending": sum(1 for a in rows if a.status == "Pending"),
           "completion_pct": round(100 * done / len(rows)) if rows else 0,
           "overdue": bool(c.due_date and c.due_date < date.today() and c.status == "Open")}
    if with_people:
        out["people"] = sorted(({"id": a.id, "user_id": a.user_id, "name": name_of(db, a.user_id),
                                 "status": a.status, "comment": a.comment, "responded_at": a.responded_at}
                                for a in rows), key=lambda x: (x["status"] != "Declined", x["status"], x["name"] or ""))
    return out


def _policy_out(db: DBSession, p: Policy, user: User | None = None, full: bool = False) -> dict:
    working = _working(db, p)
    out = {"id": p.id, "ref": p.ref, "title": p.title, "category": p.category, "summary": p.summary,
           "owner_id": p.owner_id, "owner": name_of(db, p.owner_id), "approver_id": p.approver_id,
           "approver": name_of(db, p.approver_id), "entity_id": p.entity_id, "entity": entity_name(db, p.entity_id),
           "status": p.status, "published_version": p.published_version, "review_months": p.review_months,
           "effective_date": p.effective_date, "next_review_date": p.next_review_date,
           "review_overdue": bool(p.status == "Published" and p.next_review_date
                                  and p.next_review_date < date.today()),
           "working_version": working.version if working else None,
           "working_status": working.status if working else None, "updated_at": p.updated_at}
    if full:
        out["versions"] = [{"id": v.id, "version": v.version, "status": v.status, "content": v.content,
                            "change_summary": v.change_summary, "file_name": v.file_name,
                            "author": name_of(db, v.author_id), "author_id": v.author_id,
                            "submitted_at": v.submitted_at, "reviewed_by": name_of(db, v.reviewed_by),
                            "review_comment": v.review_comment, "approved_at": v.approved_at,
                            "published_at": v.published_at, "created_at": v.created_at}
                           for v in _versions(db, p.id)]
        out["campaigns"] = [_campaign_out(db, c) for c in db.execute(
            select(AttestationCampaign).where(AttestationCampaign.policy_id == p.id)
            .order_by(AttestationCampaign.created_at.desc())).scalars()]
        out["links"] = links.linked(db, "policy", p.id)
        if user is not None:
            is_editor = can(user, "grc.policy") or p.owner_id == user.id
            out["can"] = {
                "edit": is_editor,
                "draft": is_editor and (working is None or working.status in ("Draft", "Returned")),
                "submit": is_editor and working is not None and working.status in ("Draft", "Returned"),
                "review": working is not None and working.status == "In review" and _can_approve(user, p, working),
                "publish": is_editor and working is not None and working.status == "Approved",
                "campaign": can(user, "grc.policy") and p.published_version is not None and p.status == "Published",
                "retire": can(user, "grc.policy") and p.status != "Retired",
            }
    return out


def _can_approve(user: User, p: Policy, v: PolicyVersion) -> bool:
    if v.author_id == user.id:
        return False  # segregation: nobody approves their own draft
    return user.id == p.approver_id or can(user, "grc.policy_approve")


def _can_edit(user: User, p: Policy) -> None:
    if not (can(user, "grc.policy") or p.owner_id == user.id):
        raise HTTPException(status_code=403, detail="Only the policy owner or the policy team can change this policy")


def _apply(db: DBSession, p: Policy, payload: PolicyIn, user: User) -> None:
    check_user(db, payload.owner_id)
    check_user(db, payload.approver_id, "Approver")
    check_entity(db, payload.entity_id)
    p.title, p.summary = payload.title.strip(), payload.summary
    p.category = in_list(payload.category, "policy_categories", "Category")
    p.owner_id, p.approver_id, p.entity_id = payload.owner_id, payload.approver_id, payload.entity_id
    p.review_months = payload.review_months or p.review_months or cfg("policy_review_months")
    if payload.requirement_ids is not None:
        db.flush()
        links.set_links(db, "policy", p.id, "requirement", payload.requirement_ids, user.id)


# ---------------------------------------------------------------- policies

@router.get("/policies")
def list_policies(q: str | None = None, status: str | None = None, category: str | None = None,
                  db: DBSession = Depends(get_db), user: User = Viewer) -> dict:
    stmt = select(Policy)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Policy.title.like(like), Policy.ref.like(like), Policy.summary.like(like)))
    if status:
        stmt = stmt.where(Policy.status == status)
    if category:
        stmt = stmt.where(Policy.category == category)
    items = [_policy_out(db, p) for p in db.execute(stmt.order_by(Policy.ref)).scalars()]
    for i in items:
        latest = db.execute(select(AttestationCampaign).where(AttestationCampaign.policy_id == i["id"])
                            .order_by(AttestationCampaign.created_at.desc()).limit(1)).scalar_one_or_none()
        i["attestation"] = _campaign_out(db, latest) if latest else None
    return {"items": items, "categories": cfg("policy_categories"), "can_edit": can(user, "grc.policy"),
            "summary": {"published": sum(1 for i in items if i["status"] == "Published"),
                        "in_review": sum(1 for i in items if i["working_status"] == "In review"),
                        "review_overdue": sum(1 for i in items if i["review_overdue"]),
                        "drafts": sum(1 for i in items if i["status"] == "Draft")}}


@router.post("/policies", status_code=201)
def create_policy(payload: NewPolicyIn, request: Request, db: DBSession = Depends(get_db),
                  user: User = Editor) -> dict:
    p = Policy(ref=next_reference(db, "POL"), title=payload.title.strip(), created_by=user.id, status="Draft",
               review_months=cfg("policy_review_months"))
    db.add(p)
    _apply(db, p, payload, user)
    db.flush()
    db.add(PolicyVersion(policy_id=p.id, version=1, content=payload.content, change_summary="First version",
                         author_id=user.id, status="Draft"))
    log_action(db, user_id=user.id, action=f"POLICY_CREATE {p.ref}", request=request)
    db.commit()
    return _policy_out(db, p, user, full=True)


@router.get("/policies/{policy_id}")
def get_policy(policy_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    p = _policy(db, policy_id)
    from app.core.permissions import has_perm
    from app.domains.grc.common import GRC_PERMS

    if not has_perm(user, *GRC_PERMS) and not _has_attestation(db, p.id, user.id):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    out = _policy_out(db, p, user, full=True)
    if not has_perm(user, *GRC_PERMS):  # an attesting member of staff sees only the published text
        out["versions"] = [v for v in out["versions"] if v["version"] == p.published_version]
        out["campaigns"], out["links"] = [], []
    return out


def _has_attestation(db: DBSession, policy_id: int, user_id: int) -> bool:
    return db.execute(select(Attestation.id).join(AttestationCampaign,
                                                  AttestationCampaign.id == Attestation.campaign_id)
                      .where(AttestationCampaign.policy_id == policy_id, Attestation.user_id == user_id)).first() \
        is not None


@router.put("/policies/{policy_id}")
def update_policy(policy_id: int, payload: PolicyIn, request: Request, db: DBSession = Depends(get_db),
                  user: User = Viewer) -> dict:
    p = _policy(db, policy_id)
    _can_edit(user, p)
    _apply(db, p, payload, user)
    log_action(db, user_id=user.id, action=f"POLICY_UPDATE {p.ref}", request=request)
    db.commit()
    return _policy_out(db, p, user, full=True)


@router.put("/policies/{policy_id}/draft")
def save_draft(policy_id: int, payload: DraftIn, request: Request, db: DBSession = Depends(get_db),
               user: User = Viewer) -> dict:
    """Edit the working draft, or start the next version from the published text."""
    p = _policy(db, policy_id)
    _can_edit(user, p)
    if p.status == "Retired":
        raise HTTPException(status_code=422, detail="This policy is retired")
    v = _working(db, p)
    if v is not None and v.status not in ("Draft", "Returned"):
        raise HTTPException(status_code=409, detail=f"Version {v.version} is {v.status.lower()}; it cannot be edited")
    if v is None:
        last = db.execute(select(func.max(PolicyVersion.version)).where(PolicyVersion.policy_id == p.id)).scalar()
        v = PolicyVersion(policy_id=p.id, version=(last or 0) + 1, author_id=user.id, status="Draft")
        db.add(v)
    v.content, v.change_summary, v.author_id = payload.content, payload.change_summary, user.id
    if v.status == "Returned":
        v.status = "Draft"
    log_action(db, user_id=user.id, action=f"POLICY_DRAFT {p.ref} v{v.version}", request=request)
    db.commit()
    return _policy_out(db, p, user, full=True)


@router.post("/policies/{policy_id}/draft/file")
async def upload_draft_file(policy_id: int, request: Request, file: UploadFile = File(...),
                            db: DBSession = Depends(get_db), user: User = Viewer) -> dict:
    p = _policy(db, policy_id)
    _can_edit(user, p)
    v = _working(db, p)
    if v is None or v.status not in ("Draft", "Returned"):
        raise HTTPException(status_code=409, detail="Start a draft before attaching the document")
    name, data = await read_upload(file)
    v.stored_path, v.sha256 = storage.store_encrypted(data, "policies", name)
    v.file_name = name
    log_action(db, user_id=user.id, action=f"POLICY_FILE {p.ref} v{v.version} {name} sha256={v.sha256}",
               request=request)
    db.commit()
    return _policy_out(db, p, user, full=True)


@router.get("/policies/{policy_id}/versions/{version}/file")
def download_version_file(policy_id: int, version: int, request: Request, db: DBSession = Depends(get_db),
                          user: User = Depends(require_active_user)) -> Response:
    p = _policy(db, policy_id)
    from app.core.permissions import has_perm
    from app.domains.grc.common import GRC_PERMS

    v = db.execute(select(PolicyVersion).where(PolicyVersion.policy_id == p.id, PolicyVersion.version == version)) \
        .scalar_one_or_none()
    if v is None or not v.stored_path:
        raise HTTPException(status_code=404, detail="No document for this version")
    allowed = has_perm(user, *GRC_PERMS) or (version == p.published_version and _has_attestation(db, p.id, user.id))
    if not allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    data = storage.read_verified(v.stored_path, v.sha256)
    log_action(db, user_id=user.id, action=f"POLICY_DOWNLOAD {p.ref} v{version}", request=request)
    db.commit()
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(v.file_name or 'policy')}"})


@router.post("/policies/{policy_id}/submit")
def submit_policy(policy_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Viewer) -> dict:
    p = _policy(db, policy_id)
    _can_edit(user, p)
    v = _working(db, p)
    if v is None or v.status not in ("Draft", "Returned"):
        raise HTTPException(status_code=409, detail="There is no draft to submit")
    if not v.content.strip() and not v.stored_path:
        raise HTTPException(status_code=422, detail="Write the policy text or attach the document first")
    if p.approver_id is None:
        raise HTTPException(status_code=422, detail="Name the approver on the policy before submitting it")
    if p.approver_id == v.author_id:
        raise HTTPException(status_code=422, detail="The approver cannot be the author of this draft")
    v.status, v.submitted_at = "In review", utcnow()
    if p.status in ("Draft",):
        p.status = "In review"
    notify(db, p.approver_id, f"Policy for approval: {p.ref} v{v.version}", f"{p.title} is waiting for your review.",
           link_type="policy", link_id=p.id)
    log_action(db, user_id=user.id, action=f"POLICY_SUBMIT {p.ref} v{v.version}", request=request)
    db.commit()
    return _policy_out(db, p, user, full=True)


@router.post("/policies/{policy_id}/review")
def review_policy(policy_id: int, payload: ReviewIn, request: Request, db: DBSession = Depends(get_db),
                  user: User = Depends(require_active_user)) -> dict:
    p = _policy(db, policy_id)
    v = _working(db, p)
    if v is None or v.status != "In review":
        raise HTTPException(status_code=409, detail="No version is waiting for review")
    if v.author_id == user.id:
        raise HTTPException(status_code=403, detail="You cannot approve or return your own draft")
    if not _can_approve(user, p, v):
        raise HTTPException(status_code=403, detail="Only the named approver can review this policy")
    if payload.decision == "return" and not payload.comment.strip():
        raise HTTPException(status_code=422, detail="Say what needs to change")
    v.reviewed_by, v.review_comment = user.id, payload.comment
    if payload.decision == "approve":
        v.status, v.approved_at = "Approved", utcnow()
        if p.status == "In review":
            p.status = "Approved"
    else:
        v.status = "Returned"
        if p.status == "In review":
            p.status = "Draft"
    notify_many(db, [v.author_id, p.owner_id], f"Policy {p.ref} v{v.version} {v.status.lower()}",
                payload.comment or f"{p.title} was approved and can be published.", link_type="policy",
                link_id=p.id)
    log_action(db, user_id=user.id, action=f"POLICY_REVIEW {p.ref} v{v.version} {payload.decision}",
               request=request)
    db.commit()
    return _policy_out(db, p, user, full=True)


@router.post("/policies/{policy_id}/publish")
def publish_policy(policy_id: int, payload: PublishIn, request: Request, db: DBSession = Depends(get_db),
                   user: User = Viewer) -> dict:
    p = _policy(db, policy_id)
    _can_edit(user, p)
    v = _working(db, p)
    if v is None or v.status != "Approved":
        raise HTTPException(status_code=409, detail="Only an approved version can be published")
    for old in _versions(db, p.id):
        if old.status == "Published":
            old.status = "Superseded"
    v.status, v.published_at = "Published", utcnow()
    p.status, p.published_version = "Published", v.version
    p.effective_date = payload.effective_date or date.today()
    p.next_review_date = add_months(p.effective_date, p.review_months)
    log_action(db, user_id=user.id, action=f"POLICY_PUBLISH {p.ref} v{v.version}", request=request)
    db.commit()
    return _policy_out(db, p, user, full=True)


@router.post("/policies/{policy_id}/retire")
def retire_policy(policy_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    p = _policy(db, policy_id)
    p.status = "Retired"
    for c in db.execute(select(AttestationCampaign).where(AttestationCampaign.policy_id == p.id,
                                                          AttestationCampaign.status == "Open")).scalars():
        c.status = "Closed"
    log_action(db, user_id=user.id, action=f"POLICY_RETIRE {p.ref}", request=request)
    db.commit()
    return _policy_out(db, p, user, full=True)


# ---------------------------------------------------------------- attestations

@router.post("/policies/{policy_id}/campaigns", status_code=201)
def create_campaign(policy_id: int, payload: CampaignIn, request: Request, db: DBSession = Depends(get_db),
                    user: User = Editor) -> dict:
    p = _policy(db, policy_id)
    if p.status != "Published" or p.published_version is None:
        raise HTTPException(status_code=422, detail="Publish the policy before asking staff to attest to it")
    if payload.due_date and payload.due_date < date.today():
        raise HTTPException(status_code=422, detail="The due date cannot be in the past")
    people = audience_user_ids(db, payload.user_ids, payload.job_roles, payload.tiers, payload.entity_ids or None)
    if not people:
        raise HTTPException(status_code=422, detail="Choose who must attest (people, job roles or access tiers)")
    c = AttestationCampaign(policy_id=p.id, version=p.published_version, created_by=user.id,
                            title=payload.title.strip() or f"Attest to {p.ref} {p.title} v{p.published_version}",
                            statement=payload.statement.strip() or DEFAULT_STATEMENT, due_date=payload.due_date)
    db.add(c)
    db.flush()
    for uid in people:
        db.add(Attestation(campaign_id=c.id, user_id=uid))
    due = f" by {payload.due_date:%d %b %Y}" if payload.due_date else ""
    notify_many(db, people, f"Please attest: {p.title}", f"Read version {p.published_version} of {p.ref} and "
                f"confirm{due}. Open your Task Tracker.", link_type="attestation", link_id=c.id)
    log_action(db, user_id=user.id, action=f"ATTESTATION_CAMPAIGN {p.ref} v{c.version} to {len(people)} people",
               request=request)
    db.commit()
    return _campaign_out(db, c, with_people=True)


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: DBSession = Depends(get_db), _: User = Viewer) -> dict:
    c = db.get(AttestationCampaign, campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_out(db, c, with_people=True)


@router.post("/campaigns/{campaign_id}/remind")
def remind_campaign(campaign_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    c = db.get(AttestationCampaign, campaign_id)
    if c is None or c.status != "Open":
        raise HTTPException(status_code=409, detail="The campaign is not open")
    pending = list(db.execute(select(Attestation.user_id).where(Attestation.campaign_id == c.id,
                                                                Attestation.status == "Pending")).scalars())
    sent = notify_many(db, pending, f"Reminder: {c.title}", "Your attestation is still outstanding.",
                       link_type="attestation", link_id=c.id)
    log_action(db, user_id=user.id, action=f"ATTESTATION_REMIND campaign={c.id} sent={sent}", request=request)
    db.commit()
    return {"reminded": sent}


@router.post("/campaigns/{campaign_id}/close")
def close_campaign(campaign_id: int, request: Request, db: DBSession = Depends(get_db), user: User = Editor) -> dict:
    c = db.get(AttestationCampaign, campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    c.status = "Closed"
    log_action(db, user_id=user.id, action=f"ATTESTATION_CLOSE campaign={c.id}", request=request)
    db.commit()
    return _campaign_out(db, c, with_people=True)


def my_attestations(db: DBSession, user_id: int, pending_only: bool = True) -> list[dict]:
    stmt = select(Attestation, AttestationCampaign, Policy).join(
        AttestationCampaign, AttestationCampaign.id == Attestation.campaign_id).join(
        Policy, Policy.id == AttestationCampaign.policy_id).where(Attestation.user_id == user_id)
    if pending_only:
        stmt = stmt.where(Attestation.status == "Pending", AttestationCampaign.status == "Open")
    out = []
    for a, c, p in db.execute(stmt.order_by(AttestationCampaign.due_date)).all():
        v = db.execute(select(PolicyVersion).where(PolicyVersion.policy_id == p.id,
                                                   PolicyVersion.version == c.version)).scalar_one_or_none()
        out.append({"id": a.id, "status": a.status, "responded_at": a.responded_at, "campaign_id": c.id,
                    "title": c.title, "statement": c.statement, "due_date": c.due_date,
                    "overdue": bool(c.due_date and c.due_date < date.today() and a.status == "Pending"),
                    "policy_id": p.id, "policy_ref": p.ref, "policy_title": p.title, "version": c.version,
                    "content": v.content if v else "", "file_name": v.file_name if v else None})
    return out


@router.get("/attestations/mine")
def list_my_attestations(all: bool = False, db: DBSession = Depends(get_db),  # noqa: A002
                         user: User = Depends(require_active_user)) -> list[dict]:
    return my_attestations(db, user.id, pending_only=not all)


@router.post("/attestations/{attestation_id}")
def respond(attestation_id: int, payload: AttestIn, request: Request, db: DBSession = Depends(get_db),
            user: User = Depends(require_active_user)) -> dict:
    a = db.get(Attestation, attestation_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="Attestation not found")
    c = db.get(AttestationCampaign, a.campaign_id)
    if c.status != "Open":
        raise HTTPException(status_code=409, detail="This attestation campaign is closed")
    if a.status != "Pending":
        raise HTTPException(status_code=409, detail="You have already responded")
    if payload.status == "Declined" and not payload.comment.strip():
        raise HTTPException(status_code=422, detail="Say why you cannot attest")
    a.status, a.comment, a.responded_at = payload.status, payload.comment, utcnow()
    if payload.status == "Declined":
        p = db.get(Policy, c.policy_id)
        notify(db, p.owner_id, f"Attestation declined: {p.ref}",
               f"{name_of(db, user.id)}: {payload.comment}", link_type="policy", link_id=p.id)
    log_action(db, user_id=user.id, action=f"ATTEST campaign={c.id} {payload.status}", request=request)
    db.commit()
    return {"id": a.id, "status": a.status}
