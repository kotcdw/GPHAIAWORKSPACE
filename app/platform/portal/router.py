"""Task Manager: one simple page for business users (control owners, risk owners, auditees, policy readers).

Each domain contributes the work waiting for the signed-in person through a small ``portal`` module exposing
``items(db, user) -> list[dict]``. The portal never grants access by itself: every action still goes through the
owning module's API and its own checks.

Item shape: {section, kind, id, ref, title, detail, due, overdue, status, action, open: {type, id}}.
"""

from __future__ import annotations

import importlib
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.core.database import get_db
from app.core.deps import require_active_user
from app.platform.users.models import User

router = APIRouter(prefix="/api/portal", tags=["task manager"])
logger = logging.getLogger("gpha.portal")

PROVIDERS = (
    "app.domains.grc.portal",
    "app.domains.audit.portal",
    "app.domains.issues.portal",
    "app.platform.tasks.portal",
    "app.domains.analytics.portal",
    "app.domains.work.portal",
)
SECTION_ORDER = ["Attest to policies", "Questionnaires", "Evidence requests", "Agreed actions", "Exceptions to resolve",
                 "Assess your risks", "Record indicators", "Assess compliance", "Third-party due diligence", "Tasks"]


def _due(value) -> str | None:  # noqa: ANN001
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat() if isinstance(value, date) else str(value)


def collect(db: DBSession, user: User) -> list[dict]:
    out: list[dict] = []
    for name in PROVIDERS:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError:
            continue
        try:
            for item in module.items(db, user):
                item["due"] = _due(item.get("due"))
                item.setdefault("overdue", bool(item["due"] and item["due"] < date.today().isoformat()))
                out.append(item)
        except Exception:  # noqa: BLE001 - one broken provider must not hide the rest of the page
            logger.exception("Task Manager provider %s failed", name)
            db.rollback()
    return out


@router.get("")
def my_work(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    items = collect(db, user)
    sections: dict[str, list[dict]] = {}
    for item in items:
        sections.setdefault(item["section"], []).append(item)
    order = {s: n for n, s in enumerate(SECTION_ORDER)}
    for rows in sections.values():
        rows.sort(key=lambda i: (not i["overdue"], i["due"] or "9999", i["ref"] or ""))
    return {
        "user": user.full_name or user.username,
        "total": len(items),
        "overdue": sum(1 for i in items if i["overdue"]),
        "due_this_week": sum(1 for i in items if i["due"] and not i["overdue"]
                             and (date.fromisoformat(i["due"]) - date.today()).days <= 7),
        "sections": [{"name": s, "items": sections[s]} for s in sorted(sections, key=lambda s: order.get(s, 99))],
    }


@router.get("/count")
def my_count(db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    items = collect(db, user)
    return {"total": len(items), "overdue": sum(1 for i in items if i["overdue"])}
