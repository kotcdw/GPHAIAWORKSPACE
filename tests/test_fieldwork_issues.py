"""HighBond-aligned fieldwork: Workplan procedures, walkthroughs and testing rounds, linked evidence requests,
the Issue Tracker (publish gate, sign-offs, register and KPIs) and the assurance plan coverage grid."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core.enums import ReviewLevel, Role, utcnow
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, level=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if level:
        user.job_role, user.review_level = "manager", level
        db.commit()
    return user


@pytest.fixture
def team(client, client2, db):
    lead = _u(db, "fwlead")
    admin = _u(db, "fwadm", Role.Admin)
    return {"lead": lead, "admin": admin, "h": csrf_headers(login(client, lead.username)),
            "ah": csrf_headers(login(client2, admin.username))}


def _audit(client, h, audit_type=None, **extra):
    body = {"title": f"FW {uuid.uuid4().hex[:5]}", "scope": "x", **({"audit_type": audit_type} if audit_type else {}),
            **extra}
    r = client.post("/api/audits", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _objective_risk(client, h, audit_id):
    o = client.post(f"/api/audits/{audit_id}/objectives", json={"title": "Revenue is complete"}, headers=h).json()
    r = client.post(f"/api/objectives/{o['id']}/risks", json={"title": "Tolls not banked", "likelihood": 4,
                                                             "impact": 5}, headers=h).json()
    return o, r


def test_workplan_procedures_execute_review_and_raise_issue(client, client2, db, team):
    h, ah, lead = team["h"], team["ah"], team["lead"]
    audit = _audit(client, h, "Operational")
    assert audit["workflow"] == "Workplan"  # Configuration > Audit methodology > Workplan audit types
    aid = audit["id"]
    o, risk = _objective_risk(client, h, aid)

    # Controls belong to the Internal Control workflow.
    assert client.post(f"/api/objectives/{o['id']}/controls", json={"title": "C"}, headers=h).status_code == 409
    outsider = _u(db, "fwout")
    bad = client.post(f"/api/objectives/{o['id']}/procedures",
                      json={"title": "Vouch tolls", "assigned_to": outsider.id}, headers=h)
    assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "assigned_to"
    p = client.post(f"/api/objectives/{o['id']}/procedures", json={
        "title": "Vouch toll receipts to bank", "steps": "Select 25 days; agree to bank.", "risk_ids": [risk["id"]],
        "assigned_to": lead.id, "due_date": (utcnow() + timedelta(days=7)).date().isoformat()}, headers=h)
    assert p.status_code == 201, p.text
    p = p.json()
    assert p["ref"].startswith("PRC-") and p["risks"][0]["id"] == risk["id"] and p["assigned_name"]

    # The workflow is fixed once work exists.
    sw = client.patch(f"/api/audits/{aid}/fieldwork", json={"workflow": "Internal Control"}, headers=h)
    assert sw.status_code == 422

    # Execute: results and "Were issues identified?" are required for the preparer sign-off.
    r = client.patch(f"/api/procedures/{p['id']}", json={"status": "Prepared"}, headers=h)
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "results"
    r = client.patch(f"/api/procedures/{p['id']}", json={"results": "3 of 25 days banked late", "outcome": "Maybe"},
                     headers=h)
    assert r.status_code == 422
    r = client.patch(f"/api/procedures/{p['id']}", json={"results": "3 of 25 days banked late",
                                                         "outcome": "Issue(s) noted"}, headers=h)
    assert r.json()["status"] == "In Progress"
    r = client.patch(f"/api/procedures/{p['id']}", json={"status": "Prepared"}, headers=h)
    assert r.status_code == 200 and r.json()["prepared_by"]
    assert client.patch(f"/api/procedures/{p['id']}", json={"title": "x"}, headers=h).status_code == 409

    # The preparer cannot review; another reviewer signs with their password.
    own = client.post(f"/api/procedures/{p['id']}/review", json={"password": DEFAULT_PASSWORD}, headers=h)
    assert own.status_code == 403
    rv = client2.post(f"/api/procedures/{p['id']}/review", json={"password": DEFAULT_PASSWORD, "comment": "ok"},
                      headers=ah)
    assert rv.status_code == 200 and rv.json()["status"] == "Reviewed"

    issue = client.post(f"/api/procedures/{p['id']}/raise-issue", headers=h)
    assert issue.status_code == 201, issue.text
    issue = issue.json()
    assert issue["procedure_id"] == p["id"] and issue["risk_rating"] == "High" and issue["published"] is False
    assert issue["issue_type"] == "Deficiency"

    plan = client.get(f"/api/audits/{aid}/procedures").json()
    assert plan["summary"]["by_status"]["Reviewed"] == 1 and plan["summary"]["issues_noted"] == 1
    assert plan["items"][0]["issue_ids"] == [issue["id"]]
    assert plan["objectives"][0]["risks"][0]["id"] == risk["id"]


def test_walkthroughs_test_plan_and_testing_rounds(client, client2, db, team):
    h, ah, lead = team["h"], team["ah"], team["lead"]
    audit = _audit(client, h, "Compliance")
    assert audit["workflow"] == "Internal Control"
    aid = audit["id"]
    assert client.patch(f"/api/audits/{aid}/fieldwork", json={"testing_rounds": 3}, headers=h).status_code == 422
    s = client.patch(f"/api/audits/{aid}/fieldwork", json={"testing_rounds": 2}, headers=h).json()
    assert s["round_labels"] == ["Interim", "Final"]
    o, risk = _objective_risk(client, h, aid)
    c1 = client.post(f"/api/objectives/{o['id']}/controls", json={
        "title": "Daily banking reconciliation", "frequency": "Daily", "risk_ids": [risk["id"]],
        "test_method": "Inspection", "total_sample_size": 15, "test_steps": "1. Agree deposit slip to ledger"},
        headers=h).json()
    c2 = client.post(f"/api/objectives/{o['id']}/controls", json={"title": "Monthly review", "frequency": "Monthly"},
                     headers=h).json()
    assert c1["test_method"] == "Inspection" and c1["total_sample_size"] == 15

    # Walkthrough: "Is the control designed appropriately?"
    wt = client.post(f"/api/controls/{c1['id']}/tests", json={"test_type": "Walkthrough"}, headers=h).json()
    assert wt["round_no"] is None
    client.patch(f"/api/control-tests/{wt['id']}", json={"conclusion": "Effective", "results": "Walked one day",
                                                         "status": "Completed"}, headers=h)
    w = client.get(f"/api/audits/{aid}/walkthroughs").json()
    rows = {r["control_id"]: r for r in w["rows"]}
    assert rows[c1["id"]]["design"] == "Designed appropriately" and rows[c2["id"]]["design"] == "Not walked through"

    # Round 1 (Interim): one test per key control, sample from the test plan or the configured default.
    rnd = client.get(f"/api/audits/{aid}/testing/1").json()
    assert rnd["round_label"] == "Interim" and rnd["summary"]["not_prepared"] == 2
    prep = client.post(f"/api/audits/{aid}/testing/1/prepare", headers=h).json()
    assert prep["created"] == 2
    rnd = client.get(f"/api/audits/{aid}/testing/1").json()
    by = {r["control_id"]: r for r in rnd["rows"]}
    assert by[c1["id"]]["test"]["sample_size"] == 15 and by[c1["id"]]["test"]["procedure"].startswith("1. Agree")
    assert by[c2["id"]]["test"]["sample_size"] == 3  # Monthly=3
    assert client.get(f"/api/audits/{aid}/testing/3").status_code == 404
    t2 = by[c2["id"]]["test"]
    # "Are you testing this key control this round?" and the assignee (a team member).
    r = client.patch(f"/api/control-tests/{t2['id']}", json={"in_scope": False, "assigned_to": lead.id}, headers=h)
    assert r.status_code == 200 and r.json()["in_scope"] is False and r.json()["assigned_to"] == lead.id
    assert client.post(f"/api/controls/{c1['id']}/tests", json={"test_type": "Operating Effectiveness",
                                                                 "round_no": 1}, headers=h).status_code == 409
    # Once testing exists, the number of rounds is fixed.
    assert client.patch(f"/api/audits/{aid}/fieldwork", json={"testing_rounds": 4}, headers=h).status_code == 422
    # Default sample sizes are configurable and validated.
    bad = client2.put("/api/config", json={"values": {"sample_sizes_by_frequency": ["Monthly=three"]}}, headers=ah)
    assert bad.status_code in (400, 422)


def test_evidence_request_linked_to_procedure_with_cc_and_reminders(client, client2, db, team):
    h = team["h"]
    audit = _audit(client, h, "Operational")
    other = _audit(client, h, "Operational")
    o, risk = _objective_risk(client, h, audit["id"])
    p = client.post(f"/api/objectives/{o['id']}/procedures", json={"title": "Vouch receipts"}, headers=h).json()
    ee = _u(db, "evhod", Role.Auditee)
    cc = _u(db, "evcc", Role.Auditee)
    for u in (ee, cc):
        client.post(f"/api/audits/{audit['id']}/auditees", json={"user_id": u.id}, headers=h)
    client.post(f"/api/audits/{other['id']}/auditees", json={"user_id": ee.id}, headers=h)
    body = {"title": "Bank statements Jul-Sep", "assignee_id": ee.id, "target_type": "procedure",
            "target_id": p["id"], "cc_user_ids": [cc.id], "reminder": "Daily", "message": "Scanned PDFs please"}
    wrong = client.post(f"/api/audits/{other['id']}/evidence-requests", json=body, headers=h)
    assert wrong.status_code == 422 and wrong.json()["errors"][0]["field"] == "target_id"
    r = client.post(f"/api/audits/{audit['id']}/evidence-requests", json=body, headers=h)
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["target_label"].startswith("Procedure PRC-") and req["cc"][0]["id"] == cc.id
    assert req["reminder"] == "Daily"
    linked = client.get(f"/api/audits/{audit['id']}/evidence-requests?target_type=procedure&target_id={p['id']}")
    assert [x["id"] for x in linked.json()] == [req["id"]]
    assert client.get(f"/api/audits/{audit['id']}/procedures").json()["items"][0]["evidence_requests"] == 1

    # CC'd auditee is notified; the background watcher reminds the assignee on the Daily schedule.
    login(client2, cc.username)
    assert any("Copied in" in n["title"] for n in client2.get("/api/notifications").json()["items"])
    from app.domains.audit.evidence.models import EvidenceRequest
    from app.domains.audit.evidence.router import send_due_reminders

    db.rollback()  # start a fresh transaction so rows written through the API are visible
    row = db.get(EvidenceRequest, req["id"])
    row.requested_at = utcnow() - timedelta(days=2)
    db.commit()
    assert send_due_reminders(db) >= 1
    db.refresh(row)
    assert row.last_reminded_at is not None
    before = row.last_reminded_at
    send_due_reminders(db)  # not due again for a day
    db.refresh(row)
    assert row.last_reminded_at == before


def test_issue_tracker_register_publish_and_signoffs(client, client2, db, team):
    h = team["h"]
    audit = _audit(client, h)
    tag = uuid.uuid4().hex[:6]
    owner = make_user(db, f"isown_{tag}", Role.Auditee)
    f1 = client.post(f"/api/audits/{audit['id']}/findings", json={
        "title": f"Payroll {tag}", "risk_rating": "High", "issue_type": "Material Weakness",
        "assigned_owner_email": owner.email}, headers=h).json()
    client.post(f"/api/audits/{audit['id']}/findings", json={"title": f"Fuel {tag}", "risk_rating": "Low"}, headers=h)
    bad = client.post(f"/api/audits/{audit['id']}/findings", json={"title": "x", "issue_type": "Nope"}, headers=h)
    assert bad.status_code == 422

    reg = client.get(f"/api/findings/register?q={tag}&sort=-severity").json()
    assert reg["total"] == 2 and reg["items"][0]["title"] == f"Payroll {tag}"
    row = reg["items"][0]
    assert row["issue_type"] == "Material Weakness" and row["published"] is False and row["owner"]
    assert row["signoffs"][0]["label"] == "Preparer" and row["remediation"] == "No action raised"
    assert client.get(f"/api/findings/register?q={tag}&severity=Low").json()["total"] == 1
    summ = client.get(f"/api/findings/register/summary?q={tag}").json()
    assert {x["label"]: x["count"] for x in summ["by_severity"]} == {"High": 1, "Medium": 0, "Low": 1}
    assert {x["label"]: x["count"] for x in summ["by_issue_type"]}["Material Weakness"] == 1
    assert summ["unpublished"] == 2 and summ["by_project"][0]["count"] == 2

    # Publish: the owner is notified; publishing twice is refused.
    assert client.post(f"/api/findings/{f1['id']}/publish", headers=h).status_code == 200
    assert client.post(f"/api/findings/{f1['id']}/publish", headers=h).status_code == 409
    login(client2, owner.username)
    assert any(n["title"].startswith("Audit issue for your response") for n in
               client2.get("/api/notifications").json()["items"])
    assert client2.get("/api/findings/register").status_code == 403  # the register is for audit staff

    # Review sign-off: the next sign-off level (Detail Reviewer); never the preparer.
    assert client.post(f"/api/findings/{f1['id']}/review", headers=h).status_code == 403
    uh = _u(db, "isuh", level=ReviewLevel.UnitHead)
    uhh = csrf_headers(login(client2, uh.username))
    r = client2.post(f"/api/findings/{f1['id']}/review", headers=uhh)
    assert r.status_code == 200, r.text
    dots = r.json()["signoffs"]
    assert dots[0]["label"] == "Preparer" and dots[0]["done"]
    assert dots[1]["label"] == "Detail Reviewer" and dots[1]["done"] and dots[1]["by"] == (uh.full_name or uh.username)


def test_plan_coverage_grid(client, client2, db, team):
    ah = team["ah"]
    tag = uuid.uuid4().hex[:5]
    loc = client2.post("/api/locations", json={"code": f"C{tag}", "name": f"Cov {tag}"}, headers=ah).json()
    u1 = client2.post("/api/entity-units", json={"location_id": loc["id"], "code": "U1", "name": "Marine",
                                                 "risk_likelihood": 5, "risk_impact": 5}, headers=ah).json()
    client2.post("/api/entity-units", json={"location_id": loc["id"], "code": "U2", "name": "Stores",
                                            "risk_likelihood": 5, "risk_impact": 4}, headers=ah)
    used = {p["fiscal_year"] for p in client2.get("/api/assurance-plans").json()}
    free = [y for y in range(2024, 2037) if y not in used]
    if not free:
        pytest.skip("every allowed fiscal year already has a plan in the test database")
    year = free[-1]  # other suites take years from 2024 upwards
    plan = client2.post("/api/assurance-plans", json={"fiscal_year": year, "title": f"Plan {tag}",
                                                      "total_budget_hours": 100}, headers=ah)
    assert plan.status_code == 201, plan.text
    plan = plan.json()
    e = client2.post(f"/api/assurance-plans/{plan['id']}/engagements", json={
        "title": "Marine services audit", "entity_unit_id": u1["id"], "planned_quarter": "Q1", "budget_hours": 120},
        headers=ah)
    assert e.status_code == 201, e.text
    cov = client2.get(f"/api/assurance-plans/{plan['id']}/coverage?category={loc['id']}").json()
    names = {x["name"]: x for x in cov["entities"]}
    assert names["Marine"]["covered"] and not names["Stores"]["covered"]
    assert cov["engagements"][0]["entity_unit_id"] == u1["id"] and cov["engagements"][0]["progress"] == 0
    assert cov["hours"] == {"planned": 120, "available": 100, "actual": 0, "over": 20}
    only = client2.get(f"/api/assurance-plans/{plan['id']}/coverage?category={loc['id']}&not_covered=true").json()
    assert [x["name"] for x in only["entities"]] == ["Stores"] and cov["not_covered_high"] >= 1
