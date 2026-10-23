"""Tests for the internal-control hardening (scan findings, Oct 2026).

Covers: workflow-enforced e-sign closure, segregation of duties, evidence
retention (no destructive deletes), append-only history tables, Auditee
scoping, login lockout, session revocation, encrypted backups and uploads,
and the production configuration guard.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import settings
from app.core.crypto import decrypt
from app.core.enums import Role
from app.domains.audit.audits.models import WorkingPaper
from app.platform.users.models import User
from tests.conftest import csrf_headers, decide_topicals, login, make_user

PASSWORD = "Passw0rd!"


def _audit(client, csrf, title="Control audit"):
    response = client.post("/api/audits", json={"title": title}, headers=csrf_headers(csrf))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _to_review(client, csrf, audit_id):
    for step in ("In Progress", "Review"):
        r = client.patch(f"/api/audits/{audit_id}", json={"status": step}, headers=csrf_headers(csrf))
        assert r.status_code == 200, r.text


# ------------------------------------------------------------------ workflow + SoD


def test_audit_cannot_be_created_closed(client, db):
    make_user(db, "ctl_a1", Role.Auditor)
    csrf = login(client, "ctl_a1")
    r = client.post("/api/audits", json={"title": "x", "status": "Closed"}, headers=csrf_headers(csrf))
    assert r.status_code == 400


def test_close_requires_review(client, client2, db):
    make_user(db, "ctl_prep", Role.Auditor)
    make_user(db, "ctl_signer", Role.Admin)
    prep, admin = login(client, "ctl_prep"), login(client2, "ctl_signer")
    audit_id = _audit(client, prep)
    early = client2.post(f"/api/audits/{audit_id}/close", json={"password": PASSWORD}, headers=csrf_headers(admin))
    assert early.status_code == 409
    not_review = client.post(f"/api/audits/{audit_id}/in-approval", headers=csrf_headers(prep))
    assert not_review.status_code == 409


def test_preparer_cannot_sign_off_own_audit(client, db):
    make_user(db, "ctl_solo_admin", Role.Admin)
    admin = login(client, "ctl_solo_admin")
    audit_id = _audit(client, admin)
    _to_review(client, admin, audit_id)
    decide_topicals(client, audit_id, csrf_headers(admin))
    r = client.post(f"/api/audits/{audit_id}/close", json={"password": PASSWORD}, headers=csrf_headers(admin))
    assert r.status_code == 403
    assert "Segregation of duties" in r.json()["detail"]


def test_preparer_cannot_generic_sign_own_record(client, db):
    make_user(db, "ctl_gen_admin", Role.Admin)
    admin = login(client, "ctl_gen_admin")
    audit_id = _audit(client, admin)
    r = client.post(
        "/api/approvals/sign",
        json={"record_type": "audit", "record_id": audit_id, "decision": "Approve", "password": PASSWORD},
        headers=csrf_headers(admin),
    )
    assert r.status_code == 403


# ------------------------------------------------------------------ evidence retention


def test_audit_delete_only_when_planned_and_empty(client, client2, db):
    make_user(db, "ctl_del_aud", Role.Auditor)
    make_user(db, "ctl_del_admin", Role.Admin)
    aud, admin = login(client, "ctl_del_aud"), login(client2, "ctl_del_admin")

    empty_id = _audit(client, aud, "Empty")
    assert client2.delete(f"/api/audits/{empty_id}", headers=csrf_headers(admin)).status_code == 200

    with_finding = _audit(client, aud, "Has finding")
    client.post(f"/api/audits/{with_finding}/findings", json={"title": "F"}, headers=csrf_headers(aud))
    r = client2.delete(f"/api/audits/{with_finding}", headers=csrf_headers(admin))
    assert r.status_code == 409

    started = _audit(client, aud, "Started")
    client.patch(f"/api/audits/{started}", json={"status": "In Progress"}, headers=csrf_headers(aud))
    assert client2.delete(f"/api/audits/{started}", headers=csrf_headers(admin)).status_code == 409


def test_finding_under_remediation_cannot_be_deleted(client, client2, db):
    make_user(db, "ctl_f_aud", Role.Auditor)
    make_user(db, "ctl_f_admin", Role.Admin)
    aud, admin = login(client, "ctl_f_aud"), login(client2, "ctl_f_admin")
    audit_id = _audit(client, aud)
    f = client.post(
        f"/api/audits/{audit_id}/findings", json={"title": "F", "status": "Remediating"}, headers=csrf_headers(aud)
    ).json()
    assert client2.delete(f"/api/findings/{f['id']}", headers=csrf_headers(admin)).status_code == 409


def test_progressed_records_cannot_be_deleted(client, client2, db):
    make_user(db, "ctl_r_aud", Role.Auditor)
    make_user(db, "ctl_r_admin", Role.Admin)
    aud, admin = login(client, "ctl_r_aud"), login(client2, "ctl_r_admin")
    nc = client.post("/api/nonconformances", json={"title": "NC"}, headers=csrf_headers(aud)).json()
    client.patch(f"/api/nonconformances/{nc['id']}", json={"status": "Remediating"}, headers=csrf_headers(aud))
    assert client2.delete(f"/api/nonconformances/{nc['id']}", headers=csrf_headers(admin)).status_code == 409

    fresh = client.post("/api/nonconformances", json={"title": "NC2"}, headers=csrf_headers(aud)).json()
    assert client2.delete(f"/api/nonconformances/{fresh['id']}", headers=csrf_headers(admin)).status_code == 200

    capa = client.post("/api/capa", json={"title": "C", "linked_nc_id": nc["id"]}, headers=csrf_headers(aud)).json()
    assert client2.delete(f"/api/capa/{capa['id']}", headers=csrf_headers(admin)).status_code == 409


def test_record_history_and_approval_cycles_are_append_only(db):
    db.execute(
        text(
            "INSERT INTO record_history (record_type, record_id, action, timestamp) "
            "VALUES ('audit', 424242, 'TEST', CURRENT_TIMESTAMP)"
        )
    )
    db.execute(
        text(
            "INSERT INTO approval_cycles (record_type, record_id, cycle_no, decision, comment, timestamp) "
            "VALUES ('audit', 424242, 1, 'Approve', '', CURRENT_TIMESTAMP)"
        )
    )
    db.commit()
    for table in ("record_history", "approval_cycles"):
        for stmt in (f"UPDATE {table} SET record_id = 1 WHERE record_id = 424242", f"DELETE FROM {table}"):
            with pytest.raises((IntegrityError, OperationalError)):
                db.execute(text(stmt))
            db.rollback()


def test_user_with_activity_cannot_be_deleted(client, client2, db):
    make_user(db, "ctl_u_admin", Role.Admin)
    make_user(db, "ctl_u_aud", Role.Auditor)
    admin, aud = login(client, "ctl_u_admin"), login(client2, "ctl_u_aud")
    _audit(client2, aud)
    target = db.execute(select(User).where(User.username == "ctl_u_aud")).scalar_one()
    r = client.delete(f"/api/users/{target.id}", headers=csrf_headers(admin))
    assert r.status_code == 409

    idle = make_user(db, "ctl_u_idle", Role.Auditee)
    assert client.delete(f"/api/users/{idle.id}", headers=csrf_headers(admin)).status_code == 200


# ------------------------------------------------------------------ working papers


def test_upload_is_encrypted_allowlisted_and_withdrawable(client, client2, db):
    make_user(db, "ctl_wp_aud", Role.Auditor)
    make_user(db, "ctl_wp_admin", Role.Admin)
    aud, admin = login(client, "ctl_wp_aud"), login(client2, "ctl_wp_admin")
    audit_id = _audit(client, aud)
    url = f"/api/audits/{audit_id}/working-papers"

    bad = client.post(
        url, data={"title": "x"}, files={"file": ("evil.exe", io.BytesIO(b"MZ"), "x")}, headers=csrf_headers(aud)
    )
    assert bad.status_code == 415

    content = b"confidential evidence"
    up = client.post(
        url, data={"title": "Evidence"}, files={"file": ("e.txt", io.BytesIO(content), "text/plain")},
        headers=csrf_headers(aud),
    )
    assert up.status_code == 201, up.text
    paper = up.json()
    assert paper["sha256"]
    stored = Path(settings.upload_dir) / paper["file_path"]
    assert stored.read_bytes() != content
    assert decrypt(stored.read_bytes()) == content

    dl = client.get(f"/api/working-papers/{paper['id']}/download")
    assert dl.status_code == 200 and dl.content == content

    gone = client2.delete(f"/api/working-papers/{paper['id']}", headers=csrf_headers(admin))
    assert gone.status_code == 200
    assert stored.exists(), "withdrawn evidence must be retained"
    assert client.get(url).json() == []
    withdrawn = client2.get(url, params={"include_withdrawn": True}).json()
    assert withdrawn and withdrawn[0]["is_deleted"] is True
    db.rollback()
    assert db.get(WorkingPaper, paper["id"]) is not None


def test_upload_size_limit(client, db, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    make_user(db, "ctl_big", Role.Auditor)
    aud = login(client, "ctl_big")
    audit_id = _audit(client, aud)
    big = io.BytesIO(b"x" * (1024 * 1024 + 10))
    r = client.post(
        f"/api/audits/{audit_id}/working-papers", data={"title": "big"},
        files={"file": ("big.txt", big, "text/plain")}, headers=csrf_headers(aud),
    )
    assert r.status_code == 413


# ------------------------------------------------------------------ auditee scoping


def test_auditee_sees_only_assigned_audits(client, client2, db):
    make_user(db, "ctl_scope_aud", Role.Auditor)
    auditee = make_user(db, "ctl_scope_ee", Role.Auditee, email="ee@example.com")
    aud = login(client, "ctl_scope_aud")
    login(client2, "ctl_scope_ee")

    hidden = _audit(client, aud, "Hidden")
    shown = _audit(client, aud, "Shown")
    client.post(f"/api/audits/{shown}/findings", json={"title": "F"}, headers=csrf_headers(aud))

    assert client2.get("/api/audits").json() == []
    assert client2.get(f"/api/audits/{shown}").status_code == 404

    cands = client.get("/api/audits/auditee-candidates").json()
    assert any(c["user_id"] == auditee.id for c in cands)
    assigned = client.post(f"/api/audits/{shown}/auditees", json={"user_id": auditee.id}, headers=csrf_headers(aud))
    assert assigned.status_code == 201

    ids = [a["id"] for a in client2.get("/api/audits").json()]
    assert ids == [shown]
    assert client2.get(f"/api/audits/{shown}/findings").status_code == 200
    assert client2.get(f"/api/audits/{hidden}/findings").status_code == 404
    assert client2.get(f"/api/records/audit/{hidden}/history").status_code == 404
    assert client2.get(f"/api/records/audit/{shown}/history").status_code == 200

    # Master data is internal; NCs follow audit assignment / ownership.
    assert client2.get("/api/organizations").json()["total"] == 0
    client.post("/api/nonconformances", json={"title": "Other"}, headers=csrf_headers(aud))
    client.post(
        "/api/nonconformances", json={"title": "Mine", "owner_email": "ee@example.com"}, headers=csrf_headers(aud)
    )
    titles = {n["title"] for n in client2.get("/api/nonconformances").json()["items"]}
    assert titles == {"Mine"}

    removed = client.delete(f"/api/audits/{shown}/auditees/{auditee.id}", headers=csrf_headers(aud))
    assert removed.status_code == 200 and removed.json() == []
    assert client2.get("/api/audits").json() == []


def test_tasks_list_scoped_to_participants(client, client2, db):
    make_user(db, "ctl_t_aud", Role.Auditor)
    make_user(db, "ctl_t_other", Role.Auditor)
    aud, other = login(client, "ctl_t_aud"), login(client2, "ctl_t_other")
    task = client.post("/api/tasks", json={"title": "Private task"}, headers=csrf_headers(aud)).json()
    assert all(t["id"] != task["id"] for t in client2.get("/api/tasks").json()["items"])
    assert client2.get(f"/api/tasks/{task['id']}").status_code == 404
    assert other


# ------------------------------------------------------------------ authentication


def test_login_lockout_and_admin_unlock(client, client2, db, monkeypatch):
    monkeypatch.setattr(settings, "login_max_attempts", 3)
    target = make_user(db, "ctl_lock", Role.Auditor)
    make_user(db, "ctl_lock_admin", Role.Admin)
    for _ in range(3):
        bad = client.post("/api/auth/login", json={"username": "ctl_lock", "password": "wrong"})
        assert bad.status_code == 401
    locked = client.post("/api/auth/login", json={"username": "ctl_lock", "password": PASSWORD})
    assert locked.status_code == 423

    admin = login(client2, "ctl_lock_admin")
    unlocked = client2.post(f"/api/users/{target.id}/unlock", headers=csrf_headers(admin))
    assert unlocked.status_code == 200 and unlocked.json()["locked_until"] is None
    assert client.post("/api/auth/login", json={"username": "ctl_lock", "password": PASSWORD}).status_code == 200


def test_password_change_revokes_other_sessions(client, client2, db):
    make_user(db, "ctl_pw", Role.Auditor)
    first = login(client, "ctl_pw")
    login(client2, "ctl_pw")
    changed = client.post(
        "/api/auth/me/password",
        json={"current_password": PASSWORD, "new_password": "N3w-Passw0rd!"},
        headers=csrf_headers(first),
    )
    assert changed.status_code == 200, changed.text
    assert client.get("/api/auth/me").status_code == 200
    assert client2.get("/api/auth/me").status_code == 401


def test_deactivation_revokes_sessions(client, client2, db):
    target = make_user(db, "ctl_deact", Role.Auditor)
    make_user(db, "ctl_deact_admin", Role.Admin)
    login(client, "ctl_deact")
    admin = login(client2, "ctl_deact_admin")
    client2.patch(f"/api/users/{target.id}", json={"is_active": False}, headers=csrf_headers(admin))
    assert client.get("/api/auth/me").status_code == 401


# ------------------------------------------------------------------ backups + config


def test_backups_are_encrypted_without_sessions(client, db):
    make_user(db, "ctl_bk", Role.Admin)
    csrf = login(client, "ctl_bk")
    made = client.post("/api/admin/backup", headers=csrf_headers(csrf)).json()
    assert made["filename"].endswith(".enc")
    raw = Path(made["path"]).read_bytes()
    assert b"password_hash" not in raw
    plain = decrypt(raw)
    if made["filename"].endswith(".json.enc"):
        payload = json.loads(plain)
        assert "sessions" not in payload["tables"]
        assert "users" in payload["tables"]
    else:  # mysqldump on PATH
        assert b"INSERT INTO `sessions`" not in plain
        assert b"`users`" in plain


def test_production_guard(monkeypatch):
    from app.main import check_security_settings

    assert settings.insecure_settings(), "test defaults are insecure on purpose"
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError):
        check_security_settings()
    monkeypatch.setattr(settings, "environment", "development")
    check_security_settings()


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_production_guard_rejects_published_passwords():
    from app.core.config import Settings

    good = dict(secret_key="s" * 40, cookie_secure=True, encryption_key="k" * 44,
                database_url="mysql+pymysql://gpha:Str0ng-Random@db:3306/gpha_workspace")
    assert Settings(admin_password="Unique-Admin-Pass-2026", **good).insecure_settings() == []
    for weak in ("Admin@12345", "DemoPass!123", ""):
        problems = Settings(admin_password=weak, **good).insecure_settings()
        assert any("GPHA_ADMIN_PASSWORD" in p for p in problems), weak
    dev_db = {**good, "database_url": "mysql+pymysql://gpha:gpha_dev_pass@db:3306/gpha_workspace"}
    problems = Settings(admin_password="Unique-Admin-Pass-2026", **dev_db).insecure_settings()
    assert any("gpha_dev_pass" in p for p in problems)
