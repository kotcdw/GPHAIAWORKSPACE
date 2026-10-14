"""Configurable entities: types, hierarchy and ports, custom fields, the user's workplace."""

from __future__ import annotations

import uuid

from app.core import appconfig
from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role):
    return make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)


def test_entity_hierarchy_ports_and_filters(client, client2, db):
    auditor = _u(db, "enaud", Role.Auditor)
    h = csrf_headers(login(client, auditor.username))
    tag = uuid.uuid4().hex[:5]
    bad = client.post("/api/organizations", json={"name": f"X {tag}", "category": "Spaceport"}, headers=h)
    assert bad.status_code == 422 and bad.json()["errors"][0]["field"] == "category"

    tema = client.post("/api/organizations", json={"name": f"Tema Port {tag}", "category": "port",
                                                   "address": "Harbour Road, Tema"}, headers=h).json()
    assert tema["category"] == "Port" and tema["is_port"] and tema["port_id"] == tema["id"]
    fin = client.post("/api/organizations", json={"name": f"Finance {tag}", "category": "Department",
                                                  "parent_id": tema["id"]}, headers=h).json()
    unit = client.post("/api/organizations", json={"name": f"Billing {tag}", "category": "Unit",
                                                   "parent_id": fin["id"]}, headers=h).json()
    assert unit["port_id"] == tema["id"] and unit["port_name"] == f"Tema Port {tag}"
    assert unit["parent_name"] == f"Finance {tag}"
    tko = client.post("/api/organizations", json={"name": f"Takoradi Port {tag}", "category": "Port"},
                      headers=h).json()

    # Loops and self-parenting are refused; clearing the parent works.
    loop = client.patch(f"/api/organizations/{fin['id']}", json={"parent_id": unit["id"]}, headers=h)
    assert loop.status_code == 422 and "loop" in loop.json()["errors"][0]["message"]
    assert client.patch(f"/api/organizations/{fin['id']}", json={"parent_id": fin["id"]}, headers=h).status_code == 422

    in_tema = client.get(f"/api/organizations?port_id={tema['id']}&q={tag}").json()
    assert {o["id"] for o in in_tema["items"]} == {tema["id"], fin["id"], unit["id"]}
    units = client.get(f"/api/organizations?category=Unit&q={tag}").json()
    assert [o["id"] for o in units["items"]] == [unit["id"]]
    tema_full = client.get(f"/api/organizations/{tema['id']}").json()
    assert tema_full["children"] == 1

    # Where I work -> "mine" filter.
    me = client.patch("/api/auth/me", json={"work_entity_id": unit["id"]}, headers=h)
    assert me.status_code == 200 and me.json()["user"]["work_entity_id"] == unit["id"]
    mine = client.get(f"/api/organizations?mine=true&q={tag}").json()
    assert tko["id"] not in {o["id"] for o in mine["items"]} and unit["id"] in {o["id"] for o in mine["items"]}
    assert client.patch("/api/auth/me", json={"work_entity_id": 999999}, headers=h).status_code == 422

    # Auditees cannot read the register but can pick where they work.
    ee = _u(db, "enee", Role.Auditee)
    eh = csrf_headers(login(client2, ee.username))
    picks = client2.get("/api/organizations/entities").json()
    assert any(p["id"] == tema["id"] and p["is_port"] for p in picks)
    assert "contact_email" not in picks[0]
    assert client2.patch("/api/auth/me", json={"work_entity_id": tko["id"]}, headers=eh).status_code == 200

    # Cannot delete an entity that has entities under it.
    admin = _u(db, "enadm", Role.Admin)
    ah = csrf_headers(login(client2, admin.username))
    assert client2.delete(f"/api/organizations/{fin['id']}", headers=ah).status_code == 409


def test_entity_types_and_custom_fields(client, client2, db):
    admin = _u(db, "cfadm", Role.Admin)
    auditor = _u(db, "cfaud", Role.Auditor)
    ah = csrf_headers(login(client, admin.username))
    h = csrf_headers(login(client2, auditor.username))
    try:
        bad = client.put("/api/config", json={"values": {"port_categories": ["Harbour"]}}, headers=ah)
        assert bad.status_code == 422
        ok = client.put("/api/config", json={"values": {
            "organization_categories": "Port\nHarbour\nDepartment\nVendor / Supplier",
            "port_categories": ["Port", "Harbour"]}}, headers=ah)
        assert ok.status_code == 200, ok.text
        h_ent = client2.post("/api/organizations", json={"name": "Fishing Harbour", "category": "Harbour"},
                             headers=h).json()
        assert h_ent["is_port"]

        # Admin-only field definitions.
        assert client2.post("/api/custom-fields", json={"module": "organizations", "label": "TIN"},
                            headers=h).status_code == 403
        assert client.post("/api/custom-fields", json={"module": "organizations", "label": "Tier",
                                                       "field_type": "select", "options": ["A"]},
                           headers=ah).status_code == 422
        tin = client.post("/api/custom-fields", json={"module": "organizations", "label": "Tax ID (TIN)",
                                                      "required": True}, headers=ah).json()
        tier = client.post("/api/custom-fields", json={"module": "organizations", "label": "Risk tier",
                                                       "field_type": "select", "options": ["A", "B", "C"]},
                           headers=ah).json()
        staff = client.post("/api/custom-fields", json={"module": "organizations", "label": "Staff count",
                                                        "field_type": "number"}, headers=ah).json()
        assert tin["key"] == "tax_id_tin"
        defs = client2.get("/api/custom-fields?module=organizations").json()
        assert [d["key"] for d in defs][:3] == ["tax_id_tin", "risk_tier", "staff_count"]

        missing = client2.post("/api/organizations", json={"name": "Acme"}, headers=h)
        assert missing.status_code == 422 and missing.json()["errors"][0]["field"] == "cf_tax_id_tin"
        wrong = client2.post("/api/organizations", json={"name": "Acme", "custom_fields": {
            "tax_id_tin": "C0001", "risk_tier": "Z", "staff_count": "many", "nope": 1}}, headers=h)
        assert {e["field"] for e in wrong.json()["errors"]} == {"cf_risk_tier", "cf_staff_count", "cf_nope"}
        good = client2.post("/api/organizations", json={"name": "Acme", "category": "Vendor / Supplier",
                                                        "custom_fields": {"tax_id_tin": "C0001", "risk_tier": "B",
                                                                          "staff_count": "40"}}, headers=h).json()
        assert good["custom_fields"] == {"tax_id_tin": "C0001", "risk_tier": "B", "staff_count": 40}
        upd = client2.patch(f"/api/organizations/{good['id']}", json={"custom_fields": {"risk_tier": "A"}},
                            headers=h).json()
        assert upd["custom_fields"]["risk_tier"] == "A" and upd["custom_fields"]["tax_id_tin"] == "C0001"

        # Retiring a field keeps stored values but stops asking for it.
        client.patch(f"/api/custom-fields/{tin['id']}", json={"active": False}, headers=ah)
        assert client2.post("/api/organizations", json={"name": "Beta"}, headers=h).status_code == 201
        for f in (tier, staff):
            client.patch(f"/api/custom-fields/{f['id']}", json={"active": False}, headers=ah)
    finally:
        client.post("/api/config/organization_categories/reset", headers=ah)
        client.post("/api/config/port_categories/reset", headers=ah)
        appconfig.invalidate()
