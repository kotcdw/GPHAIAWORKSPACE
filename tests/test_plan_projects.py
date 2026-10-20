"""Assurance plan projects: add to plan (new with audit type and programme, roll forward), what the audit brings
in when it starts, the plan programme overview, objectives and narratives across the plan, narrative import, the
phase-based progress and the project limit."""

from __future__ import annotations

import io
import uuid

import pytest

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


def release_year(plan_id):
    """Plan years are scarce in the test database (13 valid years); give this test's year back."""
    from app.core.database import SessionLocal
    from app.domains.assurance.planning.models import AssurancePlan

    with SessionLocal() as s:
        plan = s.get(AssurancePlan, plan_id)
        if plan is not None:
            plan.fiscal_year = 5000 + plan.id
            s.commit()


def _used_years():
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.domains.assurance.planning.models import AssurancePlan

    with SessionLocal() as s:
        return set(s.execute(select(AssurancePlan.fiscal_year)).scalars())


def _u(db, prefix, job, role=Role.Auditor):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def _free_year(client):
    used = _used_years()
    # 2031-2033 belong to test_planning_rcm.
    free = [y for y in [*range(2036, 2033, -1), *range(2030, 2023, -1)] if y not in used]
    if not free:
        pytest.skip("no free plan year in the test database")
    return free[0]


