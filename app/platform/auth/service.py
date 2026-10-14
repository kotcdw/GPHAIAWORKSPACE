"""Session helpers shared by the auth and user-admin routes."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.platform.auth.models import Session as UserSession


def revoke_sessions(db: DBSession, user_id: int, *, keep_session_id: int | None = None) -> int:
    """Revoke all of a user's active sessions (optionally keeping one). Returns the count."""
    stmt = select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked.is_(False))
    count = 0
    for sess in db.execute(stmt).scalars():
        if sess.id == keep_session_id:
            continue
        sess.revoked = True
        count += 1
    return count
