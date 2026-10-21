"""PROJECTBLUEPRINT Strategy: Treatment links from a strategic risk to audit objectives and the Assurance
roll-up built only from those explicit links."""

from __future__ import annotations

import uuid

from app.core import permissions as perms
from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, job, role=Role.Auditor):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    r = perms.JOB_ROLES_BY_CODE[job]
    user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def _control_with_test(client, h, audit_id, title, conclusion):
    o = client.post(f"/api/audits/{audit_id}/objectives", json={"title": title}, headers=h).json()
    c = client.post(f"/api/objectives/{o['id']}/controls", json={"title": f"{title} control"}, headers=h).json()
    if conclusion:
        t = client.post(f"/api/controls/{c['id']}/tests", json={"test_type": "Operating Effectiveness"},
                        headers=h).json()
        r = client.patch(f"/api/control-tests/{t['id']}", json={"conclusion": conclusion, "results": "Tested 25",
                                                                 "status": "Completed"}, headers=h)
        assert r.status_code == 200, r.text
    return o, c


def test_treatment_links_drive_assurance(client, client2, db):
    mgr = _u(db, "stmgr", "audit_manager")
    aud = _u(db, "staud", "auditor")
    h = csrf_headers(login(client, mgr.username))
    tag = uuid.uuid4().hex[:5]
    risk = client.post("/api/grc/risks", json={
        "title": f"Revenue leakage {tag}", "category": "Financial", "inherent_likelihood": 5, "inherent_impact": 5,
        "residual_likelihood": 4, "residual_impact": 4}, headers=h)
    assert risk.status_code == 201, risk.text
    risk = risk.json()

    # Nothing linked: no assurance, never a reassuring figure.
    empty = client.get(f"/api/grc/risks/{risk['id']}/assurance").json()
    assert empty["objectives"] == [] and empty["overall_assurance"] is None

    audit = client.post("/api/audits", json={"title": f"Revenue {tag}", "scope": "x",
                                             "workflow": "Internal Control"}, headers=h).json()
    o1, _ = _control_with_test(client, h, audit["id"], "Tolls are billed", "Effective")
    o2, _ = _control_with_test(client, h, audit["id"], "Dues are collected", "Ineffective")
    o3, _ = _control_with_test(client, h, audit["id"], "Credit notes are approved", None)
    unlinked, _ = _control_with_test(client, h, audit["id"], "Unrelated objective", "Effective")

    found = client.get(f"/api/grc/treatment-sources?q={tag}").json()
    project = next(x for x in found if x["type"] == "project" and x["id"] == audit["id"])
    assert {o["id"] for o in project["objectives"]} >= {o1["id"], o2["id"], o3["id"]}

    linked = client.post(f"/api/grc/risks/{risk['id']}/treatments",
                         json={"objective_ids": [o1["id"], o2["id"], o3["id"]], "note": "Revenue cycle"}, headers=h)
    assert linked.status_code == 201, linked.text
    a = linked.json()
    assert a["linked"] == 3
    assert a["controls"]["passing"] == 1 and a["controls"]["failing"] == 1 and a["controls"]["not_tested"] == 1
    assert a["overall_assurance"] == round(100 / 3, 1)
    assert unlinked["id"] not in {x["id"] for x in a["objectives"]}  # only explicit links count

    # Linking again adds nothing.
    again = client.post(f"/api/grc/risks/{risk['id']}/treatments", json={"objective_ids": [o1["id"]]}, headers=h)
    assert again.json()["linked"] == 0

    # Unlink one; the roll-up follows.
    tid = next(x["treatment_id"] for x in a["treatments"] if x["ref"] == o2["ref"])
    after = client.delete(f"/api/grc/risks/{risk['id']}/treatments/{tid}", headers=h).json()
    assert after["controls"]["failing"] == 0 and after["overall_assurance"] == 50.0

    # An auditor without the risk-editing permission cannot link treatments.
    ah = csrf_headers(login(client2, aud.username))
    refused = client2.post(f"/api/grc/risks/{risk['id']}/treatments", json={"objective_ids": [o2["id"]]}, headers=ah)
    assert refused.status_code == 403

    # Every link and unlink is in the audit log.
    from sqlalchemy import select

    from app.platform.history.models import AuditLog

    db.rollback()  # end the test session's snapshot so the request's writes are visible
    like = AuditLog.action_performed.like(f"ERM_TREATMENT_%{risk['ref']}%")
    actions = list(db.execute(select(AuditLog.action_performed).where(like)).scalars())
    assert any("LINK" in x for x in actions) and any("UNLINK" in x for x in actions)


def test_framework_treatment_rolls_up_across_projects(client, client2, db):
    mgr = _u(db, "fwmgr", "audit_manager")
    adm = _u(db, "fwadm2", "platform_admin", Role.Admin)
    h = csrf_headers(login(client, mgr.username))
    ah = csrf_headers(login(client2, adm.username))
    tag = uuid.uuid4().hex[:5]
    prog = client2.post("/api/audit-programs", json={"name": f"Vendor framework {tag}", "steps": [
        {"objective": f"Vendor oversight {tag}", "risk": "Supplier failure", "control": "Annual vendor review",
         "procedure": "Inspect reviews"}]}, headers=ah).json()
    risk = client.post("/api/grc/risks", json={
        "title": f"Third-party disruption {tag}", "category": "Operational", "inherent_likelihood": 4,
        "inherent_impact": 5, "residual_likelihood": 4, "residual_impact": 4}, headers=h).json()
    audits = []
    for n in range(2):
        a = client.post("/api/audits", json={"title": f"Vendor audit {n} {tag}", "scope": "x",
                                             "workflow": "Internal Control"}, headers=h).json()
        imp = client.post(f"/api/audits/{a['id']}/objectives/import", json={
            "source": "programme", "source_id": prog["id"], "objective_titles": [f"Vendor oversight {tag}"]},
            headers=h)
        assert imp.status_code == 201, imp.text
        audits.append(a)
    found = client.get(f"/api/grc/treatment-sources?q={tag}").json()
    fw = next(x for x in found if x["type"] == "framework" and x["id"] == prog["id"])
    assert fw["objectives"] == [{"title": f"Vendor oversight {tag}"}]
    linked = client.post(f"/api/grc/risks/{risk['id']}/treatments", json={
        "framework_objectives": [{"program_id": prog["id"], "title": f"Vendor oversight {tag}"}]}, headers=h)
    assert linked.status_code == 201, linked.text
    a = linked.json()
    assert a["controls"]["total"] == 2 and len(a["objectives"]) == 2  # one control in each project
    t = a["treatments"][0]
    assert t["type"] == "Framework objective" and t["objectives"] == 2
    # Not both: a project objective from that framework objective cannot also be linked.
    child = a["objectives"][0]["id"]
    clash = client.post(f"/api/grc/risks/{risk['id']}/treatments", json={"objective_ids": [child]}, headers=h)
    assert clash.status_code == 409
    full = client.get(f"/api/grc/risks/{risk['id']}/assurance").json()
    assert full["residual_level"] in ("High", "Medium") and full["inherent_score"] == 20
