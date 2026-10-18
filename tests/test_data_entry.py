"""Data entry: autosaved drafts, field-level validation errors and accuracy rules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_entity, make_user


def _user(client, db, role=Role.Auditor):
    name = f"de_{uuid.uuid4().hex[:8]}"
    make_user(db, name, role)
    return csrf_headers(login(client, name))


def _field(resp, name):
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["detail"].startswith("Please correct")
    return next((e["message"] for e in body["errors"] if e["field"] == name), None)


# ------------------------------------------------------------------ drafts


def test_drafts_are_private_and_never_store_passwords(client, client2, db):
    me = _user(client, db)
    other = _user(client2, db)
    saved = client.put(
        "/api/drafts/capa:new",
        json={"title": "New CAPA", "payload": {"title": "Half-typed", "owner_email": "not-an-email", "password": "x"}},
        headers=me,
    )
    assert saved.status_code == 200, saved.text
    expected = {"title": "Half-typed", "owner_email": "not-an-email"}
    assert saved.json()["payload"] == expected, "drafts keep invalid input"

    again = client.put("/api/drafts/capa:new", json={"payload": {"title": "More typed"}}, headers=me)
    assert again.json()["payload"]["title"] == "More typed"
    assert [d["form_key"] for d in client.get("/api/drafts").json()] == ["capa:new"]

    assert client2.get("/api/drafts/capa:new").status_code == 404
    assert client2.get("/api/drafts").json() == []
    assert other

    assert client.delete("/api/drafts/capa:new", headers=me).status_code == 200
    assert client.get("/api/drafts/capa:new").status_code == 404


def test_draft_key_and_size_limits(client, db):
    me = _user(client, db)
    assert client.put("/api/drafts/bad key!", json={"payload": {}}, headers=me).status_code in (400, 404)
    big = {"text": "x" * (300 * 1024)}
    assert client.put("/api/drafts/big", json={"payload": big}, headers=me).status_code == 413


# ------------------------------------------------------------------ field errors


def test_blank_and_multiline_titles_are_rejected_per_field(client, db):
    me = _user(client, db)
    assert _field(client.post("/api/capa", json={"title": "   "}, headers=me), "title") == "must not be empty"
    assert "single line" in _field(client.post("/api/audits", json={"title": "a\nb"}, headers=me), "title")


def test_email_date_and_whitespace_rules(client, db):
    me = _user(client, db)
    msg = _field(client.post("/api/capa", json={"title": "T", "owner_email": "bob@"}, headers=me), "owner_email")
    assert "valid e-mail" in msg
    past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    assert "today or a future" in _field(
        client.post("/api/capa", json={"title": "T", "due_date": past}, headers=me), "due_date"
    )
    ok = client.post(
        "/api/capa", json={"title": "  Trimmed  ", "owner_email": "  Owner@GPHA.local "}, headers=me
    ).json()
    assert ok["title"] == "Trimmed" and ok["owner_email"] == "owner@gpha.local"
    blank_email = client.post("/api/nonconformances", json={"title": "NC", "owner_email": ""}, headers=me).json()
    assert blank_email["owner_email"] is None


def test_fiscal_years_are_checked(client, db):
    admin = _user(client, db, Role.Admin)
    year = datetime.now(UTC).year
    assert "between" in _field(
        client.post("/api/assurance-plans", json={"fiscal_year": year + 50, "title": "x"}, headers=admin),
        "fiscal_year",
    )


def test_engagement_duplicates_and_inactive_units(client, db):
    admin = _user(client, db, Role.Admin)
    unit = make_entity(client, admin)
    plans = client.get("/api/assurance-plans").json()
    used = {p["fiscal_year"] for p in plans}
    year = next(y for y in range(datetime.now(UTC).year - 2, datetime.now(UTC).year + 11) if y not in used)
    plan = client.post("/api/assurance-plans", json={"fiscal_year": year, "title": "P"}, headers=admin).json()
    url = f"/api/assurance-plans/{plan['id']}/engagements"
    assert client.post(url, json={"title": "Cash", "entity_unit_id": unit["id"]}, headers=admin).status_code == 201
    dup = client.post(url, json={"title": " cash ", "entity_unit_id": unit["id"]}, headers=admin)
    assert dup.status_code == 409 and "already planned" in dup.json()["detail"]
    client.patch(f"/api/auditable-entities/{unit['id']}", json={"definition_status": "Retired"}, headers=admin)
    assert client.post(url, json={"title": "Other", "entity_unit_id": unit["id"]}, headers=admin).status_code == 400


def test_control_test_number_consistency(client, db):
    aud = _user(client, db)
    audit = client.post("/api/audits", json={"title": "Numbers"}, headers=aud).json()
    obj = client.post(f"/api/audits/{audit['id']}/objectives", json={"title": "O"}, headers=aud).json()
    ctl = client.post(f"/api/objectives/{obj['id']}/controls", json={"title": "C"}, headers=aud).json()
    test = client.post(f"/api/controls/{ctl['id']}/tests", json={"test_type": "Design"}, headers=aud).json()
    url = f"/api/control-tests/{test['id']}"
    too_big = client.patch(url, json={"population_size": 10, "sample_size": 12}, headers=aud)
    assert "population" in _field(too_big, "sample_size")
    too_many = client.patch(url, json={"population_size": 10, "sample_size": 5, "exceptions_found": 6}, headers=aud)
    assert "cannot exceed" in _field(too_many, "exceptions_found")
    fine = client.patch(url, json={"population_size": 10, "sample_size": 5, "exceptions_found": 1}, headers=aud)
    assert fine.status_code == 200


def test_health_reports_database(client):
    body = client.get("/health").json()
    assert body["can_save"] is True
    assert body["database"]["ok"] is True and body["database"]["up_to_date"] is True
    assert "url" not in body["database"]
