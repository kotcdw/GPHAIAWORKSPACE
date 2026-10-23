"""PROJECTBLUEPRINT issues: Remediation Information, Retest Information and verified closure. Where the
configured ratings need a retest, validated actions alone do not close the issue."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.enums import Role
from app.main import app
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user
from tests.test_finding_closure import _finding


def _u(db, prefix, role=Role.Auditor):
    return make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)


def _close_action(client2, ah, capa_id):
    closed = client2.post(f"/api/capa/{capa_id}/close", json={"password": DEFAULT_PASSWORD}, headers=ah)
    assert closed.status_code == 200, closed.text


def test_remediation_and_retest_gate_closure(client, client2, db):
    aud = _u(db, "rtaud")
    validator = _u(db, "rtval")
    admin = _u(db, "rtadm", Role.Admin)
    owner = _u(db, "rtown", Role.Auditee)
    h = csrf_headers(login(client, aud.username))
    ah = csrf_headers(login(client2, admin.username))
    assert client2.put("/api/config", json={"values": {"retest_required_severities": ["High"]}},
                       headers=ah).status_code == 200
    try:
        audit, f = _finding(client, h, "High")
        opts = client.get("/api/findings/remediation-options").json()
        assert "Verified" not in opts["statuses"] and opts["retest_required_severities"] == ["High"]

        # Remediation Information: configured statuses only; Verified is never set by hand.
        bad = client.post(f"/api/findings/{f['id']}/remediation", json={"remediation_status": "Verified"}, headers=h)
        assert bad.status_code == 422
        future = (date.today() + timedelta(days=5)).isoformat()
        bad = client.post(f"/api/findings/{f['id']}/remediation", json={
            "remediation_status": "Management Remediating", "actual_remediation_date": future}, headers=h)
        assert bad.status_code == 422
        ok = client.post(f"/api/findings/{f['id']}/remediation", json={
            "remediation_status": "Management Remediating", "remediation_plan": "Monthly reconciliation",
            "remediation_deadline": future}, headers=h)
        assert ok.status_code == 200, ok.text
        assert ok.json()["remediation_status"] == "Management Remediating"
        assert ok.json()["status"] == "Open"  # a status change alone is not closure

        capa = client.post(f"/api/findings/{f['id']}/raise-action", headers=h).json()
        client.patch(f"/api/capa/{capa['id']}", json={"owner_email": owner.email}, headers=h)
        with TestClient(app) as oc:
            oh = csrf_headers(login(oc, owner.username))
            imp = oc.post(f"/api/capa/{capa['id']}/implement",
                          json={"evidence": "Reconciliations for July-September attached."}, headers=oh)
            assert imp.status_code == 200, imp.text
        vh = csrf_headers(login(client2, validator.username))
        val = client2.post(f"/api/capa/{capa['id']}/validate", json={
            "result": "Effective", "comment": "Re-performed",
            "procedures": "Re-performed the reconciliation for three months."}, headers=vh)
        assert val.status_code == 200, val.text
        ah = csrf_headers(login(client2, admin.username))
        _close_action(client2, ah, capa["id"])

        # Actions validated and closed, but a High issue still needs its retest.
        mid = client.get(f"/api/findings/{f['id']}").json()
        assert mid["status"] == "Remediating" and mid["remediation_status"] == "Remediated - Awaiting Verification"
        assert mid["remediation"]["state"] == "Awaiting retest"
        refused = client.patch(f"/api/findings/{f['id']}", json={"status": "Closed"}, headers=h)
        assert refused.status_code == 422 and "retest" in refused.json()["detail"]

        # Retest validation: a result needs a date and notes; working papers must be this audit's.
        today = date.today().isoformat()
        r = client.post(f"/api/findings/{f['id']}/retest", json={"retest_result": "Effective"}, headers=h)
        assert r.status_code == 422
        r = client.post(f"/api/findings/{f['id']}/retest", json={"retest_result": "Effective", "retest_date": today,
                                                                 "retest_notes": "short"}, headers=h)
        assert r.status_code == 422
        r = client.post(f"/api/findings/{f['id']}/retest", json={"retest_working_paper_id": 999_999_999},
                        headers=h)
        assert r.status_code == 422

        # The auditee cannot record a retest.
        with TestClient(app) as oc:
            oh = csrf_headers(login(oc, owner.username))
            assert oc.post(f"/api/findings/{f['id']}/retest", json={"retest_deadline": today},
                           headers=oh).status_code == 403

        # Not effective sends it back to management; Effective closes it as Verified.
        back = client.post(f"/api/findings/{f['id']}/retest", json={
            "retest_result": "Not effective", "retest_date": today,
            "retest_notes": "Two of three months were not reconciled."}, headers=h)
        assert back.status_code == 200, back.text
        assert back.json()["remediation_status"] == "Management Remediating" and back.json()["status"] == "Remediating"
        done = client.post(f"/api/findings/{f['id']}/retest", json={
            "retest_result": "Effective", "retest_date": today,
            "retest_notes": "Re-tested three later months; all reconciled and reviewed."}, headers=h)
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "Closed" and done.json()["remediation_status"] == "Verified"
        assert done.json()["retested_by"] == aud.id
        assert client.post(f"/api/findings/{f['id']}/retest", json={"retest_deadline": today},
                           headers=h).status_code == 409
    finally:
        client2.post("/api/config/retest_required_severities/reset", headers=ah)
