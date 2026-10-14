"""GPHA review chain: Auditor -> Unit Head -> Audit Manager -> PIA -> GM Audit.

Managers carry an approval level (``users.review_level``). Reports and working papers pass through the configured
levels in order; each stage is signed by someone at that level (or, when allowed, at a higher level covering an
absence). Nobody signs two stages of the same document, and the preparer signs none. The GM Audit (CAE) gives the
final approval of reports, separately from the chain.

A document's progress is kept as a JSON trail: [{"level": "Unit Head", "user_id": 7, "name": "...", "at": "..."}].
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.enums import ReviewLevel, utcnow

ORDER = [ReviewLevel.UnitHead, ReviewLevel.Manager, ReviewLevel.PIA, ReviewLevel.CAE]
RANK = {lvl: n for n, lvl in enumerate(ORDER, start=1)}
LABELS = {ReviewLevel.UnitHead: "Unit Head", ReviewLevel.Manager: "Audit Manager", ReviewLevel.PIA: "PIA",
          ReviewLevel.CAE: "GM Audit (CAE)"}
BY_LABEL = {"unit head": ReviewLevel.UnitHead, "audit manager": ReviewLevel.Manager, "manager": ReviewLevel.Manager,
            "pia": ReviewLevel.PIA, "port internal auditor": ReviewLevel.PIA}


def label(level: ReviewLevel | str | None) -> str:
    if level is None:
        return "-"
    if isinstance(level, str):
        try:
            level = ReviewLevel(level)
        except ValueError:
            return level
    return LABELS[level]


def chain(kind: str) -> list[ReviewLevel]:
    """The configured levels for ``report`` or ``workpaper`` in GPHA order."""
    from app.core.appconfig import cfg

    names = cfg(f"{kind}_review_chain") or []
    levels = {BY_LABEL[n.strip().lower()] for n in names if n.strip().lower() in BY_LABEL}
    return [lvl for lvl in ORDER if lvl in levels]


def trail(raw: str | None) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def signer_ids(raw: str | None) -> set[int]:
    return {int(t["user_id"]) for t in trail(raw) if t.get("user_id")}


def may_sign(user, stage: ReviewLevel | None, raw_trail: str | None, preparer_id: int | None) -> tuple[bool, str]:  # noqa: ANN001
    """Whether ``user`` may sign ``stage``; returns (allowed, reason when not)."""
    from app.core.appconfig import cfg

    if stage is None:
        return False, "Nothing is waiting for review"
    if user.id == preparer_id:
        return False, "The preparer cannot review their own work"
    if user.id in signer_ids(raw_trail):
        return False, "You have already signed an earlier stage of this document"
    level = user.review_level
    if level is None:
        return False, f"Waiting for the {label(stage)} review: your account has no approval level"
    if level == stage:
        return True, ""
    if cfg("review_higher_level_may_cover") and RANK.get(level, 0) > RANK[stage]:
        return True, ""
    return False, f"Waiting for the {label(stage)} review"


def sign(raw_trail: str | None, user, stage: ReviewLevel) -> str:  # noqa: ANN001
    entries = trail(raw_trail)
    entries.append({"level": label(stage), "user_id": user.id, "name": user.full_name or user.username,
                    "acting_as": label(user.review_level) if user.review_level != stage else None,
                    "at": utcnow().isoformat(timespec="seconds")})
    return json.dumps(entries)


def next_stage(kind: str, current: ReviewLevel | None) -> ReviewLevel | None:
    levels = chain(kind)
    if current is None:
        return levels[0] if levels else None
    later = [lvl for lvl in levels if RANK[lvl] > RANK[current]]
    return later[0] if later else None


def reviewers_for(db: DBSession, stage: ReviewLevel) -> list[int]:
    """Active staff at the stage level (or, when nobody holds it and cover is allowed, the next level up)."""
    from app.core.appconfig import cfg
    from app.platform.users.models import User

    staff = list(db.execute(select(User).where(User.is_active.is_(True), User.review_level.is_not(None))).scalars())
    exact = [u.id for u in staff if u.review_level == stage]
    if exact or not cfg("review_higher_level_may_cover"):
        return exact
    for lvl in ORDER[RANK[stage]:]:
        ids = [u.id for u in staff if u.review_level == lvl]
        if ids:
            return ids
    return []
