"""HighBond parity: five-level sign-offs, narratives, favourites, terms and custom attributes per audit type,
the plan Timeline / Include audits, the audit progress views, and Results / Robots / Storyboards."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core.enums import ReviewLevel, Role, utcnow
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, level=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if level:
        user.job_role, user.review_level = "manager", level
        db.commit()
    return user


@pytest.fixture
def people(client, client2, db):
    lead = _u(db, "hblead")
    rev = _u(db, "hbrev")
    mgr = _u(db, "hbmgr", level=ReviewLevel.Manager)
    admin = _u(db, "hbadm", Role.Admin)
    return {"lead": lead, "rev": rev, "mgr": mgr, "admin": admin, "h": csrf_headers(login(client, lead.username))}


def _audit(client, h, audit_type="Operational"):
    r = client.post("/api/audits", json={"title": f"HB {uuid.uuid4().hex[:5]}", "scope": "x",
                                         "audit_type": audit_type}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_five_level_signoffs_on_a_procedure(client, client2, db, people):
    h, rev, mgr = people["h"], people["rev"], people["mgr"]
    audit = _audit(client, h)
    o = client.post(f"/api/audits/{audit['id']}/objectives", json={"title": "Revenue"}, headers=h).json()
    p = client.post(f"/api/objectives/{o['id']}/procedures", json={"title": "Vouch receipts"}, headers=h).json()
    url = f"/api/signoffs/procedure/{p['id']}"

    st = client.get(url).json()
    assert [lvl["label"] for lvl in st["levels"]][:2] == ["Preparer", "Detail Reviewer"]
    assert st["next_level"] == 1 and st["can_sign"] is True
    # The preparer sign-off needs the procedure results.
    bad = client.post(url, json={}, headers=h)
    assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "results"
    client.patch(f"/api/procedures/{p['id']}", json={"results": "OK", "outcome": "No Issues"}, headers=h)
    st = client.post(url, json={}, headers=h).json()
    assert st["levels"][0]["done"] and st["read_only"] and st["next_level"] == 2
    assert client.get(f"/api/procedures/{p['id']}").json()["status"] == "Prepared"
    # Signed off pages are read-only.
    assert client.put(f"/api/custom-values/procedures/{p['id']}", json={"values": {}},
                      headers=h).status_code == 409
    # The preparer cannot sign again; a reviewer signs only when set as Next Reviewer.
    assert client.post(url, json={}, headers=h).status_code == 409
    rh = csrf_headers(login(client2, rev.username))
    assert client2.post(url, json={}, headers=rh).status_code == 409
    nxt = client.put(f"{url}/next-reviewer", json={"reviewer_id": rev.id}, headers=h)
    assert nxt.status_code == 200 and nxt.json()["next_reviewer"]["id"] == rev.id
    st = client2.post(url, json={}, headers=rh).json()
    assert st["levels"][1]["done"] and st["next_level"] == 3 and st["next_reviewer"] is None
    # An Audit Manager may override the Next Reviewer rule; the override is recorded.
    mh = csrf_headers(login(client2, mgr.username))
    assert client2.post(url, json={}, headers=mh).status_code == 409
    st = client2.post(url, json={"override": True}, headers=mh).json()
    assert st["levels"][2]["done"] and st["levels"][2]["override"]
    # Removing a sign-off removes every later one; removing the first reopens the procedure.
    st = client2.delete(f"{url}/2", headers=mh).json()
    assert [lvl["done"] for lvl in st["levels"]][:3] == [True, False, False]
    st = client.delete(f"{url}/1", headers=h).json()
    assert not any(lvl["done"] for lvl in st["levels"])
    assert client.get(f"/api/procedures/{p['id']}").json()["status"] == "In Progress"
    status_ = client.get(f"/api/audits/{audit['id']}/signoff-status").json()
    assert status_["rows"][0]["type"] == "procedure" and len(status_["levels"]) == 5


def test_narratives_terms_attributes_and_favourites(client, client2, db, people):
    h = people["h"]
    audit = _audit(client, h, "Compliance")
    assert audit["workflow"] == "Internal Control"
    o = client.post(f"/api/audits/{audit['id']}/objectives", json={"title": "Procurement"}, headers=h).json()
    c = client.post(f"/api/objectives/{o['id']}/controls", json={"title": "Three quotes"}, headers=h).json()
    n = client.post(f"/api/objectives/{o['id']}/narratives", json={"title": "Purchase to pay",
                                                                   "description": "Requisition...",
                                                                   "control_ids": [c["id"]]}, headers=h)
    assert n.status_code == 201, n.text
    n = n.json()
    assert n["ref"].startswith("NAR-") and n["controls"][0]["id"] == c["id"]
    assert client.post(f"/api/objectives/{o['id']}/narratives", json={"title": "x" * 61},
                       headers=h).status_code == 422
    listed = client.get(f"/api/audits/{audit['id']}/narratives").json()
    assert listed[0]["signoffs"][0]["label"] == "Preparer"

    # Terms and custom attributes per audit type (administrator).
    ah = csrf_headers(login(client2, people["admin"].username))
    t = client2.put("/api/audit-types/Compliance/terms", json={"terms": {"objective": "Section"}}, headers=ah)
    assert t.status_code == 200 and t.json()["terms"]["objective"] == "Section"
    assert client.get(f"/api/audits/{audit['id']}/terms").json()["objective"] == "Section"
    assert client2.put("/api/audit-types/Compliance/terms", json={"terms": {"bogus": "x"}},
                       headers=ah).status_code == 422
    f = client2.post("/api/custom-fields", json={"module": "controls", "label": f"Assertion {uuid.uuid4().hex[:4]}",
                                                 "field_type": "select", "options": ["Existence", "Completeness"],
                                                 "audit_type": "Compliance"}, headers=ah)
    assert f.status_code == 201, f.text
    key = f.json()["key"]
    vals = client.get(f"/api/custom-values/controls/{c['id']}").json()
    assert any(d["key"] == key for d in vals["fields"])
    ok = client.put(f"/api/custom-values/controls/{c['id']}", json={"values": {key: "Existence"}}, headers=h)
    assert ok.status_code == 200 and ok.json()["values"][key] == "Existence"
    assert client.put(f"/api/custom-values/controls/{c['id']}", json={"values": {key: "Nope"}},
                      headers=h).status_code == 422
    other = _audit(client, h, "Financial")
    o2 = client.post(f"/api/audits/{other['id']}/objectives", json={"title": "Other"}, headers=h).json()
    assert all(d["key"] != key for d in client.get(f"/api/custom-values/objectives/{o2['id']}").json()["fields"])

    # Favourites float to the top with "Show favorites first".
    assert client.put(f"/api/audits/{audit['id']}/favorite", headers=h).json()["favorite"] is True
    page = client.get("/api/audits/register?fav_first=true&sort=-updated_at").json()
    assert page["items"][0]["id"] == audit["id"] and page["items"][0]["favorite"] is True
    client.delete(f"/api/audits/{audit['id']}/favorite", headers=h)
    tracker = client.get("/api/audits/status-tracker").json()
    assert any(r["id"] == audit["id"] for r in tracker)
    prog = client.get(f"/api/audits/{audit['id']}/progress").json()
    assert set(prog["work"]) == {"Not Started", "In Process", "Completed"}


def test_plan_timeline_include_and_exclude(client, client2, db, people):
    from app.domains.assurance.planning.models import AssurancePlan

    ah = csrf_headers(login(client2, people["admin"].username))
    year = 2100 + int(uuid.uuid4().hex[:3], 16) % 800
    plan = AssurancePlan(plan_ref=f"AP-T{uuid.uuid4().hex[:5]}", fiscal_year=year, title="Timeline plan",
                         total_budget_hours=500)
    db.add(plan)
    db.commit()
    eng = client2.post(f"/api/assurance-plans/{plan.id}/engagements", json={
        "title": "Port billing", "planned_quarter": "Q2", "budget_hours": 120}, headers=ah)
    assert eng.status_code in (200, 201), eng.text
    audit = _audit(client2, ah)
    options = client2.get(f"/api/assurance-plans/{plan.id}/includable-audits").json()
    assert any(a["id"] == audit["id"] for a in options)
    inc = client2.post(f"/api/assurance-plans/{plan.id}/include", json={"audit_ids": [audit["id"]],
                                                                        "quarter": "Q3"}, headers=ah)
    assert inc.status_code == 200 and inc.json()["included"] == 1
    assert all(a["id"] != audit["id"] for a in client2.get(
        f"/api/assurance-plans/{plan.id}/includable-audits").json())
    tl = client2.get(f"/api/assurance-plans/{plan.id}/timeline?group=quarter").json()
    lanes = {lane["label"]: lane["items"] for lane in tl["lanes"]}
    assert lanes["Q2"][0]["start"] == f"{year}-04-01" and lanes["Q3"][0]["audit_id"] == audit["id"]
    ex = client2.post(f"/api/plan-engagements/{inc.json()['engagement_ids'][0]}/exclude", json={}, headers=ah)
    assert ex.status_code == 200
    assert any(a["id"] == audit["id"] for a in client2.get(
        f"/api/assurance-plans/{plan.id}/includable-audits").json())


def test_robots_results_triggers_and_storyboards(client, client2, db, people):
    ah = csrf_headers(login(client2, people["admin"].username))
    h = people["h"]
    audit = _audit(client, h)
    f = client.post(f"/api/audits/{audit['id']}/findings", json={"title": f"Late banking {uuid.uuid4().hex[:4]}",
                                                                 "risk_rating": "High"}, headers=h).json()
    catalog = {a["key"]: a for a in client2.get("/api/robots/analytics").json()}
    assert "open_high_issues" in catalog and catalog["open_high_issues"]["params"]
    robot = client2.post("/api/robots", json={"name": f"Issue watch {uuid.uuid4().hex[:4]}"}, headers=ah)
    assert robot.status_code == 201, robot.text
    task = client2.post(f"/api/robots/{robot.json()['id']}/tasks", json={
        "name": f"High issues {uuid.uuid4().hex[:4]}", "analytic": "open_high_issues", "frequency": "daily",
        "starting_at": "07:30"}, headers=ah)
    assert task.status_code == 201, task.text
    task = task.json()
    assert task["table_id"] and task["next_run_at"]
    assert client2.post(f"/api/robots/{robot.json()['id']}/tasks", json={"name": "x", "analytic": "rm -rf"},
                        headers=ah).status_code == 422
    # A trigger on the table assigns new High records.
    trig = client2.post(f"/api/results/tables/{task['table_id']}/triggers", json={
        "name": "Assign High", "conditions": [{"field": "priority", "value": "High"}],
        "actions": [{"type": "assign", "user_id": people["mgr"].id}]}, headers=ah)
    assert trig.status_code == 201, trig.text
    run = client2.post(f"/api/robot-tasks/{task['id']}/run", headers=ah).json()
    assert run["status"] == "Success" and run["method"] == "manual"
    table = client2.get(f"/api/results/tables/{task['table_id']}").json()
    rec = next(r for r in table["records"] if r["key"] == f"finding:{f['id']}")
    assert rec["status"] == "New" and rec["priority"] == "High" and rec["assignee_id"] == people["mgr"].id
    upd = client2.patch(f"/api/results/records/{rec['id']}", json={"status": "Under Review"}, headers=ah)
    assert upd.json()["status"] == "Under Review"
    again = client2.post(f"/api/robot-tasks/{task['id']}/run", headers=ah).json()
    table = client2.get(f"/api/results/tables/{task['table_id']}").json()
    assert again["status"] == "Success" and len([r for r in table["records"] if r["key"] == f"finding:{f['id']}"]) == 1
    runs = client2.get(f"/api/robot-runs?task_id={task['id']}").json()
    assert len(runs) == 2 and runs[0]["duration_s"] is not None

    # Interpretation and storyboard, shared read-only.
    i = client2.post(f"/api/results/tables/{task['table_id']}/interpretations", json={
        "name": "By status", "chart": "donut", "group_by": "status"}, headers=ah).json()
    data = client2.get(f"/api/results/interpretations/{i['id']}").json()
    assert data["total"] >= 1 and any(s["label"] == "Under Review" for s in data["series"])
    sb = client2.post("/api/storyboards", json={"name": "Committee view", "blocks": [
        {"type": "text", "title": "Summary", "body": "Open issues"},
        {"type": "chart", "interpretation_id": i["id"], "width": "half"}]}, headers=ah).json()
    assert client.get(f"/api/storyboards/{sb['id']}").status_code == 404  # not shared yet
    client2.put(f"/api/storyboards/{sb['id']}/share", json={"user_ids": [people["lead"].id]}, headers=ah)
    seen = client.get(f"/api/storyboards/{sb['id']}").json()
    assert seen["blocks"][1]["data"]["total"] >= 1 and seen["can_edit"] is False
    assert client.put(f"/api/storyboards/{sb['id']}", json={"name": "x", "blocks": []}, headers=h).status_code == 403

    # The scheduler runs tasks whose time has come.
    from app.services.results.models import RobotTask
    from app.services.results.router import run_scheduled_robots

    db.rollback()
    t = db.get(RobotTask, task["id"])
    t.next_run_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert run_scheduled_robots(db) >= 1
