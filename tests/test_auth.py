"""Authentication and authorization tests."""

from __future__ import annotations

from sqlalchemy import select

from app.core.enums import Role
from app.platform.users.models import User
from tests.conftest import DEFAULT_PASSWORD, csrf_headers, login, make_user


def test_register_captures_freeqms_fields(client, db):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "grace",
            "password": "Passw0rd!",
            "email": "grace@example.com",
            "first_name": "Grace",
            "last_name": "Hopper",
            "company": "GPHA Ltd",
        },
    )
    assert response.status_code == 201, response.text

    db.rollback()  # see the row the request committed (REPEATABLE-READ snapshot)
    user = db.execute(select(User).where(User.username == "grace")).scalar_one()
    assert user.first_name == "Grace"
    assert user.last_name == "Hopper"
    assert user.company == "GPHA Ltd"
    assert user.full_name == "Grace Hopper"  # derived from first/last name


def test_admin_create_user_sets_profile_fields(client, db):
    make_user(db, "root", role=Role.Admin)
    csrf = login(client, "root")

    response = client.post(
        "/api/users",
        json={
            "username": "newbie",
            "password": "Passw0rd!",
            "email": "newbie@example.com",
            "first_name": "New",
            "last_name": "Bee",
            "company": "Acme",
            "role": "Auditor",
        },
        headers=csrf_headers(csrf),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["first_name"] == "New"
    assert body["last_name"] == "Bee"
    assert body["company"] == "Acme"
    assert body["full_name"] == "New Bee"


def test_register_creates_inactive_user(client, db):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "newauditor",
            "password": "Passw0rd!",
            "email": "new@example.com",
            "full_name": "New Auditor",
        },
    )
    assert response.status_code == 201, response.text

    # Cannot log in until approved.
    denied = client.post("/api/auth/login", json={"username": "newauditor", "password": "Passw0rd!"})
    assert denied.status_code == 403


def test_login_me_logout(client, db):
    make_user(db, "alice")
    csrf = login(client, "alice")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "alice"
    assert me.json()["csrf_token"] == csrf

    out = client.post("/api/auth/logout", headers=csrf_headers(csrf))
    assert out.status_code == 200

    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_rejected(client, db):
    make_user(db, "bob")
    response = client.post("/api/auth/login", json={"username": "bob", "password": "wrong-password"})
    assert response.status_code == 401


def test_inactive_user_cannot_login(client, db):
    make_user(db, "pending", active=False)
    response = client.post("/api/auth/login", json={"username": "pending", "password": DEFAULT_PASSWORD})
    assert response.status_code == 403


def test_csrf_required_for_writes(client, db):
    make_user(db, "carol")
    login(client, "carol")
    # Missing CSRF header -> 403
    response = client.post("/api/audits", json={"title": "No CSRF"})
    assert response.status_code == 403


def test_auditee_cannot_create_audit(client, db):
    make_user(db, "dave")  # Auditee by default
    csrf = login(client, "dave")
    response = client.post("/api/audits", json={"title": "Forbidden"}, headers=csrf_headers(csrf))
    assert response.status_code == 403


def test_update_profile(client, db):
    make_user(db, "eve", full_name="Eve Old", email="eve@old.com")
    csrf = login(client, "eve")

    response = client.patch(
        "/api/auth/me",
        json={"full_name": "Eve New", "email": "eve@new.com"},
        headers=csrf_headers(csrf),
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["full_name"] == "Eve New"
    assert response.json()["user"]["email"] == "eve@new.com"


def test_change_password(client, db):
    make_user(db, "frank")
    csrf = login(client, "frank")

    # Wrong current password
    bad = client.post(
        "/api/auth/me/password",
        json={"current_password": "wrong", "new_password": "NewPassw0rd!"},
        headers=csrf_headers(csrf),
    )
    assert bad.status_code == 400

    # Correct current password
    ok = client.post(
        "/api/auth/me/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "NewPassw0rd!"},
        headers=csrf_headers(csrf),
    )
    assert ok.status_code == 200

    # Old password no longer works
    client.post("/api/auth/logout", headers=csrf_headers(csrf))
    old_login = client.post("/api/auth/login", json={"username": "frank", "password": DEFAULT_PASSWORD})
    assert old_login.status_code == 401

    # New password works
    new_login = client.post("/api/auth/login", json={"username": "frank", "password": "NewPassw0rd!"})
    assert new_login.status_code == 200
