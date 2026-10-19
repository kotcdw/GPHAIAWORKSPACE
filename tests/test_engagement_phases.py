"""Engagement register phase / nature columns and fieldwork step progress (IIA GIAS 13-15)."""

from __future__ import annotations

import uuid

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def test_register_phase_nature_and_fieldwork_steps(client, db):
    user = make_user(db, f"ph_{uuid.uuid4().hex[:6]}", Role.Auditor)
    h = csrf_headers(login(client, user.username))
    a = client.post("/api/audits", json={"title": f"Phases {uuid.uuid4().hex[:5]}", "scope": "x",
                                         "workflow": "Internal Control"}, headers=h).json()
    o = client.post(f"/api/audits/{a['id']}/objectives", json={"title": "Dues billed"}, headers=h).json()
    r1 = client.post(f"/api/objectives/{o['id']}/risks", json={"title": "Not billed", "likelihood": 4, "impact": 4},
                     headers=h).json()
    client.post(f"/api/objectives/{o['id']}/risks", json={"title": "Unapproved credit", "likelihood": 2, "impact": 3},
                headers=h)
    r = client.post(f"/api/objectives/{o['id']}/controls", json={
        "title": "Daily reconciliation", "control_type": "Detective", "nature": "Manual", "frequency": "Daily",
        "is_key": True, "risk_ids": [r1["id"]], "test_method": "Inspection"}, headers=h)
    assert r.status_code in (200, 201), r.text

    steps = client.get(f"/api/audits/{a['id']}/fieldwork", headers=h).json()["steps"]
    assert steps["objectives"] == 1 and steps["risks"] == 2 and steps["controls"] == 1
    assert steps["risks_without_controls"] == 1 and steps["walked"] == 0 and steps["tests"] == 0

    page = client.get("/api/audits/register", params={"q": a["title"]}, headers=h).json()
    row = next(x for x in page["items"] if x["id"] == a["id"])
    assert row["phase"] == "Plan" and row["nature"] == "Assurance" and row["open_high"] == 0
    client.post(f"/api/audits/{a['id']}/findings", json={"title": "Calls not billed", "risk_rating": "High"}, headers=h)
    client.patch(f"/api/audits/{a['id']}", json={"status": "In Progress"}, headers=h)
    row = next(x for x in client.get("/api/audits/register", params={"q": a["title"]}, headers=h).json()["items"]
               if x["id"] == a["id"])
    assert row["phase"] == "Perform" and row["open_high"] == 1
    terms = client.get(f"/api/audits/{a['id']}/terms", headers=h).json()
    assert terms["issue"] == "Finding" and terms["rcm"] == "Risk & control matrix"
