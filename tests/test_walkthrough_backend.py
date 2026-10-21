"""Backend behind the interface walkthroughs: new project with framework objectives and entities, plan risk heat
and assurance, issue actions with notification and reminders, Activity Center, and the Strategy Risk Library."""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

from app.core import permissions as perms
from app.core.enums import Role
from tests.conftest import (
    DEFAULT_PASSWORD,
    csrf_headers,
    login,
    make_entity,
    make_user,
    release_plan,
    walk_plan_to_review,
)
from tests.test_plan_projects import _free_year, release_year


def _u(db, prefix, job, role=Role.Auditor):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def test_new_project_objectives_entities_and_plan_risks(client, client2, db, request):
    mgr = _u(db, "wpmgr", "audit_manager")
    adm = _u(db, "wpadm", "platform_admin", Role.Admin)
    gm = _u(db, "wpgm", "gm_audit")
    mh = csrf_headers(login(client, mgr.username))
    ah = csrf_headers(login(client2, adm.username))
    tag = uuid.uuid4().hex[:5]
    e1 = make_entity(client2, ah, f"Finance {tag}")
    e2 = make_entity(client2, ah, f"Operations {tag}")
    prog = client2.post("/api/audit-programs", json={"name": f"IT Controls {tag}", "steps": [
        {"objective": f"Access governance {tag}", "risk": "Excess access", "control": "Quarterly access review",
         "procedure": "Inspect reviews"},
        {"objective": f"Change management {tag}", "risk": "Unauthorised change", "control": "CAB approval",
         "procedure": "Sample changes"}]}, headers=ah).json()
    risk = client.post("/api/grc/risks", json={"title": f"Data protection {tag}", "category": "Information Technology",
                                               "inherent_likelihood": 5, "inherent_impact": 4,
                                               "residual_likelihood": 3, "residual_impact": 4}, headers=mh).json()
    assert client.post(f"/api/grc/risks/{risk['id']}/treatments", json={
        "framework_objectives": [{"program_id": prog["id"], "title": f"Access governance {tag}"}]},
        headers=mh).status_code == 201

    year = _free_year(client)
    plan = client.post("/api/assurance-plans", json={"fiscal_year": year, "title": f"FY{year} Assurance Plan",
                                                     "total_budget_hours": 5000, "period_start": f"{year}-01-01",
                                                     "period_end": f"{year}-12-31"}, headers=mh).json()
    request.addfinalizer(lambda: release_year(plan["id"]))
    fo = client.get(f"/api/assurance-plans/{plan['id']}/framework-objectives").json()
    linked = [o for o in fo["linked"] if o["program_id"] == prog["id"]]
    assert [o["title"] for o in linked] == [f"Access governance {tag}"] and linked[0]["strategic_risks"]
    assert len([o for o in fo["all"] if o["program_id"] == prog["id"]]) == 2

    bad = client.post(f"/api/assurance-plans/{plan['id']}/engagements", json={
        "title": "Bad", "objectives": [{"program_id": prog["id"], "title": "Not in framework"}]}, headers=mh)
    assert bad.status_code == 422
    eng = client.post(f"/api/assurance-plans/{plan['id']}/engagements", json={
        "title": f"Financial Controls Review {tag}", "audit_type": None, "planned_quarter": "Q1", "budget_hours": 800,
        "objectives": [{"program_id": prog["id"], "title": f"Access governance {tag}"}],
        "entity_unit_ids": [e1["id"], e2["id"]]}, headers=mh)
    assert eng.status_code == 201, eng.text
    eng = eng.json()
    assert sorted(eng["entity_unit_ids"]) == sorted([e1["id"], e2["id"]]) and len(eng["objectives"]) == 1

    cov = client.get(f"/api/assurance-plans/{plan['id']}/coverage").json()
    row = next(r for r in cov["engagements"] if r["engagement_id"] == eng["id"])
    assert set(row["entity_ids"]) == {e1["id"], e2["id"]}
    covered = {u["id"] for u in cov["entities"] if u["covered"]}
    assert {e1["id"], e2["id"]} <= covered

    # The framework treatment makes the strategic risk appear on the plan, with heat and assurance figures.
    prog_view = client.get(f"/api/assurance-plans/{plan['id']}/program").json()
    r = next(x for x in prog_view["strategic_risks"] if x["id"] == risk["id"])
    assert r["inherent_heat"] == 80.0 and r["residual_heat"] == 48.0 and r["projects"] == 1
    assert "overall_assurance" in r and r["description"] == ""

    # Starting the project brings in the chosen framework objective and entities.
    walk_plan_to_review(client, plan["id"], mh)
    gh = csrf_headers(login(client2, gm.username))
    assert client2.post(f"/api/assurance-plans/{plan['id']}/approve", json={"password": DEFAULT_PASSWORD},
                        headers=gh).status_code == 200
    release_plan(client2, plan["id"], gh)
    started = client.post(f"/api/plan-engagements/{eng['id']}/start", headers=mh)
    assert started.status_code == 200, started.text
    audit_id = started.json()["audit_id"]
    rcm = client.get(f"/api/audits/{audit_id}/rcm").json()
    assert [o["title"] for o in rcm["objectives"]] == [f"Access governance {tag}"]
    from sqlalchemy import select

    from app.domains.assurance.universe.models import AuditEntity

    db.rollback()
    ents = set(db.execute(select(AuditEntity.entity_id).where(AuditEntity.audit_id == audit_id)).scalars())
    assert {e1["id"], e2["id"]} <= ents


