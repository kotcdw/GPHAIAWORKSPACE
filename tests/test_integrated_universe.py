"""Integrated audit universe: Org Structure, Process library, auditable entities, audit risk assessments and
planning from them."""

from __future__ import annotations

import io
import uuid

import pytest

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


@pytest.fixture
def admin(client, db):
    u = make_user(db, f"uvadm_{uuid.uuid4().hex[:6]}", Role.Admin)
    return csrf_headers(login(client, u.username))


def _org(client, h, name, category, parent=None):
    r = client.post("/api/organizations", json={"name": name, "category": category, "parent_id": parent}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _tree(client, h, tag):
    hq = _org(client, h, f"HQ {tag}", "Head Office")
    tema = _org(client, h, f"Tema {tag}", "Port")
    fin = _org(client, h, f"Tema Finance {tag}", "Department", tema["id"])
    rev = _org(client, h, f"Tema Revenue {tag}", "Unit", fin["id"])
    ops = _org(client, h, f"Tema Marine {tag}", "Department", tema["id"])
    vendor = _org(client, h, f"Vendor {tag}", "Vendor")
    p1 = client.post("/api/processes", json={"name": f"Revenue collection {tag}", "org_ids": [rev["id"], fin["id"]]},
                     headers=h).json()
    p2 = client.post("/api/processes", json={"name": f"Pilotage {tag}", "org_ids": [ops["id"]]}, headers=h).json()
    return {"hq": hq, "tema": tema, "fin": fin, "rev": rev, "ops": ops, "vendor": vendor, "p1": p1, "p2": p2}


def test_org_structure_and_process_library(client, admin, db):
    tag = uuid.uuid4().hex[:5]
    t = _tree(client, admin, tag)
    tree = client.get("/api/org-structure").json()
    rows = {r["id"]: r for r in tree["items"]}
    assert t["vendor"]["id"] not in rows  # external parties stay out of the Org Structure
    assert rows[t["rev"]["id"]]["depth"] == rows[t["fin"]["id"]]["depth"] + 1
    assert [p["id"] for p in rows[t["rev"]["id"]]["processes"]] == [t["p1"]["id"]]
    assert t["p1"]["ref"].startswith("PROC-") and len(t["p1"]["org_units"]) == 2
    dup = client.post("/api/processes", json={"name": f"Revenue collection {tag}"}, headers=admin)
    assert dup.status_code == 422
    bad = client.post("/api/processes", json={"name": f"X {tag}", "org_ids": [t["vendor"]["id"]]}, headers=admin)
    assert bad.status_code == 422


def _entity(client, h, name, org_ids, process_ids=()):
    r = client.post("/api/auditable-entities", json={
        "name": name, "entity_type": "Process + unit" if process_ids else "Org unit", "org_ids": org_ids,
        "process_ids": list(process_ids), "definition_status": "Ready", "owner_email": "owner@gpha.test",
        "scope": f"Activities of {name}."}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_entities_coverage_and_entity_page(client, admin, db):
    tag = uuid.uuid4().hex[:5]
    t = _tree(client, admin, tag)
    fin, ops = t["fin"]["id"], t["ops"]["id"]
    p2 = t["p2"]["id"]
    before = client.get("/api/audit-universe").json()["coverage"]
    fin_e = _entity(client, admin, f"Tema Finance {tag}", [fin])
    pil = _entity(client, admin, f"Tema Marine {tag} - Pilotage {tag}", [ops], [p2])
    uni = client.get("/api/audit-universe").json()
    mine = {e["name"]: e for e in uni["entities"] if e["status"] == "Active" and tag in e["name"]}
    assert set(mine) == {fin_e["name"], pil["name"]}
    row = mine[pil["name"]]
    assert row["processes"][0]["id"] == p2 and row["org_units"][0]["id"] == ops
    assert row["category"] == f"Tema {tag}"  # entity category = the port the org unit sits in
    assert uni["coverage"]["org_units_covered"] == before["org_units_covered"] + 2
    assert uni["defined"] is True

    # Retiring keeps the entity (and its history) but takes it out of the active universe.
    client.patch(f"/api/auditable-entities/{pil['id']}", json={"definition_status": "Retired"}, headers=admin)
    states = {e["id"]: e["status"] for e in client.get("/api/audit-universe").json()["entities"]}
    assert states[fin_e["id"]] == "Active" and states[pil["id"]] == "Archived"

    # Entity page: frequency, next due date, tabs.
    keep_id = fin_e["id"]
    e = client.patch(f"/api/auditable-entities/{keep_id}", json={"audit_frequency_months": 24}, headers=admin)
    assert e.status_code == 200 and e.json()["frequency"] == "Every 2 years" and e.json()["next_due"]
    assert client.patch(f"/api/auditable-entities/{keep_id}", json={"audit_frequency_months": 7},
                        headers=admin).status_code == 422
    assert client.get(f"/api/auditable-entities/{keep_id}/audits").json() == []
    assert client.get(f"/api/auditable-entities/{keep_id}/findings").json()["summary"]["findings"] == 0


def test_audit_risk_assessment_to_plan(client, admin, db):
    tag = uuid.uuid4().hex[:5]
    t = _tree(client, admin, tag)
    for name, key in ((f"Finance {tag}", "fin"), (f"Marine {tag}", "ops"), (f"HQ {tag}", "hq")):
        _entity(client, admin, name, [t[key]["id"]])
    ents = {e["name"]: e["id"] for e in client.get("/api/audit-universe").json()["entities"]
            if e["status"] == "Active" and tag in e["name"]}
    f1 = client.post("/api/assessment-factors", json={"name": f"Fraud risk {tag}"}, headers=admin).json()
    f2 = client.post("/api/assessment-factors", json={"name": f"Materiality {tag}"}, headers=admin).json()
    factors = client.get("/api/assessment-factors").json()
    assert factors["scale"] == "Low- to High-risk" and any(x["id"] == f1["id"] for x in factors["items"])

    a = client.post("/api/audit-risk-assessments", json={"name": f"FY27 risk assessment {tag}",
                                                         "entity_ids": list(ents.values()),
                                                         "factor_ids": [f1["id"], f2["id"]]}, headers=admin)
    assert a.status_code == 201, a.text
    a = a.json()
    assert a["status"] == "Draft" and a["cells"] == 6 and a["levels"] == ["Low", "Medium", "High"]
    assert client.post("/api/audit-risk-assessments", json={"name": a["name"], "entity_ids": [ents[f"HQ {tag}"]],
                                                            "factor_ids": [f1["id"]]}, headers=admin).status_code == 422
    url = f"/api/audit-risk-assessments/{a['id']}"
    scores = {f"Finance {tag}": (3, 3), f"Marine {tag}": (3, 2), f"HQ {tag}": (1, 1)}
    first = True
    for name, (s1, s2) in scores.items():
        for fid, s in ((f1["id"], s1), (f2["id"], s2)):
            r = client.put(f"{url}/scores", json={"entity_id": ents[name], "factor_id": fid, "score": s}, headers=admin)
            assert r.status_code == 200, r.text
            if first:
                assert r.json()["status"] == "In progress"
                assert client.put(f"{url}/priorities", json={"entity_ids": [ents[name]]},
                                  headers=admin).status_code == 409  # conclude needs every cell scored
                first = False
    assert client.put(f"{url}/scores", json={"entity_id": ents[f"HQ {tag}"], "factor_id": f1["id"], "score": 4},
                      headers=admin).status_code == 422  # beyond the 3-level scale
    full = client.get(url).json()
    rows = {r["name"]: r for r in full["rows"]}
    assert rows[f"Finance {tag}"]["overall"] == 3 and rows[f"Finance {tag}"]["rating"] == "High"
    assert rows[f"Marine {tag}"]["overall"] == 2.5 and rows[f"Marine {tag}"]["rating"] == "High"
    assert rows[f"HQ {tag}"]["rating"] == "Low"

    # Conclude: prioritise, note, conclusion, mark completed.
    pr = client.put(f"{url}/priorities", json={"entity_ids": [ents[f"Finance {tag}"], ents[f"Marine {tag}"]]},
                    headers=admin).json()
    assert {r["name"]: r["priority"] for r in pr["rows"]}[f"Finance {tag}"] == 1
    client.put(f"{url}/notes/{ents[f'Finance {tag}']}", json={"note": "Cash banking delays"}, headers=admin)
    client.put(f"{url}/conclusion", json={"conclusion": "Finance and Marine carry the highest risk."}, headers=admin)
    done = client.post(f"{url}/complete", headers=admin).json()
    assert done["status"] == "Completed"
    assert client.put(f"{url}/conclusion", json={"conclusion": "x"}, headers=admin).status_code == 409
    ent = client.get(f"/api/auditable-entities/{ents[f'Finance {tag}']}").json()
    assert ent["rating"] == "High" and ent["effective_rating"] == "High" and ent["frequency"] == "Every year"
    hist = client.get(f"/api/auditable-entities/{ents[f'Finance {tag}']}/assessments").json()
    assert hist[0]["priority"] == 1 and hist[0]["rating"] == "High"

    # Start planning: a new draft plan with an engagement for each prioritised entity.
    used = {p["fiscal_year"] for p in client.get("/api/assurance-plans").json()}
    free = [y for y in range(2036, 2023, -1) if y not in used]
    if not free:
        pytest.skip("no free plan year in the test database")
    plan = client.post(f"{url}/start-planning", json={"fiscal_year": free[0]}, headers=admin)
    assert plan.status_code == 200, plan.text
    plan = plan.json()
    assert plan["added"] == 2
    detail = client.get(f"/api/assurance-plans/{plan['plan_id']}").json()
    assert sorted(e["entity_unit_id"] for e in detail["engagements"]) == sorted(
        [ents[f"Finance {tag}"], ents[f"Marine {tag}"]])
    assert client.post(f"{url}/revert", headers=admin).status_code == 409  # feeds a plan: stays completed
    again = client.post(f"{url}/start-planning", json={"plan_id": plan["plan_id"]}, headers=admin).json()
    assert again["added"] == 0  # no duplicates


def _xlsx(headers, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_bulk_add_org_units_and_processes(client, admin, db):
    tag = uuid.uuid4().hex[:5]
    data = _xlsx(["Name", "Type", "Parent", "Address"],
                 [[f"Takoradi {tag}", "Port", "", ""], [f"Takoradi Stores {tag}", "Department", f"Takoradi {tag}", ""]])
    files = {"file": ("o.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    pre = client.post("/api/import/orgunits", files=files, headers=admin).json()
    assert pre["to_create"] == 2 and not pre["errors"] and not pre["committed"]
    files = {"file": ("o.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    assert client.post("/api/import/orgunits?commit=true", files=files, headers=admin).json()["committed"]
    rows = {r["name"]: r for r in client.get("/api/org-structure").json()["items"]}
    assert rows[f"Takoradi Stores {tag}"]["parent_id"] == rows[f"Takoradi {tag}"]["id"]
    pdata = _xlsx(["Process", "Description", "Parent process", "Owner email", "Org units"],
                  [[f"Stores issues {tag}", "", "", "", f"Takoradi Stores {tag}"],
                   [f"Bad {tag}", "", "", "", "Nowhere"]])
    files = {"file": ("p.xlsx", pdata, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    res = client.post("/api/import/processes?commit=true", files=files, headers=admin).json()
    assert not res["committed"] and res["errors"][0]["field"] == "Org units"
