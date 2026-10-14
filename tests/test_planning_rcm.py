"""Planning & risk-control layer: universe -> Assurance Plan -> project RCM -> tests -> issues -> actions."""

from __future__ import annotations

import pytest

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user, release_plan, walk_plan_to_review

PASSWORD = "Passw0rd!"


@pytest.fixture
def people(client, client2, db):
    """client = Auditor (preparer), client2 = Admin (sign-off). Unique names per test."""
    import uuid

    tag = uuid.uuid4().hex[:6]
    make_user(db, f"pa_{tag}", Role.Auditor)
    make_user(db, f"pb_{tag}", Role.Admin)
    return {
        "aud": csrf_headers(login(client, f"pa_{tag}")),
        "adm": csrf_headers(login(client2, f"pb_{tag}")),
        "tag": tag,
    }


def _universe(client2, adm, tag):
    loc = client2.post("/api/locations", json={"code": f"T{tag}", "name": f"Tema {tag}"}, headers=adm)
    assert loc.status_code == 201, loc.text
    lid = loc.json()["id"]
    high = client2.post(
        "/api/entity-units",
        json={"location_id": lid, "code": "GJT", "name": "Golden Jubilee Terminal", "risk_likelihood": 4,
              "risk_impact": 5},
        headers=adm,
    ).json()
    low = client2.post(
        "/api/entity-units",
        json={"location_id": lid, "code": "FH", "name": "Fishing Harbour", "risk_likelihood": 1, "risk_impact": 2},
        headers=adm,
    ).json()
    return lid, high, low


_YEARS = iter(range(2031, 2100))


def _fiscal_year(tag: str) -> int:
    """A fiscal year not used by any other test in this session."""
    return next(_YEARS)


def _approved_plan_with_audit(client, client2, people):
    aud, adm, tag = people["aud"], people["adm"], people["tag"]
    _, high, _ = _universe(client2, adm, tag)
    plan = client.post(
        "/api/assurance-plans",
        json={"fiscal_year": _fiscal_year(tag), "title": "Assurance Plan", "total_budget_hours": 400},
        headers=aud,
    ).json()
    eng = client.post(
        f"/api/assurance-plans/{plan['id']}/engagements",
        json={"title": "GJT revenue assurance", "entity_unit_id": high["id"], "planned_quarter": "Q2",
              "budget_hours": 120},
        headers=aud,
    ).json()
    walk_plan_to_review(client2, plan["id"], adm)
    approved = client2.post(f"/api/assurance-plans/{plan['id']}/approve", json={"password": PASSWORD}, headers=adm)
    assert approved.status_code == 200, approved.text
    release_plan(client2, plan["id"], adm)
    started = client.post(f"/api/plan-engagements/{eng['id']}/start", headers=aud)
    assert started.status_code == 200, started.text
    return plan, started.json(), high


# ------------------------------------------------------------------ universe + plan


def test_universe_is_admin_managed(client, people):
    r = client.post("/api/locations", json={"code": "X", "name": "X"}, headers=people["aud"])
    assert r.status_code == 403
    assert client.get("/api/entity-units").status_code == 200


def test_assurance_plan_lifecycle(client, client2, people):
    aud, adm, tag = people["aud"], people["adm"], people["tag"]
    _, high, low = _universe(client2, adm, tag)
    fy = _fiscal_year(tag)

    plan = client.post("/api/assurance-plans", json={"fiscal_year": fy, "title": "Plan"}, headers=aud)
    assert plan.status_code == 201, plan.text
    plan = plan.json()
    assert plan["plan_ref"].startswith("AP-") and plan["status"] == "Draft"
    dup = client.post("/api/assurance-plans", json={"fiscal_year": fy, "title": "Again"}, headers=aud)
    assert dup.status_code == 409

    # Nothing to approve yet.
    empty = client2.post(f"/api/assurance-plans/{plan['id']}/approve", json={"password": PASSWORD}, headers=adm)
    assert empty.status_code == 409

    eng = client.post(
        f"/api/assurance-plans/{plan['id']}/engagements",
        json={"title": "Fishing harbour cash", "entity_unit_id": low["id"], "planned_quarter": "Q3"},
        headers=aud,
    ).json()
    detail = client.get(f"/api/assurance-plans/{plan['id']}").json()
    summary = detail["summary"]
    assert summary["engagements"] == 1 and summary["by_quarter"]["Q3"] == 1
    assert any(u["id"] == high["id"] for u in summary["uncovered_high_risk"]), "high-risk GJT is not planned"

    # Approval waits for the planning cycle.
    early = client2.post(f"/api/assurance-plans/{plan['id']}/approve", json={"password": PASSWORD}, headers=adm)
    assert early.status_code == 409 and "planning cycle" in early.json()["detail"]
    walk_plan_to_review(client2, plan["id"], adm)

    # Starting from a draft plan is refused; auditors cannot approve.
    assert client.post(f"/api/plan-engagements/{eng['id']}/start", headers=aud).status_code == 409
    assert client.post(
        f"/api/assurance-plans/{plan['id']}/approve", json={"password": PASSWORD}, headers=aud
    ).status_code == 403

    approved = client2.post(f"/api/assurance-plans/{plan['id']}/approve", json={"password": PASSWORD}, headers=adm)
    assert approved.status_code == 200 and approved.json()["status"] == "Approved"
    # Not yet distributed: execution waits for the GM Audit's distribution.
    assert client.post(f"/api/plan-engagements/{eng['id']}/start", headers=aud).status_code == 409
    release_plan(client2, plan["id"], adm)

    # Approved plan is frozen.
    frozen = client.post(
        f"/api/assurance-plans/{plan['id']}/engagements", json={"title": "Late addition"}, headers=aud
    )
    assert frozen.status_code == 409

    started = client.post(f"/api/plan-engagements/{eng['id']}/start", headers=aud).json()
    assert started["status"] == "Started" and started["audit_id"]
    audit = client.get(f"/api/audits/{started['audit_id']}").json()
    assert audit["status"] == "Planned"
    again = client.post(f"/api/plan-engagements/{eng['id']}/start", headers=aud)
    assert again.status_code == 409

    # Closing with an open audit is refused; reopening returns it to Draft.
    assert client2.post(f"/api/assurance-plans/{plan['id']}/close", headers=adm).status_code == 409
    reopened = client2.post(f"/api/assurance-plans/{plan['id']}/reopen", headers=adm).json()
    assert reopened["status"] == "Draft" and reopened["approved_by"] is None
    history = client.get(f"/api/records/assurance_plan/{plan['id']}/history").json()
    assert any("REOPENED" in h["action"] for h in history)


