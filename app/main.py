"""GPHA Audit Workspace - FastAPI application entry point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import platform, services
from app.core.access import audit_scope_guard
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.dbcheck import ensure_schema, heal_if_needed
from app.core.deps import csrf_protect
from app.core.errors import FieldValidationError
from app.domains import layers as domain_layers

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Router registry by layer: each layer package declares its own routers (see app/platform, app/domains, app/services).
LAYERS = (platform, *domain_layers(), services)
_ROUTERS = tuple(router for layer in LAYERS for router in layer.routers())


async def _backup_scheduler() -> None:
    """Periodically snapshot the database while the app runs."""
    from app.platform.backups.service import create_backup

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
    await asyncio.to_thread(_seed_automations)
    await asyncio.to_thread(_workflow_startup)
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


def _seed_automations() -> None:
    """Make sure the built-in automation rules exist (admins may edit or switch them off)."""
    from app.platform.automations.engine import ensure_builtins

    db = SessionLocal()
    try:
        ensure_builtins(db)
    except Exception:  # noqa: BLE001 - database not ready yet; seeded on the next start or first visit
        logger.exception("Could not seed automation rules")
    finally:
        db.close()


_LAST_RESYNC: list[float] = [0.0]


def _workflow_startup() -> None:
    """Seed the SLA policies and rebuild the "My work" inbox from the records."""
    import time

    from app.platform.workflow.workitems import full_resync

    db = SessionLocal()
    try:
        n = full_resync(db)
        db.commit()
        _LAST_RESYNC[0] = time.monotonic()
        logger.info("Work items rebuilt from %s records", n)
    except Exception:  # noqa: BLE001 - database not ready yet; rebuilt on the next tick
        db.rollback()
        logger.exception("Could not rebuild work items")
    finally:
        db.close()


def _workflow_tick() -> None:
    """SLA clock (warn, escalate) on every check; a full rebuild of the inbox about once a day."""
    import time

    from app.platform.workflow.workitems import run_sla_clock

    if time.monotonic() - _LAST_RESYNC[0] > 20 * 3600:
        _workflow_startup()
    db = SessionLocal()
    try:
        run_sla_clock(db)
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("SLA clock failed")
    finally:
        db.close()


async def _escalation_watcher() -> None:
    """Escalate overdue actions on a timer (owner -> Audit Manager -> CAE)."""
    from app.domains.issues.followup.service import run_escalations

    def _tick() -> None:
        db = SessionLocal()
        try:
            run_escalations(db)
        finally:
            db.close()
        db = SessionLocal()
        try:
            from app.domains.audit.evidence.router import send_due_reminders

            send_due_reminders(db)
        finally:
            db.close()
        db = SessionLocal()
        try:
            from app.platform.automations.engine import run_scheduled

            run_scheduled(db)
        finally:
            db.close()
        db = SessionLocal()
        try:
            from app.services.results.router import run_scheduled_robots

            run_scheduled_robots(db)
        finally:
            db.close()
        _workflow_tick()

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


_PROD = settings.environment.lower() == "production"
_DOCS = settings.api_docs and not _PROD
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    dependencies=[Depends(csrf_protect)],
    # The API map is for developers: not published on a production server.
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
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


MFA_SETUP_MESSAGE = "Set up two-step verification in your profile before continuing"


@app.exception_handler(StarletteHTTPException)
async def browser_aware_http_handler(request, exc: StarletteHTTPException):  # noqa: ANN001, ANN201
    """A link opened in the browser (a Word copy, a report, an export) that needs sign-in or two-step set-up
    goes back to the workspace instead of showing raw JSON; API calls keep their JSON errors."""
    navigation = (request.method == "GET" and request.url.path.startswith("/api/")
                  and "text/html" in request.headers.get("accept", "")
                  and request.headers.get("sec-fetch-mode", "navigate") == "navigate")
    if navigation and exc.status_code == 401:
        return RedirectResponse("/", status_code=303)
    if navigation and exc.status_code == 403 and exc.detail == MFA_SETUP_MESSAGE:
        return RedirectResponse("/#mfa-setup", status_code=303)
    return await http_exception_handler(request, exc)


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
    elif path.startswith("/api/"):
        # Audit data must not be kept by the browser cache or a shared proxy.
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.middleware("http")
async def switched_off_apps(request, call_next):  # noqa: ANN001, ANN201
    """Apps the Super Administrator has switched off answer 404 for everyone (Apps & customization)."""
    path = request.url.path
    if path.startswith("/api/") and not path.startswith(("/api/apps", "/api/auth")):
        from app.platform.apps.registry import disabled_prefixes

        for prefix, label in disabled_prefixes():
            if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?"):
                return JSONResponse(status_code=404, content={"detail": f"The {label} app is switched off"})
    return await call_next(request)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Audit and remediation routes resolve the record in the URL to its audit and refuse it when it lies outside the
# caller's port/team scope (app.core.access.audit_scope_guard), for reads and writes alike.
_SCOPED_MODULES = ("app.domains.audit.", "app.domains.issues.", "app.platform.dataio.", "app.services.ai.")


def _scoped(router) -> bool:  # noqa: ANN001
    return any(getattr(getattr(r, "endpoint", None), "__module__", "").startswith(_SCOPED_MODULES)
               for r in router.routes)


for router in _ROUTERS:
    app.include_router(router, dependencies=[Depends(audit_scope_guard)] if _scoped(router) else [])


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