def test_plan_projects_end_to_end(client, client2, db, request):
    adm = _u(db, "ppadm", "platform_admin", Role.Admin)
    mgr = _u(db, "ppmgr", "audit_manager")
    gm = _u(db, "ppgm", "gm_audit")
    ah = csrf_headers(login(client2, adm.username))
    mh = csrf_headers(login(client, mgr.username))
    tag = uuid.uuid4().hex[:5]
    ent = make_entity(client2, ah, f"Billing {tag}")

    # An earlier audit to roll forward: objective, risk, control with a test plan, a narrative.
    old = client.post("/api/audits", json={"title": f"Billing FY prior {tag}", "scope": "x",
                                           "workflow": "Internal Control"}, headers=mh).json()
    o = client.post(f"/api/audits/{old['id']}/objectives", json={"title": "Dues are billed"}, headers=mh).json()
    r = client.post(f"/api/objectives/{o['id']}/risks", json={"title": "Calls not billed", "likelihood": 4,
                                                              "impact": 4}, headers=mh).json()
    c = client.post(f"/api/objectives/{o['id']}/controls", json={
        "title": "Daily reconciliation", "control_type": "Detective", "nature": "Manual", "frequency": "Daily",
        "is_key": True, "risk_ids": [r["id"]]}, headers=mh).json()
    client.patch(f"/api/controls/{c['id']}", json={"test_method": "Inspection", "total_sample_size": 25,
                                                   "test_steps": "Agree calls to invoices"}, headers=mh)
    client.post(f"/api/objectives/{o['id']}/narratives", json={"title": "Billing process", "description": "Steps",
                                                               "control_ids": [c["id"]]}, headers=mh)

    # An audit programme from the Project Library.
    prog = client2.post("/api/audit-programs", json={"name": f"Fuel programme {tag}", "steps": [
        {"objective": "Fuel is accounted for", "risk": "Pilferage", "control": "Daily dip readings",
         "procedure": "Compare dips to issues"}]}, headers=ah)
    assert prog.status_code == 201, prog.text
    prog = prog.json()

    year = _free_year(client)
    plan = client.post("/api/assurance-plans", json={"fiscal_year": year, "title": f"Plan {tag}",
                                                      "total_budget_hours": 300, "period_start": f"{year}-01-01",
                                                      "period_end": f"{year}-12-31"}, headers=mh)
    assert plan.status_code == 201, plan.text
    plan = plan.json()
    request.addfinalizer(lambda: release_year(plan["id"]))
    assert plan["period_end"] == f"{year}-12-31"
    base = f"/api/assurance-plans/{plan['id']}"
    bad = client.post(f"{base}/engagements", json={"title": "x", "audit_type": "Nope"}, headers=mh)
    assert bad.status_code == 422
    both = client.post(f"{base}/engagements", json={"title": "x", "program_id": prog["id"],
                                                    "source_audit_id": old["id"]}, headers=mh)
    assert both.status_code == 422

    # Add to plan: new project with an audit type and programme; roll forward the earlier audit.
    audit_type = client.get("/api/organizations/types").json()["audit_types"][0]
    new = client.post(f"{base}/engagements", json={"title": f"Fuel {tag}", "budget_hours": 120,
                                                   "program_id": prog["id"], "entity_unit_id": ent["id"],
                                                   "audit_type": audit_type},
                      headers=mh)
    assert new.status_code == 201, new.text
    assert new.json()["program_name"].startswith(prog["prog_ref"])
    cands = client.get(f"{base}/rollforward-candidates", params={"q": tag}, headers=mh).json()
    assert any(x["id"] == old["id"] for x in cands)
    rf = client.post(f"{base}/rollforward", json={"audit_id": old["id"], "title": f"Billing FY{year} {tag}",
                                                  "budget_hours": 250}, headers=mh)
    assert rf.status_code == 201, rf.text
    assert rf.json()["source_audit_ref"] == f"AUD-{old['id']:04d}"

    prog_view = client.get(f"{base}/program", headers=mh).json()
    m = prog_view["metrics"]
    assert m["projects"] == 2 and m["max_projects"] >= 2 and m["hours"]["planned"] == 370
    assert m["hours"]["over"] == 70 and all(p["progress"] == 0 for p in prog_view["projects"])
    assert prog_view["categories"] and m["covered"] >= 1

    # Approve and launch, then start both engagements.
    walk_plan_to_review(client, plan["id"], mh)
    gh = csrf_headers(login(client2, gm.username))
    assert client2.post(f"{base}/approve", json={"password": DEFAULT_PASSWORD}, headers=gh).status_code == 200
    release_plan(client2, plan["id"], gh)
    engs = {e["title"]: e for e in client.get(base, headers=mh).json()["engagements"]}
    a_rf = client.post(f"/api/plan-engagements/{engs[f'Billing FY{year} {tag}']['id']}/start", headers=mh)
    assert a_rf.status_code == 200, a_rf.text
    rf_id = a_rf.json()["audit_id"]
    rcm = client.get(f"/api/audits/{rf_id}/rcm", headers=mh).json()
    ctl = rcm["objectives"][0]["controls"][0]
    assert ctl["title"] == "Daily reconciliation" and ctl["test_method"] == "Inspection" and not ctl["tests"]
    assert rcm["objectives"][0]["risks"][0]["control_ids"] == [ctl["id"]]
    assert len(client.get(f"/api/audits/{rf_id}/narratives", headers=mh).json()) == 1
    a_new = client.post(f"/api/plan-engagements/{engs[f'Fuel {tag}']['id']}/start", headers=mh).json()
    fuel = client.get(f"/api/audits/{a_new['audit_id']}", headers=mh).json()
    assert fuel["audit_type"] == audit_type
    fuel_rcm = client.get(f"/api/audits/{a_new['audit_id']}/rcm", headers=mh).json()
    assert fuel_rcm["objectives"][0]["title"] == "Fuel is accounted for"

    # Progress counts phases: the rolled-forward audit already has narratives, a matrix and a test plan.
    prog_view = client.get(f"{base}/program", headers=mh).json()
    rf_row = next(p for p in prog_view["projects"] if p["audit_id"] == rf_id)
    assert 0 < rf_row["progress"] < 100 and rf_row["rolled_from"] == f"AUD-{old['id']:04d}"

    # Objectives and narratives across the plan; import a narrative from a Word document.
    objs = client.get(f"{base}/objectives", headers=mh).json()
    target = next(x for x in objs if x["audit_id"] == rf_id)
    assert target["controls"] == 1 and target["narratives"] == 1
    import docx

    d = docx.Document()
    d.add_paragraph("Vessel calls are captured at the gate and billed nightly.")
    buf = io.BytesIO()
    d.save(buf)
    imp = client.post(f"/api/objectives/{target['id']}/narratives/import", headers=mh,
                      files={"file": ("Billing narrative.docx", buf.getvalue(),
                                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert imp.status_code == 201, imp.text
    narrs = client.get(f"{base}/narratives", headers=mh).json()
    assert any(n["title"] == "Billing narrative" for n in narrs)
    bad = client.post(f"/api/objectives/{target['id']}/narratives/import", headers=mh,
                      files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 422


def test_plan_project_limit(client, db, request):
    mgr = _u(db, "pplim", "audit_manager")
    mh = csrf_headers(login(client, mgr.username))
    adm = _u(db, "pplimadm", "platform_admin", Role.Admin)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c2:
        ah = csrf_headers(login(c2, adm.username))
        assert c2.put("/api/config", json={"values": {"plan_max_projects": 1}}, headers=ah).status_code == 200
        try:
            year = _free_year(client)
            plan = client.post("/api/assurance-plans", json={"fiscal_year": year, "title": "Limit"}, headers=mh).json()
            request.addfinalizer(lambda: release_year(plan["id"]))
            base = f"/api/assurance-plans/{plan['id']}"
            assert client.post(f"{base}/engagements", json={"title": "One"}, headers=mh).status_code == 201
            full = client.post(f"{base}/engagements", json={"title": "Two"}, headers=mh)
            assert full.status_code == 409 and "at most 1" in full.text
        finally:
            c2.put("/api/config", json={"values": {"plan_max_projects": 100}}, headers=ah)
