"""Helpers for writing the immutable audit trail."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.history.models import AuditLog


def client_ip(request) -> str | None:  # noqa: ANN001
    """Best-effort extraction of the client IP address."""
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None)


def log_action(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    request=None,  # noqa: ANN001
    commit: bool = False,
) -> AuditLog:
    """Append an entry to the audit trail.

    The entry is added to the current transaction. Callers usually commit
    together with their own change. Pass ``commit=True`` to commit immediately.
    """
    entry = AuditLog(
        user_id=user_id,
        action_performed=action[:500],
        ip_address=client_ip(request),
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry