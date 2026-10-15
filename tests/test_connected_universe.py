"""Connections between the audit universe, the object library, audits and risk assessments:
process/entity links to enterprise risks and standard controls, detailed scoping into an audit, audits covering
several entities (issues inherit them), and automatic assessment factors."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.enums import Role
from app.domains.assurance.planning.models import EntityUnit
from tests.conftest import csrf_headers, login, make_user


@pytest.fixture
def admin(client, db):
    u = make_user(db, f"cuadm_{uuid.uuid4().hex[:6]}", Role.Admin)
    return csrf_headers(login(client, u.username))


@pytest.fixture
def keep_universe(db):
    db.rollback()
    before = [e.id for e in db.execute(select(EntityUnit).where(EntityUnit.is_active.is_(True))).scalars()]
    yield
    db.rollback()
    for e in db.execute(select(EntityUnit).where(EntityUnit.id.in_(before or [0]))).scalars():
        e.is_active, e.archived_at = True, None
    db.commit()


def _library(db, tag):
    from app.domains.audit.frameworks.models import Framework, LibraryControl
    from app.domains.grc.risk.models import EnterpriseRisk

    fw = Framework(code=f"FW{tag}", name=f"GPHA controls {tag}")
    db.add(fw)
    db.flush()
    ctl = LibraryControl(framework_id=fw.id, ref="REV-01", title=f"Daily banking reconciliation {tag}",
                         test_procedure="Agree takings to deposit slips for 25 days.")
    risk = EnterpriseRisk(ref=f"ER{tag}", title=f"Revenue leakage {tag}", inherent_likelihood=4, inherent_impact=5)
    db.add_all([ctl, risk])
    db.commit()
    return risk.id, ctl.id


def _setup(client, admin, db, tag):
    port = client.post("/api/organizations", json={"name": f"CU Port {tag}", "category": "Port"}, headers=admin).json()
    fin = client.post("/api/organizations", json={"name": f"CU Finance {tag}", "category": "Department",
                                                  "parent_id": port["id"]}, headers=admin).json()
    proc = client.post("/api/processes", json={"name": f"CU Revenue {tag}", "org_ids": [fin["id"]]},
                       headers=admin).json()
    risk_id, ctl_id = _library(db, tag)
    links = client.put(f"/api/processes/{proc['id']}/links", json={"risk_ids": [risk_id], "control_ids": []},
                       headers=admin)
    assert links.status_code == 200, links.text
    assert client.post("/api/grc/links", json={"from_type": "risk", "from_id": risk_id, "to_type": "control",
                                               "to_id": ctl_id}, headers=admin).status_code == 201
    client.post("/api/audit-universe/define", json={"entities": [
        {"keys": [f"p:{fin['id']}:{proc['id']}"], "name": f"CU Revenue entity {tag}"}]}, headers=admin)
    ent = next(e for e in client.get("/api/audit-universe").json()["entities"]
               if e["name"] == f"CU Revenue entity {tag}")
    return {"port": port, "fin": fin, "proc": proc, "risk": risk_id, "ctl": ctl_id, "entity": ent}


def test_detailed_scoping_from_the_object_library(client, admin, db, keep_universe):
    tag = uuid.uuid4().hex[:5]
    s = _setup(client, admin, db, tag)
    assert client.get("/api/processes").json() and any(
        p["id"] == s["proc"]["id"] and p["risk_count"] == 1 for p in client.get("/api/processes").json())
    detail = client.get(f"/api/auditable-entities/{s['entity']['id']}").json()
    assert detail["links"]["processes"][0]["risks"][0]["id"] == s["risk"]

    ic = client.post("/api/audits", json={"title": f"CU IC {tag}", "scope": "x", "audit_type": "Compliance"},
                     headers=admin).json()
    assert client.post(f"/api/audits/{ic['id']}/scoping", headers=admin).status_code == 409  # no entities yet
    ents = client.put(f"/api/audits/{ic['id']}/entities", json={"entity_ids": [s["entity"]["id"]]}, headers=admin)
    assert ents.status_code == 200 and ents.json()[0]["id"] == s["entity"]["id"]
    pre = client.get(f"/api/audits/{ic['id']}/scoping").json()
    g = pre["groups"][0]
    assert g["risks"][0]["id"] == s["risk"] and g["controls"][0]["id"] == s["ctl"]
    assert g["risks"][0]["in_audit"] is False
    done = client.post(f"/api/audits/{ic['id']}/scoping", headers=admin).json()
    assert done == {"objectives": 1, "risks": 1, "controls": 1, "procedures": 0}
    rcm = client.get(f"/api/audits/{ic['id']}/rcm").json()
    risk = rcm["objectives"][0]["risks"][0]
    ctl = rcm["objectives"][0]["controls"][0]
    assert risk["enterprise_risk_id"] == s["risk"] and risk["inherent_score"] == 20
    assert ctl["library_control_id"] == s["ctl"] and ctl["risk_ids"] == [risk["id"]]
    assert ctl["test_steps"].startswith("Agree takings")
    again = client.post(f"/api/audits/{ic['id']}/scoping", headers=admin).json()
    assert again == {"objectives": 0, "risks": 0, "controls": 0, "procedures": 0}  # repeatable, no duplicates

    wp = client.post("/api/audits", json={"title": f"CU WP {tag}", "scope": "x", "audit_type": "Operational"},
                     headers=admin).json()
    client.put(f"/api/audits/{wp['id']}/entities", json={"entity_ids": [s["entity"]["id"]]}, headers=admin)
    w = client.post(f"/api/audits/{wp['id']}/scoping", headers=admin).json()
    assert w["procedures"] == 1 and w["controls"] == 0
    proc = client.get(f"/api/audits/{wp['id']}/procedures").json()["items"][0]
    assert proc["steps"].startswith("Agree takings") and proc["risks"][0]["title"] == f"Revenue leakage {tag}"

    # The entity page and the Issue Tracker follow the audits that cover the entity.
    f = client.post(f"/api/audits/{wp['id']}/findings", json={"title": f"CU late banking {tag}",
                                                              "risk_rating": "High"}, headers=admin).json()
    audits = client.get(f"/api/auditable-entities/{s['entity']['id']}/audits").json()
    assert {a["id"] for a in audits if a["id"]} >= {ic["id"], wp["id"]}
    fs = client.get(f"/api/auditable-entities/{s['entity']['id']}/findings").json()
    assert fs["summary"]["high"] == 1
    reg = client.get(f"/api/findings/register?entity_id={s['entity']['id']}").json()
    assert [r["id"] for r in reg["items"]] == [f["id"]]

    # Engagement risks can be linked to an enterprise risk by hand too, and the link is checked.
    bad = client.patch(f"/api/risks/{risk['id']}", json={"enterprise_risk_id": 999999}, headers=admin)
    assert bad.status_code == 422


def test_automatic_assessment_factors(client, admin, db, keep_universe):
    tag = uuid.uuid4().hex[:5]
    s = _setup(client, admin, db, tag)
    eid = s["entity"]["id"]
    t = client.post("/api/assessment-factors", json={"name": f"Time since audit {tag}",
                                                     "auto_source": "time_since_audit"}, headers=admin).json()
    p = client.post("/api/assessment-factors", json={"name": f"Prior results {tag}", "auto_source": "prior_results"},
                    headers=admin).json()
    m = client.post("/api/assessment-factors", json={"name": f"Manual {tag}"}, headers=admin).json()
    assert client.post("/api/assessment-factors", json={"name": "x y", "auto_source": "magic"},
                       headers=admin).status_code == 422

    a = client.post("/api/audit-risk-assessments", json={"name": f"Auto {tag}", "entity_ids": [eid],
                                                         "factor_ids": [t["id"], p["id"], m["id"]]}, headers=admin)
    assert a.status_code == 201, a.text
    row = a.json()["rows"][0]
    assert a.json()["status"] == "In progress"
    assert row["scores"][str(t["id"])] == 3  # never audited -> highest
    assert row["scores"][str(p["id"])] == 1  # no findings -> lowest
    assert row["scores"][str(m["id"])] is None  # manual factors stay for the auditor

    # A High finding on an audit covering the entity raises "Prior results" when re-scored.
    au = client.post("/api/audits", json={"title": f"CU AU {tag}", "scope": "x"}, headers=admin).json()
    client.put(f"/api/audits/{au['id']}/entities", json={"entity_ids": [eid]}, headers=admin)
    client.post(f"/api/audits/{au['id']}/findings", json={"title": "Open high", "risk_rating": "High"}, headers=admin)
    r = client.post(f"/api/audit-risk-assessments/{a.json()['id']}/auto-score", json={"overwrite": True},
                    headers=admin).json()
    assert r["filled"] == 2 and r["rows"][0]["scores"][str(p["id"])] == 3


def test_org_unit_entity_covers_its_processes_when_scoping(client, admin, db, keep_universe):
    tag = uuid.uuid4().hex[:5]
    s = _setup(client, admin, db, tag)
    client.post("/api/audit-universe/define", json={"entities": [
        {"keys": [f"o:{s['port']['id']}"], "name": f"CU whole port {tag}"}]}, headers=admin)
    ent = next(e for e in client.get("/api/audit-universe").json()["entities"]
               if e["name"] == f"CU whole port {tag}" and e["status"] == "Active")
    au = client.post("/api/audits", json={"title": f"CU port audit {tag}", "scope": "x"}, headers=admin).json()
    client.put(f"/api/audits/{au['id']}/entities", json={"entity_ids": [ent["id"]]}, headers=admin)
    groups = client.get(f"/api/audits/{au['id']}/scoping").json()["groups"]
    assert groups and groups[0]["objective"].startswith(f"CU Revenue {tag}")
