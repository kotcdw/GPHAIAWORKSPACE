"""The audit lifecycle end to end, in one chain:
Audit universe -> audit risk assessment (score and prioritise) -> Assurance Plan (generated from the assessment,
reviewed, approved, distributed) -> engagement started as an audit -> fieldwork scoped from the entity ->
closing the audit feeds the date back to the universe."""

from __future__ import annotations

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


def test_universe_to_fieldwork_in_one_chain(client, client2, db, request):
    adm = _u(db, "lfadm", "platform_admin", Role.Admin)
    ah = csrf_headers(login(client, adm.username))
    tag = uuid.uuid4().hex[:5]

    # 1-2. Audit universe: Ready auditable entities.
    hi = make_entity(client, ah, f"Revenue {tag}")
    lo = make_entity(client, ah, f"Stores {tag}")

    # 3-4. Audit risk assessment: score every entity on every factor, prioritise, complete.
    f1 = client.post("/api/assessment-factors", json={"name": f"Fraud {tag}"}, headers=ah).json()
    f2 = client.post("/api/assessment-factors", json={"name": f"Materiality {tag}"}, headers=ah).json()
    ara = client.post("/api/audit-risk-assessments", json={"name": f"Lifecycle {tag}",
                                                           "entity_ids": [hi["id"], lo["id"]],
                                                           "factor_ids": [f1["id"], f2["id"]]}, headers=ah)
    assert ara.status_code == 201, ara.text
    url = f"/api/audit-risk-assessments/{ara.json()['id']}"
    for eid, score in ((hi["id"], 3), (lo["id"], 1)):
        for fid in (f1["id"], f2["id"]):
            assert client.put(f"{url}/scores", json={"entity_id": eid, "factor_id": fid, "score": score},
                              headers=ah).status_code == 200
    client.put(f"{url}/priorities", json={"entity_ids": [hi["id"]]}, headers=ah)
    client.put(f"{url}/conclusion", json={"conclusion": "Revenue carries the highest risk."}, headers=ah)
    assert client.post(f"{url}/complete", headers=ah).json()["status"] == "Completed"
    assert client.get(f"/api/auditable-entities/{hi['id']}").json()["rating"] == "High"

    # 5-6. Create the audit plan from the assessment: one engagement per prioritised entity.
    used = _used_years()
    # 2031-2033 belong to test_planning_rcm.
    free = [y for y in [*range(2036, 2033, -1), *range(2030, 2023, -1)] if y not in used]
    if not free:
        pytest.skip("no free plan year in the test database")
    plan = client.post(f"{url}/start-planning", json={"fiscal_year": free[0]}, headers=ah)
    assert plan.status_code == 200, plan.text
    pid = plan.json()["plan_id"]
    request.addfinalizer(lambda: release_year(pid))
    engs = client.get(f"/api/assurance-plans/{pid}").json()["engagements"]
    assert [e["entity_unit_id"] for e in engs] == [hi["id"]]  # the low-risk entity is not planned

    # 7. Approve and launch: review cycle, GM Audit approval (e-signature), Audit Committee, distribution.
    mgr = _u(db, "lfmgr", "audit_manager")
    gm = _u(db, "lfgm", "gm_audit")
    mh = csrf_headers(login(client, mgr.username))
    eng_id = engs[0]["id"]
    early = client.post(f"/api/plan-engagements/{eng_id}/start", headers=mh)
    assert early.status_code == 409  # not before the plan is approved and launched
    walk_plan_to_review(client, pid, mh)
    gh = csrf_headers(login(client2, gm.username))
    r = client2.post(f"/api/assurance-plans/{pid}/approve", json={"password": DEFAULT_PASSWORD}, headers=gh)
    assert r.status_code == 200, r.text
    assert client.post(f"/api/plan-engagements/{eng_id}/start", headers=mh).status_code == 409  # not distributed
    release_plan(client2, pid, gh)

    # Audits: the engagement becomes an audit linked to the plan and the auditable entity.
    started = client.post(f"/api/plan-engagements/{eng_id}/start", headers=mh)
    assert started.status_code == 200, started.text
    aid = started.json()["audit_id"]
    audit = client.get(f"/api/audits/{aid}", headers=mh).json()
    assert audit["plan_id"] == pid and audit["status"] == "Planned"
    assert [e["id"] for e in client.get(f"/api/audits/{aid}/entities", headers=mh).json()] == [hi["id"]]
    row = next(x for x in client.get("/api/audits/register", params={"q": audit["title"]}, headers=mh).json()["items"]
               if x["id"] == aid)
    assert row["phase"] == "Plan" and row["plan"]

    # Fieldwork: scoping from the entity is offered, and the steps track the work.
    assert client.get(f"/api/audits/{aid}/scoping", headers=mh).status_code == 200
    fw = client.get(f"/api/audits/{aid}/fieldwork", headers=mh).json()
    assert set(fw["steps"]) >= {"objectives", "risks", "controls", "walked", "tests"}
