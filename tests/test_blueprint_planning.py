"""PROJECTBLUEPRINT planning rules: who may create, link and roll forward plan projects; resource overage; the
next-cycle planning signals."""

from __future__ import annotations

import uuid

import pytest

from app.core import permissions as perms
from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user
from tests.test_plan_projects import _free_year, release_year


def _u(db, prefix, job, role=Role.Auditor):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


@pytest.fixture
def without_project_creator(monkeypatch):
    """Make the given users Assurance Plans Admins without the Project Creator permission (audit.create)."""
    ids: set[int] = set()
    real = perms.permissions_of

    def patched(user):
        have = real(user)
        return have - {"audit.create"} if user is not None and user.id in ids else have

    monkeypatch.setattr(perms, "permissions_of", patched)
    return ids


def test_plan_roles_overage_and_link_without_project_creator(client, client2, db, request, without_project_creator):
    mgr = _u(db, "bpmgr", "audit_manager")
    planner = _u(db, "bpplan", "audit_manager")
    aud = _u(db, "bpaud", "auditor")
    mh = csrf_headers(login(client, mgr.username))
    year = _free_year(client)

    # An ordinary auditor cannot create a plan.
    ah = csrf_headers(login(client2, aud.username))
    refused = client2.post("/api/assurance-plans", json={"fiscal_year": year, "title": "No"}, headers=ah)
    assert refused.status_code == 403

    plan = client.post("/api/assurance-plans", json={"fiscal_year": year, "title": "Blueprint plan",
                                                     "total_budget_hours": 100}, headers=mh)
    assert plan.status_code == 201, plan.text
    plan = plan.json()
    request.addfinalizer(lambda: release_year(plan["id"]))

    # Resource use: 80 + 50 budgeted against 100 available shows 30 hours over.
    for title, hours in (("Payroll", 80), ("Procurement", 50)):
        r = client.post(f"/api/assurance-plans/{plan['id']}/engagements",
                        json={"title": title, "budget_hours": hours}, headers=mh)
        assert r.status_code == 201, r.text
    summary = client.get(f"/api/assurance-plans/{plan['id']}", headers=mh).json()["summary"]
    assert summary["planned_hours"] == 130
    assert summary["hours_over"] == 30 and summary["hours_remaining"] == 0

    # An existing audit to link and to roll forward.
    existing = client.post("/api/audits", json={"title": f"Existing {uuid.uuid4().hex[:4]}"}, headers=mh).json()

    # The planner keeps plan.prepare but has no Project Creator permission.
    without_project_creator.add(planner.id)
    ph = csrf_headers(login(client2, planner.username))
    create = client2.post(f"/api/assurance-plans/{plan['id']}/engagements",
                          json={"title": "New project", "budget_hours": 10}, headers=ph)
    assert create.status_code == 403
    roll = client2.post(f"/api/assurance-plans/{plan['id']}/rollforward",
                        json={"audit_id": existing["id"], "title": "Rolled"}, headers=ph)
    assert roll.status_code == 403
    link = client2.post(f"/api/assurance-plans/{plan['id']}/include",
                        json={"audit_ids": [existing["id"]], "quarter": "Q3"}, headers=ph)
    assert link.status_code == 200, link.text
    titles = [e["title"] for e in client2.get(f"/api/assurance-plans/{plan['id']}", headers=ph).json()["engagements"]]
    assert existing["title"] in titles


def test_next_cycle_signals(client, client2, db):
    mgr = _u(db, "bsmgr", "audit_manager")
    aud = _u(db, "bsaud", "auditor")
    mh = csrf_headers(login(client, mgr.username))
    r = client.get("/api/assurance-plans/next-cycle-signals?fiscal_year=2099", headers=mh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_fiscal_year"] == 2099, str(body)[:500]
    assert {"risks", "uncovered_entities", "deferred_engagements", "carry_forward", "note"} <= set(body)
    assert "automatically" in body["note"]
    ah = csrf_headers(login(client2, aud.username))
    assert client2.get("/api/assurance-plans/next-cycle-signals", headers=ah).status_code == 403
