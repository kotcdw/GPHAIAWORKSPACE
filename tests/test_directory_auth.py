"""Optional Active Directory / LDAP sign-in (ldap3 mock server)."""

from __future__ import annotations

import uuid

import pytest
from ldap3 import MOCK_SYNC, Connection, Server

from app.core import directory
from app.core.config import settings
from app.core.enums import Role
from app.platform.users.models import User
from tests.conftest import make_user

BASE = "ou=users,dc=gpha,dc=test"


@pytest.fixture
def ad(monkeypatch):
    people = {}

    def factory(bind_user: str, password: str):
        conn = Connection(Server("fake_ad"), user=bind_user, password=password, client_strategy=MOCK_SYNC)
        for uid, (pw, name, mail) in people.items():
            conn.strategy.add_entry(f"cn={uid},{BASE}", {"userPassword": pw, "sAMAccountName": uid,
                                                         "displayName": name, "mail": mail, "objectClass": "person"})
        return conn

    monkeypatch.setattr(settings, "ldap_url", "ldap://fake_ad")
    monkeypatch.setattr(settings, "ldap_bind_template", "cn={username}," + BASE)
    monkeypatch.setattr(settings, "ldap_base_dn", BASE)
    monkeypatch.setattr(directory, "connection_factory", factory)
    return people


def test_directory_login_existing_and_new_users(client, db, ad):
    existing = make_user(db, f"ad_{uuid.uuid4().hex[:6]}", Role.Auditor)
    ad[existing.username] = ("NetworkPass#1", "Kofi Boateng", "kofi@gpha.gov.gh")
    ok = client.post("/api/auth/login", json={"username": existing.username, "password": "NetworkPass#1"})
    assert ok.status_code == 200, ok.text
    bad = client.post("/api/auth/login", json={"username": existing.username, "password": "wrong"})
    assert bad.status_code == 401

    newbie = f"ad_{uuid.uuid4().hex[:6]}"
    ad[newbie] = ("Another#Pass2", "Ama Mensah", "ama@gpha.gov.gh")
    first = client.post("/api/auth/login", json={"username": newbie, "password": "Another#Pass2"})
    assert first.status_code == 403 and "pending" in first.json()["detail"]
    db.rollback()
    created = db.query(User).filter_by(username=newbie).one()
    assert created.role == Role.Auditee and not created.is_active
    assert created.full_name == "Ama Mensah" and created.email == "ama@gpha.gov.gh"

    # Filter injection characters are rejected outright.
    assert directory.authenticate("x*)(uid=*", "pw") is None


def test_directory_disabled_for_unknown_users_when_auto_create_off(client, ad, monkeypatch):
    monkeypatch.setattr(settings, "ldap_auto_create", False)
    name = f"ad_{uuid.uuid4().hex[:6]}"
    ad[name] = ("Pw#12345678", "Yaw", "yaw@gpha.gov.gh")
    r = client.post("/api/auth/login", json={"username": name, "password": "Pw#12345678"})
    assert r.status_code == 403 and "not registered" in r.json()["detail"]
