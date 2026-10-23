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


def test_standard_roles_and_defaults(client, db):
    root = _u(db, "rproot", Role.Admin)
    mgr = _u(db, "rpmgr")
    mgr.review_level = ReviewLevel.Manager
    db.commit()
    assert [r.code for r in perms.JOB_ROLES] == ["super_admin", "admin", "manager", "auditor", "read_only",
                                                 "audit_client"]
    assert perms.job_role_of(root) == "super_admin" and perms.job_role_of(mgr) == "manager"
    # Old job roles map onto the five.
    legacy = _u(db, "rplegacy")
    legacy.job_role = "senior_auditor"
    db.commit()
    assert perms.job_role_of(legacy) == "auditor"
    login(client, mgr.username)
    me = client.get("/api/auth/me").json()["permissions"]
    assert "audit.memo_approve" in me and "report.review" in me
    assert "plan.approve" not in me and "report.approve" not in me and "system.roles" not in me
    gm = _u(db, "rpgm", job="gm_audit")
    assert perms.job_role_of(gm) == "manager" and perms.is_cae(gm)
    assert perms.has_perm(gm, "plan.approve", "report.approve")
    assert perms.permissions_of(root) == set(perms.PERMISSIONS)


def test_only_super_admin_changes_the_matrix(client, client2, db):
    root = _u(db, "rproot2", Role.Admin)
    admin = _u(db, "rpadm2", job="admin")
    aud = _u(db, "rpaud2", job="auditor")
    h = csrf_headers(login(client, root.username))
    cat = client.get("/api/roles").json()
    assert [r["code"] for r in cat["roles"]] == ["super_admin", "admin", "manager", "auditor", "read_only",
                                                 "audit_client"]
    assert cat["can_edit"] and next(r for r in cat["roles"] if r["code"] == "super_admin")["locked"]

    ah = csrf_headers(login(client2, admin.username))
    acat = client2.get("/api/roles").json()
    assert not acat["can_edit"] and acat["can_assign"] and not acat["can_appoint_admins"]
    assert client2.put("/api/roles/auditor/permissions", json={"permissions": []}, headers=ah).status_code == 403

    aid = client.post("/api/audits", json={"title": "Matrix test", "scope": "x"}, headers=h).json()["id"]
    auditor_perms = next(r for r in cat["roles"] if r["code"] == "auditor")["permissions"]
    reduced = [p for p in auditor_perms if p != "audit.findings"]
    ok = client.put("/api/roles/auditor/permissions", json={"permissions": reduced}, headers=h)
    assert ok.status_code == 200 and next(r for r in ok.json()["roles"] if r["code"] == "auditor")["customised"]
    xh = csrf_headers(login(client2, aud.username))
    assert client2.post(f"/api/audits/{aid}/findings", json={"title": "x"}, headers=xh).status_code == 403
    assert client.put("/api/roles/super_admin/permissions", json={"permissions": []}, headers=h).status_code == 422
    assert client.put("/api/roles/admin/permissions", json={"permissions": ["system.roles"]},
                      headers=h).status_code == 422
    client.post("/api/roles/auditor/reset", headers=h)
    perms.invalidate()
    assert perms.has_perm(aud, "audit.findings")


def test_role_assignment_guards(client, client2, db):
    root = _u(db, "rproot3", Role.Admin)
    admin = _u(db, "rpadm3", job="admin")
    target = _u(db, "rptarget")
    ah = csrf_headers(login(client2, admin.username))
    res = client2.patch(f"/api/users/{target.id}/job-role", json={"job_role": "manager"}, headers=ah).json()
    assert res["role"] == "Auditor" and res["review_level"] == "Manager"
    res = client2.patch(f"/api/users/{target.id}/job-role", json={"job_role": "audit_client"}, headers=ah).json()
    assert res["role"] == "Auditee" and res["review_level"] is None
    # Administrators are appointed only by a Super Administrator.
    assert client2.patch(f"/api/users/{target.id}/job-role", json={"job_role": "admin"},
                         headers=ah).status_code == 403
    assert client2.patch(f"/api/users/{root.id}/job-role", json={"job_role": "auditor"},
                         headers=ah).status_code == 403
    h = csrf_headers(login(client, root.username))
    assert client.patch(f"/api/users/{target.id}/job-role", json={"job_role": "auditor", "approval_level": "CAE"},
                        headers=h).status_code == 422
    cae = client.patch(f"/api/users/{target.id}/job-role", json={"job_role": "manager", "approval_level": "CAE"},
                       headers=h).json()
    assert cae["review_level"] == "CAE"
    assert client.patch(f"/api/users/{target.id}/job-role", json={"job_role": "admin"},
                        headers=h).json()["role"] == "Admin"
    users = client.get("/api/users").json()
    users = users["items"] if isinstance(users, dict) else users
    row = next(u for u in users if u["id"] == target.id)
    assert row["job_role"] == "admin" and row["job_role_name"] == "Administrator"
    # The last Super Administrator cannot step down.
    from app.platform.roles.service import active_super_admins

    db.rollback()
    if len(active_super_admins(db)) == 1:
        assert client.patch(f"/api/users/{root.id}/job-role", json={"job_role": "admin"},
                            headers=h).status_code == 422


def test_admin_configures_types_and_programmes(client, client2, db):
    aa = _u(db, "rpaa", job="admin")
    aud = _u(db, "rpaud", job="auditor")
    h = csrf_headers(login(client, aa.username))
    cfg = client.get("/api/config").json()
    groups = {r["group"] for r in cfg}
    assert "Audit methodology" in groups and "Plan configuration" in groups
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


def test_super_admin_switches_apps_off_and_customizes(client, client2, db):
    root = _u(db, "approot", Role.Admin)
    admin = _u(db, "appadm", job="admin")
    h = csrf_headers(login(client, root.username))
    cat = client.get("/api/apps").json()
    assert any(a["key"] == "nonconformances" and a["enabled"] for a in cat["apps"])
    ah = csrf_headers(login(client2, admin.username))
    assert client2.put("/api/apps", json={"apps": {}}, headers=ah).status_code == 403
    saved = client.put("/api/apps", json={"apps": {"nonconformances": {"enabled": False, "label": ""},
                                                   "audits": {"enabled": False, "label": "Engagements"}},
                                          "branding": {"name": "GPHA AUDIT", "sub": "HUB"}}, headers=h)
    assert saved.status_code == 200, saved.text
    apps = {a["key"]: a for a in saved.json()["apps"]}
    assert not apps["nonconformances"]["enabled"]
    assert apps["audits"]["enabled"] and apps["audits"]["label"] == "Engagements"  # core apps stay on
    assert saved.json()["branding"]["name"] == "GPHA AUDIT"
    off = client2.get("/api/nonconformances")
    assert off.status_code == 404 and "switched off" in off.json()["detail"]
    client.put("/api/apps", json={"apps": {"nonconformances": {"enabled": True, "label": ""}},
                                  "branding": {}}, headers=h)
    assert client2.get("/api/nonconformances").status_code == 200


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
