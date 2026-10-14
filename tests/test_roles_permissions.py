"""Job roles and the permission matrix, Audit Administrator configuration, audit programmes,
evidence requests, the governance portal and the port portfolio."""

from __future__ import annotations

import io
import uuid

from app.core import permissions as perms
from app.core.enums import ReviewLevel, Role
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, job=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
        db.commit()
    return user


def test_default_job_roles_and_me_permissions(client, db):
    admin = _u(db, "rpadm", Role.Admin)
    mgr = _u(db, "rpmgr")
    mgr.review_level = ReviewLevel.Manager
    db.commit()
    assert perms.job_role_of(admin) == "platform_admin" and perms.job_role_of(mgr) == "audit_manager"
    login(client, mgr.username)
    me = client.get("/api/auth/me").json()
    assert "audit.memo_approve" in me["permissions"] and "system.roles" not in me["permissions"]


def test_platform_admin_edits_matrix_and_assigns_job_roles(client, client2, db):
    admin = _u(db, "rpadm2", Role.Admin)
    clerk = _u(db, "rpclerk", job="audit_clerk")
    h = csrf_headers(login(client, admin.username))
    cat = client.get("/api/roles").json()
    assert {r["code"] for r in cat["roles"]} >= {"platform_admin", "gm_audit", "pia", "auditee", "committee"}
    # The clerk cannot record findings.
    ch = csrf_headers(login(client2, clerk.username))
    aid = client.post("/api/audits", json={"title": "Clerk test", "scope": "x"}, headers=h).json()["id"]
    assert client2.post(f"/api/audits/{aid}/findings", json={"title": "x"}, headers=ch).status_code == 403
    assert client2.get("/api/roles", headers=ch).status_code == 403

    clerk_perms = next(r for r in cat["roles"] if r["code"] == "audit_clerk")["permissions"]
    ok = client.put("/api/roles/audit_clerk/permissions", json={"permissions": [*clerk_perms, "audit.findings"]},
                    headers=h)
    assert ok.status_code == 200 and next(r for r in ok.json()["roles"] if r["code"] == "audit_clerk")["customised"]
    assert client2.post(f"/api/audits/{aid}/findings", json={"title": "Now allowed"}, headers=ch).status_code == 201
    assert client.put("/api/roles/platform_admin/permissions", json={"permissions": ["system.users"]},
                      headers=h).status_code == 422
    assert client.put("/api/roles/committee/permissions", json={"permissions": ["governance.view", "audit.close"]},
                      headers=h).status_code == 422
    client.post("/api/roles/audit_clerk/reset", headers=h)
    assert client2.post(f"/api/audits/{aid}/findings", json={"title": "x"}, headers=ch).status_code == 403

    # Assigning a job role sets the tier and review level.
    target = _u(db, "rptarget")
    res = client.patch(f"/api/users/{target.id}/job-role", json={"job_role": "pia"}, headers=h).json()
    assert res["role"] == "Auditor" and res["review_level"] == "Manager"
    res = client.patch(f"/api/users/{target.id}/job-role", json={"job_role": "committee"}, headers=h).json()
    assert res["role"] == "Committee"
    users = client.get("/api/users").json()
    users = users["items"] if isinstance(users, dict) else users
    row = next(u for u in users if u["id"] == target.id)
    assert row["job_role"] == "committee" and row["job_role_name"].startswith("Audit Committee")


