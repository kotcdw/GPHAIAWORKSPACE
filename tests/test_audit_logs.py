"""Audit-trail tests: recording and immutability."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user

# SQLite aborts the statement with IntegrityError; MySQL's SIGNAL raises an
# OperationalError (errno 1644). Both dialects enforce the same immutability.
_APPEND_ONLY_ERRORS = (IntegrityError, OperationalError)


def test_actions_are_logged(client, db):
    make_user(db, "logger", Role.Admin)
    csrf = login(client, "logger")
    client.post("/api/audits", json={"title": "Logged audit"}, headers=csrf_headers(csrf))

    logs = client.get("/api/audit-logs")
    assert logs.status_code == 200
    actions = [entry["action_performed"] for entry in logs.json()]
    assert any("LOGIN" in action for action in actions)
    assert any("AUDIT_CREATE" in action for action in actions)


def test_audit_log_cannot_be_updated_or_deleted(client, db):
    make_user(db, "admin2", Role.Admin)
    csrf = login(client, "admin2")
    client.post("/api/audits", json={"title": "Immutable"}, headers=csrf_headers(csrf))

    with pytest.raises(_APPEND_ONLY_ERRORS):
        db.execute(text("UPDATE audit_logs SET action_performed = 'tampered'"))
        db.commit()
    db.rollback()

    with pytest.raises(_APPEND_ONLY_ERRORS):
        db.execute(text("DELETE FROM audit_logs"))
        db.commit()
    db.rollback()


def test_audit_logs_admin_only(client, db):
    make_user(db, "plainauditee", Role.Auditee)
    login(client, "plainauditee")
    assert client.get("/api/audit-logs").status_code == 403
