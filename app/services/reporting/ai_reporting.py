"""AI Reporting workstreams (PROJECTBLUEPRINT 6.12).

A workstream turns confirmed data into a report in four steps:

1. **Sources**: one or more report definitions (View, filters, period). Nothing else is read.
2. **Facts**: the sources are run with the author's access and the results are stored as facts: totals,
   groupings and sample rows, each with its source, filters, period and time. Facts are never generated.
3. **Narrative**: optional. With an AI provider configured, a draft is written from the stored facts only and
   labelled as generated; the author can edit it. Without a provider the author writes it, or the workstream
   publishes the facts alone.
4. **Review and publish**: a reviewer other than the author confirms the facts were checked against their
   source and approves; only then can it be published. Changing sources or facts sends it back to Draft.

Readers of a published workstream see the stored facts only if they could see every audit they came from.
"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import utcnow
from app.core.permissions import has_perm
from app.platform.users.models import User
from app.services.reporting import views
from app.services.reporting.models import AiWorkstream
from app.services.reporting.sharing import check_audience, ensure_staff, ids, may_read_facts, shared_with

router = APIRouter(prefix="/api/ai-reporting", tags=["ai reporting"])

SAMPLE_ROWS = 20
REVIEW_PERMS = ("report.review", "report.approve", "review.workpapers")


class SourceIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    spec: views.SpecIn


class WorkstreamIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    purpose: str = Field(default="", max_length=4000)
    sources: list[SourceIn] = Field(default_factory=list, max_length=10)
    access: Literal["Public", "Private"] = "Private"
    group_ids: list[int] = Field(default_factory=list, max_length=50)
    user_ids: list[int] = Field(default_factory=list, max_length=200)


class WorkstreamUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    purpose: str | None = Field(default=None, max_length=4000)
    sources: list[SourceIn] | None = Field(default=None, max_length=10)
    narrative: str | None = Field(default=None, max_length=50_000)
    access: Literal["Public", "Private"] | None = None
    group_ids: list[int] | None = Field(default=None, max_length=50)
    user_ids: list[int] | None = Field(default=None, max_length=200)


class ReviewIn(BaseModel):
    decision: Literal["approve", "return"]
    note: str = Field(default="", max_length=4000)
    facts_checked: bool = False


def _sources(w: AiWorkstream) -> list[dict]:
    try:
        return json.loads(w.sources or "[]")
    except ValueError:
        return []


def _facts(w: AiWorkstream) -> dict | None:
    return json.loads(w.facts) if w.facts else None


def _is_reviewer(user: User) -> bool:
    return has_perm(user, *REVIEW_PERMS)


def _visible(db: DBSession, user: User, w: AiWorkstream) -> bool:
    if w.owner_id == user.id:
        return True
    if w.archived:
        return False
    if w.status == "In review" and _is_reviewer(user):
        return True
    return w.status == "Published" and shared_with(db, user, owner_id=w.owner_id, access=w.access,
                                                   group_ids=w.group_ids, user_ids=w.user_ids)


def _get(db: DBSession, user: User, wid: int) -> AiWorkstream:
    w = db.get(AiWorkstream, wid)
    if w is None or not _visible(db, user, w):
        raise HTTPException(status_code=404, detail="Workstream not found")
    return w


def _owned_draft(db: DBSession, user: User, wid: int) -> AiWorkstream:
    w = _get(db, user, wid)
    if w.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the author can change this workstream")
    if w.status == "Published" or w.archived:
        raise HTTPException(status_code=409, detail="A published or archived workstream cannot be changed")
    return w


def _to_draft(w: AiWorkstream) -> None:
    w.status, w.reviewed_by, w.reviewed_at, w.review_note = "Draft", None, None, ""


def _out(db: DBSession, user: User, w: AiWorkstream) -> dict:
    facts = _facts(w)
    readable = facts is None or w.owner_id == user.id or may_read_facts(db, user, facts)
    names = {u.id: (u.full_name or u.username) for u in db.execute(
        select(User).where(User.id.in_({x for x in (w.owner_id, w.reviewed_by) if x} or {0}))).scalars()}
    return {
        "id": w.id, "title": w.title, "purpose": w.purpose, "sources": _sources(w),
        "facts": facts if readable else None,
        "facts_hidden": not readable,
        "facts_generated_at": w.facts_generated_at,
        "narrative": w.narrative if readable else "",
        "narrative_origin": w.narrative_origin,
        "narrative_label": {"ai": "Generated draft (AI), not yet edited", "edited": "Written or edited by the author",
                            "none": "No narrative"}.get(w.narrative_origin, w.narrative_origin),
        "status": w.status, "review_note": w.review_note, "reviewed_by": names.get(w.reviewed_by),
        "reviewed_at": w.reviewed_at, "published_at": w.published_at, "access": w.access,
        "group_ids": ids(w.group_ids), "user_ids": ids(w.user_ids), "owner_id": w.owner_id,
        "owner": names.get(w.owner_id),
        "archived": w.archived,
        "can_edit": w.owner_id == user.id and w.status != "Published" and not w.archived,
        "can_review": w.status == "In review" and w.owner_id != user.id and _is_reviewer(user),
        "created_at": w.created_at, "updated_at": w.updated_at,
    }


def _check_sources(user: User, sources: list[SourceIn]) -> list[dict]:
    for s in sources:
        views.validate(user, s.spec)
    return [s.model_dump(mode="json") for s in sources]


@router.get("")
def list_workstreams(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list[dict]:
    ensure_staff(user)
    rows = db.execute(select(AiWorkstream).where(AiWorkstream.archived.is_(False))
                      .order_by(AiWorkstream.updated_at.desc())).scalars()
    return [_out(db, user, w) for w in rows if _visible(db, user, w)]


AI_TEMPLATES: tuple[dict, ...] = (
    {"key": "erm-board", "name": "ERM Report - Board Review",
     "purpose": "Strategic risk profile for the board: residual levels, risks above target and assurance gaps.",
     "sources": [{"label": "Strategic risks by residual level",
                  "spec": {"view": "risks", "group_by": "residual_level",
                           "filters": [{"column": "status", "op": "eq", "value": "Active"}]}},
                 {"label": "Risks above target",
                  "spec": {"view": "risks", "filters": [{"column": "above_target", "op": "eq", "value": "Yes"}],
                           "group_by": "category"}}]},
    {"key": "committee-summary", "name": "Audit Committee Summary",
     "purpose": "Open audit findings, overdue actions and assurance plan progress for the Audit Committee.",
     "sources": [{"label": "Open issues by severity",
                  "spec": {"view": "issues", "filters": [{"column": "status", "op": "ne", "value": "Closed"}],
                           "group_by": "rating"}},
                 {"label": "Overdue actions", "spec": {"view": "actions", "group_by": "overdue",
                                                       "filters": [{"column": "status", "op": "ne",
                                                                    "value": "Closed"}]}},
                 {"label": "Plan projects by status", "spec": {"view": "projects", "group_by": "status"}}]},
    {"key": "remediation-status", "name": "Remediation Status Report",
     "purpose": "Where management stands on remediating audit issues.",
     "sources": [{"label": "Issues by remediation status",
                  "spec": {"view": "issues", "group_by": "remediation_status"}},
                 {"label": "Actions by status", "spec": {"view": "actions", "group_by": "status"}}]},
    {"key": "control-assurance", "name": "Control Assurance Summary",
     "purpose": "Results of control testing across projects.",
     "sources": [{"label": "Controls by conclusion", "spec": {"view": "controls", "group_by": "conclusion"}}]},
)

_KEYWORDS = (  # word in the request -> View
    (("risk", "erm", "strategic"), "risks"), (("finding", "issue"), "issues"),
    (("action", "remediat", "overdue"), "actions"), (("control", "test"), "controls"),
    (("plan", "project", "progress", "hours", "budget"), "projects"), (("audit",), "audits"),
)
_GROUPS = (("severity", "rating"), ("owner", "owner"), ("status", "status"), ("category", "category"),
           ("conclusion", "conclusion"), ("level", "residual_level"))


class SuggestIn(BaseModel):
    template: str | None = Field(default=None, max_length=60)
    request: str = Field(default="", max_length=2000)


@router.get("/templates")
def ai_templates(user: User = Depends(require_active_user)) -> list[dict]:
    ensure_staff(user)
    usable = {v.key for v in views.available(user)}
    return [t for t in AI_TEMPLATES if all(s["spec"]["view"] in usable for s in t["sources"])]


@router.post("/suggest")
def suggest_sources(payload: SuggestIn, user: User = Depends(require_active_user)) -> dict:
    """Suggested data sources for a template or a described report, for the user to review and confirm. The
    suggestion is a plain keyword match on the request; nothing is generated and no data is read here."""
    ensure_staff(user)
    usable = {v.key: v for v in views.available(user)}
    if payload.template:
        t = next((x for x in AI_TEMPLATES if x["key"] == payload.template), None)
        if t is None:
            raise HTTPException(status_code=404, detail="Template not found")
        sources = [s for s in t["sources"] if s["spec"]["view"] in usable]
        return {"title": t["name"], "purpose": t["purpose"], "sources": sources}
    text = payload.request.lower()
    if len(text.strip()) < 5:
        raise HTTPException(status_code=422, detail="Describe the report you need")
    sources = []
    for words, key in _KEYWORDS:
        if key in usable and any(w in text for w in words):
            v = usable[key]
            cols = {c.key for c in v.columns}
            group = next((col for word, col in _GROUPS if word in text and col in cols), None)
            spec: dict = {"view": key}
            if group:
                spec["group_by"] = group
            if "open" in text and "status" in cols:
                spec["filters"] = [{"column": "status", "op": "ne", "value": "Closed"}]
            sources.append({"label": v.label + (f" by {group.replace('_', ' ')}" if group else ""), "spec": spec})
    if not sources:
        raise HTTPException(status_code=422, detail="No data source matches the request; pick a template or name "
                                                    "issues, actions, controls, risks, projects or audits")
    title = payload.request.strip().split("\n")[0][:120]
    return {"title": title[0].upper() + title[1:], "purpose": payload.request.strip(), "sources": sources}


@router.post("", status_code=201)
def create_workstream(payload: WorkstreamIn, request: Request, db: DBSession = Depends(get_db),
                      user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    groups, users = check_audience(db, payload.access, payload.group_ids, payload.user_ids)
    w = AiWorkstream(title=payload.title.strip(), purpose=payload.purpose.strip(),
                     sources=json.dumps(_check_sources(user, payload.sources)), access=payload.access,
                     group_ids=json.dumps(groups), user_ids=json.dumps(users), owner_id=user.id)
    db.add(w)
    db.flush()
    log_action(db, user_id=user.id, request=request, action=f"AIREPORT_CREATE id={w.id} {w.title}")
    db.commit()
    return _out(db, user, w)


@router.get("/{wid}")
def get_workstream(wid: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    return _out(db, user, _get(db, user, wid))


@router.patch("/{wid}")
def update_workstream(wid: int, payload: WorkstreamUpdate, request: Request, db: DBSession = Depends(get_db),
                      user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    w = _owned_draft(db, user, wid)
    changed = list(payload.model_dump(exclude_unset=True))
    if payload.title is not None:
        w.title = payload.title.strip()
    if payload.purpose is not None:
        w.purpose = payload.purpose.strip()
    if payload.sources is not None:
        w.sources = json.dumps(_check_sources(user, payload.sources))
        w.facts, w.facts_generated_at = None, None  # facts must come from the current sources
    if payload.narrative is not None:
        w.narrative = payload.narrative.strip()
        w.narrative_origin = "edited" if w.narrative else "none"
    if payload.access is not None or payload.group_ids is not None or payload.user_ids is not None:
        access = payload.access or w.access
        groups, users = check_audience(db, access,
                                       payload.group_ids if payload.group_ids is not None else ids(w.group_ids),
                                       payload.user_ids if payload.user_ids is not None else ids(w.user_ids))
        w.access, w.group_ids, w.user_ids = access, json.dumps(groups), json.dumps(users)
    if {"sources", "narrative"} & set(changed):
        _to_draft(w)
    log_action(db, user_id=user.id, request=request, action=f"AIREPORT_UPDATE id={w.id} [{', '.join(changed)}]")
    db.commit()
    return _out(db, user, w)


@router.post("/{wid}/facts")
def build_facts(wid: int, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(require_active_user)) -> dict:
    """Run the confirmed sources with the author's access and store the results as facts."""
    ensure_staff(user)
    w = _owned_draft(db, user, wid)
    sources = _sources(w)
    if not sources:
        raise HTTPException(status_code=422, detail="Add at least one source first")
    out = []
    for s in sources:
        res = views.run(db, user, views.SpecIn.model_validate(s["spec"]))
        out.append({"label": s["label"], "source": res["source"], "view": res["view"],
                    "filters_text": res["filters_text"], "period_text": res["period_text"],
                    "scope_text": res["scope_text"], "generated_at": res["generated_at"],
                    "total": res["total"], "group_by": res["group_by"], "groups": res["groups"],
                    "columns": res["columns"], "sample_rows": res["rows"][:SAMPLE_ROWS],
                    "audit_ids": res["audit_ids"], "perms": res["perms"]})
    w.facts = json.dumps({"sources": out}, default=str)
    w.facts_generated_at = utcnow()
    _to_draft(w)
    log_action(db, user_id=user.id, request=request,
               action=f"AIREPORT_FACTS id={w.id} sources={len(out)} totals={[s['total'] for s in out]}")
    db.commit()
    return _out(db, user, w)


