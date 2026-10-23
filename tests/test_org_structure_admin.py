"""Administration phase 3: organisational structure. Unit heads, deactivation instead of deletion, the unit
overview, workplaces that point at deactivated units, and the summary on the Administration page."""

from __future__ import annotations

import uuid

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, job=None):
    from app.core import permissions as perms

    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    if job:
        r = perms.JOB_ROLES_BY_CODE[job]
        user.job_role, user.role, user.review_level = r.code, r.tier, r.review_level
    db.commit()
    return user


def _unit(client, h, name, category="Department", parent_id=None):
    r = client.post("/api/organizations", json={"name": f"{name} {uuid.uuid4().hex[:5]}", "category": category,
                                                "parent_id": parent_id}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_unit_head_needs_reference_permission_and_an_active_account(client, db):
    admin = _u(db, "os_adm", Role.Admin, job="admin")
    head = _u(db, "os_head", Role.Auditee, job="audit_client")
    gone = _u(db, "os_gone")
    gone.is_active = False
    db.commit()
    h = csrf_headers(login(client, admin.username))
    dept = _unit(client, h, "Finance")
    r = client.patch(f"/api/organizations/{dept['id']}", json={"head_user_id": gone.id}, headers=h)
    assert r.status_code == 422
    r = client.patch(f"/api/organizations/{dept['id']}", json={"head_user_id": head.id}, headers=h)
    assert r.status_code == 200 and r.json()["head_name"] == head.full_name
    assert any(p["id"] == head.id for p in client.get("/api/organizations/people").json())
    # An auditor may maintain units through the module but not name heads (reference data).
    aud = _u(db, "os_aud", job="auditor")
    h2 = csrf_headers(login(client, aud.username))
    assert client.patch(f"/api/organizations/{dept['id']}", json={"head_user_id": None}, headers=h2).status_code == 403
    assert client.get("/api/organizations/people").status_code == 403


def test_deactivate_and_reactivate_rules(client, db):
    admin = _u(db, "os_adm2", Role.Admin, job="admin")
    h = csrf_headers(login(client, admin.username))
    dept = _unit(client, h, "Operations")
    unit = _unit(client, h, "Marine", "Unit", dept["id"])
    # The unit under it is still active.
    merged = {"reason": "Merged into Engineering"}
    r = client.post(f"/api/organizations/{dept['id']}/deactivate", json=merged, headers=h)
    assert r.status_code == 409 and "active unit" in r.json()["detail"]
    assert client.post(f"/api/organizations/{unit['id']}/deactivate", json={"reason": ""}, headers=h).status_code == 422
    assert client.post(f"/api/organizations/{unit['id']}/deactivate", json={"reason": "Section closed"},
                       headers=h).status_code == 200
    r = client.post(f"/api/organizations/{dept['id']}/deactivate", json=merged, headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is False and r.json()["deactivation_reason"]
    # Out of the tree unless asked for; refused as a parent for new units.
    ids = {x["id"] for x in client.get("/api/org-structure").json()["items"]}
    assert dept["id"] not in ids and unit["id"] not in ids
    tree = client.get("/api/org-structure?include_inactive=true").json()
    assert {dept["id"], unit["id"]} <= {x["id"] for x in tree["items"]} and tree["inactive_count"] >= 2
    r = client.post("/api/organizations", json={"name": "New section", "category": "Unit", "parent_id": dept["id"]},
                    headers=h)
    assert r.status_code == 422 and "deactivated" in r.text
    # Reactivate the child first: refused while its parent is deactivated.
    r = client.post(f"/api/organizations/{unit['id']}/reactivate", headers=h)
    assert r.status_code == 409 and "Reactivate" in r.json()["detail"]
    assert client.post(f"/api/organizations/{dept['id']}/reactivate", headers=h).status_code == 200
    assert client.post(f"/api/organizations/{unit['id']}/reactivate", headers=h).json()["is_active"] is True
    hist = client.get(f"/api/organizations/{dept['id']}/overview").json()["history"]
    assert [x["action"] for x in hist][:2] == ["REACTIVATED", "DEACTIVATED: Merged into Engineering"]


def test_overview_and_workplaces(client, db):
    admin = _u(db, "os_adm3", Role.Admin, job="admin")
    h = csrf_headers(login(client, admin.username))
    dept = _unit(client, h, "Revenue")
    unit = _unit(client, h, "Billing", "Unit", dept["id"])
    staff = _u(db, "os_staff")
    lower = _u(db, "os_low")
    staff.work_entity_id, lower.work_entity_id = dept["id"], unit["id"]
    db.commit()
    ov = client.get(f"/api/organizations/{dept['id']}/overview").json()
    assert [p["id"] for p in ov["people"]] == [staff.id] and ov["people_below"] == 1
    assert [c["id"] for c in ov["children"]] == [unit["id"]]
    assert ov["can"]["administer"] and not ov["can"]["delete"]  # it has a sub-unit and people
    # A unit people work in cannot be deleted.
    r = client.delete(f"/api/organizations/{unit['id']}", headers=h)
    assert r.status_code == 409 and "workplace" in r.json()["detail"]
    # Deactivate the unit: its people stay placed there (flagged), but nobody new can choose it.
    client.post(f"/api/organizations/{unit['id']}/deactivate", json={"reason": "Billing moved to Finance"}, headers=h)
    other = _u(db, "os_other")
    r = client.patch(f"/api/users/{other.id}", json={"work_entity_id": unit["id"]}, headers=h)
    assert r.status_code == 422 and "deactivated" in r.text
    h3 = csrf_headers(login(client, other.username))
    assert client.patch("/api/auth/me", json={"work_entity_id": unit["id"]}, headers=h3).status_code == 422
    # Saving your profile with the deactivated unit you already have is fine.
    h4 = csrf_headers(login(client, lower.username))
    assert client.patch("/api/auth/me", json={"work_entity_id": unit["id"]}, headers=h4).status_code == 200
    login(client, admin.username)
    found = client.get(f"/api/users/search?workplace=inactive&q={lower.username}").json()["items"]
    assert [x["id"] for x in found] == [lower.id] and found[0]["workplace_active"] is False
    nobody = client.get(f"/api/users/search?workplace=none&q={other.username}").json()["items"]
    assert [x["id"] for x in nobody] == [other.id] and nobody[0]["workplace"] is None
    org = client.get("/api/admin/overview").json()["org"]
    assert org["people_at_inactive_unit"] >= 1 and org["people_without_workplace"] >= 1 and org["inactive"] >= 1
    assert client.get(f"/api/users/{lower.id}/access").json()["workplace"]["is_active"] is False


def test_deactivated_ports_and_process_links(client, db):
    admin = _u(db, "os_adm4", Role.Admin, job="admin")
    h = csrf_headers(login(client, admin.username))
    port = _unit(client, h, "Port of Keta", "Port")
    unit = _unit(client, h, "Keta stores", "Unit", port["id"])
    proc = client.post("/api/processes", json={"name": f"Stores {uuid.uuid4().hex[:4]}", "org_ids": [unit["id"]]},
                       headers=h)
    assert proc.status_code in (200, 201), proc.text
    mgr = _u(db, "os_mgr", job="manager")
    hm = csrf_headers(login(client, mgr.username))
    audit = client.post("/api/audits", json={"title": "Keta stores review", "scope": "Stock",
                                             "port_entity_id": port["id"]}, headers=hm)
    h = csrf_headers(login(client, admin.username))
    assert audit.status_code in (200, 201), audit.text
    client.post(f"/api/organizations/{unit['id']}/deactivate", json={"reason": "Stores closed"}, headers=h)
    client.post(f"/api/organizations/{port['id']}/deactivate", json={"reason": "Port handed over"}, headers=h)
    # An existing process link to the deactivated unit can stay; a new audit cannot name the port.
    pid = proc.json()["id"]
    r = client.patch(f"/api/processes/{pid}", json={"org_ids": [unit["id"]], "description": "kept"}, headers=h)
    assert r.status_code == 200, r.text
    hm = csrf_headers(login(client, mgr.username))
    r = client.post("/api/audits", json={"title": "New audit", "scope": "x", "port_entity_id": port["id"]}, headers=hm)
    assert r.status_code == 422 and "deactivated" in r.text
    # The audit that already names it keeps it when edited.
    aid = audit.json()["id"]
    r = client.patch(f"/api/audits/{aid}", json={"title": "Keta stores review (final)", "port_entity_id": port["id"]},
                     headers=hm)
    assert r.status_code == 200, r.text
    login(client, admin.username)
    ov = client.get(f"/api/organizations/{port['id']}/overview").json()
    assert ov["audit_total"] == 1 and ov["audits"][0]["id"] == aid


def test_register_import_and_distribution_leave_out_deactivated_units(client, db):
    from app.domains.assurance.plancycle.router import sites
    from tests.test_integrated_universe import _xlsx

    admin = _u(db, "os_adm5", Role.Admin, job="admin")
    h = csrf_headers(login(client, admin.username))
    port = _unit(client, h, "Port of Ada", "Port")
    child = _unit(client, h, "Ada wharf", "Unit", port["id"])
    client.post(f"/api/organizations/{child['id']}/deactivate", json={"reason": "Wharf closed"}, headers=h)
    client.post(f"/api/organizations/{port['id']}/deactivate", json={"reason": "Port handed over"}, headers=h)
    # Register filter and status.
    gone = client.get("/api/organizations?active=false").json()["items"]
    assert {port["id"], child["id"]} <= {o["id"] for o in gone} and all(not o["is_active"] for o in gone)
    assert port["id"] not in {o["id"] for o in client.get("/api/organizations?active=true").json()["items"]}
    # A form that resends the unchanged (deactivated) parent can still save other fields.
    r = client.patch(f"/api/organizations/{child['id']}", json={"name": "Ada wharf (old)", "parent_id": port["id"]},
                     headers=h)
    assert r.status_code == 200, r.text
    # Plan distribution no longer lists it.
    db.expire_all()
    assert port["id"] not in {s["id"] for s in sites(db)}
    # Bulk import: a deactivated parent, or updating a deactivated unit, is refused in the preview.
    data = _xlsx(["Name", "Type", "Parent", "Address"],
                 [[f"Ada new unit {uuid.uuid4().hex[:4]}", "Unit", port["name"], ""], [port["name"], "Port", "", ""]])
    files = {"file": ("o.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    res = client.post("/api/import/orgunits?commit=true", files=files, headers=h).json()
    assert not res["committed"] and {e["field"] for e in res["errors"]} == {"Parent", "Name"}



def test_review_fixes_scope_copy_audit_unit_and_role_signout(client, client2, db):
    root = _u(db, "os_root", Role.Admin, job="super_admin")
    h = csrf_headers(login(client2, root.username))
    port = _unit(client2, h, "Port of Elmina", "Port")
    dept = _unit(client2, h, "Elmina finance", "Department", port["id"])
    gone = _unit(client2, h, "Elmina old desk", "Unit", dept["id"])
    mgr = _u(db, "os_mgr2", job="manager")
    mgr.work_entity_id = port["id"]
    db.commit()
    hm = csrf_headers(login(client, mgr.username))
    assert client.post("/api/audits", json={"title": "Elmina cash", "scope": "x"}, headers=hm).status_code in (200, 201)
    # The deactivated unit cannot be an audit's organisation.
    client2.post(f"/api/organizations/{gone['id']}/deactivate", json={"reason": "Desk closed"}, headers=h)
    r = client.post("/api/audits", json={"title": "Old desk", "scope": "x", "organization_id": gone["id"]}, headers=hm)
    assert r.status_code == 422 and "deactivated" in r.text
    # Copying a unit never places an active copy under a deactivated one.
    child = _unit(client2, h, "Elmina till", "Unit", dept["id"])
    client2.post(f"/api/organizations/{child['id']}/deactivate", json={"reason": "Till closed"}, headers=h)
    client2.post(f"/api/organizations/{dept['id']}/deactivate", json={"reason": "Merged into HQ"}, headers=h)
    assert client2.post(f"/api/organizations/{child['id']}/copy", headers=h).status_code == 422
    # Port scope: an auditor based elsewhere does not see Elmina's audits in the unit panel.
    assert client2.put("/api/config", json={"values": {"port_scope_enforced": True}}, headers=h).status_code == 200
    try:
        aud = _u(db, "os_aud2", job="auditor")
        login(client, aud.username)
        ov = client.get(f"/api/organizations/{port['id']}/overview").json()
        assert ov["audit_total"] == 0 and ov["audits"] == []
        login(client, mgr.username)
        assert client.get(f"/api/organizations/{port['id']}/overview").json()["audit_total"] == 1
    finally:
        client2.post("/api/config/port_scope_enforced/reset", headers=h)
    # Any change of role signs the person out (Auditor -> Read-only User keeps the same access tier).
    person = _u(db, "os_person", job="auditor")
    login(client, person.username)
    r = client2.patch(f"/api/users/{person.id}/job-role", json={"job_role": "read_only"}, headers=h)
    assert r.status_code == 200 and r.json()["sessions_ended"] >= 1
    assert client.get("/api/auth/me").status_code == 401


def test_super_administrator_deletes_approved_units_and_sub_units(client, client2, db):
    from tests.conftest import DEFAULT_PASSWORD

    sa = _u(db, "os_sa", Role.Admin, job="super_admin")
    admin = _u(db, "os_adm9", Role.Admin, job="admin")
    h = csrf_headers(login(client, sa.username))
    dept = _unit(client, h, "Marine")
    sub = _unit(client, h, "Pilotage", "Unit", dept["id"])
    ah = csrf_headers(login(client2, admin.username))
    client2.post(f"/api/organizations/{dept['id']}/approve", json={"password": DEFAULT_PASSWORD}, headers=ah)

    # An administrator cannot delete an approved unit; the Super Administrator sees what it would take.
    assert client2.delete(f"/api/organizations/{dept['id']}", headers=ah).status_code == 409
    ov = client.get(f"/api/organizations/{dept['id']}/overview").json()
    assert ov["can"]["superdelete"] and ov["delete_check"]["subunits"] == 1
    assert ov["delete_check"]["blockers"] and not ov["delete_check"]["with_subunits_blockers"]

    url = f"/api/organizations/{dept['id']}"
    body = {"reason": "Merged into Marine Services", "password": DEFAULT_PASSWORD}
    assert client.request("DELETE", url, json=body, headers=h).status_code == 409  # the sub-unit
    assert client.request("DELETE", url, json={**body, "reason": "x", "with_subunits": True},
                          headers=h).status_code == 422
    assert client.request("DELETE", url, json={**body, "with_subunits": True, "password": "wrong"},
                          headers=h).status_code == 400
    # Someone working in the sub-unit blocks it until they are moved.
    staff = _u(db, "os_wk")
    staff.work_entity_id = sub["id"]
    db.commit()
    r = client.request("DELETE", url, json={**body, "with_subunits": True}, headers=h)
    assert r.status_code == 409 and "workplace" in r.json()["detail"]
    staff.work_entity_id = None
    db.commit()
    r = client.request("DELETE", url, json={**body, "with_subunits": True}, headers=h)
    assert r.status_code == 200, r.text
    assert client.get(url).status_code == 404 and client.get(f"/api/organizations/{sub['id']}").status_code == 404


def test_new_type_typed_in_the_unit_form_joins_the_configured_types(client, client2, db):
    from app.core.appconfig import cfg

    admin = _u(db, "os_typ", Role.Admin, job="admin")
    h = csrf_headers(login(client, admin.username))
    name = f"Terminal {uuid.uuid4().hex[:4]}"
    try:
        r = client.post("/api/organizations", json={"name": f"GJT {uuid.uuid4().hex[:4]}", "category": f"  {name} "},
                        headers=h)
        assert r.status_code == 201, r.text
        assert r.json()["category"] == name
        assert name in cfg("organization_categories") and name in cfg("org_structure_categories")
        assert name in client.get("/api/org-structure").json()["types"]
        # Someone without reference-data rights picks from the list only.
        staff = _u(db, "os_typ2")
        sh = csrf_headers(login(client2, staff.username))
        bad = client2.post("/api/organizations", json={"name": "X unit", "category": "Made-up type"}, headers=sh)
        assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "category"
    finally:
        client.post("/api/config/organization_categories/reset", headers=h)
        client.post("/api/config/org_structure_categories/reset", headers=h)
