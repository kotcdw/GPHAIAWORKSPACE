"""IIA Topical Requirements on engagements: applicability with a rationale, each requirement assessed or excluded,
the closure gate for assurance engagements, and the conformance view for quality assessments."""

from __future__ import annotations

import uuid

from app.core.enums import Role
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user


def _u(db, prefix: str, role: Role):
    return make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)


def _cyber(view: dict) -> dict:
    return next(r for r in view["requirements"] if r["code"] == "cybersecurity")


def _others_not_in_scope(client, aid: int, h: dict) -> None:
    """Every other topical requirement (Third-Party, Organizational Behavior, ...) recorded as not in scope."""
    for r in client.get(f"/api/audits/{aid}/topical").json()["requirements"]:
        if r["code"] != "cybersecurity" and r["decision"] is None:
            assert client.put(f"/api/audits/{aid}/topical/{r['id']}",
                              json={"in_scope": False, "rationale": "Not part of this engagement's scope"},
                              headers=h).status_code == 200


def test_cybersecurity_requirement_is_seeded_with_three_areas(client, db):
    staff = _u(db, "tropen", Role.Auditor)
    login(client, staff.username)
    cat = client.get("/api/topical-requirements").json()
    cyber = next(r for r in cat if r["code"] == "cybersecurity")
    assert cyber["effective_on"] == "2026-02-05"
    assert {i["area"] for i in cyber["items"]} == {"Governance", "Risk management", "Control processes"}
    assert len(cyber["items"]) == 17


def test_applicability_checklist_and_closure_gate(client, client2, db):
    auditor = _u(db, "traud", Role.Auditor)
    admin = _u(db, "tradm", Role.Admin)
    h = csrf_headers(login(client, auditor.username))
    aid = client.post("/api/audits", json={"title": "ICT general controls", "scope": "Network and access"},
                      headers=h).json()["id"]
    view = client.get(f"/api/audits/{aid}/topical").json()
    assert view["mandatory"] is True and _cyber(view)["decision"] is None
    assert any("applicability not decided" in p for p in view["open_points"])

    # Not in scope needs a rationale; in scope needs how it came into scope.
    rid = _cyber(view)["id"]
    assert client.put(f"/api/audits/{aid}/topical/{rid}", json={"in_scope": False, "rationale": "no"},
                      headers=h).status_code == 422
    assert client.put(f"/api/audits/{aid}/topical/{rid}", json={"in_scope": True}, headers=h).status_code == 422
    view = client.put(f"/api/audits/{aid}/topical/{rid}",
                      json={"in_scope": True, "trigger": "Subject of a planned engagement"}, headers=h).json()
    items = _cyber(view)["items"]
    assert len(items) == 17 and _cyber(view)["progress"] == {"total": 17, "done": 0, "assessed": 0, "excluded": 0,
                                                             "exceptions": 0}

    first, second = items[0]["item_id"], items[1]["item_id"]
    url = f"/api/audits/{aid}/topical/{rid}/items"
    assert client.put(f"{url}/{first}", json={"outcome": "Excluded", "notes": "n/a"}, headers=h).status_code == 422
    assert client.put(f"{url}/{first}", json={"outcome": "Assessed"}, headers=h).status_code == 422
    fid = client.post(f"/api/audits/{aid}/findings", json={"title": "No cyber strategy", "risk_rating": "High"},
                      headers=h).json()["id"]
    ok = client.put(f"{url}/{first}", json={"outcome": "Assessed", "conclusion": "Exceptions noted", "finding_id": fid,
                                            "notes": "Strategy drafted, not approved"}, headers=h)
    assert ok.status_code == 200, ok.text
    client.put(f"{url}/{second}", json={"outcome": "Excluded", "notes": "Policies are covered by the ISO audit in Q2"},
               headers=h)
    p = _cyber(client.get(f"/api/audits/{aid}/topical").json())["progress"]
    assert p["done"] == 2 and p["exceptions"] == 1 and p["excluded"] == 1

    # The open checklist blocks closing an assurance audit.
    client.patch(f"/api/audits/{aid}", json={"status": "In Progress"}, headers=h)
    client.patch(f"/api/audits/{aid}", json={"status": "Review"}, headers=h)
    checks = {c["key"]: c for c in client.get(f"/api/audits/{aid}/closure-check").json()["checks"]}
    assert checks["topical"]["required"] and not checks["topical"]["ok"]
    assert "15 requirement" in checks["topical"]["detail"]
    ah = csrf_headers(login(client2, admin.username))
    blocked = client2.post(f"/api/audits/{aid}/close", json={"password": DEFAULT_PASSWORD}, headers=ah)
    assert blocked.status_code == 409 and "topical" in blocked.json()["detail"]
    for it in items[2:]:
        client.put(f"{url}/{it['item_id']}", json={"outcome": "Assessed", "conclusion": "No exceptions"}, headers=h)
    _others_not_in_scope(client, aid, h)
    checks = {c["key"]: c for c in client.get(f"/api/audits/{aid}/closure-check").json()["checks"]}
    assert checks["topical"]["ok"]

    # Conformance view for quality assessments.
    conf = client.get("/api/topical-requirements/conformance?status=open").json()
    row = next(r for r in conf["engagements"] if r["audit_id"] == aid)
    assert next(q for q in row["requirements"] if q["code"] == "cybersecurity")["state"] == "Complete"


