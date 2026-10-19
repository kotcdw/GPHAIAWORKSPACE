"""Administration phase 5: audit and activity log. Plain-language events, the protection check, your own account
activity, lockout alerts to administrators and the export."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.audit_describe import describe
from app.core.enums import Role
from tests.conftest import login, make_user


def _u(db, prefix, role=Role.Auditor, job=None):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def test_event_names_are_plain_language():
    assert describe("LOGIN") == ("Signed in", "")
    assert describe("LOGIN_FAILED wrong_password username=x")[0] == "Failed sign-in"
    assert describe("CONFIG_UPDATE date_format=DD MMM YYYY") == ("Changed settings", "date_format=DD MMM YYYY")
    assert describe("FINDING_CREATE id=4") == ("Finding created", "id=4")
    assert describe("IMPORT_ORG_UNITS created=2")[0] == "Imported org units"
    assert describe("ARA_SCORE id=1")[0] == "Audit risk assessment score"


def test_register_shows_events_and_the_trail_is_protected(client, db):
    admin = _u(db, "al_adm", Role.Admin, job="admin")
    login(client, admin.username)
    page = client.get("/api/audit-logs/register?q=" + admin.username).json()
    assert page["items"] and all(r["event"] for r in page["items"])
    assert any(r["event"] == "Signed in" for r in page["items"])
    g = client.get("/api/audit-logs/integrity").json()
    assert g["protected"] is True and g["entries"] > 0
    assert {t["table"] for t in g["tables"]} == {"audit_logs", "workflow_transitions", "app_config_history",
                                                 "import_runs", "backup_checks", "report_revisions"}
    aud = _u(db, "al_aud", job="auditor")
    login(client, aud.username)
    assert client.get("/api/audit-logs/integrity").status_code == 403


def test_my_activity_shows_own_sign_ins_and_failed_attempts(client, client2, db):
    person = _u(db, "al_me")
    r = client2.post("/api/auth/login", json={"username": person.username, "password": "not-the-password"})
    assert r.status_code == 401
    login(client, person.username)
    items = client.get("/api/auth/me/activity").json()["items"]
    events = [i["event"] for i in items]
    assert events[0] == "Signed in" and "Failed sign-in" in events
    assert any(i["outcome"] == "failure" for i in items)
    # Someone else's activity never appears.
    other = _u(db, "al_other")
    login(client2, other.username)
    assert all(i["event"] != "Failed sign-in" for i in client2.get("/api/auth/me/activity").json()["items"])


def test_lockout_alerts_account_administrators(client, db):
    from app.core.config import settings
    from app.platform.notifications.models import Notification

    admin = _u(db, "al_alert", Role.Admin, job="admin")
    victim = _u(db, "al_victim")
    for _ in range(settings.login_max_attempts):
        client.post("/api/auth/login", json={"username": victim.username, "password": "wrong-password-1"})
    db.expire_all()
    notes = db.execute(select(Notification).where(Notification.user_id == admin.id,
                                                  Notification.title.like("Account locked%"))).scalars().all()
    assert notes and victim.username in notes[0].body


def test_export_has_event_and_local_time(client, db):
    admin = _u(db, "al_exp", Role.Admin, job="admin")
    login(client, admin.username)
    r = client.get(f"/api/audit-logs/export.csv?q={admin.username}")
    assert r.status_code == 200
    header = r.text.lstrip("﻿").splitlines()[0]
    assert "Local time" in header and "Event" in header and "Action (as recorded)" in header
