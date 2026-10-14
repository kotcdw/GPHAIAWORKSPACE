"""System Configuration, audit lifecycle gates, engagement letter, action SLA and the Audit Committee pack."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import timedelta

from app.core import appconfig
from app.core.enums import Role, utcnow
from app.platform.notifications.models import Notification
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user


def _u(db, prefix: str, role: Role):
    return make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)


def _reset(client, h, *keys):
    for key in keys:
        client.post(f"/api/config/{key}/reset", headers=h)
    appconfig.invalidate()


def test_configuration_is_admin_only_validated_and_applied(client, client2, db):
    admin = _u(db, "cfgadm", Role.Admin)
    auditor = _u(db, "cfgaud", Role.Auditor)
    h = csrf_headers(login(client, admin.username))
    ah = csrf_headers(login(client2, auditor.username))
    assert client2.get("/api/config").status_code == 403
    assert client2.put("/api/config", json={"values": {"capa_due_days_high": 5}}, headers=ah).status_code == 403

    rules = {r["key"]: r for r in client.get("/api/config").json()}
    assert rules["capa_due_days_high"]["value"] == 30 and rules["capa_due_days_high"]["is_default"]
    assert rules["org_name"]["group"] == "Reports"

    bad = client.put("/api/config", json={"values": {"escalate_manager_days": 40, "escalate_cae_days": 30,
                                                     "capa_due_days_low": 0, "nope": 1}}, headers=h)
    assert bad.status_code == 422
    fields = {e["field"] for e in bad.json()["errors"]}
    assert {"escalate_cae_days", "capa_due_days_low", "nope"} <= fields

    try:
        ok = client.put("/api/config", json={"values": {"capa_due_days_high": 10, "mfa_required_roles": []}},
                        headers=h)
        assert ok.status_code == 200
        assert {r["key"]: r for r in ok.json()}["capa_due_days_high"]["value"] == 10
        capa = client.post("/api/capa", json={"title": "Urgent fix", "severity": "High"}, headers=h).json()
        due = capa["due_date"][:10]
        assert due == (utcnow() + timedelta(days=10)).strftime("%Y-%m-%d")
        low = client.post("/api/capa", json={"title": "Minor fix", "severity": "Low"}, headers=h).json()
        assert low["due_date"][:10] == (utcnow() + timedelta(days=90)).strftime("%Y-%m-%d")
    finally:
        _reset(client, h, "capa_due_days_high", "mfa_required_roles")
    assert {r["key"]: r for r in client.get("/api/config").json()}["capa_due_days_high"]["is_default"]


def test_closure_gates_fieldwork_notice_and_engagement_letter(client, client2, db):
    admin = _u(db, "lcadm", Role.Admin)
    auditor = _u(db, "lcaud", Role.Auditor)
    auditee = _u(db, "lcee", Role.Auditee)
    h = csrf_headers(login(client, auditor.username))
    adm = csrf_headers(login(client2, admin.username))
    audit = client.post("/api/audits", json={"title": "Stores audit", "scope": "Stores FY2026"}, headers=h).json()
    aid = audit["id"]
    client.post(f"/api/audits/{aid}/auditees", json={"user_id": auditee.id}, headers=h)

    client.patch(f"/api/audits/{aid}", json={"status": "In Progress"}, headers=h)
    db.rollback()
    notes = db.query(Notification).filter(Notification.user_id == auditee.id).all()
    assert any("fieldwork has started" in n.title for n in notes)

    letter = client.get(f"/api/audits/{aid}/engagement-letter.docx")
    assert letter.status_code == 200
    with zipfile.ZipFile(io.BytesIO(letter.content)) as zf:
        assert "STORES AUDIT" in zf.read("word/document.xml").decode()

    client.post(f"/api/audits/{aid}/findings", json={"title": "Stock not counted", "risk_rating": "High"}, headers=h)
    client.patch(f"/api/audits/{aid}", json={"status": "Review"}, headers=h)
    try:
        client2.put("/api/config", json={"values": {"require_report_to_close": True,
                                                    "require_findings_actioned_to_close": True}}, headers=adm)
        check = client.get(f"/api/audits/{aid}/closure-check").json()
        assert check["ready"] is False
        failing = {c["key"] for c in check["checks"] if c["required"] and not c["ok"]}
        assert failing == {"report", "responses", "actions"}
        blocked = client2.post(f"/api/audits/{aid}/close", json={"password": DEFAULT_PASSWORD}, headers=adm)
        assert blocked.status_code == 409 and "audit report issued" in blocked.json()["detail"]

        # Turning the gates off (as configured by the CAE) lets the audit close.
        client2.put("/api/config", json={"values": {"require_report_to_close": False,
                                                    "require_findings_actioned_to_close": False}}, headers=adm)
        assert client.get(f"/api/audits/{aid}/closure-check").json()["ready"] is True
        closed = client2.post(f"/api/audits/{aid}/close", json={"password": DEFAULT_PASSWORD}, headers=adm)
        assert closed.status_code == 200, closed.text
    finally:
        _reset(client2, adm, "require_report_to_close", "require_findings_actioned_to_close")


def test_committee_pack(client, client2, db):
    auditor = _u(db, "acaud", Role.Auditor)
    auditee = _u(db, "acee", Role.Auditee)
    login(client, auditor.username)
    summary = client.get("/api/committee/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert set(body["open_findings_by_age"]) == {"0-30 days", "31-90 days", "91-180 days", "Over 180 days"}
    assert {"open", "overdue", "awaiting_validation", "closed"} <= set(body["actions"])
    pack = client.get("/api/committee/pack.docx")
    assert pack.status_code == 200 and pack.headers["content-disposition"].startswith("attachment")
    with zipfile.ZipFile(io.BytesIO(pack.content)) as zf:
        assert "Audit Committee" in zf.read("word/document.xml").decode()
    login(client2, auditee.username)
    assert client2.get("/api/committee/summary").status_code == 403
