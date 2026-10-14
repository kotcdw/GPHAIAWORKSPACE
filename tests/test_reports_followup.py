"""Audit reports (review chain), follow-up validation, escalation, notifications, MFA, throttling."""

from __future__ import annotations

import io
import time
import uuid
import zipfile
from datetime import timedelta

from fastapi.testclient import TestClient

from app.core import totp
from app.core.config import settings
from app.core.enums import ReviewLevel, Role, utcnow
from app.main import app
from app.modules.capa.models import Capa
from app.modules.followup.service import run_escalations
from app.modules.notifications.models import Notification
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user


def _u(db, prefix: str, role: Role, level: ReviewLevel | None = None, email: str | None = None):
    name = f"{prefix}_{uuid.uuid4().hex[:6]}"
    user = make_user(db, name, role, email=email)
    if level is not None:
        user.review_level = level
        db.commit()
    return user


def _notes(db, user_id: int) -> list[Notification]:
    db.rollback()  # end the open transaction so rows committed by the app are visible
    return db.query(Notification).filter(Notification.user_id == user_id).order_by(Notification.id).all()


# ------------------------------------------------------------------ notifications


def test_task_assignment_notifies_and_bell_is_private(client, client2, db):
    boss = _u(db, "boss", Role.Auditor)
    worker = _u(db, "worker", Role.Auditor)
    h = csrf_headers(login(client, boss.username))
    made = client.post("/api/tasks", json={"title": "Review cash count", "assignee_id": worker.id}, headers=h)
    assert made.status_code == 201, made.text

    wh = csrf_headers(login(client2, worker.username))
    bell = client2.get("/api/notifications").json()
    assert bell["unread"] >= 1 and bell["items"][0]["title"].startswith("New task")
    note_id = bell["items"][0]["id"]
    assert client.post(f"/api/notifications/{note_id}/read", headers=h).status_code == 404, "not yours"
    assert client2.post(f"/api/notifications/{note_id}/read", headers=wh).status_code == 200
    assert client2.post("/api/notifications/read-all", headers=wh).status_code == 200
    assert client2.get("/api/notifications").json()["unread"] == 0


# ------------------------------------------------------------------ audit report


