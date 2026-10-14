"""Risk & compliance apps: Risk Manager & Strategy, Compliance Maps, Policy Manager and Asset Inventory."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.core import permissions as perms
from app.core.enums import Role
from app.domains.grc.common import add_months
from app.platform.notifications.models import Notification
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, job=None, role=Role.Auditee):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
        db.commit()
    return user


def _framework_control(client, h):
    code = f"GRC{uuid.uuid4().hex[:5]}".upper()
    fw = client.post("/api/library/frameworks", json={"code": code, "name": "Test framework"}, headers=h).json()
    c = client.post("/api/library/controls", json={"framework_id": fw["id"], "ref": "C-1", "title": "Monthly review",
                                                   "control_type": "Detective"}, headers=h)
    assert c.status_code == 201, c.text
    return fw, c.json()


def test_risk_register_assessments_heat_map_and_kris(client, client2, db):
    officer = _u(db, "rko", "admin")
    owner = _u(db, "rkown", "auditee")
    auditor = _u(db, "rkaud", "auditor")
    h = csrf_headers(login(client, officer.username))

    obj = client.post("/api/grc/objectives", json={"title": "Grow container throughput", "period": "2026-2028",
                                                   "owner_id": owner.id}, headers=h)
    assert obj.status_code == 201, obj.text
    bad = client.post("/api/grc/risks", json={"title": "Upside down", "inherent_likelihood": 2, "inherent_impact": 2,
                                              "residual_likelihood": 4, "residual_impact": 4}, headers=h)
    assert bad.status_code == 422
    bad_cat = client.post("/api/grc/risks", json={"title": "Bad category", "category": "Nonsense",
                                                  "inherent_likelihood": 2, "inherent_impact": 2,
                                                  "residual_likelihood": 1, "residual_impact": 1}, headers=h)
    assert bad_cat.status_code == 422 and "configured list" in bad_cat.json()["detail"]
    r = client.post("/api/grc/risks", json={
        "title": "Quay crane failure halts operations", "category": "operational", "objective_id": obj.json()["id"],
        "owner_id": owner.id, "inherent_likelihood": 4, "inherent_impact": 5, "residual_likelihood": 3,
        "residual_impact": 4, "target_likelihood": 2, "target_impact": 3, "appetite": "Cautious",
        "treatment": "Mitigate"}, headers=h)
    assert r.status_code == 201, r.text
    risk = r.json()
    assert risk["ref"].startswith("ERM-") and risk["category"] == "Operational"
    assert risk["inherent_level"] == "High" and risk["residual_score"] == 12 and risk["above_target"]
    assert len(risk["assessments"]) == 1 and risk["next_review_date"] > str(date.today())

    s = client.get("/api/grc/risks/summary").json()
    assert risk["id"] in s["residual_grid"][3][2] and risk["id"] in s["inherent_grid"][4][3]

    # The risk owner (a business user) can re-assess and record KRI readings, but not edit the risk.
    oh = csrf_headers(login(client2, owner.username))
    assert client2.put(f"/api/grc/risks/{risk['id']}", json={"title": "x" * 5, "inherent_likelihood": 1,
                                                             "inherent_impact": 1, "residual_likelihood": 1,
                                                             "residual_impact": 1}, headers=oh).status_code == 403
    a = client2.post(f"/api/grc/risks/{risk['id']}/assess", json={
        "inherent_likelihood": 4, "inherent_impact": 5, "residual_likelihood": 2, "residual_impact": 3,
        "control_effectiveness": "Effective", "comment": "New maintenance contract in place"}, headers=oh)
    assert a.status_code == 200 and a.json()["residual_score"] == 6 and not a.json()["above_target"]
    assert len(a.json()["assessments"]) == 2

    k = client.post(f"/api/grc/risks/{risk['id']}/kris", json={"name": "Crane downtime hours", "unit": "h",
                                                               "amber_at": 10, "red_at": 20}, headers=h)
    assert k.status_code == 201, k.text
    assert client.post(f"/api/grc/risks/{risk['id']}/kris", json={"name": "Wrong way", "amber_at": 10, "red_at": 5},
                       headers=h).status_code == 422
    kid = k.json()["id"]
    read = client2.post(f"/api/grc/kris/{kid}/readings", json={"period_date": str(date.today()), "value": 25},
                        headers=oh)
    assert read.status_code == 201 and read.json()["rag"] == "Red"
    db.rollback()
    assert db.query(Notification).filter(Notification.user_id == owner.id,
                                         Notification.title.like("KRI breached%")).count() == 1
    assert any(x["id"] == kid and x["rag"] == "Red" for x in client.get("/api/grc/kris").json())

    # Link a standard control to the risk.
    _, ctl = _framework_control(client2, csrf_headers(login(client2, _u(db, "rkadm", "audit_admin").username)))
    up = client.put(f"/api/grc/risks/{risk['id']}", json={**{f: risk[f] for f in (
        "title", "category", "objective_id", "owner_id", "inherent_likelihood", "inherent_impact",
        "residual_likelihood", "residual_impact", "appetite", "treatment")}, "control_ids": [ctl["id"]]}, headers=h)
    assert up.status_code == 200 and [x["id"] for x in up.json()["links"] if x["type"] == "control"] == [ctl["id"]]

    # Audit staff can view the register but not change it; plain auditees cannot see it.
    ah = csrf_headers(login(client2, auditor.username))
    assert client2.get("/api/grc/risks").status_code == 200
    assert client2.post("/api/grc/objectives", json={"title": "Nope nope"}, headers=ah).status_code == 403
    login(client2, _u(db, "rkplain", "auditee").username)
    assert client2.get("/api/grc/risks").status_code == 403


def test_compliance_map_coverage_version_change_and_assessment(client, client2, db):
    officer = _u(db, "cmo", "admin")
    owner = _u(db, "cmown", "auditee")
    admin = _u(db, "cmadm", "audit_admin")
    _, ctl = _framework_control(client2, csrf_headers(login(client2, admin.username)))
    h = csrf_headers(login(client, officer.username))
    code = f"ACT{uuid.uuid4().hex[:4]}".upper()
    g = client.post("/api/grc/regulations", json={"code": code, "title": "Internal Audit Agency Act, 2003",
                                                  "reg_type": "Law / Act", "version": "2003", "owner_id": owner.id},
                    headers=h)
    assert g.status_code == 201, g.text
    gid = g.json()["id"]
    r1 = client.post(f"/api/grc/regulations/{gid}/requirements", json={
        "ref": "s.16(1)", "title": "Internal audit unit in every covered entity", "owner_id": owner.id,
        "control_ids": [ctl["id"]]}, headers=h)
    assert r1.status_code == 201 and r1.json()["covered"]
    r2 = client.post(f"/api/grc/regulations/{gid}/requirements", json={"ref": "s.16(5)", "title": "Report quarterly"},
                     headers=h)
    assert r2.status_code == 201 and not r2.json()["covered"]
    assert client.post(f"/api/grc/regulations/{gid}/requirements", json={"ref": "s.16(5)", "title": "Dup dup"},
                       headers=h).status_code == 409
    csv_body = ("ref,title,text,owner_email,applicable,control_refs\n"
                f"s.16(6),Annual report,,{owner.email},yes,\n"
                "s.99,Not for GPHA,,,no,\n"
                "s.100,Bad control,,,yes,NOPE 1\n")
    imp = client.post(f"/api/grc/regulations/{gid}/import", files={"file": ("r.csv", csv_body, "text/csv")},
                      headers=h)
    assert imp.status_code == 200 and imp.json()["created"] == 2 and len(imp.json()["errors"]) == 1

    reg = client.get(f"/api/grc/regulations/{gid}").json()
    st = reg["stats"]
    assert st["requirements"] == 4 and st["applicable"] == 3 and st["covered"] == 1 and st["gaps"] == 2
    gaps = client.get("/api/grc/compliance/map").json()
    assert any(x["ref"] == "s.16(5)" for x in gaps["gaps"])
    assert any(c["id"] == ctl["id"] and code in c["obligations"] for c in gaps["common_controls"])

    # The requirement owner assesses it; a gap needs an explanation.
    oh = csrf_headers(login(client2, owner.username))
    rid = r1.json()["id"]
    assert client2.post(f"/api/grc/requirements/{rid}/assess", json={"status": "Non-compliant"},
                        headers=oh).status_code == 422
    ok = client2.post(f"/api/grc/requirements/{rid}/assess", json={"status": "Compliant", "comment": "Unit staffed"},
                      headers=oh)
    assert ok.status_code == 200 and ok.json()["status"] == "Compliant"

    # A new version flags every requirement for review and tells the owners.
    upd = client.put(f"/api/grc/regulations/{gid}", json={"code": code, "title": "Internal Audit Agency Act",
                                                          "reg_type": "Law / Act", "version": "2026 amendment",
                                                          "owner_id": owner.id}, headers=h)
    assert upd.status_code == 200 and upd.json()["flagged"] == 4
    assert upd.json()["stats"]["review_required"] == 4
    db.rollback()
    assert db.query(Notification).filter(Notification.user_id == owner.id,
                                         Notification.title.like(f"{code} changed%")).count() == 1


def test_policy_lifecycle_segregation_and_attestations(client, client2, db):
    author = _u(db, "pola", "admin")
    approver = _u(db, "polap", "auditee")
    staff1 = _u(db, "pols1", "auditee")
    staff2 = _u(db, "pols2", "auditee")
    h = csrf_headers(login(client, author.username))
    p = client.post("/api/grc/policies", json={"title": "Procurement Policy", "category": "Procurement",
                                               "owner_id": author.id, "content": ""}, headers=h)
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    assert p.json()["ref"].startswith("POL-") and p.json()["working_version"] == 1
    assert client.post(f"/api/grc/policies/{pid}/submit", headers=h).status_code == 422  # empty text
    client.put(f"/api/grc/policies/{pid}/draft", json={"content": "1. Purpose\nAll purchases follow Act 663.",
                                                       "change_summary": "First issue"}, headers=h)
    assert "approver" in client.post(f"/api/grc/policies/{pid}/submit", headers=h).json()["detail"]
    client.put(f"/api/grc/policies/{pid}", json={"title": "Procurement Policy", "category": "Procurement",
                                                 "owner_id": author.id, "approver_id": approver.id}, headers=h)
    sub = client.post(f"/api/grc/policies/{pid}/submit", headers=h)
    assert sub.status_code == 200 and sub.json()["working_status"] == "In review"
    # The author cannot approve their own draft even though the role holds the approval permission.
    assert client.post(f"/api/grc/policies/{pid}/review", json={"decision": "approve"}, headers=h).status_code == 403
    ah = csrf_headers(login(client2, approver.username))
    assert client2.post(f"/api/grc/policies/{pid}/review", json={"decision": "return"}, headers=ah).status_code == 422
    ret = client2.post(f"/api/grc/policies/{pid}/review", json={"decision": "return", "comment": "Cite Act 914 too"},
                       headers=ah)
    assert ret.status_code == 200 and ret.json()["working_status"] == "Returned"
    client.put(f"/api/grc/policies/{pid}/draft", json={"content": "1. Purpose\nActs 663 and 914 apply.",
                                                       "change_summary": "Added Act 914"}, headers=h)
    client.post(f"/api/grc/policies/{pid}/submit", headers=h)
    assert client2.post(f"/api/grc/policies/{pid}/review", json={"decision": "approve"}, headers=ah).status_code == 200
    pub = client.post(f"/api/grc/policies/{pid}/publish", json={}, headers=h)
    assert pub.status_code == 200 and pub.json()["status"] == "Published" and pub.json()["published_version"] == 1
    assert pub.json()["next_review_date"] == str(add_months(date.today(), 24))

    # Attestation campaign to two people.
    bad = client.post(f"/api/grc/policies/{pid}/campaigns", json={"due_date": str(date.today() - timedelta(days=1)),
                                                                  "user_ids": [staff1.id]}, headers=h)
    assert bad.status_code == 422
    camp = client.post(f"/api/grc/policies/{pid}/campaigns", json={
        "due_date": str(date.today() + timedelta(days=14)), "user_ids": [staff1.id, staff2.id]}, headers=h)
    assert camp.status_code == 201 and camp.json()["total"] == 2
    s1 = csrf_headers(login(client2, staff1.username))
    mine = client2.get("/api/grc/attestations/mine").json()
    assert len(mine) == 1 and "914" in mine[0]["content"]
    # Staff attesting can open the published policy but nothing else in the GRC apps.
    assert client2.get(f"/api/grc/policies/{pid}").status_code == 200
    assert client2.get("/api/grc/policies").status_code == 403
    assert client2.post(f"/api/grc/attestations/{mine[0]['id']}", json={"status": "Attested"},
                        headers=s1).status_code == 200
    assert client2.post(f"/api/grc/attestations/{mine[0]['id']}", json={"status": "Attested"},
                        headers=s1).status_code == 409
    s2 = csrf_headers(login(client2, staff2.username))
    a2 = client2.get("/api/grc/attestations/mine").json()[0]
    assert client2.post(f"/api/grc/attestations/{a2['id']}", json={"status": "Declined"}, headers=s2).status_code == 422
    assert client2.post(f"/api/grc/attestations/{a2['id']}", json={"status": "Declined", "comment": "Not my area"},
                        headers=s2).status_code == 200
    res = client.get(f"/api/grc/campaigns/{camp.json()['id']}").json()
    assert res["attested"] == 1 and res["declined"] == 1 and res["completion_pct"] == 50

    # Next version starts from a new draft; the published version stays in force meanwhile.
    v2 = client.put(f"/api/grc/policies/{pid}/draft", json={"content": "Revised", "change_summary": "Annual review"},
                    headers=h)
    assert v2.json()["working_version"] == 2 and v2.json()["published_version"] == 1


def test_asset_inventory_and_third_party_due_diligence(client, client2, db):
    officer = _u(db, "aso", "admin")
    h = csrf_headers(login(client, officer.username))
    sys_ = client.post("/api/grc/assets", json={"name": "Port Community System",
                                                "asset_type": "IT system / Application",
                                                "criticality": "Critical", "classification": "Confidential"},
                       headers=h)
    assert sys_.status_code == 201 and not sys_.json()["is_third_party"]
    assert client.post("/api/grc/assets", json={"name": "Thing", "asset_type": "Spaceship"},
                       headers=h).status_code == 422
    vendor = client.post("/api/grc/assets", json={
        "name": "Crane Maintenance Ltd", "asset_type": "Third party / Contractor", "criticality": "High",
        "contract_ref": "GPHA/PROC/2026/14", "contract_start": str(date.today() - timedelta(days=300)),
        "contract_end": str(date.today() + timedelta(days=30))}, headers=h)
    assert vendor.status_code == 201
    v = vendor.json()
    assert v["is_third_party"] and v["assessment_due"] and v["contract_expiring"]
    assert client.post(f"/api/grc/assets/{sys_.json()['id']}/assessments", json={
        "assessed_on": str(date.today()), "rating": "Low", "outcome": "Approved"}, headers=h).status_code == 422
    a = client.post(f"/api/grc/assets/{v['id']}/assessments", json={
        "assessed_on": str(date.today()), "rating": "High", "outcome": "Approved with conditions",
        "findings": "No business continuity plan"}, headers=h)
    assert a.status_code == 201 and not a.json()["assessment_due"] and a.json()["due_diligence"] == \
        "Approved with conditions"
    lst = client.get("/api/grc/assets?third_party=true").json()
    assert any(i["id"] == v["id"] for i in lst["items"]) and not any(i["id"] == sys_.json()["id"]
                                                                     for i in lst["items"])
    assert lst["summary"]["contracts_expiring"] >= 1


def test_task_manager_collects_work_for_a_business_user(client, client2, db):
    officer = _u(db, "tmo", "admin")
    owner = _u(db, "tmown", "auditee")
    approver = _u(db, "tmapp", "auditee")
    h = csrf_headers(login(client, officer.username))
    risk = client.post("/api/grc/risks", json={"title": "Cyber attack on terminal systems", "owner_id": owner.id,
                                               "inherent_likelihood": 4, "inherent_impact": 5,
                                               "residual_likelihood": 3, "residual_impact": 4}, headers=h).json()
    client.post(f"/api/grc/risks/{risk['id']}/kris", json={"name": "Phishing click rate", "unit": "%", "amber_at": 5,
                                                           "red_at": 10}, headers=h)
    g = client.post("/api/grc/regulations", json={"code": f"DPA{uuid.uuid4().hex[:4]}", "title": "Data Protection Act"},
                    headers=h).json()
    client.post(f"/api/grc/regulations/{g['id']}/requirements", json={"ref": "s.17", "title": "Privacy notices",
                                                                       "owner_id": owner.id}, headers=h)
    client.post("/api/grc/assets", json={"name": "Cleaning Services Ltd", "asset_type": "Third party / Vendor",
                                         "owner_id": owner.id}, headers=h)
    p = client.post("/api/grc/policies", json={"title": "Acceptable Use Policy", "approver_id": approver.id,
                                               "content": "Use systems for work."}, headers=h).json()
    client.post(f"/api/grc/policies/{p['id']}/submit", headers=h)
    ah = csrf_headers(login(client2, approver.username))
    client2.post(f"/api/grc/policies/{p['id']}/review", json={"decision": "approve"}, headers=ah)
    client.post(f"/api/grc/policies/{p['id']}/publish", json={}, headers=h)
    client.post(f"/api/grc/policies/{p['id']}/campaigns", json={"user_ids": [owner.id]}, headers=h)

    login(client2, owner.username)
    work = client2.get("/api/portal")
    assert work.status_code == 200, work.text
    names = {s["name"]: s["items"] for s in work.json()["sections"]}
    assert {"Attest to policies", "Record indicators", "Assess compliance", "Third-party due diligence"} <= set(names)
    assert names["Attest to policies"][0]["data"]["content"] == "Use systems for work."
    assert client2.get("/api/portal/count").json()["total"] == work.json()["total"]
    # The owner can open the records behind their items even without the risk & compliance apps.
    assert client2.get(f"/api/grc/risks/{risk['id']}").status_code == 200
    asset_id = names["Third-party due diligence"][0]["id"]
    assert client2.get(f"/api/grc/assets/{asset_id}").json()["can_assess"] is True
