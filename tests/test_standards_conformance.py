"""Standards conformance: correcting issued reports (GIAS 11.4), advisory engagements (13.1), the assurance map
(9.5), independence of every team member with rotation and cooling-off (2.2, 7.1) and risk acceptance escalation
(11.5)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from app.core import permissions as perms
from app.core.database import SessionLocal
from app.core.enums import ReviewLevel, Role, Severity, utcnow
from app.domains.audit.audits.models import Audit
from app.domains.issues.capa.models import Capa
from app.main import app
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_entity, make_user


def _u(db, prefix, role=Role.Auditor, job=None, level=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    if level:
        user.review_level = level
    db.commit()
    return user


def _set(client, h, values):
    r = client.put("/api/config", json={"values": values}, headers=h)
    assert r.status_code == 200, r.text


def _issue(prep, ph, rid, manager, cae):
    """Submit, review and issue a report that has nothing blocking it."""
    assert prep.post(f"/api/reports/{rid}/submit-for-review", headers=ph).status_code == 200
    with TestClient(app) as m:
        mh = csrf_headers(login(m, manager.username))
        assert m.post(f"/api/reports/{rid}/manager-review", json={"password": DEFAULT_PASSWORD}, headers=mh).json()[
            "status"] == "CAE Approval"
    with TestClient(app) as c:
        ch = csrf_headers(login(c, cae.username))
        r = c.post(f"/api/reports/{rid}/cae-approve", json={"password": DEFAULT_PASSWORD}, headers=ch)
        assert r.status_code == 200, r.text
        return r.json()


# ------------------------------------------------------------------ 1. correcting an issued report


def test_issued_report_is_corrected_as_a_new_version(client, client2, db):
    prep = _u(db, "sc_prep")
    manager = _u(db, "sc_mgr", job="manager")
    cae = _u(db, "sc_cae", job="manager", level=ReviewLevel.CAE)
    ph = csrf_headers(login(client, prep.username))
    audit = client.post("/api/audits", json={"title": "Stores", "scope": "Stores Q2"}, headers=ph).json()
    rid = client.post(f"/api/audits/{audit['id']}/report", headers=ph).json()["id"]
    client.patch(f"/api/reports/{rid}", json={"overall_rating": "Satisfactory", "executive_summary": "Original text.",
                                              "overall_opinion": "Controls work."}, headers=ph)
    issued = _issue(client, ph, rid, manager, cae)
    assert issued["version"] == 1 and issued["can_correct"] is True  # the GM Audit's view
    assert client.get(f"/api/reports/{rid}").json()["can_correct"] is False  # the preparer's
    sent = {"recipient": "Audit Committee", "channel": "Letter", "sent_at": utcnow().isoformat()}
    assert client.post(f"/api/reports/{rid}/distribution", json=sent, headers=ph).status_code == 201

    reason = {"reason": "The stock count total in the summary was misstated."}
    assert client.post(f"/api/reports/{rid}/correction", json=reason, headers=ph).status_code == 403
    ch = csrf_headers(login(client2, cae.username))
    opened = client2.post(f"/api/reports/{rid}/correction", json=reason, headers=ch)
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["status"] == "Draft" and body["version"] == 2 and body["correction_reason"].startswith("The stock")
    assert client2.post(f"/api/reports/{rid}/correction", json=reason, headers=ch).status_code == 409

    versions = client.get(f"/api/reports/{rid}/versions").json()
    assert [v["version"] for v in versions] == [1]
    old = client.get(f"/api/reports/{rid}/versions/1/print")
    assert old.status_code == 200 and "Original text." in old.text and "Superseded by version 2" in old.text
    assert client.get(f"/api/reports/{rid}/versions/1/export.docx").status_code == 200

    client.patch(f"/api/reports/{rid}", json={"executive_summary": "Corrected text."}, headers=ph)
    again = _issue(client, ph, rid, manager, cae)
    assert again["status"] == "Issued" and again["version"] == 2
    page = client.get(f"/api/reports/{rid}/print").text
    assert "Corrected text." in page and "correcting version 1" in page and "Version 2 issued" in page
    assert again["issued_at"] == issued["issued_at"], "the first issue date is kept for KPIs"
    assert "Original text." in client.get(f"/api/reports/{rid}/versions/1/print").text, "the old version is frozen"
    dist = client.get(f"/api/reports/{rid}/distribution").json()
    assert dist["version"] == 2 and "Audit Committee" in dist["missing"], "earlier recipients need the correction"
    client.post(f"/api/reports/{rid}/distribution", json={
        "recipient": "Audit Committee", "channel": "Letter", "sent_at": utcnow().isoformat()}, headers=ph)
    dist = client.get(f"/api/reports/{rid}/distribution").json()
    assert "Audit Committee" not in dist["missing"] and {d["version"] for d in dist["sent"]} == {1, 2}


# ------------------------------------------------------------------ 2. advisory engagements


def test_advisory_engagement_has_no_rating_or_required_actions(client, db):
    lead = _u(db, "sc_adv")
    h = csrf_headers(login(client, lead.username))
    audit = client.post("/api/audits", json={"title": "New ERP design", "audit_type": "Advisory"}, headers=h).json()
    assert audit["nature"] == "Advisory"
    assert client.post("/api/audits", json={"title": "Payroll", "audit_type": "Financial"},
                       headers=h).json()["nature"] == "Assurance"
    client.post(f"/api/audits/{audit['id']}/findings", json={"title": "Role design gap", "risk_rating": "High"},
                headers=h)
    report = client.post(f"/api/audits/{audit['id']}/report", headers=h).json()
    assert report["title"].startswith("Advisory Report") and report["advisory"] is True
    assert not any("rating" in b for b in report["blockers"])
    checks = {c["key"]: c for c in client.get(f"/api/audits/{audit['id']}/closure-check").json()["checks"]}
    assert checks["actions"]["required"] is False and not checks["actions"]["ok"]
    assert "Observations" in client.get(f"/api/reports/{report['id']}/print").text


# ------------------------------------------------------------------ 3. assurance map


def test_assurance_map_records_providers_and_reliance(client, client2, db):
    admin = _u(db, "sc_map", Role.Admin, job="admin")
    h = csrf_headers(login(client, admin.username))
    entity = make_entity(client, h, "Marine services")
    bad = client.post("/api/assurance-providers", json={"name": "Risk Unit", "line": "Fourth line"}, headers=h)
    assert bad.status_code == 422
    prov = client.post("/api/assurance-providers", json={"name": f"Risk Unit {uuid.uuid4().hex[:4]}",
                                                         "line": "Second line (risk and compliance)"}, headers=h)
    assert prov.status_code == 201, prov.text
    pid = prov.json()["id"]
    cover = {"entity_id": entity["id"], "provider_id": pid, "result": "Effective", "reliance": "Partial",
             "last_assurance_on": (utcnow() - timedelta(days=40)).date().isoformat()}
    no_basis = client.post("/api/assurance-coverage", json=cover, headers=h)
    assert no_basis.status_code == 422 and "competence" in no_basis.text
    made = client.post("/api/assurance-coverage", json={
        **cover, "reliance_basis": "Qualified staff, reports to the Board Risk Committee, followed its method."},
        headers=h)
    assert made.status_code == 201, made.text
    assert client.post("/api/assurance-coverage", json={**cover, "reliance": "None"}, headers=h).status_code == 409
    m = client.get("/api/assurance-map").json()
    row = next(r for r in m["rows"] if r["id"] == entity["id"])
    assert row["cells"]["Second line (risk and compliance)"][0]["reliance"] == "Partial"
    assert m["summary"]["relied_on"] >= 1
    history = client.get(f"/api/auditable-entities/{entity['id']}/history").json()
    assert any("Assurance:" in x["action"] for x in history)
    auditee = _u(db, "sc_map_ae", Role.Auditee)
    login(client2, auditee.username)
    assert client2.get("/api/assurance-map").status_code == 403
    viewer = _u(db, "sc_map_aud", job="auditor")
    vh = csrf_headers(login(client2, viewer.username))
    assert client2.get("/api/assurance-map").status_code == 200
    assert client2.post("/api/assurance-providers", json={"name": "X provider", "line": "External assurance"},
                        headers=vh).status_code == 403
    assert client.delete(f"/api/assurance-coverage/{made.json()['id']}", headers=h).status_code == 200


# ------------------------------------------------------------------ 4. independence of the whole team


def test_every_member_declares_and_rotation_and_cooling_off_are_flagged(client, client2, db):
    admin = _u(db, "sc_ind_adm", Role.Admin, job="admin")
    lead = _u(db, "sc_ind_lead", job="auditor")
    reviewer = _u(db, "sc_ind_rev", job="manager")
    boss = _u(db, "sc_ind_boss", job="manager")
    h = csrf_headers(login(client, admin.username))
    _set(client, h, {"auditor_rotation_years": 2, "cooling_off_months": 12})
    try:
        entity = make_entity(client, h, "Revenue collection")
        h = csrf_headers(login(client, boss.username))
        ids = []
        for years_ago in (2, 1, 0):
            a = client.post("/api/audits", json={"title": f"Revenue {years_ago}"}, headers=h).json()
            assert client.post(f"/api/audits/{a['id']}/team", json={"user_id": lead.id, "team_role": "Lead auditor"},
                               headers=h).status_code == 200
            with SessionLocal() as s:
                s.execute(Audit.__table__.update().where(Audit.id == a["id"]).values(
                    entity_unit_id=entity["id"], created_at=utcnow() - timedelta(days=366 * years_ago)))
                s.commit()
            ids.append(a["id"])
        current = ids[-1]
        member = next(m for m in client.get(f"/api/audits/{current}/team").json() if m["user_id"] == lead.id)
        assert member["independence"] == "Not declared"
        assert any("previous 2 consecutive years" in i for i in member["objectivity"])

        lh = csrf_headers(login(client2, lead.username))
        role = client2.post("/api/proficiency/prior-roles", json={
            "org_unit_id": entity["org_unit_id"], "role": "Revenue officer",
            "to_date": (utcnow() - timedelta(days=60)).date().isoformat()}, headers=lh)
        assert role.status_code == 201, role.text
        assert client2.delete(f"/api/proficiency/prior-roles/{role.json()['id']}", headers=lh).status_code == 403
        member = next(m for m in client.get(f"/api/audits/{current}/team").json() if m["user_id"] == lead.id)
        assert any("Worked in" in i and "cooling-off 12 months" in i for i in member["objectivity"])

        from app.domains.audit.proficiency.service import declaration_blockers

        db.rollback()
        problems = declaration_blockers(db, db.get(Audit, current))
        assert any(lead.full_name in p and "not declared" in p for p in problems)
        assert any("rotation" in p for p in problems) and any("cooling-off" in p for p in problems)

        # Declaring the conflict and having it cleared with safeguards lifts the automatic flags.
        client2.post("/api/proficiency/declarations", json={
            "kind": "annual", "independence_confirmed": True, "ethics_confirmed": True,
            "confidentiality_confirmed": True}, headers=lh)
        d = client2.post("/api/proficiency/declarations", json={
            "kind": "engagement", "audit_id": current, "independence_confirmed": True, "ethics_confirmed": True,
            "confidentiality_confirmed": True, "has_conflict": True,
            "conflict_details": "Led the last two audits and worked in Revenue until recently."}, headers=lh).json()
        with TestClient(app) as c3:
            rh = csrf_headers(login(c3, reviewer.username))
            cleared = c3.post(f"/api/proficiency/declarations/{d['id']}/review", json={
                "decision": "Cleared", "notes": "Second reviewer on all working papers."}, headers=rh)
            assert cleared.status_code == 200, cleared.text
        member = next(m for m in client.get(f"/api/audits/{current}/team").json() if m["user_id"] == lead.id)
        assert member["independence"] == "Cleared" and member["objectivity"] == []
    finally:
        h = csrf_headers(login(client, admin.username))
        for key in ("auditor_rotation_years", "cooling_off_months"):
            client.post(f"/api/config/{key}/reset", headers=h)


# ------------------------------------------------------------------ 5. risk acceptance escalation


def test_high_risk_acceptance_is_decided_by_the_gm_audit(client, client2, db):
    raiser = _u(db, "sc_ra_aud", job="auditor")
    proposer = _u(db, "sc_ra_mgr", job="manager")
    cae = _u(db, "sc_ra_cae", job="manager", level=ReviewLevel.CAE)
    h = csrf_headers(login(client, raiser.username))
    cid = client.post("/api/capa", json={"title": "Replace the gate system", "owner_email": "gate@gpha.test"},
                      headers=h).json()["id"]
    with SessionLocal() as s:
        s.execute(Capa.__table__.update().where(Capa.id == cid).values(severity=Severity.High.name))
        s.commit()
    mh = csrf_headers(login(client2, proposer.username))
    proposal = {"reason": "Budget not available until 2028; manual gate checks continue daily.",
                "accepted_by": "Director-General"}
    proposed = client2.post(f"/api/capa/{cid}/accept-risk", json=proposal, headers=mh).json()
    assert proposed["risk_acceptance_status"] == "Proposed" and proposed["status"] != "Closed"
    assert client2.post(f"/api/capa/{cid}/accept-risk", json=proposal, headers=mh).status_code == 409
    decision = {"decision": "Agree", "comment": "Discussed with the Director-General on 12 October."}
    assert client2.post(f"/api/capa/{cid}/risk-acceptance/decision", json=decision, headers=mh).status_code == 403

    with TestClient(app) as c3:
        ch = csrf_headers(login(c3, cae.username))
        agreed = c3.post(f"/api/capa/{cid}/risk-acceptance/decision", json=decision, headers=ch).json()
        # The GM Audit's agreement closes the action (no Audit Committee referral).
        assert agreed["risk_acceptance_status"] == "Accepted" and agreed["status"] == "Closed"
    db.rollback()
    capa = db.get(Capa, cid)
    assert capa.status.value == "Closed" and capa.implementation_status == "Risk Accepted"
    assert capa.risk_acceptance_status == "Accepted"
    kinds = [e["kind"] for e in client.get(f"/api/capa/{cid}/timeline").json()]
    assert kinds.count("risk_proposed") == 1 and kinds[-1] == "risk_accepted"


def test_staff_directory_is_for_audit_staff(client, client2, db):
    staff = _u(db, "sc_dir", job="auditor")
    login(client, staff.username)
    rows = client.get("/api/users/directory").json()
    assert any(r["id"] == staff.id for r in rows) and set(rows[0]) == {"id", "name", "approval_level"}
    auditee = _u(db, "sc_dir_ae", Role.Auditee)
    login(client2, auditee.username)
    assert client2.get("/api/users/directory").status_code == 403
