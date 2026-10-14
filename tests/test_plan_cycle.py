"""Annual planning cycle: preparation -> universe review -> managers' meeting -> draft -> internal review
-> submission -> Audit Committee decision -> approved version -> GM distribution -> PIA / Manager execution."""

from __future__ import annotations

import uuid

from app.core import permissions as perms
from app.core.enums import Role, utcnow
from tests.conftest import DEFAULT_PASSWORD, PREP_CHECKS, csrf_headers, login, make_user

_YEARS = iter(range(2024, 2031))


def _u(db, prefix, job):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", Role.Auditor)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def test_full_annual_planning_cycle(client, client2, db):
    mgr = _u(db, "pcmgr", "audit_manager")
    gm = _u(db, "pcgm", "gm_audit")
    pia = _u(db, "pcpia", "pia")
    aud = _u(db, "pcaud", "auditor")
    h = csrf_headers(login(client, mgr.username))
    for fy in _YEARS:
        created = client.post(
            "/api/assurance-plans", json={"fiscal_year": fy, "title": "Plan", "total_budget_hours": 600}, headers=h
        )
        if created.status_code == 201:
            break
    plan = created.json()
    pid = plan["id"]
    base = f"/api/assurance-plans/{pid}/cycle"
    eng = client.post(
        f"/api/assurance-plans/{pid}/engagements",
        json={"title": "Payroll", "budget_hours": 100, "lead_auditor_id": pia.id},
        headers=h,
    ).json()
    cyc = client.get(base).json()
    assert cyc["stage"] == "preparation" and cyc["can"]["preparation"] and len(cyc["stages"]) == 10

    # 1. Preparation needs every checklist item.
    assert client.post(f"{base}/preparation", json={"checks": PREP_CHECKS[:2]}, headers=h).status_code == 422
    # Steps cannot be skipped.
    assert client.post(f"{base}/submit-review", json={}, headers=h).status_code == 409
    assert client.post(f"{base}/preparation", json={"checks": PREP_CHECKS}, headers=h).status_code == 200
    # 2. Universe review stores a snapshot of the risk universe.
    preview = client.get(f"{base}/universe").json()
    assert "due_count" in preview
    assert (
        client.post(
            f"{base}/universe-review", json={"notes": "Ratings refreshed with management"}, headers=h
        ).status_code
        == 200
    )
    # 3. Managers' meeting (not in the future).
    future = utcnow().replace(year=utcnow().year + 1).isoformat()
    assert (
        client.post(
            f"{base}/managers-meeting",
            json={"meeting_date": future, "attendees": "All managers", "minutes": "Agreed the coverage"},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{base}/managers-meeting",
            json={
                "meeting_date": utcnow().isoformat(),
                "attendees": "GM Audit; PIAs; Audit Managers",
                "minutes": "Agreed coverage and priorities",
            },
            headers=h,
        ).status_code
        == 200
    )
    # 4. Draft -> internal review; an auditor cannot prepare.
    ah = csrf_headers(login(client2, aud.username))
    assert client2.post(f"{base}/submit-review", json={}, headers=ah).status_code == 403
    assert client.post(f"{base}/submit-review", json={"notes": "Ready"}, headers=h).json()["stage"] == "internal_review"

    # 5. Internal review: GM returns once, then e-signs.
    gh = csrf_headers(login(client2, gm.username))
    back = client2.post(f"{base}/return", json={"comment": "Add IT coverage"}, headers=gh).json()
    assert back["stage"] == "drafting"
    client.post(f"{base}/submit-review", json={}, headers=h)
    ok = client2.post(f"/api/assurance-plans/{pid}/approve", json={"password": DEFAULT_PASSWORD}, headers=gh)
    assert ok.status_code == 200, ok.text
    assert client2.get(base).json()["stage"] == "submission"

    # Engagements cannot start before distribution.
    ph = csrf_headers(login(client, pia.username))
    assert client.post(f"/api/plan-engagements/{eng['id']}/start", headers=ph).status_code == 409

    # 6. Submission; 7. Committee decision (deferred, then approved with amendments).
    now = utcnow().isoformat()
    assert (
        client2.post(
            f"{base}/submit-authority",
            json={"authority": "Audit Committee", "submitted_on": now, "reference": "IA/SUB/1"},
            headers=gh,
        ).json()["stage"]
        == "committee"
    )
    assert (
        client2.post(
            f"{base}/committee-decision",
            json={"decision": "Deferred", "meeting_date": now, "reference": "AC/1"},
            headers=gh,
        ).json()["stage"]
        == "committee"
    )
    assert (
        client2.post(
            f"{base}/committee-decision",
            json={"decision": "Approved with amendments", "meeting_date": now, "reference": "AC/2"},
            headers=gh,
        ).status_code
        == 422
    )
    cyc = client2.post(
        f"{base}/committee-decision",
        json={
            "decision": "Approved with amendments",
            "meeting_date": now,
            "reference": "AC/2",
            "notes": "Add a cyber security review in Q4",
        },
        headers=gh,
    ).json()
    # 8. Approved version 1 frozen.
    assert cyc["stage"] == "distribution" and cyc["current_version"] == 1 and cyc["versions"][0]["version"] == 1
    v1 = client2.get(f"/api/assurance-plans/{pid}/versions/1").json()
    assert v1["committee_reference"] == "AC/2" and v1["engagements"][0]["title"] == "Payroll"
    doc = client2.get(f"/api/assurance-plans/{pid}/versions/1/export.docx")
    assert doc.status_code == 200 and doc.content[:2] == b"PK"

    # 9. Only the GM Audit distributes; the PIA acknowledges.
    assert client.post(f"{base}/distribute", json={"user_ids": [pia.id]}, headers=ph).status_code == 403
    rec = client2.get(f"{base}/recipients").json()
    assert any(r["id"] == pia.id and r["suggested"] for r in rec)
    cyc = client2.post(
        f"{base}/distribute", json={"user_ids": [pia.id, mgr.id], "note": "Approved plan"}, headers=gh
    ).json()
    assert cyc["stage"] == "execution" and len(cyc["distribution"]) == 2
    mine = client.get(base).json()
    assert mine["can"]["acknowledge"]
    acked = client.post(f"{base}/acknowledge", headers=ph).json()
    assert any(d["user_id"] == pia.id and d["acknowledged_at"] for d in acked["distribution"])

    # 10. Execution.
    started = client.post(f"/api/plan-engagements/{eng['id']}/start", headers=ph)
    assert started.status_code == 200, started.text
    cyc = client.get(base).json()
    assert cyc["execution"]["started"] == 1
    assert [s["state"] for s in cyc["stages"]][-1] == "current"

    # Returned by the Committee after a reopen -> back to drafting; re-approval makes version 2.
    client2.post(
        f"/api/assurance-plans/{pid}/reopen", json={"reason": "Mid-year revision after restructuring"}, headers=gh
    )
    assert client2.get(base).json()["stage"] == "drafting"