def test_plan_preparer_cannot_approve(client2, people):
    adm, tag = people["adm"], people["tag"]
    plan = client2.post(
        "/api/assurance-plans", json={"fiscal_year": _fiscal_year(tag), "title": "Solo"}, headers=adm
    ).json()
    client2.post(f"/api/assurance-plans/{plan['id']}/engagements", json={"title": "E"}, headers=adm)
    r = client2.post(f"/api/assurance-plans/{plan['id']}/approve", json={"password": PASSWORD}, headers=adm)
    assert r.status_code == 403


# ------------------------------------------------------------------ RCM end-to-end


def test_rcm_test_issue_action_flow(client, client2, people):
    aud, adm = people["aud"], people["adm"]
    _, eng, _ = _approved_plan_with_audit(client, client2, people)
    audit_id = eng["audit_id"]

    obj = client.post(f"/api/audits/{audit_id}/objectives", json={"title": "Revenue is complete"}, headers=aud)
    assert obj.status_code == 201, obj.text
    obj = obj.json()
    r_high = client.post(
        f"/api/objectives/{obj['id']}/risks",
        json={"title": "Unbilled vessel calls", "likelihood": 4, "impact": 5},
        headers=aud,
    ).json()
    r_low = client.post(
        f"/api/objectives/{obj['id']}/risks", json={"title": "Rounding", "likelihood": 1, "impact": 2}, headers=aud
    ).json()
    assert r_high["inherent_score"] == 20 and r_high["inherent_rating"] == "High"
    assert r_low["inherent_rating"] == "Low"

    ctl = client.post(
        f"/api/objectives/{obj['id']}/controls",
        json={"title": "Monthly billing reconciliation", "frequency": "Monthly", "owner_email": "fin@example.com",
              "risk_ids": [r_high["id"], r_low["id"]]},
        headers=aud,
    )
    assert ctl.status_code == 201, ctl.text
    ctl = ctl.json()
    assert sorted(ctl["risk_ids"]) == sorted([r_high["id"], r_low["id"]])

    rcm = client.get(f"/api/audits/{audit_id}/rcm").json()
    assert rcm["summary"]["risks"] == 2 and rcm["summary"]["key_controls_untested"]

    test = client.post(
        f"/api/controls/{ctl['id']}/tests",
        json={"test_type": "Operating Effectiveness", "procedure": "Re-perform reconciliations"},
        headers=aud,
    ).json()
    rec = client.get(f"/api/control-tests/{test['id']}/sample-recommendation").json()
    assert rec["recommended_size"] == 3
    sampled = client.post(
        f"/api/control-tests/{test['id']}/sample", json={"population_size": 12, "seed": 42}, headers=aud
    ).json()
    again = client.post(
        f"/api/control-tests/{test['id']}/sample", json={"population_size": 12, "seed": 42}, headers=aud
    ).json()
    assert sampled["sample_size"] == 3 and sampled["sample_items"] == again["sample_items"]
    assert sampled["status"] == "In Progress"

    # Close is blocked while fieldwork is unreviewed.
    for step in ("In Progress", "Review"):
        client.patch(f"/api/audits/{audit_id}", json={"status": step}, headers=aud)
    blocked = client2.post(f"/api/audits/{audit_id}/close", json={"password": PASSWORD}, headers=adm)
    assert blocked.status_code == 409 and "not yet reviewed" in blocked.json()["detail"]

    no_conclusion = client.patch(f"/api/control-tests/{test['id']}", json={"status": "Completed"}, headers=aud)
    assert no_conclusion.status_code == 422
    assert no_conclusion.json()["errors"][0]["field"] == "conclusion"
    no_results = client.patch(
        f"/api/control-tests/{test['id']}", json={"conclusion": "Ineffective", "status": "Completed"}, headers=aud
    )
    assert no_results.status_code == 422
    done = client.patch(
        f"/api/control-tests/{test['id']}",
        json={"conclusion": "Ineffective", "exceptions_found": 1, "results": "March not reviewed",
              "status": "Completed"},
        headers=aud,
    )
    assert done.status_code == 200, done.text
    assert done.json()["performed_by"] is not None

    # The performer cannot review their own test; another person can.
    self_review = client.post(f"/api/control-tests/{test['id']}/review", json={"password": PASSWORD}, headers=aud)
    assert self_review.status_code == 403
    reviewed = client2.post(
        f"/api/control-tests/{test['id']}/review", json={"password": PASSWORD, "comment": "agreed"}, headers=adm
    )
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "Reviewed"
    locked = client.patch(f"/api/control-tests/{test['id']}", json={"results": "edit"}, headers=aud)
    assert locked.status_code == 409

    rcm = client.get(f"/api/audits/{audit_id}/rcm").json()
    control = rcm["objectives"][0]["controls"][0]
    assert control["effectiveness"] == "Ineffective"
    assert rcm["summary"]["controls_by_effectiveness"]["Ineffective"] == 1

    issue = client.post(f"/api/control-tests/{test['id']}/raise-issue", headers=aud)
    assert issue.status_code == 201, issue.text
    issue = issue.json()
    assert issue["risk_rating"] == "High" and issue["control_id"] == ctl["id"] and issue["test_id"] == test["id"]
    assert "exception" in issue["condition"]
    assert client.post(f"/api/control-tests/{test['id']}/raise-issue", headers=aud).status_code == 409

    patched = client.patch(
        f"/api/findings/{issue['id']}",
        json={"cause": "Reviewer on leave", "recommendation": "Assign a backup reviewer",
              "root_cause_whys": ["No backup", "No rota", "Policy silent"]},
        headers=aud,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["root_cause_whys"] == ["No backup", "No rota", "Policy silent"]

    action = client.post(f"/api/findings/{issue['id']}/raise-action", headers=aud)
    assert action.status_code == 201, action.text
    action = action.json()
    assert action["severity"] == "High" and "Why 1: No backup" in action["root_cause"]
    assert action["corrective_action"] == "Assign a backup reviewer"
    assert client.get(f"/api/findings/{issue['id']}").json()["status"] == "Remediating"
    assert client.post(f"/api/findings/{issue['id']}/raise-action", headers=aud).status_code == 409

    # Evidence-bearing controls cannot be deleted.
    assert client.delete(f"/api/controls/{ctl['id']}", headers=aud).status_code == 409

    # Sign-off now succeeds and locks the matrix.
    closed = client2.post(f"/api/audits/{audit_id}/close", json={"password": PASSWORD}, headers=adm)
    assert closed.status_code == 200, closed.text
    late = client.post(f"/api/audits/{audit_id}/objectives", json={"title": "Late"}, headers=aud)
    assert late.status_code == 409
    units = client.get("/api/entity-units").json()
    gjt = next(u for u in units if u["id"] == eng["entity_unit_id"])
    assert gjt["last_audited_at"] is not None


def test_control_mapping_rejects_other_audits(client, client2, people):
    aud = people["aud"]
    _, eng, _ = _approved_plan_with_audit(client, client2, people)
    other = client.post("/api/audits", json={"title": "Other"}, headers=aud).json()
    o1 = client.post(f"/api/audits/{eng['audit_id']}/objectives", json={"title": "A"}, headers=aud).json()
    o2 = client.post(f"/api/audits/{other['id']}/objectives", json={"title": "B"}, headers=aud).json()
    foreign = client.post(f"/api/objectives/{o2['id']}/risks", json={"title": "R"}, headers=aud).json()
    r = client.post(
        f"/api/objectives/{o1['id']}/controls", json={"title": "C", "risk_ids": [foreign["id"]]}, headers=aud
    )
    assert r.status_code == 400


def test_auditee_cannot_read_rcm_but_can_respond(client, client2, db, people):
    aud = people["aud"]
    audit = client.post("/api/audits", json={"title": "Respond"}, headers=aud).json()
    finding = client.post(f"/api/audits/{audit['id']}/findings", json={"title": "F"}, headers=aud).json()
    ee = make_user(db, f"ee_{people['tag']}", Role.Auditee)
    client.post(f"/api/audits/{audit['id']}/auditees", json={"user_id": ee.id}, headers=aud)

    client2.cookies.clear()
    ee_h = csrf_headers(login(client2, ee.username))
    assert client2.get(f"/api/audits/{audit['id']}/rcm").status_code == 403
    assert client2.get("/api/assurance-plans").status_code == 403
    resp = client2.post(
        f"/api/findings/{finding['id']}/response", json={"management_response": "We agree; fix by Q4"}, headers=ee_h
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["management_response"] == "We agree; fix by Q4"
