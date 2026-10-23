"""Comments, @mentions and lineage on records (audits, issues, actions, plans, reports, risks, entities).

* ``GET  /api/records/{type}/{id}/collab``     lineage, comments and the people who can be mentioned
* ``POST /api/records/{type}/{id}/comments``   post a comment; mentioned people are notified and get a Projects item
* ``POST /api/comments/{id}/withdraw``         the author withdraws a comment (kept in the audit trail)
* ``POST /api/mentions/{id}/done``             the mentioned person marks the mention handled
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import utcnow
from app.platform.collaboration import records
from app.platform.collaboration.lineage import lineage
from app.platform.collaboration.models import Comment, CommentMention
from app.platform.users.models import User

router = APIRouter(tags=["collaboration"])

# Notification links the web app can open for each record type.
_LINKABLE = {"audit", "finding", "capa", "assurance_plan", "audit_report", "erm_risk", "entity_unit",
             "risk_assessment"}


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    mention_ids: list[int] = Field(default_factory=list, max_length=20)


def _name(u: User | None) -> str:
    return (u.full_name or u.username) if u else "Former user"


def _comments(db: DBSession, record_type: str, record_id: int, user: User) -> list[dict]:
    rows = list(db.execute(select(Comment).where(Comment.record_type == record_type, Comment.record_id == record_id)
                           .order_by(Comment.created_at, Comment.id)).scalars())
    mentions: dict[int, list[CommentMention]] = {}
    if rows:
        q = select(CommentMention).where(CommentMention.comment_id.in_([r.id for r in rows]))
        for m in db.execute(q).scalars():
            mentions.setdefault(m.comment_id, []).append(m)
    people = {u.id: u for u in db.execute(select(User).where(User.id.in_(
        {r.author_id for r in rows if r.author_id} | {m.user_id for ms in mentions.values() for m in ms} or {0}))
    ).scalars()}
    out = []
    for r in rows:
        ms = mentions.get(r.id, [])
        mine = next((m for m in ms if m.user_id == user.id and m.done_at is None), None)
        out.append({"id": r.id, "author_id": r.author_id, "author": _name(people.get(r.author_id)),
                    "body": "" if r.withdrawn_at else r.body, "withdrawn": r.withdrawn_at is not None,
                    "created_at": r.created_at.isoformat(),
                    "can_withdraw": r.author_id == user.id and not r.withdrawn_at,
                    "mentions": [{"user_id": m.user_id, "name": _name(people.get(m.user_id)),
                                  "done": m.done_at is not None} for m in ms],
                    "my_open_mention": mine.id if mine else None})
    return out


def _mentionable(db: DBSession, record_type: str, obj) -> list[dict]:  # noqa: ANN001
    """Active people who may read the record (only they can be mentioned on it)."""
    out = []
    for u in db.execute(select(User).where(User.is_active.is_(True)).order_by(User.full_name, User.username)).scalars():
        if records.can_read(db, u, record_type, obj):
            out.append({"id": u.id, "name": _name(u), "username": u.username})
    return out


@router.get("/api/records/{record_type}/{record_id}/collab")
def collab(record_type: str, record_id: int, db: DBSession = Depends(get_db),
           user: User = Depends(require_active_user)) -> dict:
    obj = records.load(db, user, record_type, record_id)
    ref, title = records.name(record_type, obj)
    return {"record": {"type": record_type, "id": record_id, "ref": ref, "title": title,
                       "kind": records.LABEL.get(record_type, record_type)},
            **lineage(db, user, record_type, obj),
            "comments": _comments(db, record_type, record_id, user),
            "mentionable": _mentionable(db, record_type, obj)}


@router.post("/api/records/{record_type}/{record_id}/comments", status_code=201)
def post_comment(record_type: str, record_id: int, payload: CommentIn, request: Request,
                 db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    from app.platform.notifications.service import notify

    obj = records.load(db, user, record_type, record_id)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Write a comment")
    targets = []
    for uid in dict.fromkeys(payload.mention_ids):
        u = db.get(User, uid)
        if u is None or not u.is_active:
            raise HTTPException(status_code=422, detail="Mention active people only")
        if not records.can_read(db, u, record_type, obj):
            raise HTTPException(status_code=422, detail=f"{_name(u)} cannot open this record, so cannot be mentioned")
        targets.append(u)
    c = Comment(record_type=record_type, record_id=record_id, author_id=user.id, body=body)
    db.add(c)
    db.flush()
    ref, title = records.name(record_type, obj)
    for u in targets:
        db.add(CommentMention(comment_id=c.id, user_id=u.id))
        if u.id != user.id:
            notify(db, u.id, f"{_name(user)} mentioned you on {ref}", f"{title}\n\n{body[:500]}",
                   link_type=record_type if record_type in _LINKABLE else None, link_id=record_id)
    # Replying on the record handles the replier's own open mentions there.
    for m in db.execute(select(CommentMention).join(Comment, Comment.id == CommentMention.comment_id).where(
            Comment.record_type == record_type, Comment.record_id == record_id, CommentMention.user_id == user.id,
            CommentMention.done_at.is_(None), Comment.id != c.id)).scalars():
        m.done_at = utcnow()
    log_action(db, user_id=user.id, request=request,
               action=f"COMMENT_POST {record_type}={record_id} mentions={len(targets)}")
    db.commit()
    return {"comments": _comments(db, record_type, record_id, user)}


@router.post("/api/comments/{comment_id}/withdraw")
def withdraw(comment_id: int, request: Request, db: DBSession = Depends(get_db),
             user: User = Depends(require_active_user)) -> dict:
    c = db.get(Comment, comment_id)
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    records.load(db, user, c.record_type, c.record_id)
    if c.author_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the author can withdraw a comment")
    if c.withdrawn_at is None:
        c.withdrawn_at = utcnow()
        for m in db.execute(select(CommentMention).where(CommentMention.comment_id == c.id,
                                                         CommentMention.done_at.is_(None))).scalars():
            m.done_at = c.withdrawn_at
    log_action(db, user_id=user.id, request=request, action=f"COMMENT_WITHDRAW id={c.id} {c.record_type}={c.record_id}")
    db.commit()
    return {"comments": _comments(db, c.record_type, c.record_id, user)}


@router.post("/api/mentions/{mention_id}/done")
def mention_done(mention_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    m = db.get(CommentMention, mention_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mention not found")
    if m.done_at is None:
        m.done_at = utcnow()
        db.commit()
    return {"ok": True}


def open_mentions(db: DBSession, user: User) -> list[dict]:
    """The person's unhandled mentions, for Projects (records they can no longer read are left out)."""
    rows = db.execute(select(CommentMention, Comment).join(Comment, Comment.id == CommentMention.comment_id).where(
        CommentMention.user_id == user.id, CommentMention.done_at.is_(None), Comment.withdrawn_at.is_(None),
        Comment.author_id != user.id).order_by(Comment.created_at.desc()).limit(200)).all()
    out = []
    for m, c in rows:
        model = records.model_for(c.record_type)
        obj = db.get(model, c.record_id) if model else None
        if not records.can_read(db, user, c.record_type, obj):
            continue
        ref, title = records.name(c.record_type, obj)
        author = db.get(User, c.author_id) if c.author_id else None
        out.append({"mention_id": m.id, "record_type": c.record_type, "record_id": c.record_id, "ref": ref,
                    "title": title, "author": _name(author), "body": c.body[:300], "at": c.created_at,
                    "audit_id": obj.id if c.record_type == "audit" else getattr(obj, "audit_id", None)})
    return out