def test_plan_lifecycle_statuses(client, client2, db):
    """Draft -> In Review -> Returned -> In Review -> Submitted -> Approved -> Distributed -> In Execution
    -> Revised -> ... -> Closed -> Archived."""
    from tests.conftest import walk_plan_to_review

    mgr = _u(db, "lsmgr", "audit_manager")
    gm = _u(db, "lsgm", "gm_audit")
    h = csrf_headers(login(client, mgr.username))
    gh = csrf_headers(login(client2, gm.username))
    for fy in _YEARS:
        created = client.post("/api/assurance-plans", json={"fiscal_year": fy, "title": "Plan"}, headers=h)
        if created.status_code == 201:
            break
    pid = created.json()["id"]
    base = f"/api/assurance-plans/{pid}/cycle"

    def st() -> str:
        return client.get(f"/api/assurance-plans/{pid}").json()["lifecycle_status"]

    assert st() == "Draft"
    eng = client.post(
        f"/api/assurance-plans/{pid}/engagements", json={"title": "Stores", "budget_hours": 50}, headers=h
    ).json()
    walk_plan_to_review(client, pid, h)
    assert st() == "In Review"
    client2.post(f"{base}/return", json={"comment": "Rework hours"}, headers=gh)
    assert st() == "Returned"
    client.patch(f"/api/plan-engagements/{eng['id']}", json={"budget_hours": 60}, headers=h)
    assert st() == "Returned", "editing a returned plan keeps it Returned until resubmitted"
    client.post(f"{base}/submit-review", json={}, headers=h)
    assert st() == "In Review"
    client2.post(f"/api/assurance-plans/{pid}/approve", json={"password": DEFAULT_PASSWORD}, headers=gh)
    assert st() == "Submitted"
    now = utcnow().isoformat()
    client2.post(f"{base}/submit-authority", json={"submitted_on": now}, headers=gh)
    assert st() == "Submitted"
    client2.post(
        f"{base}/committee-decision",
        json={"decision": "Approved", "meeting_date": now, "reference": "AC/9"},
        headers=gh,
    )
    assert st() == "Approved"
    client2.post(f"{base}/distribute", json={"user_ids": [mgr.id]}, headers=gh)
    assert st() == "Distributed"
    started = client.post(f"/api/plan-engagements/{eng['id']}/start", headers=h)
    assert started.status_code == 200, started.text
    assert st() == "In Execution"

    # Mid-year revision of the approved version.
    client2.post(
        f"/api/assurance-plans/{pid}/reopen", json={"reason": "Mid-year revision after restructuring"}, headers=gh
    )
    assert st() == "Revised"
    client.post(f"{base}/submit-review", json={}, headers=h)
    assert st() == "In Review"
    client2.post(f"/api/assurance-plans/{pid}/approve", json={"password": DEFAULT_PASSWORD}, headers=gh)
    client2.post(f"{base}/submit-authority", json={"submitted_on": now}, headers=gh)
    cyc = client2.post(
        f"{base}/committee-decision",
        json={"decision": "Approved", "meeting_date": now, "reference": "AC/10"},
        headers=gh,
    ).json()
    assert cyc["current_version"] == 2 and st() == "Approved"

    # Close the year (the started audit must be closed first) and archive it.
    from app.core.enums import AuditStatus
    from app.domains.audit.audits.models import Audit

    db.rollback()
    audit = db.get(Audit, started.json()["audit_id"])
    audit.status = AuditStatus.Closed
    db.commit()
    assert client2.post(f"/api/assurance-plans/{pid}/archive", headers=gh).status_code == 409
    assert client2.post(f"/api/assurance-plans/{pid}/close", headers=gh).status_code == 200
    assert st() == "Closed"
    assert client2.post(f"/api/assurance-plans/{pid}/archive", headers=gh).status_code == 200
    assert st() == "Archived"
    listed = [p["id"] for p in client.get("/api/assurance-plans").json()]
    assert pid not in listed
    assert pid in [p["id"] for p in client.get("/api/assurance-plans?include_archived=true").json()]
