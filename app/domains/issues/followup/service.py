"""Overdue action escalation (IIA GIAS 15.2 - monitoring action plans).

Levels, raised once each as an action stays overdue:
  1 - overdue: the owner (and the auditor who raised it) are notified;
  2 - ``escalate_manager_days`` overdue: Audit Managers are notified;
  3 - ``escalate_cae_days`` overdue: the CAE is notified;
  4 - ``escalate_committee_days`` overdue: reported to the Audit Committee (CAE and Admins notified).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.enums import CapaStatus, ReviewLevel, utcnow
from app.domains.issues.capa.models import Capa
from app.platform.notifications.service import notify_many, user_id_by_email, user_ids_with_level

LEVEL_NAMES = {0: "Not overdue", 1: "Owner", 2: "Audit Manager", 3: "CAE", 4: "Audit Committee"}


@dataclass
class OverdueItem:
    capa: Capa
    days_overdue: int
    due_level: int


def due_level(days_overdue: int) -> int:
    if days_overdue <= 0:
        return 0
    if days_overdue >= cfg("escalate_committee_days"):
        return 4
    if days_overdue >= cfg("escalate_cae_days"):
        return 3
    if days_overdue >= cfg("escalate_manager_days"):
        return 2
    return 1


def overdue_actions(db: DBSession, now: datetime | None = None) -> list[OverdueItem]:
    now = now or utcnow()
    rows = db.execute(
        select(Capa).where(
            Capa.status != CapaStatus.Closed, Capa.due_date.is_not(None), Capa.due_date < now
        ).order_by(Capa.due_date)
    ).scalars().all()
    items = []
    for capa in rows:
        days = (now - capa.due_date).days
        days = max(days, 1)
        items.append(OverdueItem(capa=capa, days_overdue=days, due_level=due_level(days)))
    return items


def run_escalations(db: DBSession, now: datetime | None = None) -> int:
    """Raise each overdue action to its due level once; return how many moved."""
    if not cfg("escalation_enabled"):
        return 0
    now = now or utcnow()
    moved = 0
    for item in overdue_actions(db, now):
        capa = item.capa
        if item.due_level <= (capa.escalation_level or 0):
            continue
        owner = user_id_by_email(db, capa.owner_email)
        title = f"Overdue action {capa.capa_ref}: {item.days_overdue} days past due"
        body = (
            f"{capa.title}\nOwner: {capa.owner_email or 'not assigned'}\n"
            f"Due: {capa.due_date:%d %b %Y}. Escalation level: {LEVEL_NAMES[item.due_level]}."
        )
        try:  # the owner can be left out of reminders for one action (Actions › Add › Reminders)
            reminders = json.loads(capa.custom_fields or "{}").get("reminders", True) is not False
        except ValueError:
            reminders = True
        recipients: list[int | None] = [owner if reminders else None, capa.created_by]
        if item.due_level >= 2:
            recipients += user_ids_with_level(db, ReviewLevel.Manager)
        if item.due_level >= 3:
            recipients += user_ids_with_level(db, ReviewLevel.CAE)
        if item.due_level >= 4:
            from sqlalchemy import select as _select

            from app.core.enums import Role
            from app.platform.users.models import User

            recipients += list(db.execute(_select(User.id).where(User.role == Role.Admin,
                                                                 User.is_active.is_(True))).scalars())
            title = f"For the Audit Committee - {title}"
        notify_many(db, recipients, title, body, link_type="capa", link_id=capa.id)
        capa.escalation_level = item.due_level
        capa.last_escalated_at = now
        from app.domains.issues.capa.timeline import add_event

        add_event(db, capa, "escalation", user_id=None,
                  text=f"{item.days_overdue} days overdue: escalated to {LEVEL_NAMES[item.due_level]}")
        log_action(db, user_id=None, action=f"ESCALATION_RAISED remediation id={capa.id} level={item.due_level}",
                   entity_type="remediation", entity_id=capa.id)
        moved += 1
    db.commit()
    return moved
