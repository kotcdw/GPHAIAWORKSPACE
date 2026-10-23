"""A finding closes only through verified remediation (blueprint 6.4)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.enums import Role
from app.main import app
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor):
    return make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)


def _finding(client, h, rating):
    title = f"Closure {uuid.uuid4().hex[:5]}"
    audit = client.post("/api/audits", json={"title": title, "scope": "x"}, headers=h).json()
    f = client.post(f"/api/audits/{audit['id']}/findings", json={
        "title": "Fuel coupons not reconciled", "description": "d", "risk_rating": rating,
        "condition": "Not reconciled", "recommendation": "Reconcile monthly"}, headers=h).json()
    return audit, f


def test_finding_cannot_be_closed_by_editing_while_remediation_is_unverified(client, client2, db):
    aud = _u(db, "clsaud")
    validator = _u(db, "clsval")
    admin = _u(db, "clsadm", Role.Admin)
    owner = make_user(db, f"clsown_{uuid.uuid4().hex[:6]}", Role.Auditee)
    h = csrf_headers(login(client, aud.username))
    audit, f = _finding(client, h, "High")

    # High finding without an action: closing by edit is refused.
    r = client.patch(f"/api/findings/{f['id']}", json={"status": "Closed"}, headers=h)
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "status"
    assert "raise the action first" in r.json()["detail"]

    capa = client.post(f"/api/findings/{f['id']}/raise-action", headers=h).json()
    client.patch(f"/api/capa/{capa['id']}", json={"owner_email": owner.email}, headers=h)
    listed = client.get(f"/api/audits/{audit['id']}/findings").json()[0]
    assert listed["status"] == "Remediating" and listed["remediation"]["state"] == "Action in progress"
    assert listed["remediation"]["refs"] == [capa["capa_ref"]]
    r = client.patch(f"/api/findings/{f['id']}", json={"status": "Closed"}, headers=h)
    assert r.status_code == 422 and capa["capa_ref"] in r.json()["detail"]

    # Owner implements; another auditor validates as Effective; the action is e-signed closed -> finding closes.
    with TestClient(app) as oc:
        oh = csrf_headers(login(oc, owner.username))
        imp = oc.post(f"/api/capa/{capa['id']}/implement",
                      json={"evidence": "Reconciliation for July-September attached and signed."}, headers=oh)
        assert imp.status_code == 200, imp.text
    state = client.get(f"/api/audits/{audit['id']}/findings").json()[0]["remediation"]["state"]
    assert state == "Awaiting verification"
    vh = csrf_headers(login(client2, validator.username))
    val = client2.post(f"/api/capa/{capa['id']}/validate", json={
        "result": "Effective", "comment": "Re-performed for three months",
        "procedures": "Re-performed the reconciliation for three months and agreed to the fleet log."}, headers=vh)
    assert val.status_code == 200, val.text
    ah = csrf_headers(login(client2, admin.username))
    closed = client2.post(f"/api/capa/{capa['id']}/close", json={"password": DEFAULT_PASSWORD}, headers=ah)
    assert closed.status_code == 200, closed.text
    after = client.get(f"/api/findings/{f['id']}").json()
    assert after["status"] == "Closed" and after["remediation"]["state"] == "Closed - verified"


def test_low_finding_without_action_follows_configuration(client, client2, db):
    aud = _u(db, "lowaud")
    admin = _u(db, "lowadm", Role.Admin)
    h = csrf_headers(login(client, aud.username))
    _, low = _finding(client, h, "Low")
    _, med = _finding(client, h, "Medium")
    assert client.patch(f"/api/findings/{med['id']}", json={"status": "Closed"}, headers=h).status_code == 422
    ah = csrf_headers(login(client2, admin.username))
    client2.put("/api/config", json={"values": {"low_findings_close_without_action": False}}, headers=ah)
    try:
        assert client.patch(f"/api/findings/{low['id']}", json={"status": "Closed"}, headers=h).status_code == 422
    finally:
        client2.post("/api/config/low_findings_close_without_action/reset", headers=ah)
    ok = client.patch(f"/api/findings/{low['id']}", json={"status": "Closed"}, headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "Closed"
