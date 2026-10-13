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
from app.core.dbcheck import database_status, ensure_schema
from app.core.deps import csrf_protect
from app.core.errors import FieldValidationError
from app.modules.approvals.router import router as approvals_router
from app.modules.audits.findings import router as findings_router
from app.modules.audits.router import router as audits_router
from app.modules.audits.working_papers import router as working_papers_router
from app.modules.auth.router import router as auth_router
from app.modules.backups.router import router as backups_router
from app.modules.capa.router import router as capa_router
from app.modules.drafts.router import router as drafts_router
from app.modules.history.router import records_router
from app.modules.history.router import router as history_router
from app.modules.nonconformances.router import router as nonconformances_router
from app.modules.organizations.router import router as organizations_router
from app.modules.planning.router import router as planning_router
from app.modules.rcm.router import router as rcm_router
from app.modules.service_feedback.router import router as service_feedback_router
from app.modules.stakeholders.router import router as stakeholders_router
from app.modules.tasks.router import router as tasks_router
from app.modules.users.router import router as users_router

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
    task: asyncio.Task | None = None
    if settings.backup_interval_hours > 0:
        task = asyncio.create_task(_backup_scheduler())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


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
        out.append({"field": name, "message": msg})
    return out


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc: RequestValidationError):  # noqa: ANN001, ANN201
    """Return validation problems per field so the UI can highlight them."""
    errors = _field_errors(exc)
    summary = "; ".join(f"{e['field'].replace('_', ' ')}: {e['message']}" for e in errors)
    return JSONResponse(status_code=422, content={"detail": f"Please correct: {summary}", "errors": errors})


# MySQL client errors meaning "cannot reach / lost the server".
_CONNECTION_ERRORS = {2002, 2003, 2005, 2006, 2013, 2055}


@app.exception_handler(DBAPIError)
async def database_error_handler(request, exc: DBAPIError):  # noqa: ANN001, ANN201
    """Database down / unreachable: answer 503 with a clear message instead of a bare 500."""
    code = exc.orig.args[0] if getattr(exc, "orig", None) is not None and getattr(exc.orig, "args", None) else None
    unavailable = exc.connection_invalidated or (
        isinstance(exc, OperationalError) and (code in _CONNECTION_ERRORS or "unable to open database" in str(exc))
    )
    if not unavailable:
        raise exc
    logger.error("Database error on %s %s: %s", request.method, request.url.path, str(exc).splitlines()[0])
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is unavailable, so nothing could be saved. Your entries are kept as a draft."},
    )


@app.exception_handler(FieldValidationError)
async def business_validation_handler(request, exc: FieldValidationError):  # noqa: ANN001, ANN201
    summary = "; ".join(f"{e['field'].replace('_', ' ')}: {e['message']}" for e in exc.errors)
    return JSONResponse(status_code=422, content={"detail": f"Please correct: {summary}", "errors": exc.errors})


@app.middleware("http")
async def security_headers(request, call_next):  # noqa: ANN001, ANN201
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if settings.cookie_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

for router in _ROUTERS:
    app.include_router(router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness plus database status; the UI warns users when saving is impossible."""
    db = database_status()
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