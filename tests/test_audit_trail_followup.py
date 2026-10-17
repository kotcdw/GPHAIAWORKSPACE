"""Audit trail (sign-in successes and failures, structured fields, filters, export) and follow-up management
(timeline, evidence files, target-date extensions, reopening, risk acceptance, aging, workflow integrity)."""

from __future__ import annotations

import io
import uuid
from datetime import timedelta

from sqlalchemy import select, text

from app.core import permissions as perms
from app.core.audit import classify
from app.core.enums import Role, utcnow
from app.domains.issues.capa.models import Capa, CapaEvent
from app.platform.history.models import AuditLog
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, job=None, email=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role, email=email)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
        db.commit()
    return user


def _logs(db, **where):
    db.rollback()
    stmt = select(AuditLog).order_by(AuditLog.id)
    for k, v in where.items():
        stmt = stmt.where(getattr(AuditLog, k) == v)
    return list(db.execute(stmt).scalars())


# ------------------------------------------------------------------ audit trail


def test_classify():
    assert classify("LOGIN_FAILED wrong_password username=x")[:2] == ("authentication", "failure")
    assert classify("LOGIN")[:2] == ("authentication", "success")
    assert classify("REMEDIATION_UPDATE id=5 [title]") == ("data", "success", "remediation", 5)
    assert classify("USER_DELETE username=a")[0] == "user_admin"
    assert classify("AUDIT_LOG_EXPORT rows=3")[0] == "export"
    assert classify("ESIGN_FAILED wrong_password record=capa id=2")[:2] == ("security", "failure")


def test_sign_in_success_and_failures_are_recorded(client, db):
    user = _u(db, "at_user")
    # wrong password for a known account: tied to the account
    bad = client.post("/api/auth/login", json={"username": user.username, "password": "Wrong-pass-1"})
    assert bad.status_code == 401
    failed = _logs(db, user_id=user.id, outcome="failure")
    assert failed and failed[-1].action_performed.startswith("LOGIN_FAILED wrong_password")
    assert failed[-1].category == "authentication" and failed[-1].username == user.username
    # unknown account: the typed name is kept
    ghost = f"ghost_{uuid.uuid4().hex[:6]}"
    client.post("/api/auth/login", json={"username": ghost, "password": "Whatever-1"})
    assert _logs(db, username=ghost)[-1].action_performed.startswith("LOGIN_FAILED unknown_user")
    # success
    login(client, user.username)
    ok = [e for e in _logs(db, user_id=user.id) if e.action_performed == "LOGIN"]
    assert ok and ok[-1].outcome == "success" and ok[-1].user_agent and ok[-1].ip_address
    # pending account
    pending = _u(db, "at_pend", Role.Auditee)
    pending.is_active = False
    db.commit()
    client.post("/api/auth/login", json={"username": pending.username, "password": DEFAULT_PASSWORD})
    assert _logs(db, user_id=pending.id)[-1].action_performed == "LOGIN_DENIED pending_approval"


def test_failed_password_change_and_esign_are_recorded(client, db):
    user = _u(db, "at_pw")
    h = csrf_headers(login(client, user.username))
    r = client.post("/api/auth/me/password",
                    json={"current_password": "nope-nope-1", "new_password": "Harbour-Gate-77"}, headers=h)
    assert r.status_code == 400
    assert _logs(db, user_id=user.id)[-1].action_performed.startswith("PASSWORD_CHANGE_FAILED")


def test_audit_register_filters_summary_and_export(client, db):
    admin = _u(db, "at_adm", Role.Admin)
    victim = _u(db, "at_vic")
    client.post("/api/auth/login", json={"username": victim.username, "password": "Bad-pass-11"})
    h = csrf_headers(login(client, admin.username))
    fails = client.get("/api/audit-logs/register", params={"category": "authentication", "outcome": "failure",
                                                          "user_id": victim.id}).json()
    assert fails["total"] >= 1 and all(i["outcome"] == "failure" for i in fails["items"])
    assert fails["items"][0]["user"] and fails["items"][0]["category"] == "authentication"
    summary = client.get("/api/audit-logs/summary", params={"days": 1}).json()
    assert summary["failed_sign_ins"] >= 1 and summary["sign_ins"] >= 1
    export = client.get("/api/audit-logs/export.csv", params={"category": "authentication"}, headers=h)
    assert export.status_code == 200 and "Timestamp (UTC)" in export.text and "LOGIN" in export.text
    assert _logs(db, user_id=admin.id)[-1].action_performed.startswith("AUDIT_LOG_EXPORT")
    # Non-admins cannot read the trail.
    other = _u(db, "at_aud")
    login(client, other.username)
    assert client.get("/api/audit-logs/register").status_code == 403