def test_audit_admin_configures_types_and_programmes(client, client2, db):
    aa = _u(db, "rpaa", job="audit_admin")
    aud = _u(db, "rpaud", job="auditor")
    h = csrf_headers(login(client, aa.username))
    cfg = client.get("/api/config").json()
    groups = {r["group"] for r in cfg}
    assert "Audit methodology" in groups and "Plan configuration" in groups and "Security" not in groups
    assert client.put("/api/config", json={"values": {"risk_high_threshold": 5, "risk_medium_threshold": 9}},
                        headers=h).status_code == 422

    steps = [{"objective": "Cash is safeguarded", "risk": "Theft of cash", "likelihood": 4, "impact": 4,
              "control": "Daily cash count", "control_type": "Detective", "procedure": "Re-perform 10 counts"},
             {"objective": "Cash is safeguarded", "risk": "Theft of cash", "control": "Safe access log",
              "procedure": "Inspect the log for a month"}]
    p = client.post("/api/audit-programs", json={"name": "Cash management", "steps": steps}, headers=h)
    assert p.status_code == 201, p.text
    prog = p.json()
    assert prog["prog_ref"].startswith("PRG-") and prog["step_count"] == 2
    ah = csrf_headers(login(client2, aud.username))
    assert client2.post("/api/audit-programs", json={"name": "Nope", "steps": []}, headers=ah).status_code == 403
    aid = client2.post("/api/audits", json={"title": "Cash audit", "scope": "x"}, headers=ah).json()["id"]
    applied = client2.post(f"/api/audits/{aid}/apply-program/{prog['id']}", headers=ah).json()
    assert applied == {"program": prog["prog_ref"], "objectives": 1, "risks": 1, "controls": 2, "tests": 2}


def test_evidence_request_cycle(client, client2, db):
    aud = _u(db, "evaud", job="auditor")
    auditee = _u(db, "evee", Role.Auditee)
    other = _u(db, "evother", Role.Auditee)
    h = csrf_headers(login(client, aud.username))
    aid = client.post("/api/audits", json={"title": "Payroll", "scope": "x"}, headers=h).json()["id"]
    assert client.post(f"/api/audits/{aid}/evidence-requests", json={"title": "Payroll register",
                       "assignee_id": other.id}, headers=h).status_code == 422
    client.post(f"/api/audits/{aid}/auditees", json={"user_id": auditee.id}, headers=h)
    er = client.post(f"/api/audits/{aid}/evidence-requests",
                     json={"title": "Payroll register March", "assignee_id": auditee.id}, headers=h).json()
    assert er["request_ref"].startswith("ER-") and er["status"] == "Requested"

    eh = csrf_headers(login(client2, auditee.username))
    mine = client2.get("/api/evidence-requests").json()
    assert [r["id"] for r in mine] == [er["id"]] and mine[0]["can_respond"]
    assert client2.post(f"/api/evidence-requests/{er['id']}/submit", json={"response": ""},
                        headers=eh).status_code == 422
    up = client2.post(f"/api/evidence-requests/{er['id']}/files",
                      files={"file": ("register.txt", io.BytesIO(b"employee,net\nA,100"), "text/plain")}, headers=eh)
    assert up.status_code == 200, up.text
    sub = client2.post(f"/api/evidence-requests/{er['id']}/submit", json={"response": "Attached"}, headers=eh).json()
    assert sub["status"] == "Submitted"
    assert client2.post(f"/api/evidence-requests/{er['id']}/review", json={"decision": "Accepted"},
                        headers=eh).status_code == 403
    assert client.post(f"/api/evidence-requests/{er['id']}/review", json={"decision": "Returned"},
                       headers=h).status_code == 422
    done = client.post(f"/api/evidence-requests/{er['id']}/review",
                       json={"decision": "Accepted", "file_as_working_paper": True}, headers=h).json()
    assert done["status"] == "Accepted"
    papers = client.get(f"/api/audits/{aid}/working-papers").json()
    assert any(p["title"].startswith(er["request_ref"]) for p in papers)
    fid = done["files"][0]["id"]
    assert client2.get(f"/api/evidence-files/{fid}/download").content == b"employee,net\nA,100"


def test_committee_governance_portal_and_port_portfolio(client, client2, db):
    committee = _u(db, "gvcom", job="committee")
    aud = _u(db, "gvaud", job="auditor")
    login(client, committee.username)
    ov = client.get("/api/governance/overview")
    assert ov.status_code == 200 and "plan_completion_pct" in ov.json()["kpis"]
    assert client.get("/api/portfolio/ports").status_code == 200
    # Read-only: no working data.
    assert client.get("/api/audits").status_code == 403 or client.get("/api/audits").json() in ([], {"items": []}) \
        or not client.get("/api/audits").json().get("items")
    h = csrf_headers(login(client, committee.username))
    assert client.post("/api/audits", json={"title": "x", "scope": "x"}, headers=h).status_code == 403
    login(client2, aud.username)
    assert client2.get("/api/governance/overview").status_code == 403