def _prompt(w: AiWorkstream, facts: dict) -> str:
    lines = [f"Report title: {w.title}", f"Purpose: {w.purpose or '-'}", "",
             "Write a short management report narrative (3-6 paragraphs) using ONLY the facts below. Do not add "
             "figures, names or conclusions that are not in the facts. Say when the facts are insufficient.", ""]
    for s in facts["sources"]:
        lines.append(f"Source: {s['label']} ({s['source']}); filters: {s['filters_text']}; period: {s['period_text']}; "
                     f"records: {s['total']}")
        for g in s.get("groups") or []:
            lines.append(f"  {s['group_by']} = {g['value']}: {g['count']}")
    return "\n".join(lines)


@router.post("/{wid}/narrative")
def draft_narrative(wid: int, request: Request, db: DBSession = Depends(get_db),
                    user: User = Depends(require_active_user)) -> dict:
    """Draft the narrative from the stored facts with the configured AI provider (optional feature)."""
    from app.services.ai import service
    from app.services.ai.providers import AiError

    ensure_staff(user)
    w = _owned_draft(db, user, wid)
    facts = _facts(w)
    if facts is None:
        raise HTTPException(status_code=422, detail="Build the facts first; the narrative is drafted from them only")
    if not has_perm(user, "ai.use"):
        raise HTTPException(status_code=403, detail="Your role does not use AI assistance")
    if not service.status()["ready"]:
        raise HTTPException(status_code=409, detail="AI assistance is not set up. Write the narrative yourself, "
                                                    "or publish the facts alone.")
    try:
        text = service.run(db, user=user, feature="report_narrative", prompt=_prompt(w, facts),
                           record_type="ai_report", record_id=w.id, request=request)
    except AiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    w = db.get(AiWorkstream, wid)
    w.narrative, w.narrative_origin = text.strip()[:50_000], "ai"
    _to_draft(w)
    log_action(db, user_id=user.id, request=request, action=f"AIREPORT_NARRATIVE id={w.id} chars={len(w.narrative)}")
    db.commit()
    return _out(db, user, w)