def test_not_in_scope_with_rationale_satisfies_the_gate_and_auditees_are_refused(client, client2, db):
    auditor = _u(db, "trno", Role.Auditor)
    auditee = _u(db, "trcl", Role.Auditee)
    h = csrf_headers(login(client, auditor.username))
    aid = client.post("/api/audits", json={"title": "Payroll", "scope": "Payroll FY2026"}, headers=h).json()["id"]
    rid = _cyber(client.get(f"/api/audits/{aid}/topical").json())["id"]
    view = client.put(f"/api/audits/{aid}/topical/{rid}",
                      json={"in_scope": False, "rationale": "Payroll calculations only; no system review in scope"},
                      headers=h).json()
    assert _cyber(view)["decision"]["decided_by"]
    _others_not_in_scope(client, aid, h)
    assert client.get(f"/api/audits/{aid}/topical").json()["open_points"] == []
    login(client2, auditee.username)
    assert client2.get(f"/api/audits/{aid}/topical").status_code == 403


def test_third_party_and_organizational_behavior_are_seeded(client, db):
    staff = _u(db, "trseed", Role.Auditor)
    login(client, staff.username)
    cat = {r["code"]: r for r in client.get("/api/topical-requirements").json()}
    tp, ob = cat["third_party"], cat["organizational_behavior"]
    assert tp["effective_on"] == "2026-09-15" and len(tp["items"]) == 17
    assert ob["effective_on"] == "2026-12-15" and len(ob["items"]) == 15
    assert {i["area"] for i in tp["items"]} == {i["area"] for i in ob["items"]} == {
        "Governance", "Risk management", "Control processes"}


def test_library_administrator_maintains_the_catalogue(client, client2, db):
    admin = _u(db, "trlib", Role.Admin)
    auditor = _u(db, "trlaud", Role.Auditor)
    h = csrf_headers(login(client, admin.username))
    ah = csrf_headers(login(client2, auditor.username))
    body = {"title": f"Resilience {uuid.uuid4().hex[:4]}", "version": "draft", "effective_on": "2099-01-01",
            "description": "Pilot", "source_url": "https://www.theiia.org/"}
    assert client2.post("/api/topical-requirements", json=body, headers=ah).status_code == 403
    r = client.post("/api/topical-requirements", json=body, headers=h)
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["in_force"] is False and req["used_on"] == 0
    rid = req["id"]
    assert client.post(f"/api/topical-requirements/{rid}/items",
                       json={"area": "Elsewhere", "ref": "X", "text": "Not an area of the standard"},
                       headers=h).status_code == 422
    req = client.post(f"/api/topical-requirements/{rid}/items",
                      json={"area": "Governance", "ref": "G-A", "text": "A resilience strategy is approved"},
                      headers=h).json()
    item = req["items"][0]["id"]
    req = client.put(f"/api/topical-requirement-items/{item}",
                     json={"area": "Governance", "ref": "G-A",
                           "text": "A resilience strategy is approved and reviewed"},
                     headers=h).json()
    assert req["items"][0]["text"].endswith("reviewed")

    # Not yet in force: shown on engagements but does not block closure until its date.
    aid = client2.post("/api/audits", json={"title": "Continuity", "scope": "BCP"}, headers=ah).json()["id"]
    view = client2.get(f"/api/audits/{aid}/topical").json()
    assert any(x["id"] == rid for x in view["requirements"])
    assert not any(body["title"] in p for p in view["open_points"])

    # Once an engagement decides on it, the checklist is fixed; a new version carries the changes.
    assert client2.put(f"/api/audits/{aid}/topical/{rid}", json={"in_scope": True, "trigger": "Engagement request"},
                       headers=ah).status_code == 200
    assert client.post(f"/api/topical-requirements/{rid}/items",
                       json={"area": "Governance", "ref": "G-B", "text": "Roles for resilience are set"},
                       headers=h).status_code == 409
    assert client.delete(f"/api/topical-requirement-items/{item}", headers=h).status_code == 409
    nv = client.post(f"/api/topical-requirements/{rid}/new-version", json={"version": "2026"}, headers=h).json()
    assert nv["is_active"] is False and len(nv["items"]) == 1 and nv["code"] != req["code"]
    assert client.delete(f"/api/topical-requirement-items/{nv['items'][0]['id']}", headers=h).status_code == 200

    # Retiring the old version keeps it on the engagement that used it.
    client.patch(f"/api/topical-requirements/{rid}", json={"is_active": False}, headers=h)
    assert any(x["id"] == rid for x in client2.get(f"/api/audits/{aid}/topical").json()["requirements"])
    other = client2.post("/api/audits", json={"title": "Fleet", "scope": "Vehicles"}, headers=ah).json()["id"]
    assert not any(x["id"] == rid for x in client2.get(f"/api/audits/{other}/topical").json()["requirements"])
    full = client.get("/api/topical-requirements?include_inactive=true").json()
    assert any(x["id"] == nv["id"] for x in full)
