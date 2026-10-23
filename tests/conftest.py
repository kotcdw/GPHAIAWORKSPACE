"""Shared pytest fixtures.

The environment variables are set *before* importing the application so that
the app's settings and database engine point at an isolated MySQL test
database. A session-level fixture drops and recreates ``gpha_workspace_test``
and then applies all Alembic migrations against it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# --- Determine the test database URL ---------------------------------------
# These mirror app/config.py defaults so pytest works out of the box with the
# docker-compose MySQL instance. Set GPHA_TEST_DATABASE_URL to override with a
# fully-qualified URL (e.g. for CI secrets).
_HOST = os.environ.get("GPHA_MYSQL_HOST", "127.0.0.1")
_PORT = os.environ.get("GPHA_MYSQL_PORT", "3307")
_USER = os.environ.get("GPHA_MYSQL_USER", "gpha")
_PASS = os.environ.get("GPHA_MYSQL_PASSWORD", "gpha_dev_pass")
_TEST_DB = "gpha_workspace_test"
_TEST_URL = os.environ.get(
    "GPHA_TEST_DATABASE_URL",
    f"mysql+pymysql://{_USER}:{_PASS}@{_HOST}:{_PORT}/{_TEST_DB}?charset=utf8mb4",
)

# Admin connection (no database selected) used to drop/create the test DB.
_ADMIN_URL = os.environ.get(
    "GPHA_TEST_ADMIN_URL",
    f"mysql+pymysql://{_USER}:{_PASS}@{_HOST}:{_PORT}/?charset=utf8mb4",
)

_TMP = Path(tempfile.mkdtemp(prefix="gpha_test_"))
os.environ["GPHA_DATABASE_URL"] = _TEST_URL
os.environ["GPHA_UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["GPHA_BACKUP_DIR"] = str(_TMP / "backups")
os.environ["GPHA_BACKUP_INTERVAL_HOURS"] = "0"
os.environ["GPHA_ADMIN_USERNAME"] = "admin"
os.environ["GPHA_ADMIN_PASSWORD"] = "Admin@12345"
os.environ["GPHA_COOKIE_SECURE"] = "false"
os.environ["GPHA_LOGIN_RATE_LIMIT_PER_MINUTE"] = "0"  # tests sign in many times from one client
os.environ["GPHA_ESCALATION_CHECK_MINUTES"] = "0"
# Older tests close audits without a report; the closure gates have their own tests.
os.environ["GPHA_REQUIRE_REPORT_TO_CLOSE"] = "false"
os.environ["GPHA_REQUIRE_FINDINGS_ACTIONED_TO_CLOSE"] = "false"
os.environ["GPHA_REQUIRE_MEMO_APPROVAL_FOR_FIELDWORK"] = "false"
os.environ["GPHA_REQUIRE_ENGAGEMENT_DECLARATION"] = "false"
# Older tests use one Audit Manager review and one working-paper sign-off; the chain has its own tests.
os.environ["GPHA_REPORT_REVIEW_CHAIN"] = "Audit Manager"
os.environ["GPHA_WORKPAPER_REVIEW_CHAIN"] = ""
# Older tests let any auditor work on any audit; port/team scoping has its own tests (test_scope_team.py).
os.environ["GPHA_PORT_SCOPE_ENFORCED"] = "false"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from alembic import command  # noqa: E402
from app.core.config import BASE_DIR  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.enums import Role  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.platform.users.models import User  # noqa: E402

DEFAULT_PASSWORD = "Passw0rd!"


def _recreate_test_database() -> None:
    admin = create_engine(_ADMIN_URL, future=True)
    try:
        with admin.begin() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {_TEST_DB}"))
            conn.execute(
                text(
                    f"CREATE DATABASE {_TEST_DB} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrate_database():
    _recreate_test_database()
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _engagement_lead_role():
    _grant_engagement_lead_permissions()  # again before each test: some tests reset the Auditor role
    yield


# Most tests use an Auditor-tier account as the engagement lead who opens the audit. In the least-privilege role
# design an Auditor does not create audits, review or export; the tests grant those back the way a Super
# Administrator would (Roles & permissions), and switch off "Auditors work only on their assigned engagements" so
# port-scope tests keep their meaning. tests/test_least_privilege.py restores the standard Auditor role.
ENGAGEMENT_LEAD_GRANTS = ("audit.create", "review.workpapers", "review.notes", "data.export")


def _grant_engagement_lead_permissions() -> None:
    from app.core import appconfig
    from app.core import permissions as perms
    from app.platform.roles.models import RolePermission

    with SessionLocal() as s:
        for p in ENGAGEMENT_LEAD_GRANTS:
            s.merge(RolePermission(job_role="auditor", permission=p, granted=True))
        s.merge(appconfig.AppConfig(key="auditor_assigned_only", value="false"))
        s.commit()
    perms.invalidate()
    appconfig.invalidate()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client2():
    """A second independent client (its own cookies/session).

    Useful when a test needs two users logged in at once (the session cookie and
    CSRF token are per-client).
    """
    with TestClient(app) as test_client:
        yield test_client


def make_user(
    db,
    username: str,
    role: Role = Role.Auditee,
    *,
    active: bool = True,
    password: str = DEFAULT_PASSWORD,
    full_name: str | None = None,
    email: str | None = None,
) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        email=email or f"{username}@example.com",
        full_name=full_name or username.title(),
        role=role,
        is_active=active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client: TestClient, username: str, password: str = DEFAULT_PASSWORD) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def csrf_headers(csrf_token: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token}

# ------------------------------------------------------------------ annual planning cycle helpers

PREP_CHECKS = ["strategy", "prior_year", "stakeholders", "resources", "regulatory"]


def decide_topicals(client: TestClient, audit_id: int, headers: dict) -> None:
    """Record every IIA topical requirement as not in scope of the engagement (closing an assurance audit needs a
    decision on each)."""
    for r in client.get(f"/api/audits/{audit_id}/topical").json()["requirements"]:
        res = client.put(f"/api/audits/{audit_id}/topical/{r['id']}",
                         json={"in_scope": False, "rationale": "Topic not in the scope of this engagement"},
                         headers=headers)
        assert res.status_code == 200, res.text


def walk_plan_to_review(client: TestClient, plan_id: int, headers: dict) -> None:
    """Preparation -> universe review -> managers' meeting -> submitted for internal review."""
    from app.core.enums import utcnow

    base = f"/api/assurance-plans/{plan_id}/cycle"
    steps = [
        ("preparation", {"checks": PREP_CHECKS, "notes": "Strategy 2026-2028"}),
        ("universe-review", {"notes": "Universe reviewed; ratings refreshed"}),
        ("managers-meeting", {"meeting_date": utcnow().isoformat(), "attendees": "GM Audit; PIAs; Managers",
                              "minutes": "Agreed coverage and priorities for the year"}),
        ("submit-review", {"notes": ""}),
    ]
    for path, body in steps:
        r = client.post(f"{base}/{path}", json=body, headers=headers)
        assert r.status_code == 200, f"{path}: {r.text}"