def test_issue_actions_activity_center_and_library(client, client2, db):
    aud = _u(db, "wiaud", "audit_manager")
    owner = make_user(db, f"wiown_{uuid.uuid4().hex[:6]}", Role.Auditee)
    h = csrf_headers(login(client, aud.username))
    tag = uuid.uuid4().hex[:5]
    audit = client.post("/api/audits", json={"title": f"Access {tag}", "scope": "x"}, headers=h).json()
    f = client.post(f"/api/audits/{audit['id']}/findings", json={
        "title": f"Access review evidence incomplete {tag}", "description": "d", "risk_rating": "High",
        "condition": "c", "recommendation": "r", "assigned_owner_email": owner.email}, headers=h).json()
    due = (date.today() + timedelta(days=5)).isoformat()
    a1 = client.post(f"/api/findings/{f['id']}/actions", json={
        "title": "Document and approve quarterly access review", "owner_email": owner.email,
        "description": "Update the review process", "due_date": due, "priority": "High", "notify_now": True,
        "reminders": False}, headers=h)
    assert a1.status_code == 201, a1.text
    assert a1.json()["notified"] is True
    a2 = client.post(f"/api/findings/{f['id']}/actions", json={"title": "Store evidence in repository",
                                                                "priority": "Medium", "notify_now": False},
                     headers=h)
    assert a2.status_code == 201
    past = client.post(f"/api/findings/{f['id']}/actions", json={"title": "Late", "due_date": "2000-01-01"},
                       headers=h)
    assert past.status_code == 422
    acts = client.get(f"/api/findings/{f['id']}/actions").json()
    assert [x["priority"] for x in acts] == ["High", "Medium"]
    after = client.get(f"/api/findings/{f['id']}").json()
    assert after["status"] == "Remediating" and after["remediation_status"] == "Management Remediating"
    from app.domains.issues.capa.models import Capa

    db.rollback()
    capa = db.get(Capa, a1.json()["id"])
    assert json.loads(capa.custom_fields)["reminders"] is False

    ac = client.get(f"/api/activity-center/issues-actions?audit_id={audit['id']}").json()
    assert ac["open_issues"] == 1 and ac["actions"]["due_soon"] == 1 and ac["actions"]["open"] == 2
    assert ac["actions_by_priority"]["High"] == 1
    assert ac["follow_up"][0]["remediation_status"] == "Management Remediating"
    assert ac["follow_up"][0]["retest"] == "Not started"
    oh = csrf_headers(login(client2, owner.username))
    assert client2.get("/api/activity-center/issues-actions", headers=oh).status_code == 403

    lib = client.get("/api/grc/risk-library?industry=Ports%20%26%20maritime").json()
    keys = {r["key"] for r in lib["risks"]}
    assert "equipment" in keys and "Ports & maritime" in lib["industries"]
    imp = client.post("/api/grc/risk-library/import", json={"keys": ["equipment", "environment"]}, headers=h)
    assert imp.status_code == 201, imp.text
    again = client.post("/api/grc/risk-library/import", json={"keys": ["equipment"]}, headers=h).json()
    assert again["imported"] == 0  # already in the register
    assert client.post("/api/grc/risk-library/import", json={"keys": ["nope"]}, headers=h).status_code == 422
