"""GPHA Working Paper Template and the split Audit Client / Management responses on findings."""

from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from app.core.enums import ReviewLevel, Role
from app.main import app
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, level=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if level:
        user.job_role, user.review_level = "manager", level
        db.commit()
    return user


def test_working_paper_template_form(client, client2, db):
    prep = _u(db, "wpprep")
    other = _u(db, "wpother", Role.Auditee)
    rev = _u(db, "wprev", level=ReviewLevel.Manager)
    ph = csrf_headers(login(client, prep.username))
    audit = client.post("/api/audits", json={"title": "Expenditure - payment vouchers", "scope": "Q3"},
                        headers=ph).json()

    # A paper can be the template form alone, without a file.
    made = client.post(f"/api/audits/{audit['id']}/working-papers", data={"title": "PV testing"}, headers=ph)
    assert made.status_code == 201, made.text
    wp = made.json()
    assert wp["has_file"] is False and wp["form_filled"] == 0
    assert client.get(f"/api/working-papers/{wp['id']}/download").status_code == 404

    form = client.get(f"/api/working-papers/{wp['id']}/template").json()
    keys = [f["key"] for f in form["fields"]]
    assert keys[:3] == ["audit_period", "location", "audited_unit"]
    for k in ("objective", "scope", "criteria", "risk_statement", "control_objective", "key_controls", "procedures",
              "evidence", "observations", "recommendation", "client_response", "action_plan",
              "responsible_officer", "target_date"):
        assert k in keys
    assert form["locations"] == ["Headquarters", "Tema Port", "Takoradi Port"]
    assert form["admin"]["audit_title"] == audit["title"] and form["admin"]["prepared_by"]
    assert form["can_edit"] is True

    url = f"/api/working-papers/{wp['id']}/template"
    bad = client.put(url, json={"values": {"location": "Accra"}}, headers=ph)
    assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "location"
    assert client.put(url, json={"values": {"target_date": "31/12/2026"}}, headers=ph).status_code == 422
    assert client.put(url, json={"values": {"colour": "red"}}, headers=ph).status_code == 422
    values = {"audit_period": "July - September 2026", "location": "Tema Port", "audited_unit": "Finance",
              "objective": "Confirm payment vouchers are authorised", "procedures": "Tested 25 vouchers",
              "target_date": "2026-12-31"}
    saved = client.put(url, json={"values": values}, headers=ph)
    assert saved.status_code == 200, saved.text
    assert saved.json()["values"]["location"] == "Tema Port" and saved.json()["complete"] == 6
    assert saved.json()["review_restarted"] is False

    # An audit client cannot edit the form.
    with TestClient(app) as c3:
        oh = csrf_headers(login(c3, other.username))
        assert c3.put(url, json={"values": {"scope": "x"}}, headers=oh).status_code == 403

    # Sign-off, then an edit restarts the review chain.
    rh = csrf_headers(login(client2, rev.username))
    signed = client2.post(f"/api/working-papers/{wp['id']}/review", json={"password": DEFAULT_PASSWORD}, headers=rh)
    assert signed.status_code == 200, signed.text
    assert client.get(url).json()["signed"] is True
    again = client.put(url, json={"values": {**values, "scope": "All Q3 vouchers above GHS 5,000"}}, headers=ph)
    assert again.status_code == 200 and again.json()["review_restarted"] is True
    assert again.json()["signed"] is False and again.json()["admin"]["reviewed_by"] == []

    # A new version (with a file) carries the form forward; the old version is read-only.
    v2 = client.post(f"/api/audits/{audit['id']}/working-papers", data={"title": "PV testing"},
                     files={"file": ("pv.txt", io.BytesIO(b"25 vouchers tested"), "text/plain")}, headers=ph)
    assert v2.status_code == 201 and v2.json()["version_number"] == 2 and v2.json()["has_file"] is True
    assert v2.json()["form_filled"] == 7
    assert client.get(url).json()["can_edit"] is False
    assert client.put(url, json={"values": {"scope": "y"}}, headers=ph).status_code == 403


def test_client_and_management_responses(client, client2, db):
    aud = _u(db, "frprep")
    ee = _u(db, "frhod", Role.Auditee)
    ah = csrf_headers(login(client, aud.username))
    audit = client.post("/api/audits", json={"title": "Revenue - tolls", "scope": "Q3"}, headers=ah).json()
    client.post(f"/api/audits/{audit['id']}/auditees", json={"user_id": ee.id}, headers=ah)
    finding = client.post(f"/api/audits/{audit['id']}/findings", json={
        "title": "Toll receipts not banked daily", "description": "x", "risk_rating": "High",
        "criteria": "Daily banking", "condition": "Banked weekly", "cause": "No courier", "effect": "Loss risk",
        "recommendation": "Bank daily"}, headers=ah).json()
    fid = finding["id"]

    eh = csrf_headers(login(client2, ee.username))
    # The Head of Department responds; only the audit team confirms it at the exit meeting.
    assert client2.post(f"/api/findings/{fid}/client-response",
                        json={"client_response": "Agreed", "confirmed_at_exit": True}, headers=eh).status_code == 403
    r = client2.post(f"/api/findings/{fid}/client-response", json={"client_response": "Agreed, courier now hired"},
                     headers=eh)
    assert r.status_code == 200 and r.json()["client_response"] == "Agreed, courier now hired"
    assert r.json()["client_confirmed_at_exit"] is False
    c = client.post(f"/api/findings/{fid}/client-response",
                    json={"client_response": "Agreed, courier now hired", "confirmed_at_exit": True}, headers=ah)
    assert c.status_code == 200 and c.json()["client_confirmed_at_exit"] is True
    assert client2.post(f"/api/findings/{fid}/client-response", json={"client_response": "Changed my mind"},
                        headers=eh).status_code == 409

    # Management response: action plan, responsible officer and target date (required by default).
    miss = client2.post(f"/api/findings/{fid}/response", json={"management_response": "Bank daily from Nov"},
                        headers=eh)
    assert miss.status_code == 422
    action = client.post(f"/api/findings/{fid}/raise-action", headers=ah)
    assert action.status_code == 201, action.text
    ok = client2.post(f"/api/findings/{fid}/response", json={
        "management_response": "Bank takings daily via the new courier", "responsible_officer": "rev.head@gpha.test",
        "target_date": "2026-11-30"}, headers=eh)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["responsible_officer"] == "rev.head@gpha.test" and body["target_date"].startswith("2026-11-30")
    assert body["management_response_at"]
    capa = client.get(f"/api/capa/{action.json()['id']}").json()
    assert capa["corrective_action"] == "Bank takings daily via the new courier"
    assert capa["owner_email"] == "rev.head@gpha.test" and capa["due_date"].startswith("2026-11-30")