def release_plan(client: TestClient, plan_id: int, headers: dict) -> None:
    """Approved plan -> submitted -> Audit Committee approval -> distributed by the GM Audit."""
    from app.core.enums import utcnow

    base = f"/api/assurance-plans/{plan_id}/cycle"
    now = utcnow().isoformat()
    r = client.post(f"{base}/submit-authority", json={"authority": "Audit Committee", "submitted_on": now},
                    headers=headers)
    assert r.status_code == 200, r.text
    r = client.post(f"{base}/committee-decision", json={"decision": "Approved", "meeting_date": now,
                                                        "reference": "AC/TEST"}, headers=headers)
    assert r.status_code == 200, r.text
    me = client.get("/api/auth/me").json()["user"]["id"]
    r = client.post(f"{base}/distribute", json={"user_ids": [me]}, headers=headers)
    assert r.status_code == 200, r.text


def make_entity(client: TestClient, headers: dict, name: str | None = None, *, likelihood: int = 3,
                impact: int = 3, parent_id: int | None = None) -> dict:
    """A Ready auditable entity defined the supported way: an org unit of the Org Structure, then the entity.
    ``likelihood``/``impact`` set the inherent score that rates an entity until an assessment is completed."""
    import uuid as _uuid

    tag = _uuid.uuid4().hex[:6]
    name = name or f"Entity {tag}"
    unit = client.post("/api/organizations", json={"name": f"{name} unit {tag}", "category": "Port" if parent_id is None
                                                   else "Department", "parent_id": parent_id}, headers=headers)
    assert unit.status_code == 201, unit.text
    r = client.post("/api/auditable-entities", json={
        "name": name, "entity_type": "Org unit", "org_ids": [unit.json()["id"]], "definition_status": "Ready",
        "owner_email": "owner@gpha.test", "scope": f"Operations of {name}.", "allow_duplicate": True}, headers=headers)
    assert r.status_code == 201, r.text
    entity = r.json()
    entity["org_unit_id"] = unit.json()["id"]
    if (likelihood, impact) != (3, 3):
        from app.core.database import SessionLocal
        from app.domains.assurance.planning.models import EntityUnit

        with SessionLocal() as s:
            s.execute(EntityUnit.__table__.update().where(EntityUnit.id == entity["id"])
                      .values(risk_likelihood=likelihood, risk_impact=impact))
            s.commit()
    return entity