def test_report_review_chain_and_exports(client, client2, db):
    preparer = _u(db, "prep", Role.Auditor)
    manager = _u(db, "mgr", Role.Auditor, ReviewLevel.Manager)
    cae = _u(db, "cae", Role.Admin, ReviewLevel.CAE)
    auditee = _u(db, "aud", Role.Auditee)
    ph = csrf_headers(login(client, preparer.username))

    audit = client.post("/api/audits", json={"title": "Payroll", "scope": "Payroll Q1"}, headers=ph).json()
    client.post(f"/api/audits/{audit['id']}/auditees", json={"user_id": auditee.id}, headers=ph)
    finding = client.post(
        f"/api/audits/{audit['id']}/findings",
        json={"title": "Ghost employees", "risk_rating": "High", "condition": "3 leavers still paid"},
        headers=ph,
    ).json()

    report = client.post(f"/api/audits/{audit['id']}/report", headers=ph)
    assert report.status_code == 201, report.text
    report = report.json()
    rid = report["id"]
    assert report["report_ref"].startswith("RPT-") and report["status"] == "Draft"
    assert client.post(f"/api/audits/{audit['id']}/report", headers=ph).status_code == 409

    # Auditees cannot see a draft.
    ah = csrf_headers(login(client2, auditee.username))
    assert client2.get(f"/api/reports/{rid}").status_code == 404

    not_ready = client.post(f"/api/reports/{rid}/submit-for-review", headers=ph)
    assert not_ready.status_code == 400 and "overall rating" in not_ready.json()["detail"]
    upd = client.patch(
        f"/api/reports/{rid}",
        json={
            "overall_rating": "Needs Improvement",
            "executive_summary": "Payroll controls need work.",
            "overall_opinion": "Controls are partly effective.",
            "distribution_list": "MD, DMD Finance",
        },
        headers=ph,
    )
    assert upd.status_code == 200 and upd.json()["blockers"] == ["1 finding(s) still need a management response."]

    sent = client.post(f"/api/reports/{rid}/send-to-management", headers=ph)
    assert sent.status_code == 200 and sent.json()["status"] == "Management Review"
    assert any("Draft audit report" in n.title for n in _notes(db, auditee.id))
    assert client.patch(f"/api/reports/{rid}", json={"title": "x y"}, headers=ph).status_code == 409

    seen = client2.get(f"/api/reports/{rid}")
    assert seen.status_code == 200 and seen.json()["can_comment"] is True
    assert (
        client2.put(
            f"/api/reports/{rid}/management-comments",
            json={"management_comments": "We accept the findings."},
            headers=ah,
        ).status_code
        == 200
    )
    assert (
        client2.post(
            f"/api/findings/{finding['id']}/response",
            json={"management_response": "Leavers removed; HR checklist updated."},
            headers=ah,
        ).status_code
        == 200
    )

    sub = client.post(f"/api/reports/{rid}/submit-for-review", headers=ph)
    assert sub.status_code == 200 and sub.json()["status"] == "Manager Review"
    assert any("Report to review" in n.title for n in _notes(db, manager.id))

    # The preparer has no review level; a plain auditor cannot review.
    bad = client.post(f"/api/reports/{rid}/manager-review", json={"password": DEFAULT_PASSWORD}, headers=ph)
    assert bad.status_code == 403

    with TestClient(app) as c3:
        mh = csrf_headers(login(c3, manager.username))
        back = c3.post(
            f"/api/reports/{rid}/manager-review",
            json={"password": DEFAULT_PASSWORD, "decision": "Reject", "comment": "Add root cause"},
            headers=mh,
        )
        assert back.status_code == 200 and back.json()["status"] == "Draft"
        assert any("returned" in n.title for n in _notes(db, preparer.id))
        assert client.post(f"/api/reports/{rid}/submit-for-review", headers=ph).status_code == 200
        ok = c3.post(f"/api/reports/{rid}/manager-review", json={"password": DEFAULT_PASSWORD}, headers=mh)
        assert ok.status_code == 200 and ok.json()["status"] == "CAE Approval"
        # The manager reviewer cannot also approve as CAE.
        manager.review_level = ReviewLevel.CAE
        db.commit()
        sod = c3.post(f"/api/reports/{rid}/cae-approve", json={"password": DEFAULT_PASSWORD}, headers=mh)
        assert sod.status_code == 403

    with TestClient(app) as c4:
        ch = csrf_headers(login(c4, cae.username))
        issued = c4.post(f"/api/reports/{rid}/cae-approve", json={"password": DEFAULT_PASSWORD}, headers=ch)
        assert issued.status_code == 200, issued.text
        body = issued.json()
        assert body["status"] == "Issued" and body["issued_at"] and body["can_edit"] is False
        assert [s["name"] is not None for s in body["signoffs"]] == [True, True, True]

    # Issued report is frozen: later finding edits do not change it.
    client.patch(f"/api/findings/{finding['id']}", json={"title": "Changed later"}, headers=ph)
    page = client.get(f"/api/reports/{rid}/print")
    assert page.status_code == 200 and "Ghost employees" in page.text and "Changed later" not in page.text
    assert "DRAFT" not in page.text
    docx = client.get(f"/api/reports/{rid}/export.docx")
    assert docx.status_code == 200 and "RPT-" in docx.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(docx.content)) as zf:
        assert "Ghost employees" in zf.read("word/document.xml").decode()
    assert client2.get(f"/api/reports/{rid}").status_code == 200, "auditees see the issued report"


# ------------------------------------------------------------------ follow-up


