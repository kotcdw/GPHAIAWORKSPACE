"""PROJECTBLUEPRINT project execution: Import Objective (many, from an audit or a framework programme), Clone
Objective (one at a time), the per-audit objective cap and the narratives rule."""

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


def _audit(client, h, workflow="Internal Control"):
    r = client.post("/api/audits", json={"title": f"OBJ {uuid.uuid4().hex[:5]}", "scope": "x", "workflow": workflow},
                    headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _objectives(client, audit_id):
    return client.get(f"/api/audits/{audit_id}/rcm").json()["objectives"]


def test_import_clone_cap_and_narrative_rule(client, client2, db):
    aud = _u(db, "obaud", "auditor")
    adm = _u(db, "obadm", "admin", Role.Admin)
    h = csrf_headers(login(client, aud.username))
    ah = csrf_headers(login(client2, adm.username))

    src = _audit(client, h)
    objs = []
    for title in ("Revenue is complete", "Receipts are banked", "Refunds are approved"):
        o = client.post(f"/api/audits/{src['id']}/objectives", json={"title": title}, headers=h).json()
        client.post(f"/api/objectives/{o['id']}/risks", json={"title": f"{title} risk", "likelihood": 3,
                                                              "impact": 3}, headers=h)
        c = client.post(f"/api/objectives/{o['id']}/controls", json={"title": f"{title} control"}, headers=h).json()
        t = client.post(f"/api/controls/{c['id']}/tests", json={"test_type": "Operating Effectiveness"},
                        headers=h).json()
        client.patch(f"/api/control-tests/{t['id']}", json={"conclusion": "Effective", "results": "OK",
                                                            "status": "Completed"}, headers=h)
        objs.append(o)
    nar = client.post(f"/api/objectives/{objs[0]['id']}/narratives", json={"title": "Billing walk"}, headers=h)
    assert nar.status_code == 201, nar.text

    # Import many from another audit, with results.
    target = _audit(client, h)
    sources = client.get(f"/api/audits/{target['id']}/objective-sources").json()
    assert src["id"] in {a["id"] for a in sources["audits"]}
    listed = client.get(f"/api/audits/{target['id']}/objective-sources/{src['id']}").json()
    assert len(listed) == 3
    none = client.post(f"/api/audits/{target['id']}/objectives/import",
                       json={"source": "audit", "source_id": src["id"], "objective_ids": []}, headers=h)
    assert none.status_code == 422
    imp = client.post(f"/api/audits/{target['id']}/objectives/import", json={
        "source": "audit", "source_id": src["id"], "objective_ids": [objs[0]["id"], objs[1]["id"]],
        "include_results": True}, headers=h)
    assert imp.status_code == 201, imp.text
    body = imp.json()
    assert body["imported"] == 2 and body["counts"]["controls"] == 2 and body["counts"]["narratives"] == 1
    assert body["counts"]["tests"] == 2
    assert {o["title"] for o in _objectives(client, target["id"])} == {"Revenue is complete", "Receipts are banked"}

    # Into a Workplan audit narratives do not travel (narratives belong to the Internal Control workflow).
    workplan = _audit(client, h, "Workplan")
    wp = client.post(f"/api/audits/{workplan['id']}/objectives/import", json={
        "source": "audit", "source_id": src["id"], "objective_ids": [objs[0]["id"]]}, headers=h).json()
    assert wp["counts"]["narratives"] == 0
    wo = _objectives(client, workplan["id"])[0]
    refused = client.post(f"/api/objectives/{wo['id']}/narratives", json={"title": "No"}, headers=h)
    assert refused.status_code == 409

    # Clone one objective to one target audit.
    clone_target = _audit(client, h)
    cl = client.post(f"/api/objectives/{objs[2]['id']}/clone", json={"target_audit_id": clone_target["id"]},
                     headers=h)
    assert cl.status_code == 201, cl.text
    assert cl.json()["counts"]["tests"] == 0  # results stay behind unless asked for
    assert [o["title"] for o in _objectives(client, clone_target["id"])] == ["Refunds are approved"]

    # Import from a framework (audit programme) in the Project Library.
    prog = client2.post("/api/audit-programs", json={"name": f"Cash framework {uuid.uuid4().hex[:4]}", "steps": [
        {"objective": "Cash is safeguarded", "risk": "Theft", "control": "Daily count", "procedure": "Recount"},
        {"objective": "Petty cash is reconciled", "risk": "Misuse", "control": "Monthly recon",
         "procedure": "Reperform"}]}, headers=ah)
    assert prog.status_code == 201, prog.text
    fw_target = _audit(client, h)
    fw = client.post(f"/api/audits/{fw_target['id']}/objectives/import", json={
        "source": "programme", "source_id": prog.json()["id"], "objective_titles": ["Cash is safeguarded"]},
        headers=h)
    assert fw.status_code == 201, fw.text
    assert [o["title"] for o in _objectives(client, fw_target["id"])] == ["Cash is safeguarded"]
    with_results = client.post(f"/api/audits/{fw_target['id']}/objectives/import", json={
        "source": "programme", "source_id": prog.json()["id"], "objective_titles": ["Petty cash is reconciled"],
        "include_results": True}, headers=h)
    assert with_results.status_code == 422

    # The per-audit cap (Configuration > Audit methodology) applies to add, import and clone.
    assert client2.put("/api/config", json={"values": {"audit_max_objectives": 2}}, headers=ah).status_code == 200
    try:
        from app.core import appconfig

        if hasattr(appconfig, "invalidate"):
            appconfig.invalidate()
        full = client.post(f"/api/audits/{target['id']}/objectives", json={"title": "Third"}, headers=h)
        assert full.status_code == 409
        over = client.post(f"/api/objectives/{objs[2]['id']}/clone", json={"target_audit_id": target["id"]},
                           headers=h)
        assert over.status_code == 409
    finally:
        client2.put("/api/config", json={"values": {"audit_max_objectives": 500}}, headers=ah)
