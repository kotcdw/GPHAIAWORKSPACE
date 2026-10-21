"""Reports app: Reports, Dashboards and Present (Reports and Dashboards & Presentations walkthroughs).

* A **report** is a saved View definition: columns, filters, period, grouping and a chart. Start from scratch
  (Create › Report) or from a template (Browse › Templates › Make a copy).
* A **dashboard** has one or more tabs, each a canvas or static layout of widgets: report widgets (table or chart),
  filter widgets (Project, Period) that apply to every report on the tab, text and images.
* A **presentation** (Present) is an ordered set of slides with the same widgets, and an optional theme.

Items are saved in a folder and published as Draft (owner only) or Active, with Public (all audit staff, "folder
users") or Private (chosen users and groups) access. Every run uses the viewer's own access, so sharing never shows
anyone data they could not see themselves. Every change is logged; items are archived, never erased.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.appconfig import cfg
from app.core.audit import log_action
from app.core.database import get_db
from app.core.deps import require_active_user
from app.core.permissions import has_perm
from app.platform.users.models import User
from app.services.reporting import views
from app.services.reporting.models import ReportItem
from app.services.reporting.sharing import check_audience, ensure_staff, ids, shared_with

router = APIRouter(prefix="/api/reporting", tags=["reporting"])

MAX_WIDGETS = 24
MAX_TABS = 10
MAX_SLIDES = 60
MAX_IMAGE = 400_000  # characters of a data: URI (about 300 KB of image)
MY_REPORTS = "My Reports"


class WidgetIn(BaseModel):
    type: Literal["report", "text", "image", "filter"]
    report_id: int | None = None
    visualization: Literal["table", "chart", "both"] = "both"
    title: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=10_000)
    image: str = Field(default="", max_length=MAX_IMAGE)
    filter: Literal["project", "period"] | None = None
    x: int = Field(default=0, ge=0, le=11)
    y: int = Field(default=0, ge=0, le=200)
    w: int = Field(default=6, ge=1, le=12)
    h: int = Field(default=4, ge=1, le=20)

    @field_validator("image")
    @classmethod
    def _image(cls, v: str) -> str:
        if v and not v.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/gif;base64,",
                                   "data:image/webp;base64,")):
            raise ValueError("images must be PNG, JPEG, GIF or WebP")
        return v


class TabIn(BaseModel):
    name: str = Field(default="Tab 1", min_length=1, max_length=80)
    widgets: list[WidgetIn] = Field(default_factory=list, max_length=MAX_WIDGETS)


class DashboardDef(BaseModel):
    layout: Literal["canvas", "static"] = "canvas"
    tabs: list[TabIn] = Field(default_factory=lambda: [TabIn()], min_length=1, max_length=MAX_TABS)


class PresentationDef(BaseModel):
    theme: Literal["Default", "Harbour", "Slate", "High contrast"] = "Default"
    slides: list[TabIn] = Field(default_factory=list, max_length=MAX_SLIDES)


class SettingsIn(BaseModel):
    show_on_browse: bool = True
    allow_dashboards: bool = True


class ItemIn(BaseModel):
    kind: Literal["report", "dashboard", "presentation"]
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=4000)
    definition: dict = Field(default_factory=dict)
    folder: str = Field(default=MY_REPORTS, min_length=1, max_length=120)
    access: Literal["Public", "Private"] = "Private"
    group_ids: list[int] = Field(default_factory=list, max_length=50)
    user_ids: list[int] = Field(default_factory=list, max_length=200)
    settings: SettingsIn = Field(default_factory=SettingsIn)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    definition: dict | None = None
    folder: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["Draft", "Active"] | None = None
    access: Literal["Public", "Private"] | None = None
    group_ids: list[int] | None = Field(default=None, max_length=50)
    user_ids: list[int] | None = Field(default=None, max_length=200)
    settings: SettingsIn | None = None


class EmailIn(BaseModel):
    user_ids: list[int] = Field(default_factory=list, max_length=200)
    group_ids: list[int] = Field(default_factory=list, max_length=50)
    message: str = Field(default="", max_length=2000)


def folders() -> list[str]:
    return [MY_REPORTS, *[f for f in (cfg("report_folders") or []) if f != MY_REPORTS]]


def _folder(name: str) -> str:
    wanted = name.strip()
    match = next((f for f in folders() if f.lower() == wanted.lower()), None)
    if match is None:
        raise HTTPException(status_code=422, detail=f"Choose a folder: {', '.join(folders())}")
    return match


def _settings(it: ReportItem) -> dict:
    try:
        return {**SettingsIn().model_dump(), **json.loads(it.settings or "{}")}
    except ValueError:
        return SettingsIn().model_dump()


def _visible(db: DBSession, user: User, it: ReportItem) -> bool:
    if it.owner_id == user.id:
        return True
    if it.archived or it.status != "Active":
        return False
    return shared_with(db, user, owner_id=it.owner_id, access=it.access, group_ids=it.group_ids,
                       user_ids=it.user_ids)


def _item(db: DBSession, user: User, item_id: int, kind: str | None = None) -> ReportItem:
    it = db.get(ReportItem, item_id)
    if it is None or (kind and it.kind != kind) or not _visible(db, user, it):
        raise HTTPException(status_code=404, detail=f"{(kind or 'item').capitalize()} not found")
    return it


def _owned(db: DBSession, user: User, item_id: int) -> ReportItem:
    it = _item(db, user, item_id)
    if it.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can change this")
    return it


def _check_widgets(db: DBSession, user: User, widgets: list[WidgetIn]) -> None:
    for w in widgets:
        if w.type == "report":
            if w.report_id is None:
                raise HTTPException(status_code=422, detail="A report widget needs a report")
            rep = _item(db, user, w.report_id, "report")
            if not _settings(rep)["allow_dashboards"] and rep.owner_id != user.id:
                raise HTTPException(status_code=422, detail=f"'{rep.name}' cannot be added to dashboards")
        if w.type == "filter" and w.filter is None:
            raise HTTPException(status_code=422, detail="Choose what the filter widget filters (Project or Period)")


def _clean_definition(db: DBSession, user: User, kind: str, definition: dict) -> dict:
    """Validate a definition for its kind; referenced reports must be ones the author can see."""
    try:
        return _validate_definition(db, user, kind, definition)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(x) for x in first.get("loc", ()))
        raise HTTPException(status_code=422, detail=f"{where}: {first.get('msg', 'invalid')}") from None


def _validate_definition(db: DBSession, user: User, kind: str, definition: dict) -> dict:
    if kind == "report":
        spec = views.SpecIn.model_validate(definition)
        views.validate(user, spec)
        return spec.model_dump(mode="json")
    if kind == "dashboard":
        d = DashboardDef.model_validate(definition)
        for t in d.tabs:
            _check_widgets(db, user, t.widgets)
        return d.model_dump(mode="json")
    d = PresentationDef.model_validate(definition)
    for s in d.slides:
        _check_widgets(db, user, s.widgets)
    return d.model_dump(mode="json")


def _ready_to_activate(it: ReportItem) -> None:
    d = json.loads(it.definition or "{}")
    if it.kind == "dashboard":
        empty = [t["name"] for t in d.get("tabs", []) if not t.get("widgets")]
        if empty:
            raise HTTPException(status_code=409, detail=f"Every dashboard tab needs content before it is activated "
                                                        f"(empty: {', '.join(empty)})")
    if it.kind == "presentation" and not d.get("slides"):
        raise HTTPException(status_code=409, detail="Add at least one slide before activating the presentation")


def _names(db: DBSession, user_ids: set[int]) -> dict[int, str]:
    return {u.id: (u.full_name or u.username)
            for u in db.execute(select(User).where(User.id.in_(user_ids or {0}))).scalars()}


def _out(db: DBSession, user: User, it: ReportItem, names: dict[int, str] | None = None) -> dict:
    names = names if names is not None else _names(db, {it.owner_id} if it.owner_id else set())
    return {"id": it.id, "kind": it.kind, "name": it.name, "description": it.description,
            "definition": json.loads(it.definition or "{}"), "status": it.status, "access": it.access,
            "group_ids": ids(it.group_ids), "user_ids": ids(it.user_ids), "folder": it.folder,
            "settings": _settings(it), "owner_id": it.owner_id, "owner": names.get(it.owner_id),
            "archived": it.archived, "can_edit": it.owner_id == user.id and not it.archived,
            "created_at": it.created_at, "updated_at": it.updated_at}


def run_report(db: DBSession, user: User, it: ReportItem, context: dict | None = None) -> dict:
    spec = views.SpecIn.model_validate(json.loads(it.definition or "{}"))
    if context:
        spec = views.with_context(views.view_for(user, spec.view), spec, **context)
    return views.run(db, user, spec)


def _run_widgets(db: DBSession, user: User, widgets: list[dict], context: dict) -> list[dict]:
    out = []
    for w in widgets:
        w = dict(w)
        if w["type"] == "report":
            try:
                rep = _item(db, user, w.get("report_id") or 0, "report")
                w.update(title=w.get("title") or rep.name, result=run_report(db, user, rep, context))
            except HTTPException as exc:
                w.update(error="This report is not shared with you" if exc.status_code == 404 else exc.detail)
        out.append(w)
    return out


def _context(audit: str | None, date_from: date | None, date_to: date | None) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="The period starts after it ends")
    return {k: v for k, v in {"audit": audit, "date_from": date_from, "date_to": date_to}.items() if v}


@router.get("/views")
def list_views(user: User = Depends(require_active_user)) -> list[dict]:
    ensure_staff(user)
    return views.catalog(user)


@router.get("/folders")
def list_folders(user: User = Depends(require_active_user)) -> list[str]:
    ensure_staff(user)
    return folders()


@router.get("/templates")
def list_templates(user: User = Depends(require_active_user)) -> list[dict]:
    ensure_staff(user)
    usable = {v.key for v in views.available(user)}
    return [t for t in views.TEMPLATES if t["definition"]["view"] in usable]


@router.post("/templates/{key}/copy", status_code=201)
def copy_template(key: str, request: Request, db: DBSession = Depends(get_db),
                  user: User = Depends(require_active_user)) -> dict:
    """Make a copy: the template becomes a Draft report in My Reports."""
    ensure_staff(user)
    t = next((x for x in views.TEMPLATES if x["key"] == key), None)
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found")
    definition = _clean_definition(db, user, "report", t["definition"])
    it = ReportItem(kind="report", name=f"Copy of {t['name']}", description=t["description"],
                    definition=json.dumps(definition), access="Private", group_ids="[]", user_ids="[]",
                    folder=MY_REPORTS, owner_id=user.id, status="Draft")
    db.add(it)
    db.flush()
    log_action(db, user_id=user.id, request=request, action=f"REPORTING_TEMPLATE_COPY {key} -> report id={it.id}")
    db.commit()
    return _out(db, user, it)


@router.post("/run")
def preview(spec: views.SpecIn, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    return views.run(db, user, spec)


@router.get("/items")
def list_items(kind: Literal["report", "dashboard", "presentation"] | None = None, archived: bool = False,
               folder: str | None = Query(None, max_length=120),
               scope: Literal["all", "mine", "shared"] = "all",
               db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> list[dict]:
    ensure_staff(user)
    stmt = select(ReportItem).where(ReportItem.archived.is_(archived)).order_by(ReportItem.name)
    if kind:
        stmt = stmt.where(ReportItem.kind == kind)
    if folder:
        stmt = stmt.where(ReportItem.folder == folder)
    rows = [it for it in db.execute(stmt).scalars() if _visible(db, user, it)]
    if scope == "mine":
        rows = [it for it in rows if it.owner_id == user.id]
    elif scope == "shared":
        rows = [it for it in rows if it.owner_id != user.id and _settings(it)["show_on_browse"]]
    names = _names(db, {it.owner_id for it in rows if it.owner_id})
    return [_out(db, user, it, names) for it in rows]


@router.post("/items", status_code=201)
def create_item(payload: ItemIn, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    definition = _clean_definition(db, user, payload.kind, payload.definition)
    groups, users = check_audience(db, payload.access, payload.group_ids, payload.user_ids)
    it = ReportItem(kind=payload.kind, name=payload.name.strip(), description=payload.description.strip(),
                    definition=json.dumps(definition), access=payload.access, group_ids=json.dumps(groups),
                    user_ids=json.dumps(users), folder=_folder(payload.folder),
                    settings=json.dumps(payload.settings.model_dump()), owner_id=user.id, status="Draft")
    db.add(it)
    db.flush()
    log_action(db, user_id=user.id, request=request, action=f"REPORTING_CREATE {it.kind} id={it.id} {it.name}")
    db.commit()
    return _out(db, user, it)


@router.get("/items/{item_id}")
def get_item(item_id: int, db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    return _out(db, user, _item(db, user, item_id))


@router.patch("/items/{item_id}")
def update_item(item_id: int, payload: ItemUpdate, request: Request, db: DBSession = Depends(get_db),
                user: User = Depends(require_active_user)) -> dict:
    """Edit, or Publish: Save → Draft / Save → Activate with name, description, folder, access and settings."""
    ensure_staff(user)
    it = _owned(db, user, item_id)
    if it.archived:
        raise HTTPException(status_code=409, detail="Archived items cannot be changed; restore it first")
    changes = list(payload.model_dump(exclude_unset=True))
    if payload.definition is not None:
        it.definition = json.dumps(_clean_definition(db, user, it.kind, payload.definition))
    if payload.access is not None or payload.group_ids is not None or payload.user_ids is not None:
        access = payload.access or it.access
        groups, users = check_audience(db, access,
                                       payload.group_ids if payload.group_ids is not None else ids(it.group_ids),
                                       payload.user_ids if payload.user_ids is not None else ids(it.user_ids))
        it.access, it.group_ids, it.user_ids = access, json.dumps(groups), json.dumps(users)
    if payload.name is not None:
        it.name = payload.name.strip()
    if payload.description is not None:
        it.description = payload.description.strip()
    if payload.folder is not None:
        it.folder = _folder(payload.folder)
    if payload.settings is not None:
        it.settings = json.dumps(payload.settings.model_dump())
    if payload.status is not None:
        if payload.status == "Active":
            _ready_to_activate(it)
        it.status = payload.status
    log_action(db, user_id=user.id, request=request,
               action=f"REPORTING_UPDATE {it.kind} id={it.id} [{', '.join(changes)}] "
                      f"status={it.status} access={it.access}")
    db.commit()
    return _out(db, user, it)


@router.delete("/items/{item_id}")
def archive_item(item_id: int, request: Request, db: DBSession = Depends(get_db),
                 user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    it = _owned(db, user, item_id)
    it.archived = True
    log_action(db, user_id=user.id, request=request, action=f"REPORTING_ARCHIVE {it.kind} id={it.id} {it.name}")
    db.commit()
    return _out(db, user, it)


@router.post("/items/{item_id}/restore")
def restore_item(item_id: int, request: Request, db: DBSession = Depends(get_db),
                 user: User = Depends(require_active_user)) -> dict:
    ensure_staff(user)
    it = _owned(db, user, item_id)
    it.archived = False
    log_action(db, user_id=user.id, request=request, action=f"REPORTING_RESTORE {it.kind} id={it.id}")
    db.commit()
    return _out(db, user, it)


@router.get("/items/{item_id}/run")
def run_item(item_id: int, audit: str | None = Query(None, max_length=20), date_from: date | None = None,
             date_to: date | None = None, db: DBSession = Depends(get_db),
             user: User = Depends(require_active_user)) -> dict:
    """Run the item now with the viewer's access. Dashboard and presentation filters (Project, Period) apply to
    every report widget that supports them."""
    ensure_staff(user)
    it = _item(db, user, item_id)
    context = _context(audit, date_from, date_to)
    out = _out(db, user, it)
    d = json.loads(it.definition or "{}")
    if it.kind == "report":
        out["result"] = run_report(db, user, it, context)
    elif it.kind == "dashboard":
        out["tabs"] = [{**t, "widgets": _run_widgets(db, user, t.get("widgets", []), context)}
                       for t in d.get("tabs", [])]
    else:
        out["slides"] = [{**s, "widgets": _run_widgets(db, user, s.get("widgets", []), context)}
                         for s in d.get("slides", [])]
    out["context"] = context
    return out


@router.post("/items/{item_id}/email")
def email_item(item_id: int, payload: EmailIn, request: Request, db: DBSession = Depends(get_db),
               user: User = Depends(require_active_user)) -> dict:
    """Email: notify chosen users and groups (in the app, and by e-mail when mail is set up). Only people the item
    is shared with can be sent it; each opens it with their own access."""
    from app.platform.groups.models import UserGroupMember
    from app.platform.notifications.service import notify

    ensure_staff(user)
    it = _item(db, user, item_id)
    if it.status != "Active":
        raise HTTPException(status_code=409, detail="Activate it before sending it")
    recipients = set(payload.user_ids)
    if payload.group_ids:
        recipients |= set(db.execute(select(UserGroupMember.user_id)
                                     .where(UserGroupMember.group_id.in_(payload.group_ids))).scalars())
    recipients.discard(user.id)
    if not recipients:
        raise HTTPException(status_code=422, detail="Choose who to send it to")
    blocked = []
    sent = 0
    for uid in sorted(recipients):
        target = db.get(User, uid)
        if target is None or not target.is_active or not _visible(db, target, it):
            blocked.append(uid)
            continue
        body = (payload.message.strip() + "\n\n" if payload.message.strip() else "") + \
            f"{it.kind.capitalize()} '{it.name}' shared by {user.full_name or user.username}."
        if notify(db, uid, f"{it.kind.capitalize()}: {it.name}"[:255], body, link_type="report_item",
                  link_id=it.id) is not None:
            sent += 1
    if blocked and not sent:
        raise HTTPException(status_code=422, detail="It is not shared with the people chosen; change its access first")
    log_action(db, user_id=user.id, request=request,
               action=f"REPORTING_EMAIL {it.kind} id={it.id} sent={sent} not_shared={len(blocked)}")
    db.commit()
    return {"sent": sent, "not_shared": len(blocked)}


@router.get("/items/{item_id}/export")
def export_report(item_id: int, request: Request, fmt: Literal["csv", "xlsx"] = Query("xlsx", alias="format"),
                  db: DBSession = Depends(get_db), user: User = Depends(require_active_user)) -> Response:
    """Export a report's rows (CSV or Excel) with the viewer's access; cells are made formula-safe."""
    from app.services.documents.excel import safe_row, workbook, xlsx_response

    ensure_staff(user)
    if not has_perm(user, "data.export"):
        raise HTTPException(status_code=403, detail="Your role does not allow exporting data")
    it = _item(db, user, item_id, "report")
    spec = views.SpecIn.model_validate({**json.loads(it.definition or "{}"), "limit": views.MAX_ROWS})
    res = views.run(db, user, spec)
    head = [c["label"] for c in res["columns"]]
    body = [[r.get(c["key"]) for c in res["columns"]] for r in res["rows"]]
    log_action(db, user_id=user.id, request=request,
               action=f"REPORTING_EXPORT report id={it.id} format={fmt} rows={len(body)}")
    db.commit()
    stem = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in it.name).strip() or "report"
    if fmt == "xlsx":
        meta = [["Source", res["source"]], ["Filters", res["filters_text"]], ["Period", res["period_text"]],
                ["Access", res["scope_text"]], ["Generated", res["generated_at"]]]
        return xlsx_response(workbook([("Report", head, body), ("About", ["Item", "Value"], meta)], title=it.name),
                             f"{stem}.xlsx")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(safe_row(head))
    for row in body:
        w.writerow(safe_row(row))
    return Response(content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(stem)}.csv"})
