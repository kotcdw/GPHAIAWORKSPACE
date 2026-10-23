"""Administration landing page: what an administrator needs to know, from data the system can verify.

``GET /api/admin/overview`` returns only the sections the caller may see. Every figure comes from a table or a
file the application can read; where something is not recorded, the section says so instead of guessing.
``GET /api/admin/policies`` shows the data and attachment limits in force (read-only).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession

from app.core.audit_describe import describe
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.enums import Role, utcnow
from app.core.permissions import has_perm
from app.platform.history.models import AuditLog
from app.platform.users.models import User

router = APIRouter(prefix="/api/admin", tags=["administration"])

INACTIVE_DAYS = 90  # an active account with no sign-in for this long is listed for review
NEW_ACCOUNT_GRACE_DAYS = 14  # accounts younger than this are not "inactive" yet

# Administration area -> permissions that open it (any one).
AREAS: dict[str, tuple[str, ...]] = {
    "users": ("system.users", "system.roles"),
    "org": ("system.reference", "system.config"),
    "settings": ("system.config", "system.workflow", "system.reference", "method.reporting", "method.audit_types",
                 "method.plan_config", "grc.manage", "governance.charter"),
    "activity": ("system.technical",),
    "imports": ("system.reference", "method.library", "system.technical"),
    "policies": ("system.technical", "system.config"),
    "backups": ("system.technical",),
}


def allowed_areas(user: User) -> set[str]:
    return {area for area, perms in AREAS.items() if has_perm(user, *perms)}


def require_admin_area(user: User = Depends(require_active_user)) -> User:
    if not allowed_areas(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to administration")
    return user


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _name(u: User) -> str:
    return u.full_name or u.username


def _users(db: DBSession, now: datetime) -> dict:
    users = list(db.execute(select(User)).scalars())
    active = [u for u in users if u.is_active]
    last = dict(db.execute(select(AuditLog.user_id, func.max(AuditLog.timestamp)).where(
        AuditLog.user_id.is_not(None),
        or_(AuditLog.action_performed == "LOGIN", AuditLog.action_performed == "LOGIN directory"),
    ).group_by(AuditLog.user_id)).all())
    cutoff = now - timedelta(days=INACTIVE_DAYS)
    grace = now - timedelta(days=NEW_ACCOUNT_GRACE_DAYS)
    inactive = []
    for u in active:
        seen = last.get(u.id)
        if (seen is not None and seen < cutoff) or (seen is None and u.created_at < grace):
            inactive.append({"id": u.id, "name": _name(u), "username": u.username, "last_sign_in": _iso(seen)})
    inactive.sort(key=lambda r: r["last_sign_in"] or "")
    pending = [u for u in users if not u.is_active and last.get(u.id) is None]
    locked = [u for u in active if u.locked_until and u.locked_until > now]
    admins = [u for u in active if u.role == Role.Admin]
    return {
        "total": len(users), "active": len(active), "deactivated": len(users) - len(active) - len(pending),
        "pending": [{"id": u.id, "name": _name(u), "username": u.username, "created_at": _iso(u.created_at)}
                    for u in sorted(pending, key=lambda u: u.created_at)][:10],
        "pending_count": len(pending),
        "locked": [{"id": u.id, "name": _name(u), "until": _iso(u.locked_until)} for u in locked],
        "inactive": inactive[:10], "inactive_count": len(inactive), "inactive_days": INACTIVE_DAYS,
        "admins_active": len(admins), "admins_without_mfa": sum(1 for u in admins if not u.mfa_enabled),
    }


def _org(db: DBSession) -> dict:
    """The internal structure (types listed under Org Structure types) and who is not placed in it."""
    from app.core.appconfig import cfg
    from app.platform.organizations.models import Organization

    types = {t.lower() for t in (cfg("org_structure_categories") or [])}
    units = [o for o in db.execute(select(Organization)).scalars() if (o.category or "").lower() in types]
    by_id = {o.id: o for o in db.execute(select(Organization)).scalars()}
    active = [o for o in units if o.is_active]
    staff = [u for u in db.execute(select(User).where(User.is_active.is_(True))).scalars()]
    no_place = [u for u in staff if u.work_entity_id is None]
    retired_place = [u for u in staff if u.work_entity_id in by_id and not by_id[u.work_entity_id].is_active]
    return {
        "units": len(units), "active": len(active), "inactive": len(units) - len(active),
        "pending": sum(1 for o in active if o.status.value == "Pending"),
        "without_head": sum(1 for o in active if not o.head_user_id),
        "people_without_workplace": len(no_place), "people_at_inactive_unit": len(retired_place),
    }


def _settings(db: DBSession, user: User) -> dict:
    """How far the configuration has moved from the defaults, and the latest recorded change."""
    from app.core.appconfig import RULES, AppConfigHistory, cfg
    from app.platform.configuration.router import _editable_groups

    groups = _editable_groups(user)
    mine = [r for r in RULES if r.group in groups]
    changed = sum(1 for r in mine if cfg(r.key) != r.default_value())
    last = db.execute(select(AppConfigHistory).where(AppConfigHistory.key.in_([r.key for r in mine]))
                      .order_by(AppConfigHistory.changed_at.desc(), AppConfigHistory.id.desc()).limit(1)
                      ).scalar_one_or_none() if mine else None
    by_key = {r.key: r for r in mine}
    return {"total": len(mine), "changed_from_default": changed,
            "regional": {k: cfg(k) for k in ("time_zone", "date_format", "fiscal_year_start_month")},
            "last_change": {"at": _iso(last.changed_at), "by": last.changed_by_name, "label": by_key[last.key].label}
            if last else None}


def _recent_admin_changes(db: DBSession, limit: int = 8) -> list[dict]:
    rows = db.execute(select(AuditLog).where(
        AuditLog.category.in_(("user_admin", "system", "security")), AuditLog.user_id.is_not(None),
        ~AuditLog.action_performed.like("ESCALATION%"),
    ).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit)).scalars().all()
    names = {u.id: _name(u) for u in db.execute(select(User).where(
        User.id.in_({r.user_id for r in rows}))).scalars()} if rows else {}
    return [{"at": _iso(r.timestamp), "user": names.get(r.user_id) or r.username or "-",
             "action": r.action_performed, "event": describe(r.action_performed)[0],
             "details": describe(r.action_performed)[1], "category": r.category, "outcome": r.outcome} for r in rows]


def _security(db: DBSession, now: datetime) -> dict:
    since = now - timedelta(days=7)
    base = select(func.count()).select_from(AuditLog).where(AuditLog.timestamp >= since)
    return {
        "days": 7,
        "failed_sign_ins": db.execute(base.where(AuditLog.action_performed.like("LOGIN_FAILED%"))).scalar_one(),
        "lockouts": db.execute(base.where(AuditLog.action_performed.like("ACCOUNT_LOCKED%"))).scalar_one(),
        "denied": db.execute(base.where(AuditLog.action_performed.like("ACCESS_DENIED%"))).scalar_one(),
    }


def _imports(db: DBSession, now: datetime) -> dict:
    """Imports carried out and uploads rejected in the last 30 days (from the import history)."""
    from app.platform.dataio.models import ImportRun

    since = now - timedelta(days=30)
    runs = list(db.execute(select(ImportRun).where(ImportRun.at >= since)
                           .order_by(ImportRun.at.desc(), ImportRun.id.desc())).scalars())
    return {"days": 30, "completed": sum(1 for r in runs if r.outcome == "imported"),
            "failed": sum(1 for r in runs if r.outcome == "rejected"),
            "recent": [{"at": _iso(r.at), "kind": r.kind, "outcome": r.outcome, "user": r.user_name}
                       for r in runs[:5]]}


def backups_summary(db: DBSession, now: datetime) -> dict:
    from app.platform.backups import service
    from app.platform.backups.models import BackupCheck
    from app.platform.backups.router import latest_checks

    files = service.list_backups()
    latest = files[0] if files else None
    age_hours = None
    if latest is not None:
        created = datetime.fromisoformat(latest.created_at).astimezone(UTC).replace(tzinfo=None)
        age_hours = round((now - created).total_seconds() / 3600, 1)
    failure = db.execute(select(AuditLog).where(AuditLog.action_performed.like("BACKUP_FAILED%"))
                         .order_by(AuditLog.timestamp.desc()).limit(1)).scalar_one_or_none()
    interval = service.interval_hours()
    check = latest_checks(db, [latest.stamp]).get(latest.stamp) if latest else None
    restore = db.execute(select(BackupCheck).where(BackupCheck.kind == "restore_test")
                         .order_by(BackupCheck.at.desc(), BackupCheck.id.desc()).limit(1)).scalar_one_or_none()
    return {
        "count": len(files), "retention": service.retention(), "interval_hours": interval,
        "server_schedule": settings.backup_interval_hours > 0,
        "include_attachments": service.include_attachments(),
        "latest": {"filename": latest.filename, "stamp": latest.stamp, "created_at": latest.created_at,
                   "size_bytes": latest.size_bytes, "files_bytes": latest.files_bytes,
                   "file_count": latest.file_count, "age_hours": age_hours} if latest else None,
        # Overdue = no backup newer than 1.5 x the schedule (only when a schedule is set).
        "overdue": bool(interval) and (age_hours is None or age_hours > interval * 1.5),
        "next_due": _iso(created + timedelta(hours=interval)) if latest and interval else None,
        "last_failure": {"at": _iso(failure.timestamp), "action": failure.action_performed} if failure else None,
        # The latest set's most recent check (files intact, decrypts with the current key, complete).
        "verified": {"outcome": check.outcome, "at": _iso(check.at)} if check else None,
        # The most recent full restore into a test database (scripts.verify_backup on the server).
        "restore_test": {"outcome": restore.outcome, "at": _iso(restore.at)} if restore else None,
        "includes_attachments": bool(latest and latest.files_name),
    }


_backups = backups_summary


def policies_data() -> dict:
    """The data, attachment and sign-in rules in force (settings within the server limits)."""
    from app.core import upload_policy
    from app.core.appconfig import cfg
    from app.platform.dataio.router import import_max_bytes, import_max_rows
    from app.platform.history.router import EXPORT_MAX_ROWS

    return {
        "attachments": {"max_upload_mb": upload_policy.max_mb(), "server_max_mb": settings.max_upload_mb,
                        "allowed_extensions": sorted(upload_policy.allowed()),
                        "never_allowed": sorted(upload_policy.NEVER),
                        "content_checked": bool(cfg("attachment_check_content")),
                        "encrypted_at_rest": True, "integrity_hash": "SHA-256"},
        "imports": {"max_file_mb": import_max_bytes() // (1024 * 1024), "max_rows": import_max_rows(),
                    "formats": ["xlsx"],
                    "all_or_nothing": True},
        "sessions": {"ttl_hours": int(cfg("session_max_hours")), "idle_minutes": int(cfg("session_idle_minutes")),
                     "max_failed_sign_ins": int(cfg("login_max_attempts")),
                     "lockout_minutes": int(cfg("login_lockout_minutes")),
                     "password_min_length": int(cfg("password_min_length"))},
        "activity_log": {"max_download_rows": EXPORT_MAX_ROWS},
    }


def storage_data() -> dict:
    """What the stored attachments take up on disk, by file type (files are kept encrypted as <name>.enc)."""
    import shutil
    from pathlib import Path

    root = Path(settings.upload_dir)
    by_type: dict[str, list[int]] = {}
    total_files = total_bytes = 0
    if root.exists():
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            name = f.name[:-4] if f.name.endswith(".enc") else f.name
            ext = Path(name).suffix.lower() or "(none)"
            size = f.stat().st_size
            entry = by_type.setdefault(ext, [0, 0])
            entry[0] += 1
            entry[1] += size
            total_files += 1
            total_bytes += size
    try:
        usage = shutil.disk_usage(root if root.exists() else root.parent)
        disk = {"total_bytes": usage.total, "free_bytes": usage.free}
    except OSError:
        disk = None
    return {"files": total_files, "bytes": total_bytes, "disk": disk,
            "by_type": [{"type": k, "files": v[0], "bytes": v[1]}
                        for k, v in sorted(by_type.items(), key=lambda kv: -kv[1][1])]}


@router.get("/overview")
def overview(db: DBSession = Depends(get_db), user: User = Depends(require_admin_area)) -> dict:
    now = utcnow()
    areas = allowed_areas(user)
    out: dict = {"areas": sorted(areas), "generated_at": now.isoformat(), "address": settings.app_base_url}
    if "users" in areas:
        out["users"] = _users(db, now)
    if "org" in areas:
        out["org"] = _org(db)
    if "settings" in areas:
        out["settings"] = _settings(db, user)
    if "activity" in areas:
        out["recent_changes"] = _recent_admin_changes(db)
        out["security"] = _security(db, now)
    if "imports" in areas:
        out["imports"] = _imports(db, now)
    if "backups" in areas:
        out["backups"] = _backups(db, now)
    if "policies" in areas:
        out["policies"] = policies_data()
    return out


@router.get("/storage")
def storage(user: User = Depends(require_admin_area)) -> dict:
    if "policies" not in allowed_areas(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to storage figures")
    return storage_data()


@router.get("/policies")
def policies(user: User = Depends(require_admin_area)) -> dict:
    if "policies" not in allowed_areas(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to data policies")
    return policies_data()


@router.get("/closeout")
def closeout(db: DBSession = Depends(get_db), user: User = Depends(require_admin_area)) -> dict:
    """Year-end closeout and next-cycle readiness: what is still open in this fiscal year and what the next one
    needs (plan, fiscal year end, people, seats, units). Every figure is counted from the records."""
    from datetime import date

    from app.core.appconfig import cfg
    from app.core.enums import AuditStatus, CapaStatus, FindingStatus
    from app.domains.assurance.planning.models import AssurancePlan
    from app.domains.audit.audits.models import Audit, Finding
    from app.domains.issues.capa.models import Capa
    from app.platform.organizations.models import Organization
    from app.platform.users import licenses as lic

    now = utcnow()
    start_month = int(cfg("fiscal_year_start_month"))
    fy = now.year if now.month >= start_month else now.year - 1
    end = (date(fy + 1, start_month, 1) if start_month > 1 else date(fy + 1, 1, 1)) - timedelta(days=1)

    def plan(year: int) -> dict | None:
        p = db.execute(select(AssurancePlan).where(AssurancePlan.fiscal_year == year)).scalar_one_or_none()
        return {"id": p.id, "title": p.title, "status": p.status.value, "ref": p.plan_ref} if p else None

    count = lambda stmt: db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()  # noqa: E731
    open_findings = select(Finding.id).where(Finding.status != FindingStatus.Closed)
    no_owner = or_(Finding.assigned_owner_email.is_(None), Finding.assigned_owner_email == "")
    open_capa = select(Capa.id).where(Capa.status != CapaStatus.Closed)
    seats = [r for r in lic.licenses(db) if r["seats"] is not None]
    out = {
        "fiscal_year": fy, "fiscal_year_end": end.isoformat(), "fiscal_year_start_month": start_month,
        "days_to_year_end": (end - now.date()).days,
        "plan": plan(fy), "next_plan": plan(fy + 1),
        "audits": {"open": count(select(Audit.id).where(Audit.status != AuditStatus.Closed)),
                   "in_review": count(select(Audit.id).where(Audit.status == AuditStatus.Review))},
        "issues": {"open": count(open_findings), "no_owner": count(open_findings.where(no_owner)),
                   "no_due_date": count(open_findings.where(Finding.target_date.is_(None)))},
        "actions": {"open": count(open_capa),
                    "no_owner": count(open_capa.where(or_(Capa.owner_email.is_(None), Capa.owner_email == ""))),
                    "no_due_date": count(open_capa.where(Capa.due_date.is_(None)))},
        "people": {"active": count(select(User.id).where(User.is_active.is_(True))),
                   "invited": len(lic.open_invitation_user_ids(db)),
                   "full_roles": [r["name"] for r in seats if r["available"] == 0]},
        "units": count(select(Organization.id).where(Organization.is_active.is_(True))),
        "areas": sorted(allowed_areas(user)),
    }
    if "backups" in out["areas"]:
        out["backups"] = _backups(db, now)
    return out
