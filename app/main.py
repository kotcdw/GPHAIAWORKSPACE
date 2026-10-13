"""GPHA Audit Workspace - FastAPI application entry point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.deps import csrf_protect
from app.modules.approvals.router import router as approvals_router
from app.modules.audits.findings import router as findings_router
from app.modules.audits.router import router as audits_router
from app.modules.audits.working_papers import router as working_papers_router
from app.modules.auth.router import router as auth_router
from app.modules.backups.router import router as backups_router
from app.modules.capa.router import router as capa_router
from app.modules.history.router import records_router
from app.modules.history.router import router as history_router
from app.modules.nonconformances.router import router as nonconformances_router
from app.modules.organizations.router import router as organizations_router
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
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")