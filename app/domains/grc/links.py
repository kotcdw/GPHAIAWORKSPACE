"""Links between GRC records: risk <-> control, requirement <-> control, asset <-> risk, policy <-> requirement...

One table holds every link, stored once in a canonical direction, and read from either end. Each end is a
(type, id) pair; ``describe`` turns it into a reference and title for display.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, and_, or_, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import Session as DBSession

from app.core.audit import log_action
from app.core.database import Base, get_db
from app.core.deps import require_active_user
from app.core.enums import utcnow
from app.platform.users.models import User

LINK_TYPES = ("objective", "risk", "control", "requirement", "policy", "asset", "unit")
# Who may add or remove a link touching this type.
EDIT_PERMS = {"objective": "grc.risk", "risk": "grc.risk", "control": "grc.compliance",
              "requirement": "grc.compliance", "policy": "grc.policy", "asset": "grc.assets", "unit": "grc.risk"}


class GrcLink(Base):
    __tablename__ = "grc_links"
    __table_args__ = (UniqueConstraint("a_type", "a_id", "b_type", "b_id", name="uq_grc_links"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    a_type: Mapped[str] = mapped_column(String(20), nullable=False)
    a_id: Mapped[int] = mapped_column(Integer, nullable=False)
    b_type: Mapped[str] = mapped_column(String(20), nullable=False)
    b_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


def _canon(t1: str, i1: int, t2: str, i2: int) -> tuple[str, int, str, int]:
    return (t1, i1, t2, i2) if (t1, i1) <= (t2, i2) else (t2, i2, t1, i1)


def _model(kind: str):  # noqa: ANN202
    if kind == "objective":
        from app.domains.grc.risk.models import StrategicObjective as M
    elif kind == "risk":
        from app.domains.grc.risk.models import EnterpriseRisk as M
    elif kind == "control":
        from app.domains.audit.frameworks.models import LibraryControl as M
    elif kind == "requirement":
        from app.domains.grc.compliance.models import Requirement as M
    elif kind == "policy":
        from app.domains.grc.policies.models import Policy as M
    elif kind == "asset":
        from app.domains.grc.assets.models import Asset as M
    elif kind == "unit":
        from app.domains.assurance.planning.models import EntityUnit as M
    else:
        raise HTTPException(status_code=422, detail=f"Unknown link type {kind}")
    return M


def describe(db: DBSession, kind: str, rec_id: int) -> dict | None:
    rec = db.get(_model(kind), rec_id)
    if rec is None:
        return None
    if kind == "control":
        from app.domains.audit.frameworks.models import Framework

        fw = db.get(Framework, rec.framework_id)
        ref = f"{fw.code if fw else ''} {rec.ref}".strip()
        extra = rec.control_type.value
    elif kind == "unit":
        ref, extra = getattr(rec, "code", None) or f"U-{rec.id}", getattr(rec, "category", "") or ""
    elif kind == "requirement":
        ref, extra = rec.ref, rec.status
    else:
        ref, extra = rec.ref, getattr(rec, "status", "")
    title = getattr(rec, "title", None) or getattr(rec, "name", "")
    return {"type": kind, "id": rec.id, "ref": ref, "title": title, "extra": extra}


def linked(db: DBSession, kind: str, rec_id: int, only: str | None = None) -> list[dict]:
    rows = db.execute(select(GrcLink).where(or_(and_(GrcLink.a_type == kind, GrcLink.a_id == rec_id),
                                                and_(GrcLink.b_type == kind, GrcLink.b_id == rec_id)))).scalars()
    out = []
    for r in rows:
        other = (r.b_type, r.b_id) if (r.a_type, r.a_id) == (kind, rec_id) else (r.a_type, r.a_id)
        if only and other[0] != only:
            continue
        d = describe(db, *other)
        if d:
            out.append({**d, "link_id": r.id})
    return sorted(out, key=lambda d: (d["type"], d["ref"] or ""))


def linked_ids(db: DBSession, kind: str, rec_id: int, other: str) -> list[int]:
    return [d["id"] for d in linked(db, kind, rec_id, other)]


def add_link(db: DBSession, t1: str, i1: int, t2: str, i2: int, user_id: int | None) -> GrcLink:
    for k, i in ((t1, i1), (t2, i2)):
        if k not in LINK_TYPES:
            raise HTTPException(status_code=422, detail=f"Unknown link type {k}")
        if db.get(_model(k), i) is None:
            raise HTTPException(status_code=404, detail=f"{k.capitalize()} {i} not found")
    if (t1, i1) == (t2, i2):
        raise HTTPException(status_code=422, detail="A record cannot be linked to itself")
    a_t, a_i, b_t, b_i = _canon(t1, i1, t2, i2)
    existing = db.execute(select(GrcLink).where(GrcLink.a_type == a_t, GrcLink.a_id == a_i, GrcLink.b_type == b_t,
                                                GrcLink.b_id == b_i)).scalar_one_or_none()
    if existing:
        return existing
    link = GrcLink(a_type=a_t, a_id=a_i, b_type=b_t, b_id=b_i, created_by=user_id)
    db.add(link)
    db.flush()
    return link


def set_links(db: DBSession, kind: str, rec_id: int, other: str, ids: list[int], user_id: int | None) -> None:
    """Make the links from (kind, rec_id) to records of type ``other`` exactly ``ids``."""
    want = set(ids)
    for d in linked(db, kind, rec_id, other):
        if d["id"] not in want:
            db.delete(db.get(GrcLink, d["link_id"]))
        else:
            want.discard(d["id"])
    for i in want:
        add_link(db, kind, rec_id, other, i, user_id)
    db.flush()


def drop_links(db: DBSession, kind: str, rec_id: int) -> None:
    for r in db.execute(select(GrcLink).where(or_(and_(GrcLink.a_type == kind, GrcLink.a_id == rec_id),
                                                  and_(GrcLink.b_type == kind, GrcLink.b_id == rec_id)))).scalars():
        db.delete(r)


# ---------------------------------------------------------------- API

router = APIRouter(prefix="/api/grc/links", tags=["risk & compliance"])


class LinkIn(BaseModel):
    from_type: str
    from_id: int
    to_type: str
    to_id: int


def _can_edit(user: User, *kinds: str) -> bool:
    from app.core.permissions import has_perm

    return has_perm(user, "grc.manage") or any(has_perm(user, EDIT_PERMS.get(k, "grc.manage")) for k in kinds)


@router.get("/{kind}/{rec_id}")
def get_links(kind: str, rec_id: int, db: DBSession = Depends(get_db),
              user: User = Depends(require_active_user)) -> list[dict]:
    from app.core.permissions import has_perm

    if not has_perm(user, "grc.view", "grc.manage", "grc.risk", "grc.compliance", "grc.policy", "grc.assets"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if describe(db, kind, rec_id) is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return linked(db, kind, rec_id)


@router.post("", status_code=201)
def create_link(payload: LinkIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(require_active_user)) -> dict:
    if not _can_edit(user, payload.from_type, payload.to_type):
        raise HTTPException(status_code=403, detail="Your role does not allow changing these links")
    link = add_link(db, payload.from_type, payload.from_id, payload.to_type, payload.to_id, user.id)
    log_action(db, user_id=user.id, request=request,
               action=f"GRC_LINK {payload.from_type}:{payload.from_id} -> {payload.to_type}:{payload.to_id}")
    db.commit()
    return {"id": link.id}


@router.delete("/{link_id}")
def delete_link(link_id: int, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(require_active_user)) -> dict:
    link = db.get(GrcLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    if not _can_edit(user, link.a_type, link.b_type):
        raise HTTPException(status_code=403, detail="Your role does not allow changing these links")
    db.delete(link)
    log_action(db, user_id=user.id, request=request,
               action=f"GRC_UNLINK {link.a_type}:{link.a_id} -> {link.b_type}:{link.b_id}")
    db.commit()
    return {"ok": True}



people_router = APIRouter(prefix="/api/grc", tags=["risk & compliance"])


@people_router.get("/people")
def people(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    """Active users for owner / approver / audience pickers in the risk & compliance apps."""
    from app.core.permissions import JOB_ROLES, has_perm, job_role_of
    from app.domains.grc.common import GRC_PERMS

    if not has_perm(user, *GRC_PERMS):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    names = {r.code: r.name for r in JOB_ROLES}
    rows = db.execute(select(User).where(User.is_active.is_(True)).order_by(User.full_name, User.username)).scalars()
    return {"people": [{"id": u.id, "name": u.full_name or u.username, "job_role": names.get(job_role_of(u)),
                        "tier": u.role.value} for u in rows],
            "job_roles": [{"code": r.code, "name": r.name} for r in JOB_ROLES]}


@people_router.get("/lookup/{kind}")
def lookup(kind: str, q: str = "", db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list:
    """Search records of one link type for the link picker (reference and title)."""
    from app.core.permissions import has_perm
    from app.domains.grc.common import GRC_PERMS

    if not has_perm(user, *GRC_PERMS):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    model = _model(kind)
    stmt = select(model)
    text_cols = [c for c in ("title", "name", "ref", "code") if hasattr(model, c)
                 and not isinstance(getattr(model, c), property)]
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(*[getattr(model, c).like(like) for c in text_cols]))
    out = []
    for rec in db.execute(stmt.limit(60)).scalars():
        d = describe(db, kind, rec.id)
        if d:
            out.append(d)
    return sorted(out, key=lambda d: d["ref"] or "")
