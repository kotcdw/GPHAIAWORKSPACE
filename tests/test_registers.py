"""Server-side registers: paging, sorting, search, filters and authorization before paging."""

from __future__ import annotations

import uuid

from app.core.enums import Role
from tests.conftest import csrf_headers, login, make_user


def _u(db, prefix, role=Role.Auditor):
    return make_user(db, f"{prefix}_{uuid.uuid4().hex[:6]}", role)


def test_audit_register_pages_sorts_searches_and_filters(client, db):
    aud = _u(db, "regaud")
    h = csrf_headers(login(client, aud.username))
    tag = uuid.uuid4().hex[:6]
    ids = [client.post("/api/audits", json={"title": f"Register {tag} {n}", "scope": "x"}, headers=h).json()["id"]
           for n in range(5)]

    page1 = client.get(f"/api/audits/register?q={tag}&page_size=2&sort=ref")
    assert page1.status_code == 200, page1.text
    body = page1.json()
    assert body["total"] == 5 and body["page_size"] == 2 and body["sort"] == "ref"
    assert [r["id"] for r in body["items"]] == ids[:2]
    assert body["items"][0]["ref"] == f"AUD-{ids[0]:04d}"
    page3 = client.get(f"/api/audits/register?q={tag}&page_size=2&page=3&sort=ref").json()
    assert [r["id"] for r in page3["items"]] == ids[4:]
    desc = client.get(f"/api/audits/register?q={tag}&sort=-ref").json()
    assert [r["id"] for r in desc["items"]] == list(reversed(ids))

    client.patch(f"/api/audits/{ids[0]}", json={"status": "In Progress"}, headers=h)
    only = client.get(f"/api/audits/register?q={tag}&status=In%20Progress").json()
    assert [r["id"] for r in only["items"]] == [ids[0]]
    for key in ("title", "status", "port", "lead", "updated_at", "open_findings"):
        assert client.get(f"/api/audits/register?sort={key}").status_code == 200

    # Bad parameters are refused, not ignored.
    assert client.get("/api/audits/register?sort=password_hash").status_code == 422
    assert client.get("/api/audits/register?page_size=500").status_code == 422
    assert client.get("/api/audits/register?page=0").status_code == 422


def test_audit_register_only_counts_what_the_user_may_read(client, client2, db):
    aud = _u(db, "regown")
    ee = _u(db, "regee", Role.Auditee)
    h = csrf_headers(login(client, aud.username))
    tag = uuid.uuid4().hex[:6]
    seen = client.post("/api/audits", json={"title": f"Visible {tag}", "scope": "x"}, headers=h).json()
    client.post("/api/audits", json={"title": f"Hidden {tag}", "scope": "x"}, headers=h)
    client.post(f"/api/audits/{seen['id']}/auditees", json={"user_id": ee.id}, headers=h)

    login(client2, ee.username)
    res = client2.get(f"/api/audits/register?q={tag}").json()
    assert res["total"] == 1 and [r["id"] for r in res["items"]] == [seen["id"]]


def test_audit_log_register_is_admin_only_and_filtered(client, client2, db):
    admin = _u(db, "regadm", Role.Admin)
    aud = _u(db, "regnot")
    login(client, admin.username)
    login(client2, aud.username)
    assert client2.get("/api/audit-logs/register").status_code == 403

    res = client.get("/api/audit-logs/register?page_size=5")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["page_size"] == 5 and len(body["items"]) <= 5 and body["total"] >= len(body["items"])
    stamps = [r["timestamp"] for r in body["items"]]
    assert stamps == sorted(stamps, reverse=True)
    mine = client.get(f"/api/audit-logs/register?user_id={admin.id}&q=login").json()
    assert mine["total"] >= 1 and all(r["user_id"] == admin.id for r in mine["items"])
    assert all(r["user"] for r in mine["items"])
    assert client.get("/api/audit-logs/register?sort=-timestamp&date_from=2999-01-01").json()["total"] == 0
    assert client.get("/api/audit-logs/register?sort=action").status_code == 422
