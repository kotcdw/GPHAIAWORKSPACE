"""Port / engagement-team scope for audit staff (blueprint Module 1) and engagement teams."""

from __future__ import annotations

import io
import uuid

import pytest

from app.core.enums import ReviewLevel, Role
from app.platform.organizations.models import Organization
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor, workplace=None, level=None):
    user = make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)
    user.work_entity_id = workplace
    if level:
        user.job_role, user.review_level = "manager", level
    db.commit()
    return user


def _org(db, name, category, parent=None):
    o = Organization(org_ref=f"T{uuid.uuid4().hex[:8]}", name=name, category=category, parent_id=parent)
    db.add(o)
    db.commit()
    return o


@pytest.fixture
def scoped(client2, db):
    """Switch port/team scope on for the test (the suite default is off for older tests)."""
    root = _u(db, "scroot", Role.Admin)
    h = csrf_headers(login(client2, root.username))
    assert client2.put("/api/config", json={"values": {"port_scope_enforced": True}}, headers=h).status_code == 200
    yield client2, h
    client2.post("/api/config/port_scope_enforced/reset", headers=h)


def test_port_staff_see_their_port_and_their_teams_only(client, scoped, db):
    admin_client, ah = scoped
    tag = uuid.uuid4().hex[:6]
    tema = _org(db, f"Tema {tag}", "Port")
    tako = _org(db, f"Takoradi {tag}", "Port")
    hq = _org(db, f"HQ {tag}", "Head Office")
    tema_fin = _org(db, f"Tema Finance {tag}", "Department", parent=tema.id)
    tema_aud = _u(db, "tema", workplace=tema_fin.id)
    tako_aud = _u(db, "tako", workplace=tako.id)
    hq_aud = _u(db, "hq", workplace=hq.id)
    gm = _u(db, "gm", level=ReviewLevel.CAE)
    nowhere = _u(db, "nowp")

    # Each port auditor creates an audit at their port (the creator leads its team).
    th = csrf_headers(login(client, tema_aud.username))
    a_tema = client.post("/api/audits", json={"title": f"Tema tolls {tag}", "scope": "x"}, headers=th).json()
    assert a_tema["port_entity_id"] == tema.id
    finding = client.post(f"/api/audits/{a_tema['id']}/findings",
                          json={"title": "Receipts not banked", "description": "d", "risk_rating": "Medium"},
                          headers=th).json()
    wp = client.post(f"/api/audits/{a_tema['id']}/working-papers", data={"title": "Cash count"},
                     files={"file": ("c.txt", io.BytesIO(b"count"), "text/plain")}, headers=th).json()
    team = client.get(f"/api/audits/{a_tema['id']}/team").json()
    assert [(t["user_id"], t["team_role"]) for t in team] == [(tema_aud.id, "Lead auditor")]

    def sees(user, audit_id) -> bool:
        login(client, user.username)
        reg = client.get(f"/api/audits/register?q={tag}").json()
        return audit_id in {r["id"] for r in reg["items"]}

    # Takoradi staff and staff without a workplace cannot see, open, or change the Tema audit.
    for outsider in (tako_aud, nowhere):
        assert not sees(outsider, a_tema["id"])
        h = csrf_headers(login(client, outsider.username))
        assert client.get(f"/api/audits/{a_tema['id']}").status_code == 404
        assert client.get(f"/api/findings/{finding['id']}").status_code == 404
        assert client.get(f"/api/working-papers/{wp['id']}/template").status_code == 404
        assert client.patch(f"/api/findings/{finding['id']}", json={"title": "hijack"}, headers=h).status_code == 404
        new = {"title": "x", "description": "x", "risk_rating": "Low"}
        assert client.post(f"/api/audits/{a_tema['id']}/findings", json=new, headers=h).status_code == 404
        assert all(r["id"] != a_tema["id"] for r in client.get("/api/audits").json())
        hits = client.get(f"/api/search?q=Tema%20tolls%20{tag}").json()
        assert not any(x["type"] == "audit" and x["id"] == a_tema["id"] for x in hits)

    # HQ staff, the GM Audit and administrators see every port.
    assert sees(hq_aud, a_tema["id"]) and sees(gm, a_tema["id"])
    assert a_tema["id"] in {r["id"] for r in admin_client.get(f"/api/audits/register?q={tag}").json()["items"]}

    # Adding the Takoradi auditor to the team opens the audit to them (and only them).
    login(client, tema_aud.username)
    th = csrf_headers(login(client, tema_aud.username))
    res = client.post(f"/api/audits/{a_tema['id']}/team", json={"user_id": tako_aud.id, "team_role": "Reviewer"},
                      headers=th)
    assert res.status_code == 200, res.text
    assert sees(tako_aud, a_tema["id"]) and not sees(nowhere, a_tema["id"])
    # One lead: making someone else lead demotes the old lead; the lead cannot be removed.
    th = csrf_headers(login(client, tema_aud.username))
    client.post(f"/api/audits/{a_tema['id']}/team", json={"user_id": tako_aud.id, "team_role": "Lead auditor"},
                headers=th)
    roles = {t["user_id"]: t["team_role"] for t in client.get(f"/api/audits/{a_tema['id']}/team").json()}
    assert roles == {tema_aud.id: "Auditor", tako_aud.id: "Lead auditor"}
    assert client.delete(f"/api/audits/{a_tema['id']}/team/{tako_aud.id}", headers=th).status_code == 409
    assert client.post(f"/api/audits/{a_tema['id']}/team", json={"user_id": tako_aud.id, "team_role": "Boss"},
                       headers=th).status_code == 422
    # The register shows the team lead.
    row = next(r for r in client.get(f"/api/audits/register?q={tag}").json()["items"] if r["id"] == a_tema["id"])
    assert row["lead"] == tako_aud.full_name


def test_scope_switched_off_lets_all_staff_work_on_any_audit(client, client2, db):
    # With scope off (suite default) a staff member without workplace sees every audit.
    owner = _u(db, "offown")
    other = _u(db, "offoth")
    h = csrf_headers(login(client, owner.username))
    a = client.post("/api/audits", json={"title": "Scope off check", "scope": "x"}, headers=h).json()
    login(client2, other.username)
    assert client2.get(f"/api/audits/{a['id']}").status_code == 200
