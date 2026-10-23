"""Platform map: how the workspace is put together, generated from the code itself.

GPHA INTERNAL AUDIT -> API / Platform Core -> Audit / Assurance / Issues domain modules -> Shared Data ->
AI / Analytics / Documents services. Each layer package declares its modules and routers; the tables each
module owns are read from the ORM mappings, so the map cannot drift from the running system.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.deps import require_perm
from app.platform.users.models import User

router = APIRouter(prefix="/api/platform", tags=["platform"])

CORE = {
    "name": "Core (cross-cutting)",
    "package": "app.core",
    "components": [
        "Sign-in sessions, CSRF protection and two-step verification (security, totp, deps)",
        "Job roles and permissions (permissions)",
        "Admin-configurable rules (appconfig)",
        "Audit trail of every action (audit) and record history (history)",
        "E-signatures with segregation of duties (approvalsvc)",
        "Encryption of stored files (crypto)",
        "Database session and schema checks (database, dbcheck)",
    ],
}


def _tables_by_package() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for mapper in Base.registry.mappers:
        table = getattr(mapper.class_, "__tablename__", None)
        if table:
            out.setdefault(mapper.class_.__module__, []).append(table)
    return out


def _owned(tables: dict[str, list[str]], package: str) -> list[str]:
    return sorted({t for mod, names in tables.items() if mod == package or mod.startswith(package + ".")
                   for t in names})


def _layer(layer, tables: dict[str, list[str]]) -> dict:  # noqa: ANN001
    base = layer.__name__
    return {
        "name": layer.NAME,
        "package": base,
        "description": layer.DESCRIPTION,
        "modules": [{"code": code, "summary": summary, "package": f"{base}.{code}",
                     "tables": _owned(tables, f"{base}.{code}"),
                     "endpoints": sorted({r.path.split("/")[2] for r in _routes(f"{base}.{code}")})}
                    for code, summary in layer.MODULES.items()],
    }


def _routes(package: str) -> list:
    from app.main import _ROUTERS

    return [r for router in _ROUTERS for r in router.routes
            if getattr(getattr(r, "endpoint", None), "__module__", "").startswith(package)
            and getattr(r, "path", "").startswith("/api/")]


def platform_map() -> dict:
    from app import platform, services
    from app.domains import layers
    from app.services.ai import service as ai
    from app.services.documents import CATALOGUE

    tables = _tables_by_package()
    service_layer = _layer(services, tables)
    status = ai.status()
    for module in service_layer["modules"]:
        if module["code"] == "ai":
            module["status"] = {"enabled": status["enabled"], "ready": status["ready"],
                                "provider": status["provider_name"], "model": status["model"],
                                "problems": status["problems"]}
        elif module["code"] == "documents":
            module["status"] = {"documents": CATALOGUE}
        else:
            module["status"] = {"enabled": True}
    url = settings.database_url
    db_name = url.rsplit("/", 1)[-1].split("?")[0] if "/" in url else ""
    return {
        "system": "GPHA INTERNAL AUDIT WORKSPACE",
        "core": {**CORE, "tables": _owned(tables, "app.core")},
        "platform": _layer(platform, tables),
        "domains": [_layer(d, tables) for d in layers()],
        "shared_data": {
            "name": "Shared Data",
            "description": "One MySQL database used by every domain through app.core.database; schema changes "
                           "only through Alembic migrations; every change written to the audit trail.",
            "engine": url.split(":", 1)[0],
            "database": db_name,
            "tables": len({t for names in tables.values() for t in names}),
        },
        "services": service_layer,
    }


@router.get("")
def get_platform_map(_: User = Depends(require_perm("system.technical", "system.config")),
                     db: DBSession = Depends(get_db)) -> dict:
    return platform_map()
