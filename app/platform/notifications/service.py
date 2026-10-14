"""Notification service: in-app rows plus best-effort e-mail.

``notify`` adds a notification to the caller's transaction. E-mails are only
queued, and are sent after that transaction commits (never for work that was
rolled back). E-mail is skipped silently when ``GPHA_SMTP_HOST`` is not set,
so the in-app bell always works on its own.
"""

from __future__ import annotations

import logging
import smtplib
import threading
from collections.abc import Iterable
from email.message import EmailMessage

from sqlalchemy import event, select
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.enums import ReviewLevel, Role
from app.platform.notifications.models import Notification
from app.platform.users.models import User

logger = logging.getLogger("gpha")

_PENDING = "pending_emails"

# Where a notification's link opens in the web app (hash routes).
_LINK_LABEL = {
    "audit": "audit",
    "audit_report": "audit report",
    "capa": "Remediation",
    "finding": "finding",
    "task": "task",
    "control_test": "control test",
    "assurance_plan": "Assurance Plan",
}


def email_enabled() -> bool:
    return bool(settings.smtp_host)


def notify(
    db: DBSession,
    user_id: int | None,
    title: str,
    body: str = "",
    *,
    link_type: str | None = None,
    link_id: int | None = None,
    email: bool = True,
) -> Notification | None:
    """Notify one user (no-op for ``None`` or inactive users)."""
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    note = Notification(
        user_id=user_id, title=title[:255], body=body, link_type=link_type, link_id=link_id, is_read=False
    )
    db.add(note)
    db.flush()
    if email and email_enabled() and user.email:
        note.emailed = True
        db.info.setdefault(_PENDING, []).append((user.email, title, _email_body(body, link_type, link_id)))
    return note


def notify_many(db: DBSession, user_ids: Iterable[int | None], title: str, body: str = "", **kw) -> int:  # noqa: ANN003
    sent = 0
    for uid in dict.fromkeys(u for u in user_ids if u is not None):  # de-duplicate, keep order
        if notify(db, uid, title, body, **kw) is not None:
            sent += 1
    return sent


def user_ids_with_level(db: DBSession, *levels: ReviewLevel) -> list[int]:
    return list(
        db.execute(
            select(User.id).where(
                User.review_level.in_(levels), User.is_active.is_(True), User.role.in_((Role.Admin, Role.Auditor))
            )
        ).scalars()
    )


def user_id_by_email(db: DBSession, email: str | None) -> int | None:
    from app.core.tasksvc import _user_id_by_email

    return _user_id_by_email(db, email)


def _email_body(body: str, link_type: str | None, link_id: int | None) -> str:
    lines = [body or "", ""]
    if link_type and link_id and settings.app_base_url:
        label = _LINK_LABEL.get(link_type, link_type.replace("_", " "))
        lines.append(f"Open the {label}: {settings.app_base_url.rstrip('/')}/#open/{link_type}/{link_id}")
    lines.append("")
    lines.append(f"- {settings.app_name} (automatic message, do not reply)")
    return "\n".join(lines)


def _send(messages: list[tuple[str, str, str]]) -> None:
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            for to, subject, text in messages:
                msg = EmailMessage()
                msg["From"] = settings.smtp_from
                msg["To"] = to
                msg["Subject"] = f"[GPHA Audit] {subject}"
                msg.set_content(text)
                smtp.send_message(msg)
    except Exception:  # noqa: BLE001 - e-mail is best effort; the in-app bell already has it
        logger.exception("Could not send %d notification e-mail(s)", len(messages))


@event.listens_for(DBSession, "after_commit")
def _flush_emails(session: DBSession) -> None:
    pending = session.info.pop(_PENDING, None)
    if pending:
        threading.Thread(target=_send, args=(pending,), daemon=True).start()


@event.listens_for(DBSession, "after_rollback")
def _drop_emails(session: DBSession) -> None:
    session.info.pop(_PENDING, None)
