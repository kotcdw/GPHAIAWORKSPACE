"""GPHA Audit Workspace - FastAPI application entry point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.dbcheck import ensure_schema, heal_if_needed
from app.core.deps import csrf_protect
from app.core.errors import FieldValidationError
from app.modules.approvals.router import router as approvals_router
from app.modules.audits.findings import router as findings_router
from app.modules.audits.lifecycle import router as lifecycle_router
from app.modules.audits.router import router as audits_router
from app.modules.audits.working_papers import router as working_papers_router
from app.modules.auth.router import router as auth_router
from app.modules.backups.router import router as backups_router
from app.modules.capa.router import router as capa_router
from app.modules.capacity.router import router as capacity_router
from app.modules.committee.router import router as committee_router
from app.modules.configuration.router import router as configuration_router
from app.modules.customfields.router import router as customfields_router
from app.modules.dataio.router import router as dataio_router
from app.modules.drafts.router import router as drafts_router
from app.modules.followup.router import router as followup_router
from app.modules.history.router import records_router
from app.modules.history.router import router as history_router
from app.modules.insights.router import router as insights_router
from app.modules.memos.router import router as memos_router
from app.modules.methodology.router import router as methodology_router
from app.modules.nonconformances.router import router as nonconformances_router
from app.modules.notifications.router import router as notifications_router
from app.modules.organizations.router import router as organizations_router
from app.modules.planning.router import router as planning_router
from app.modules.qaip.router import router as qaip_router
from app.modules.rcm.router import router as rcm_router
from app.modules.reports.router import router as reports_router
from app.modules.service_feedback.router import router as service_feedback_router
from app.modules.stakeholders.router import router as stakeholders_router
from app.modules.tasks.router import router as tasks_router
from app.modules.users.router import router as users_router
from app.modules.views.router import router as views_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Explicit router registry (one entry per module).
_ROUTERS = (
    auth_router,
    users_router,
    audits_router,
    findings_router,
    working_papers_router,
    history_router,
    records_router,
    organizations_router,
    stakeholders_router,
    nonconformances_router,
    capa_router,
    service_feedback_router,
    tasks_router,
    approvals_router,
    backups_router,
    planning_router,
    rcm_router,
    drafts_router,
    notifications_router,
    followup_router,
    reports_router,
    lifecycle_router,
    configuration_router,
    committee_router,
    memos_router,
    capacity_router,
    qaip_router,
    insights_router,
    dataio_router,
    views_router,
    customfields_router,
    methodology_router,
)


async def _backup_scheduler() -> None:
    """Periodically snapshot the database while the app runs."""
    from app.modules.backups.service import create_backup

    interval = settings.backup_interval_hours * 3600
    while True:
        await asyncio.sleep(interval)
        db = SessionLocal()
        try:
            create_backup(db)
        except Exception:  # noqa: BLE001 - a failed backup must not kill the app
            logger.exception("Scheduled backup failed")
        finally:
            db.close()


logger = logging.getLogger("gpha")


def check_security_settings() -> None:
    """Refuse to run in production with insecure defaults; warn in development."""
    problems = settings.insecure_settings()
    if not problems:
        return
    if settings.environment.lower() == "production":
        raise RuntimeError("Insecure production configuration:\n  - " + "\n  - ".join(problems))
    for problem in problems:
        logger.warning("Insecure setting (acceptable for development only): %s", problem)


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_security_settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    # Make sure the database can accept writes (and is migrated) before serving.
    await asyncio.to_thread(ensure_schema)
    tasks: list[asyncio.Task] = [asyncio.create_task(_schema_watcher())]
    if settings.escalation_check_minutes > 0:
        tasks.append(asyncio.create_task(_escalation_watcher()))
    if settings.backup_interval_hours > 0:
        tasks.append(asyncio.create_task(_backup_scheduler()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _escalation_watcher() -> None:
    """Escalate overdue actions on a timer (owner -> Audit Manager -> CAE)."""
    from app.modules.followup.service import run_escalations

    def _tick() -> None:
        db = SessionLocal()
        try:
            run_escalations(db)
        finally:
            db.close()

    while True:
        await asyncio.sleep(settings.escalation_check_minutes * 60)
        try:
            await asyncio.to_thread(_tick)
        except Exception:  # noqa: BLE001 - never let the watcher die
            logger.exception("Escalation check failed")


async def _schema_watcher() -> None:
    """Every 30 s: if the database came back after an outage, migrate it without a restart."""
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(heal_if_needed)
        except Exception:  # noqa: BLE001 - never let the watcher die
            logger.exception("Schema watcher check failed")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    dependencies=[Depends(csrf_protect)],
)

_FRIENDLY = {
    "missing": "is required",
    "string_too_short": "must not be empty",
    "string_too_long": "is too long",
    "too_long": "has too many entries",
    "greater_than_equal": "is too small",
    "less_than_equal": "is too large",
    "int_parsing": "must be a whole number",
    "int_from_float": "must be a whole number",
    "float_parsing": "must be a number",
    "datetime_from_date_parsing": "must be a valid date",
    "datetime_parsing": "must be a valid date",
    "enum": "is not one of the allowed values",
    "literal_error": "is not one of the allowed values",
    "bool_parsing": "must be yes/no",
    "string_type": "must be text",
    "dict_type": "is invalid",
    "list_type": "must be a list",
}


def _field_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    out = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        name = loc[-1] if loc else "form"
        if name.isdigit() and len(loc) > 1:  # list item, e.g. root_cause_whys.2
            name = loc[-2]
        msg = err.get("msg", "is invalid")
        if err.get("type") in _FRIENDLY and err.get("type") not in ("greater_than_equal", "less_than_equal"):
            msg = _FRIENDLY[err["type"]]
        elif msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        if name == "form" and msg.startswith("Password "):
            name, msg = "password", msg[len("Password ") :]
        out.append({"field": name, "message": msg})
    return out


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc: RequestValidationError):  # noqa: ANN001, ANN201
    """Return validation problems per field so the UI can highlight them."""
    errors = _field_errors(exc)
    summary = "; ".join(
        e["message"] if e["field"] == "form" else f"{e['field'].replace('_', ' ')}: {e['message']}" for e in errors
    )
    return JSONResponse(status_code=422, content={"detail": f"Please correct: {summary}", "errors": errors})


# MySQL client errors meaning "cannot reach / lost the server".
_CONNECTION_ERRORS = {2002, 2003, 2005, 2006, 2013, 2055}
# Unknown column / unknown table: the database schema is behind the code.
_SCHEMA_ERRORS = {1054, 1146}


@app.exception_handler(DBAPIError)
async def database_error_handler(request, exc: DBAPIError):  # noqa: ANN001, ANN201
    """Database down / unreachable: answer 503 with a clear message instead of a bare 500."""
    code = exc.orig.args[0] if getattr(exc, "orig", None) is not None and getattr(exc.orig, "args", None) else None
    unavailable = exc.connection_invalidated or (
        isinstance(exc, OperationalError) and (code in _CONNECTION_ERRORS or "unable to open database" in str(exc))
    )
    if code in _SCHEMA_ERRORS:
        # The code is newer than the database (e.g. it was down when the app started): migrate now.
        logger.error("Schema out of date on %s %s: %s", request.method, request.url.path, str(exc).splitlines()[0])
        await asyncio.to_thread(heal_if_needed)
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The database was just updated to the latest version. Please try again.",
                "code": "database_updating",
            },
        )
    if not unavailable:
        raise exc
    logger.error("Database error on %s %s: %s", request.method, request.url.path, str(exc).splitlines()[0])
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The database server is not running, so this request could not be completed. "
            "An administrator needs to start it (run .\\run.ps1, or 'docker compose up -d').",
            "code": "database_unavailable",
        },
    )


@app.exception_handler(FieldValidationError)
async def business_validation_handler(request, exc: FieldValidationError):  # noqa: ANN001, ANN201
    summary = "; ".join(f"{e['field'].replace('_', ' ')}: {e['message']}" for e in exc.errors)
    return JSONResponse(status_code=422, content={"detail": f"Please correct: {summary}", "errors": exc.errors})


# Everything the UI loads is served from this app (fonts and icons are self-hosted).
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'"
)


@app.middleware("http")
async def security_headers(request, call_next):  # noqa: ANN001, ANN201
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", _CSP)
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.cookie_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    path = request.url.path
    if path == "/" or path.startswith("/static/"):
        # Always revalidate the UI so a browser never mixes old scripts with a new stylesheet.
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

for router in _ROUTERS:
    app.include_router(router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness plus database status; the UI warns users when saving is impossible."""
    db = heal_if_needed()
    return {
        "status": "ok" if db.ok and db.up_to_date else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "database": {k: v for k, v in db.as_dict().items() if k != "url"},
        "can_save": db.ok and db.up_to_date,
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")