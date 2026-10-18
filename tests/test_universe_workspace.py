"""Audit universe workspace: overview counts, unit review, process mapping, entity definition (create, edit,
duplicate and Ready checks, history, delete or retire) and the hand-off to the audit risk assessment."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.enums import Role
from app.domains.assurance.planning.models import EntityUnit
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, job=None):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    user.email = f"{user.username}@gpha.test"
    db.commit()
    return user


@pytest.fixture
def admin(client, db):
    u = _u(db, "uw_adm", Role.Admin)
    return csrf_headers(login(client, u.username)), u


def _org(client, h, name, category, parent=None):
    r = client.post("/api/organizations", json={"name": name, "category": category, "parent_id": parent}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _setup(client, h):
    tag = uuid.uuid4().hex[:5]
    port = _org(client, h, f"Port {tag}", "Port")
    fin = _org(client, h, f"Finance {tag}", "Department", port)
    ops = _org(client, h, f"Marine {tag}", "Department", port)
    idle = _org(client, h, f"Idle {tag}", "Unit", port)
    p1 = client.post("/api/processes", json={"name": f"Cargo clearance {tag}", "org_ids": [fin, ops]}, headers=h).json()
    p2 = client.post("/api/processes", json={"name": f"Business continuity {tag}"}, headers=h).json()
    return {"tag": tag, "port": port, "fin": fin, "ops": ops, "idle": idle, "p1": p1["id"], "p2": p2["id"]}


def test_overview_and_unit_review(client, db, admin):
    h, _ = admin
    t = _setup(client, h)
    units = {r["id"]: r for r in client.get("/api/audit-universe/units").json()["items"]}
    assert units[t["fin"]]["status"] == "Needs review" and units[t["fin"]]["processes"] == 1
    assert units[t["fin"]]["location"] == f"Port {t['tag']}" and units[t["fin"]]["parent"]["id"] == t["port"]
    before = client.get("/api/audit-universe/overview").json()
    # Include two units; mark one Not included (a reason is required).
    assert client.post("/api/audit-universe/units/review", json={"ids": [t["fin"], t["ops"]], "decision": "Included"},
                       headers=h).status_code == 200
    no_reason = client.post("/api/audit-universe/units/review", json={"ids": [t["idle"]], "decision": "Not included"},
                            headers=h)
    assert no_reason.status_code == 422
    assert client.post("/api/audit-universe/units/review", json={"ids": [t["idle"]], "decision": "Not included",
                                                               "reason": "Dormant unit, no activity"},
                       headers=h).status_code == 200
    after = client.get("/api/audit-universe/overview").json()
    assert after["units"]["included"] == before["units"]["included"] + 2
    assert after["units"]["needs_review"] == before["units"]["needs_review"] - 3
    assert after["processes"]["unmapped"] >= 1
    detail = client.get(f"/api/audit-universe/units/{t['idle']}").json()
    assert detail["status"] == "Not included" and detail["review"]["reason"] == "Dormant unit, no activity"
    fin = client.get(f"/api/audit-universe/units/{t['fin']}").json()
    assert [p["id"] for p in fin["process_list"]] == [t["p1"]] and fin["path"].startswith(f"Port {t['tag']}")
    # Back to review.
    client.post("/api/audit-universe/units/review", json={"ids": [t["idle"]], "decision": "Needs review"}, headers=h)
    assert client.get(f"/api/audit-universe/units/{t['idle']}").json()["status"] == "Needs review"


def test_process_mapping(client, db, admin):
    h, _ = admin
    t = _setup(client, h)
    rows = {r["id"]: r for r in client.get("/api/audit-universe/processes").json()["items"]}
    assert rows[t["p2"]]["mapping"] == "Unmapped" and rows[t["p1"]]["mapping"] == "Mapped"
    assert {u["id"] for u in rows[t["p1"]]["units"]} == {t["fin"], t["ops"]}
    # Map the unmapped process to a unit, then replace the units of the first one.
    assert client.post("/api/audit-universe/processes/map", json={"process_ids": [t["p2"]], "org_ids": [t["port"]]},
                       headers=h).status_code == 200
    assert client.post("/api/audit-universe/processes/map", json={"process_ids": [t["p1"]], "org_ids": [t["fin"]],
                                                                "mode": "replace"}, headers=h).status_code == 200
    rows = {r["id"]: r for r in client.get("/api/audit-universe/processes").json()["items"]}
    assert rows[t["p2"]]["mapping"] == "Mapped" and [u["id"] for u in rows[t["p1"]]["units"]] == [t["fin"]]
    # The Process library itself shows the change (no copy).
    lib = {p["id"]: p for p in client.get("/api/processes").json()}
    assert [o["id"] for o in lib[t["p1"]]["org_units"]] == [t["fin"]]


def test_entity_definition_rules_history_and_handoff(client, db, admin):
    h, me = admin
    t = _setup(client, h)
    body = {"name": f"Finance — Cargo clearance {t['tag']}", "entity_type": "Process + unit", "org_ids": [t["fin"]],
            "process_ids": [t["p1"]]}
    # Ready needs a business owner and a scope statement.
    r = client.post("/api/auditable-entities", json={**body, "definition_status": "Ready"}, headers=h)
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "owner_email"
    bad_type = client.post("/api/auditable-entities", json={**body, "entity_type": "Spaceship"}, headers=h)
    assert bad_type.status_code == 422
    e = client.post("/api/auditable-entities", json=body, headers=h)
    assert e.status_code == 201, e.text
    e = e.json()
    assert e["definition_status"] == "Draft" and e["entity_type"] == "Process + unit"
    assert [o["id"] for o in e["org_units"]] == [t["fin"]] and [p["id"] for p in e["processes"]] == [t["p1"]]
    # The same units and processes again: a duplicate warning that can be overridden; the same name is refused.
    dup = client.post("/api/auditable-entities", json={**body, "name": f"Other {t['tag']}"}, headers=h)
    assert dup.status_code == 409 and "duplicate" in dup.json()["detail"].lower()
    same_name = client.post("/api/auditable-entities", json={**body, "org_ids": [t["ops"]]}, headers=h)
    assert same_name.status_code == 422 and same_name.json()["errors"][0]["field"] == "name"
    # A process-only entity takes the units that perform it.
    proc_only = client.post("/api/auditable-entities", json={"name": f"Cargo everywhere {t['tag']}",
                                                             "entity_type": "Process", "process_ids": [t["p1"]],
                                                             "allow_duplicate": True}, headers=h).json()
    assert {o["id"] for o in proc_only["org_units"]} == {t["fin"], t["ops"]}
    unmapped = client.post("/api/auditable-entities", json={"name": f"BCP {t['tag']}", "entity_type": "Process",
                                                            "process_ids": [t["p2"]]}, headers=h)
    assert unmapped.status_code == 422 and unmapped.json()["errors"][0]["field"] == "org_ids"
    # Made Ready with a business owner and a scope statement.
    ready = client.patch(f"/api/auditable-entities/{e['id']}", json={
        "definition_status": "Ready", "owner_email": me.email, "scope": "Clearance of import cargo at Tema.",
        "objectives": "Revenue is complete."}, headers=h)
    assert ready.status_code == 200, ready.text
    assert ready.json()["definition_status"] == "Ready" and ready.json()["owner"] == me.full_name
    # Units and processes edited: recorded in the history with before and after.
    twin = client.patch(f"/api/auditable-entities/{e['id']}", json={"org_ids": [t["fin"], t["ops"]]}, headers=h)
    assert twin.status_code == 409  # now the same as the process-only entity
    both = {"org_ids": [t["fin"], t["ops"]], "allow_duplicate": True}
    assert client.patch(f"/api/auditable-entities/{e['id']}", json=both, headers=h).status_code == 200
    hist = client.get(f"/api/auditable-entities/{e['id']}/history").json()
    actions = " | ".join(x["action"] for x in hist)
    assert "Created as Draft" in actions and "Status: Draft -> Ready" in actions and "Changed scope" in actions
    assert f"added Marine {t['tag']}" in actions
    # Hand-off: the entity can be assessed; a Draft one cannot.
    fac = client.post("/api/assessment-factors", json={"name": f"Materiality {t['tag']}"}, headers=h).json()
    ara = client.post("/api/audit-risk-assessments", json={"name": f"ARA {t['tag']}", "entity_ids": [e["id"]],
                                                           "factor_ids": [fac["id"]], "scale": "Low- to High-risk"},
                      headers=h)
    assert ara.status_code == 201, ara.text
    page = client.get(f"/api/auditable-entities/{e['id']}").json()
    assert page["open_assessment"]["id"] == ara.json()["id"] and page["rating"] is None
    draft = client.post("/api/audit-risk-assessments", json={"name": f"ARA2 {t['tag']}",
                                                             "entity_ids": [proc_only["id"]],
                                                             "factor_ids": [fac["id"]], "scale": "Low- to High-risk"},
                        headers=h)
    assert draft.status_code == 422
    # Used by an assessment: cannot be deleted, only retired; an unused entity can be deleted.
    assert client.delete(f"/api/auditable-entities/{e['id']}", headers=h).status_code == 409
    assert client.delete(f"/api/auditable-entities/{proc_only['id']}", headers=h).status_code == 200
    db.expire_all()
    assert db.execute(select(EntityUnit).where(EntityUnit.id == proc_only["id"])).first() is None
    retired = client.patch(f"/api/auditable-entities/{e['id']}", json={"definition_status": "Retired"},
                           headers=h).json()
    assert retired["definition_status"] == "Retired" and retired["status"] == "Archived"
    reg = {r["id"]: r for r in client.get("/api/audit-universe/entities").json()["items"]}
    assert reg[e["id"]]["definition_status"] == "Retired" and reg[e["id"]]["owner"] == me.full_name


def test_permissions(client, db):
    viewer = _u(db, "uw_aud", job="auditor")
    h = csrf_headers(login(client, viewer.username))
    assert client.get("/api/audit-universe/overview").status_code == 200
    assert client.post("/api/audit-universe/units/review", json={"ids": [1], "decision": "Included"},
                       headers=h).status_code == 403
    assert client.post("/api/auditable-entities", json={"name": "x entity", "entity_type": "Org unit",
                                                        "org_ids": [1]}, headers=h).status_code == 403
    auditee = _u(db, "uw_cli", Role.Auditee)
    login(client, auditee.username)
    assert client.get("/api/audit-universe/units").status_code == 403


def test_review_fixes_shared_names_links_and_reactivation(client, db, admin):
    from app.domains.grc.links import GrcLink

    h, _ = admin
    t = _setup(client, h)
    # Older universes can share names: editing or retiring one of them still works.
    a = client.post("/api/auditable-entities", json={"name": f"Finance {t['tag']} A", "entity_type": "Org unit",
                                                     "org_ids": [t["fin"]]}, headers=h).json()
    b = client.post("/api/auditable-entities", json={"name": f"Finance {t['tag']} B", "entity_type": "Org unit",
                                                     "org_ids": [t["ops"]]}, headers=h).json()
    db.execute(EntityUnit.__table__.update().where(EntityUnit.id == b["id"]).values(name=a["name"]))
    db.commit()
    assert client.patch(f"/api/auditable-entities/{b['id']}", json={"objectives": "x"}, headers=h).status_code == 200
    assert client.patch(f"/api/auditable-entities/{b['id']}", json={"definition_status": "Retired"},
                        headers=h).status_code == 200
    # Reactivating through the older Active/Archived path returns as Draft (Ready rules are not forced).
    back = client.patch(f"/api/auditable-entities/{b['id']}", json={"status": "Active", "name": f"Ops {t['tag']}"},
                        headers=h)
    assert back.status_code == 200 and back.json()["definition_status"] == "Draft"
    # Deleting an unused entity removes its risk and control links too.
    risk_link = GrcLink(a_type="risk", a_id=999999, b_type="unit", b_id=a["id"])
    db.add(risk_link)
    db.commit()
    assert client.delete(f"/api/auditable-entities/{a['id']}", headers=h).status_code == 200
    db.expire_all()
    assert db.execute(select(GrcLink).where(GrcLink.b_type == "unit", GrcLink.b_id == a["id"])).first() is None


def test_assessment_keeps_members_that_are_no_longer_ready(client, db, admin):
    h, me = admin
    t = _setup(client, h)
    e = client.post("/api/auditable-entities", json={
        "name": f"Marine {t['tag']} entity", "entity_type": "Org unit", "org_ids": [t["ops"]],
        "definition_status": "Ready", "owner_email": me.email, "scope": "Marine operations at the port."},
        headers=h).json()
    fac = client.post("/api/assessment-factors", json={"name": f"Fraud {t['tag']}"}, headers=h).json()
    ara = client.post("/api/audit-risk-assessments", json={"name": f"ARA keep {t['tag']}", "entity_ids": [e["id"]],
                                                           "factor_ids": [fac["id"]], "scale": "Low- to High-risk"},
                      headers=h).json()
    client.patch(f"/api/auditable-entities/{e['id']}", json={"definition_status": "Needs review"}, headers=h)
    r = client.patch(f"/api/audit-risk-assessments/{ara['id']}", json={"name": f"ARA kept {t['tag']}",
                                                                       "entity_ids": [e["id"]],
                                                                       "factor_ids": [fac["id"]]}, headers=h)
    assert r.status_code == 200, r.text