@router.post("/{wid}/generate")
def generate(wid: int, request: Request, db: DBSession = Depends(get_db),
             user: User = Depends(require_active_user)) -> dict:
    """Generate report: store the facts from the confirmed sources, then draft the narrative from them when AI
    assistance is set up and the user may use it. Without AI the report holds the facts alone."""
    from app.services.ai import service

    build_facts(wid, request, db, user)
    ai_used, ai_error = False, None
    if has_perm(user, "ai.use") and service.status()["ready"]:
        try:
            draft_narrative(wid, request, db, user)
            ai_used = True
        except HTTPException as exc:  # the facts are kept; the author writes the narrative or tries again
            db.rollback()
            ai_error = str(exc.detail)
    w = _get(db, user, wid)
    return {**_out(db, user, w), "ai_used": ai_used, "ai_error": ai_error}


@router.post("/{wid}/submit")
def submit_for_review(wid: int, request: Request, db: DBSession = Depends(get_db),
                      user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    w = _owned_draft(db, user, wid)
    if w.facts is None:
        raise HTTPException(status_code=422, detail="Build the facts before review")
    w.status = "In review"
    log_action(db, user_id=user.id, request=request, action=f"AIREPORT_SUBMIT id={w.id}")
    db.commit()
    return _out(db, user, w)


@router.post("/{wid}/review")
def review(wid: int, payload: ReviewIn, request: Request, db: DBSession = Depends(get_db),
           user: User = Depends(require_active_user)) -> dict:
    """Human review: someone other than the author, with a review permission, approves or returns it."""
    ensure_staff(user)
    w = _get(db, user, wid)
    if w.status != "In review":
        raise HTTPException(status_code=409, detail="The workstream is not awaiting review")
    if w.owner_id == user.id:
        raise HTTPException(status_code=403, detail="Authors cannot review their own report")
    if not _is_reviewer(user):
        raise HTTPException(status_code=403, detail="Your role does not review reports")
    if payload.decision == "approve" and not payload.facts_checked:
        raise HTTPException(status_code=422, detail="Confirm the facts were checked against their sources")
    if payload.decision == "return" and len(payload.note.strip()) < 5:
        raise HTTPException(status_code=422, detail="Say what needs to change")
    w.status = "Approved" if payload.decision == "approve" else "Draft"
    w.reviewed_by, w.reviewed_at, w.review_note = user.id, utcnow(), payload.note.strip()
    log_action(db, user_id=user.id, request=request, action=f"AIREPORT_REVIEW id={w.id} decision={payload.decision}")
    db.commit()
    return _out(db, user, w)


@router.post("/{wid}/publish")
def publish(wid: int, request: Request, db: DBSession = Depends(get_db),
            user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    w = _get(db, user, wid)
    if w.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the author publishes")
    if w.status != "Approved" or w.reviewed_by is None:
        raise HTTPException(status_code=409, detail="A reviewer must approve the report before it is published")
    w.status, w.published_at = "Published", utcnow()
    log_action(db, user_id=user.id, request=request, action=f"AIREPORT_PUBLISH id={w.id} access={w.access}")
    db.commit()
    return _out(db, user, w)


@router.delete("/{wid}")
def archive(wid: int, request: Request, db: DBSession = Depends(get_db),
            user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    w = _get(db, user, wid)
    if w.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the author can archive this workstream")
    w.archived = True
    log_action(db, user_id=user.id, request=request, action=f"AIREPORT_ARCHIVE id={w.id}")
    db.commit()
    return _out(db, user, w)