def test_audit_trail_stays_append_only(db):
    import pytest
    from sqlalchemy.exc import DatabaseError

    with pytest.raises(DatabaseError):
        db.execute(text("UPDATE audit_logs SET category = 'x'"))
    db.rollback()
    db.add(CapaEvent(capa_id=0, kind="note", text="probe", created_at=utcnow()))
    db.commit()
    with pytest.raises(DatabaseError):
        db.execute(text("DELETE FROM capa_events"))
    db.rollback()


# ------------------------------------------------------------------ follow-up management


def _action(client, h, owner_email, **extra):
    r = client.post("/api/capa", json={"title": "Reconcile suspense account", "owner_email": owner_email, **extra},
                    headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_status_workflow_is_enforced(client, db):
    auditor = _u(db, "fm_aud")
    h = csrf_headers(login(client, auditor.username))
    cid = _action(client, h, "owner@giaw-qa.com")["id"]
    assert client.patch(f"/api/capa/{cid}", json={"status": "Review"}, headers=h).status_code == 409
    assert client.patch(f"/api/capa/{cid}", json={"status": "In Progress"}, headers=h).status_code == 200
    client.post(f"/api/capa/{cid}/implement", json={"evidence": "Suspense account reconciled and cleared."}, headers=h)
    assert client.patch(f"/api/capa/{cid}", json={"status": "In Progress"}, headers=h).status_code == 409


def test_extension_needs_manager_and_reason_and_is_kept(client, client2, db):
    auditor = _u(db, "fm_aud2")
    manager = _u(db, "fm_mgr", job="manager")
    h = csrf_headers(login(client, auditor.username))
    action = _action(client, h, "owner2@giaw-qa.com", due_date=(utcnow() + timedelta(days=10)).isoformat())
    cid = action["id"]
    new_due = (utcnow() + timedelta(days=40)).isoformat()
    assert client.patch(f"/api/capa/{cid}", json={"due_date": new_due, "due_date_reason": "Need more time please"},
                        headers=h).status_code == 403
    mh = csrf_headers(login(client2, manager.username))
    assert client2.patch(f"/api/capa/{cid}", json={"due_date": new_due}, headers=mh).status_code == 422
    row = db.get(Capa, cid)
    row.escalation_level = 2
    db.commit()
    ok = client2.patch(f"/api/capa/{cid}", json={"due_date": new_due,
                                                "due_date_reason": "Supplier delivery delayed to next quarter"},
                       headers=mh)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["extension_count"] == 1 and body["original_due_date"][:10] == action["due_date"][:10]
    assert body["escalation_level"] == 0
    tl = client2.get(f"/api/capa/{cid}/timeline").json()
    ext = [e for e in tl if e["kind"] == "extension"]
    assert ext and "Supplier delivery" in ext[0]["text"] and ext[0]["old_due_date"] and ext[0]["new_due_date"]


def test_timeline_keeps_every_progress_note_and_evidence_file(client, client2, db):
    auditor = _u(db, "fm_aud3")
    owner = _u(db, "fm_own", Role.Auditee, email=f"own_{uuid.uuid4().hex[:6]}@giaw-qa.com")
    h = csrf_headers(login(client, auditor.username))
    cid = _action(client, h, owner.email)["id"]
    oh = csrf_headers(login(client2, owner.username))
    for note in ("First half of the ledger reconciled.", "Second half reconciled, awaiting sign-off."):
        assert client2.post(f"/api/capa/{cid}/progress", json={"status": "Partially Implemented", "note": note},
                            headers=oh).status_code == 200
    up = client2.post(f"/api/capa/{cid}/files", files={"file": ("signed-recon.pdf", io.BytesIO(b"%PDF-1.4 test"),
                                                                "application/pdf")}, headers=oh)
    assert up.status_code == 201, up.text
    files = client2.get(f"/api/capa/{cid}/files").json()
    assert [f["original_name"] for f in files] == ["signed-recon.pdf"]
    dl = client2.get(f"/api/capa-files/{files[0]['id']}/download")
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4 test"
    bad = client2.post(f"/api/capa/{cid}/files", files={"file": ("run.exe", io.BytesIO(b"MZ"), "application/x")},
                       headers=oh)
    assert bad.status_code == 415
    kinds = [e["kind"] for e in client2.get(f"/api/capa/{cid}/timeline").json()]
    assert kinds.count("progress") == 2 and "evidence_file" in kinds and kinds[0] == "created"
    db.rollback()
    assert db.execute(select(CapaEvent).where(CapaEvent.capa_id == cid)).scalars().first() is not None
    # Someone else's auditee cannot attach evidence.
    stranger = _u(db, "fm_str", Role.Auditee)
    sh = csrf_headers(login(client2, stranger.username))
    blocked = client2.post(f"/api/capa/{cid}/files", files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
                           headers=sh)
    assert blocked.status_code in (403, 404)


def test_risk_acceptance_reopen_and_aging(client, client2, db):
    auditor = _u(db, "fm_aud4")
    manager = _u(db, "fm_mgr2", job="manager")
    h = csrf_headers(login(client, auditor.username))
    cid = _action(client, h, "owner4@giaw-qa.com")["id"]
    mh = csrf_headers(login(client2, manager.username))
    assert client.post(f"/api/capa/{cid}/accept-risk", json={"reason": "x" * 25, "accepted_by": "Director"},
                       headers=h).status_code == 403
    short = client2.post(f"/api/capa/{cid}/accept-risk", json={"reason": "too short", "accepted_by": "Director"},
                         headers=mh)
    assert short.status_code == 422
    accepted = client2.post(f"/api/capa/{cid}/accept-risk",
                            json={"reason": "Legacy system retires in March; compensating weekly review in place",
                                  "accepted_by": "Director of Finance"}, headers=mh)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "Closed" and accepted.json()["implementation_status"] == "Risk Accepted"
    # Reopen a closed action
    assert client2.post(f"/api/capa/{cid}/reopen", json={"reason": "short"}, headers=mh).status_code == 422
    reopened = client2.post(f"/api/capa/{cid}/reopen",
                            json={"reason": "The compensating review stopped in April; risk no longer accepted"},
                            headers=mh)
    assert reopened.status_code == 200 and reopened.json()["status"] == "In Progress"
    assert reopened.json()["reopen_count"] == 1
    kinds = [e["kind"] for e in client2.get(f"/api/capa/{cid}/timeline").json()]
    assert "risk_accepted" in kinds and "reopened" in kinds
    # Aging
    row = db.get(Capa, cid)
    row.due_date = utcnow() - timedelta(days=45)
    db.commit()
    aging = client2.get("/api/followup/aging").json()
    assert aging["buckets"]["31-60 days"] >= 1
    assert any(r["id"] == cid and r["bucket"] == "31-60 days" for r in aging["rows"])
    csv_out = client2.get("/api/followup/aging.csv")
    assert csv_out.status_code == 200 and "Days overdue" in csv_out.text


def test_close_is_signed_by_followup_manager_not_system_admin(client, db):
    admin = _u(db, "fm_sysadm", Role.Admin, job="admin")
    auditor = _u(db, "fm_aud5")
    h = csrf_headers(login(client, auditor.username))
    cid = _action(client, h, "owner5@giaw-qa.com")["id"]
    ah = csrf_headers(login(client, admin.username))
    r = client.post(f"/api/capa/{cid}/close", json={"password": DEFAULT_PASSWORD}, headers=ah)
    assert r.status_code == 403
