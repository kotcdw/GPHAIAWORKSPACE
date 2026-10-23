"""The data wipe keeps users, roles, settings, libraries and the audit trail, and empties every other table.

It runs against a throw-away database on the same server, so the shared test database is left alone."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.database import Base
from scripts import wipe_data


@pytest.fixture
def scratch_engine():
    from app.core.config import settings

    url = make_url(settings.database_url)
    if url.get_backend_name() != "mysql":
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        yield engine
        return
    admin = create_engine(url)
    try:
        with admin.begin() as c:
            c.execute(text("CREATE DATABASE IF NOT EXISTS gpha_wipe_test"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"cannot create a scratch database: {exc}")
    engine = create_engine(url.set(database="gpha_wipe_test"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    with admin.begin() as c:
        c.execute(text("DROP DATABASE gpha_wipe_test"))
    admin.dispose()


def test_wipe_keeps_users_roles_and_settings(scratch_engine):
    engine = scratch_engine
    from app.core.appconfig import AppConfig
    from app.core.enums import Role
    from app.domains.audit.audits.models import Audit
    from app.platform.organizations.models import Organization
    from app.platform.roles.models import RolePermission
    from app.platform.users.models import User

    with Session(engine) as db:
        unit = Organization(org_ref="ORG-0001", name="Head Office", category="Head Office")
        db.add(unit)
        db.flush()
        user = User(username="keeper", password_hash="x", email="k@example.com", role=Role.Auditor, is_active=True,
                    work_entity_id=unit.id)
        db.add_all([user, RolePermission(job_role="auditor", permission="data.export", granted=True),
                    AppConfig(key="fiscal_year_start_month", value="1")])
        db.flush()
        db.add(Audit(title="Cash", scope="Q3", created_by=user.id))
        db.commit()

        removed = wipe_data.wipe(db)
        db.commit()
        assert removed >= 2
        assert db.execute(select(func.count()).select_from(Audit)).scalar() == 0
        assert db.execute(select(func.count()).select_from(Organization)).scalar() == 0
        kept = db.execute(select(User)).scalar_one()
        assert kept.username == "keeper" and kept.work_entity_id is None
        assert db.execute(select(func.count()).select_from(RolePermission)).scalar() == 1
        assert db.get(AppConfig, "fiscal_year_start_month") is not None


def test_every_table_is_either_kept_or_wiped():
    names = {t.name for t in Base.metadata.sorted_tables}
    assert wipe_data.KEEP <= names
    wiped = {t.name for t in wipe_data.wiped_tables()}
    assert {"audits", "findings", "capa", "organizations", "assurance_plans", "notifications"} <= wiped
    assert not wiped & {"users", "role_permissions", "role_module_access", "app_config", "audit_logs"}