def test_owner_implements_auditor_rejects_then_escalation(client, client2, db):
    auditor = _u(db, "fu_aud", Role.Auditor)
    owner = _u(db, "fu_own", Role.Auditee)
    manager = _u(db, "fu_mgr", Role.Auditor, ReviewLevel.Manager)
    h = csrf_headers(login(client, auditor.username))
    capa = client.post("/api/capa", json={"title": "Fix reconciliations", "owner_email": owner.email}, headers=h)
    cid = capa.json()["id"]

    oh = csrf_headers(login(client2, owner.username))
    short = client2.post(f"/api/capa/{cid}/implement", json={"evidence": "done"}, headers=oh)
    assert short.status_code == 422
    done = client2.post(
        f"/api/capa/{cid}/implement", json={"evidence": "Monthly reconciliation now signed by the FM."}, headers=oh
    )
    assert done.status_code == 200 and done.json()["status"] == "Review"
    assert any("Ready to validate" in n.title for n in _notes(db, auditor.id))

    no_reason = client.post(f"/api/capa/{cid}/validate", json={"result": "Not Effective"}, headers=h)
    assert no_reason.status_code == 422
    reopened = client.post(
        f"/api/capa/{cid}/validate", json={"result": "Not Effective", "comment": "No sign-off for March"}, headers=h
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "In Progress" and reopened.json()["reopen_count"] == 1
    assert any("reopened" in n.title for n in _notes(db, owner.id))

    # Overdue escalation: owner first, Audit Manager after 14 days, once per level.
    row = db.get(Capa, cid)
    row.due_date = utcnow() - timedelta(days=2)
    db.commit()
    assert run_escalations(db) >= 1
    assert db.get(Capa, cid).escalation_level == 1
    assert not any("Overdue" in n.title for n in _notes(db, manager.id))
    assert run_escalations(db) == 0 or db.get(Capa, cid).escalation_level == 1
    row = db.get(Capa, cid)
    row.due_date = utcnow() - timedelta(days=settings.escalate_manager_days + 1)
    db.commit()
    run_escalations(db)
    assert db.get(Capa, cid).escalation_level == 2
    assert any("Overdue" in n.title for n in _notes(db, manager.id))
    overdue = client.get("/api/followup/overdue").json()
    assert any(o["id"] == cid and o["escalation_name"] == "Audit Manager" for o in overdue)


# ------------------------------------------------------------------ security


def test_totp_mfa_enrol_login_and_disable(client, db):
    user = _u(db, "mfa", Role.Auditor)
    h = csrf_headers(login(client, user.username))
    setup = client.post("/api/auth/mfa/setup", headers=h)
    assert setup.status_code == 200 and setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    secret = setup.json()["secret"]
    assert client.post("/api/auth/mfa/enable", json={"code": "000000"}, headers=h).status_code == 400
    on = client.post("/api/auth/mfa/enable", json={"code": totp.code_at(secret, time.time())}, headers=h)
    assert on.status_code == 200 and on.json()["user"]["mfa_enabled"] is True

    with TestClient(app) as fresh:
        need = fresh.post("/api/auth/login", json={"username": user.username, "password": DEFAULT_PASSWORD})
        assert need.status_code == 401 and need.json()["detail"].startswith("MFA_REQUIRED")
        wrong = fresh.post(
            "/api/auth/login", json={"username": user.username, "password": DEFAULT_PASSWORD, "otp": "123456"}
        )
        assert wrong.status_code == 401
        good = fresh.post(
            "/api/auth/login",
            json={"username": user.username, "password": DEFAULT_PASSWORD, "otp": totp.code_at(secret, time.time())},
        )
        assert good.status_code == 200
    off = client.post(
        "/api/auth/mfa/disable",
        json={"password": DEFAULT_PASSWORD, "code": totp.code_at(secret, time.time())},
        headers=h,
    )
    assert off.status_code == 200 and off.json()["user"]["mfa_enabled"] is False


def test_mfa_required_role_is_enforced(client, db, monkeypatch):
    user = _u(db, "mfareq", Role.Auditor)
    monkeypatch.setattr(settings, "mfa_required_roles", "Auditor")
    login(client, user.username)
    me = client.get("/api/auth/me").json()
    assert me["mfa_setup_required"] is True
    blocked = client.get("/api/audits")
    assert blocked.status_code == 403 and "two-step" in blocked.json()["detail"]
    # A link opened in the browser (e.g. a Word copy) goes to the set-up screen instead of raw JSON.
    nav = client.get(
        "/api/audits",
        headers={"Accept": "text/html,application/xhtml+xml", "Sec-Fetch-Mode": "navigate"},
        follow_redirects=False,
    )
    assert nav.status_code == 303 and nav.headers["location"] == "/#mfa-setup"
    # Signed out: back to the sign-in page.
    client.post("/api/auth/logout", headers=csrf_headers(client.cookies.get("gpha_csrf") or ""))
    anon = client.get("/api/audits", headers={"Accept": "text/html"}, follow_redirects=False)
    assert anon.status_code in (303, 401)


def test_login_throttle_and_security_headers(client, db, monkeypatch):
    monkeypatch.setattr(settings, "login_rate_limit_per_minute", 3)
    from app.modules.auth import router as auth_router

    auth_router._ATTEMPTS.clear()
    codes = [client.post("/api/auth/login", json={"username": "nobody", "password": "x"}).status_code for _ in range(4)]
    assert codes[:3] == [401, 401, 401] and codes[3] == 429
    auth_router._ATTEMPTS.clear()
    page = client.get("/")
    csp = page.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "googleapis" not in page.text and "jsdelivr" not in page.text
