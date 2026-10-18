"""Administration landing page: access by area, verified summaries only, backup outcomes recorded."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.enums import Role, utcnow
from app.platform.history.models import AuditLog
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, job=None, active=True):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    user.is_active = active
    db.commit()
    return user


def test_overview_access_follows_permissions(client, db):
    auditor = _u(db, "adm_aud", job="auditor")
    login(client, auditor.username)
    assert client.get("/api/admin/overview").status_code == 403
    client_user = _u(db, "adm_cli", Role.Auditee, job="audit_client")
    login(client, client_user.username)
    assert client.get("/api/admin/overview").status_code == 403
    assert client.get("/api/admin/policies").status_code == 403

    admin = _u(db, "adm_adm", Role.Admin, job="admin")
    login(client, admin.username)
    r = client.get("/api/admin/overview")
    assert r.status_code == 200, r.text
    d = r.json()
    assert {"users", "settings", "activity", "imports", "policies", "backups"} <= set(d["areas"])
    assert {"users", "recent_changes", "security", "imports", "backups", "policies"} <= set(d)


def test_users_summary_is_computed_from_records(client, db):
    admin = _u(db, "adm_sum", Role.Admin, job="admin")
    pending = _u(db, "adm_pend", Role.Auditee, active=False)
    dormant = _u(db, "adm_dorm")
    dormant.created_at = utcnow() - timedelta(days=200)
    db.add(AuditLog(user_id=dormant.id, username=dormant.username, action_performed="LOGIN",
                    timestamp=utcnow() - timedelta(days=120), category="authentication", outcome="success"))
    fresh = _u(db, "adm_fresh")  # new account, never signed in: not "inactive" yet
    locked = _u(db, "adm_lock")
    locked.locked_until = utcnow() + timedelta(minutes=10)
    db.commit()
    login(client, admin.username)
    u = client.get("/api/admin/overview").json()["users"]
    assert pending.id in [p["id"] for p in u["pending"]]
    inactive_ids = {i["id"] for i in u["inactive"]} if u["inactive_count"] <= 10 else None
    if inactive_ids is not None:
        assert dormant.id in inactive_ids and fresh.id not in inactive_ids and admin.id not in inactive_ids
    assert any(x["id"] == locked.id for x in u["locked"])
    assert u["active"] >= 3 and u["admins_active"] >= 1


def test_backup_status_reports_files_checks_and_failures(client, db):
    admin = _u(db, "adm_bk", Role.Admin, job="admin")
    h = csrf_headers(login(client, admin.username))
    assert client.post("/api/admin/backup", headers=h).status_code == 200
    b = client.get("/api/admin/overview").json()["backups"]
    assert b["latest"] and b["latest"]["size_bytes"] > 0 and b["latest"]["age_hours"] < 1
    # Each backup is checked when it finishes; attachments are included by default.
    assert b["verified"]["outcome"] == "passed" and b["includes_attachments"] is True
    assert b["count"] >= 1 and b["retention"] >= 1

    # A failed scheduled backup is recorded in the audit trail and surfaces here.
    from app.main import _scheduled_backup

    def boom(_db):
        raise OSError("disk full")

    _scheduled_backup(boom)
    db.rollback()
    row = db.execute(select(AuditLog).where(AuditLog.action_performed.like("BACKUP_FAILED%"))
                     .order_by(AuditLog.id.desc())).scalars().first()
    assert row is not None and row.outcome == "failure" and row.category == "system"
    b = client.get("/api/admin/overview").json()["backups"]
    assert b["last_failure"] and b["last_failure"]["action"].startswith("BACKUP_FAILED scheduled")

    # A successful scheduled backup is recorded too.
    from app.platform.backups.service import create_backup

    _scheduled_backup(create_backup)
    db.rollback()
    ok = db.execute(select(AuditLog).where(AuditLog.action_performed.like("BACKUP_CREATE scheduled%"))
                    .order_by(AuditLog.id.desc())).scalars().first()
    assert ok is not None and ok.user_id is None


def test_policies_show_the_limits_in_force(client, db):
    from app.core.config import settings

    admin = _u(db, "adm_pol", Role.Admin, job="admin")
    login(client, admin.username)
    p = client.get("/api/admin/policies").json()
    assert p["attachments"]["max_upload_mb"] == settings.max_upload_mb
    assert set(p["attachments"]["allowed_extensions"]) == settings.allowed_extensions
    assert p["imports"]["max_rows"] == 2000 and p["imports"]["all_or_nothing"] is True
    assert p["sessions"]["max_failed_sign_ins"] == settings.login_max_attempts


def test_recent_changes_lists_administrative_actions(client, client2, db):
    admin = _u(db, "adm_rc", Role.Admin, job="super_admin")
    h = csrf_headers(login(client, admin.username))
    target = _u(db, "adm_tgt")
    r = client.patch(f"/api/users/{target.id}", json={"full_name": "Renamed Person"}, headers=h)
    assert r.status_code == 200, r.text
    changes = client.get("/api/admin/overview").json()["recent_changes"]
    assert any(c["action"].startswith("USER_UPDATE") for c in changes)
    del client2
