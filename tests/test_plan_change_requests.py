"""Changes to an approved plan: change request, reason, affected items, resource and coverage impact,
requester, independent reviewer, approver's e-signature and a new, re-distributed version."""

from __future__ import annotations

import uuid

from app.core import permissions as perms
from app.core.enums import Role, utcnow
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user, release_plan, walk_plan_to_review

_YEARS = iter(range(2024, 2031))


def _u(db, prefix, job, role=Role.Auditor):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def test_change_request_lifecycle(client, client2, db):
    adm = _u(db, "cradm", "platform_admin", Role.Admin)
    pia = _u(db, "crpia", "pia")
    mgr = _u(db, "crmgr", "audit_manager")
    ah = csrf_headers(login(client2, adm.username))
    # Universe unit to measure coverage.
    loc = client2.post("/api/locations", json={"code": f"L{uuid.uuid4().hex[:4]}", "name": "Tema"}, headers=ah).json()
    unit = client2.post(
        "/api/entity-units",
        json={"location_id": loc["id"], "code": "CY", "name": "Container yard", "risk_likelihood": 5, "risk_impact": 4},
        headers=ah,
    ).json()
    mh = csrf_headers(login(client, mgr.username))
    for fy in _YEARS:
        created = client.post(
            "/api/assurance-plans", json={"fiscal_year": fy, "title": "Plan", "total_budget_hours": 250}, headers=mh
        )
        if created.status_code == 201:
            break
    pid = created.json()["id"]
    eng = client.post(
        f"/api/assurance-plans/{pid}/engagements", json={"title": "Payroll", "budget_hours": 200}, headers=mh
    ).json()
    base = f"/api/assurance-plans/{pid}/change-requests"
    draft = client.post(
        base,
        json={
            "title": "Too early",
            "reason": "Too early to change",
            "items": [{"action": "cancel", "engagement_id": eng["id"]}],
        },
        headers=mh,
    )
    assert draft.status_code == 409  # a draft is edited directly

    walk_plan_to_review(client, pid, mh)
    assert (
        client2.post(f"/api/assurance-plans/{pid}/approve", json={"password": DEFAULT_PASSWORD}, headers=ah).status_code
        == 200
    )
    release_plan(client2, pid, ah)  # committee approval v1, distributed to the admin

    # Direct edits of the approved plan are refused.
    assert (
        client2.post(
            f"/api/plan-engagements/{eng['id']}/cancel", json={"reason": "No longer needed now"}, headers=ah
        ).status_code
        == 409
    )
    assert (
        client2.post(
            f"/api/plan-engagements/{eng['id']}/amend",
            json={"budget_hours": 10, "reason": "Shorter scope agreed"},
            headers=ah,
        ).status_code
        == 409
    )

    # Requester: the Audit Manager. Reason and items are validated.
    assert (
        client.post(
            base,
            json={"title": "Add yard", "reason": "short", "items": [{"action": "add", "title": "Yard"}]},
            headers=mh,
        ).status_code
        == 422
    )
    assert (
        client.post(
            base,
            json={
                "title": "Bad",
                "reason": "Engagement from another plan",
                "items": [{"action": "cancel", "engagement_id": 999999}],
            },
            headers=mh,
        ).status_code
        == 422
    )
    body = {
        "title": "Cover the container yard",
        "reason": "New high-risk unit identified by the Board",
        "items": [
            {
                "action": "add",
                "title": "Container yard controls",
                "entity_unit_id": unit["id"],
                "planned_quarter": "Q3",
                "budget_hours": 150,
                "lead_auditor_id": pia.id,
            },
            {"action": "change", "engagement_id": eng["id"], "budget_hours": 120},
        ],
    }
    preview = client.post(f"{base}/impact", json=body, headers=mh).json()
    assert preview["resource"]["hours_delta"] == 70 and preview["resource"]["over_budget"] is True
    assert preview["coverage"]["coverage_after"] > preview["coverage"]["coverage_before"]
    assert any("Container yard" in n for n in preview["coverage"]["high_risk_newly_covered"])
    cr = client.post(base, json=body, headers=mh).json()
    assert cr["cr_ref"].startswith("PCR-") and cr["status"] == "Submitted" and cr["base_version"] == 1

    # Reviewer: not the requester. Return, rework, resubmit, endorse.
    assert (
        client.post(
            f"/api/plan-change-requests/{cr['id']}/review", json={"decision": "Endorse"}, headers=mh
        ).status_code
        == 403
    )
    ph = csrf_headers(login(client2, pia.username))
    assert (
        client2.post(
            f"/api/plan-change-requests/{cr['id']}/review", json={"decision": "Return"}, headers=ph
        ).status_code
        == 422
    )
    back = client2.post(
        f"/api/plan-change-requests/{cr['id']}/review",
        json={"decision": "Return", "comment": "Keep within budget"},
        headers=ph,
    ).json()
    assert back["status"] == "Returned" and back["reviewer"]
    body["items"][1]["budget_hours"] = 100
    body["items"][0]["budget_hours"] = 100
    again = client.post(f"/api/plan-change-requests/{cr['id']}/resubmit", json=body, headers=mh).json()
    assert again["status"] == "Submitted" and again["impact"]["resource"]["over_budget"] is False
    assert (
        client2.post(
            f"/api/plan-change-requests/{cr['id']}/approve", json={"password": DEFAULT_PASSWORD}, headers=ph
        ).status_code
        == 403
    )  # PIA cannot approve
    ok = client2.post(f"/api/plan-change-requests/{cr['id']}/review", json={"decision": "Endorse"}, headers=ph).json()
    assert ok["status"] == "Endorsed"

    # Approver: GM Audit role (here the Platform Administrator) e-signs; the plan moves to version 2.
    ah = csrf_headers(login(client2, adm.username))
    assert (
        client2.post(
            f"/api/plan-change-requests/{cr['id']}/approve", json={"password": "wrong-password"}, headers=ah
        ).status_code
        == 400
    )
    cae = client2.post(
        f"/api/plan-change-requests/{cr['id']}/approve", json={"password": DEFAULT_PASSWORD}, headers=ah
    ).json()
    # Adding an engagement is significant: IIA GIAS 9.4 -> the Audit Committee approves it after the CAE.
    assert cae["significant"] and cae["status"] == "Awaiting Committee" and cae["approver"]
    assert any("adds an engagement" in r for r in cae["impact"]["significance"])
    assert client2.get(f"/api/assurance-plans/{pid}").json()["current_version"] == 1, "not applied yet"
    now = utcnow().isoformat()
    deferred = client2.post(
        f"/api/plan-change-requests/{cr['id']}/committee-decision",
        json={"decision": "Deferred", "meeting_date": now, "reference": "AC/7"},
        headers=ah,
    ).json()
    assert deferred["status"] == "Awaiting Committee"
    done = client2.post(
        f"/api/plan-change-requests/{cr['id']}/committee-decision",
        json={"decision": "Approved", "meeting_date": now, "reference": "AC/8", "notes": "Approved at the Q3 meeting"},
        headers=ah,
    ).json()
    assert done["status"] == "Approved" and done["new_version"] == 2 and done["committee_reference"] == "AC/8"
    plan = client2.get(f"/api/assurance-plans/{pid}").json()
    assert plan["current_version"] == 2
    assert {e["title"]: e["budget_hours"] for e in plan["engagements"]} == {
        "Payroll": 100,
        "Container yard controls": 100,
    }
    v2 = client2.get(f"/api/assurance-plans/{pid}/versions/2").json()
    assert v2["decision"].startswith("Amended by PCR-") and "Audit Committee AC/8" in v2["decision"]
    # Approved versions are submitted to the Internal Audit Agency.
    iaa = client2.post(
        f"/api/assurance-plans/{pid}/versions/2/iaa-submission",
        json={"submitted_on": now, "reference": "IAA/GPHA/2026/14"},
        headers=ah,
    ).json()
    assert next(v for v in iaa["versions"] if v["version"] == 2)["iaa_reference"] == "IAA/GPHA/2026/14"

    # A minor change (below the hours threshold, nothing added or cancelled) is approved by the CAE alone.
    mh = csrf_headers(login(client, mgr.username))
    minor = client.post(
        base,
        json={
            "title": "Re-time payroll",
            "reason": "Payroll system cut-over moved",
            "items": [{"action": "change", "engagement_id": eng["id"], "planned_quarter": "Q4"}],
        },
        headers=mh,
    ).json()
    assert minor["significant"] is False
    ph = csrf_headers(login(client2, pia.username))
    client2.post(f"/api/plan-change-requests/{minor['id']}/review", json={"decision": "Endorse"}, headers=ph)
    ah = csrf_headers(login(client2, adm.username))
    m2 = client2.post(
        f"/api/plan-change-requests/{minor['id']}/approve", json={"password": DEFAULT_PASSWORD}, headers=ah
    ).json()
    assert m2["status"] == "Approved" and m2["new_version"] == 3
    changes = client2.get(f"/api/assurance-plans/{pid}/changes").json()
    assert {c["change_type"] for c in changes} >= {"Added", "Changed"}
    assert all(
        c["reason"].startswith((cr["cr_ref"], minor["cr_ref"]))
        for c in changes
        if c["change_type"] in ("Added", "Changed")
    )
    cyc = client2.get(f"/api/assurance-plans/{pid}/cycle").json()
    assert any(d["version"] == 2 and d["user_id"] == adm.id for d in cyc["distribution"]), "re-distributed"

    # A request raised against an old version cannot be approved; a rejection closes a request.
    mh = csrf_headers(login(client, mgr.username))
    cr2 = client.post(
        base,
        json={
            "title": "Drop payroll",
            "reason": "Covered by external auditors",
            "items": [{"action": "cancel", "engagement_id": eng["id"]}],
        },
        headers=mh,
    ).json()
    ph = csrf_headers(login(client2, pia.username))
    client2.post(f"/api/plan-change-requests/{cr2['id']}/review", json={"decision": "Endorse"}, headers=ph)
    ah = csrf_headers(login(client2, adm.username))
    rej = client2.post(
        f"/api/plan-change-requests/{cr2['id']}/approve",
        json={"password": DEFAULT_PASSWORD, "decision": "Reject", "comment": "Keep payroll"},
        headers=ah,
    ).json()
    assert rej["status"] == "Rejected"
    assert client2.get(f"/api/assurance-plans/{pid}").json()["current_version"] == 3

    # Full revision needs a reason.
    assert client2.post(f"/api/assurance-plans/{pid}/reopen", json={}, headers=ah).status_code == 422
