# GIAW UI redesign – Prompt 2: design system and application shell

**Date:** 15 October 2026 · **Stack unchanged:** FastAPI + MySQL backend; plain JavaScript single-page front end (no React, no build step).

## 1. What changed

| Area | Before | Now |
|---|---|---|
| Theme | Dark; 218 colours hard-coded outside the theme | Light, dense GPHA theme. **Every colour comes from tokens in `:root`** (`app/static/css/styles.css`). The only literal colours left are on the sign-in page, which keeps its approved look |
| Top bar | Search and bell only; brand in the sidebar | Navy bar: GPHA logo and name, **scope chip** (workplace, role, approval level), search, help, notifications, user and role, sign out |
| Navigation | 36 links in one list | Grouped into the blueprint modules (Home; Universe, risk & controls; Assurance planning; Engagements & fieldwork; Evidence; Findings & remediation; Resources & time; Reporting & analytics; Organization & access; Integrations & operations). Groups collapse; the choice is remembered on the device. The group of the open page always opens |
| Breadcrumbs | None | "Module / Page" on every page; "Module / Page / Record" on record pages (audit, plan) |
| Registers | Lists loaded whole into the browser | `serverTable`: server paging (10/25/50/100), sorting, search, filter dropdowns, Clear, result count, column chooser, Excel/CSV export through the same server query. Used on **Audits** and **Audit log**; the other registers move to it module by module |
| Record page | Summary cards stacked above 13 tabs | `recordLayout`: title row with reference, status, actions and utility links (Review notes, Time, Tasks, History, Approvals); **tabs directly under the title**; summary and close-out readiness in a right-hand panel. Used on the **audit page** |
| States | Mixed | One set: loading, empty, filtered-empty, error (with retry), access denied |

## 2. Tokens

| Group | Tokens |
|---|---|
| Surfaces | `--bar`, `--bar-2`, `--bar-text`, `--bar-muted`, `--bg`, `--panel`, `--panel-2`, `--panel-3`, `--field-bg` |
| Lines and text | `--border`, `--border-strong`, `--text`, `--text-2`, `--muted`, `--on-accent` |
| Meaning | `--accent*`, `--ok*`, `--warn*`, `--danger*`, `--purple*`, `--neutral-soft`. Each has a base, `-text`, `-soft` (background) and `-line` (border) |
| Shape and focus | `--radius`, `--radius-sm`, `--shadow`, `--shadow-color`, `--overlay`, `--focus` |
| Scale | `--fs-xs`…`--fs-xl` (11.5–18 px), `--sp-1`…`--sp-5` (4–24 px, 8 px rhythm), `--sidebar-w` 232 px, `--topbar-h` 48 px |

To change the brand colour or density, change the tokens. No other file needs editing.

## 3. Shared components (`app/static/js/ui.js`)

| Component | Use |
|---|---|
| `setCrumbs(items)`, `navCrumbs(view)`, `recordCrumbs(view, record)` | Breadcrumbs |
| `statusBadge(value)` | Status label; the text always carries the meaning, colour only supports it |
| `emptyState`, `loadingState`, `errorState(err, retry)`, `deniedState` | Page and panel states. `errorState` shows the access-denied state for HTTP 403 |
| `confirmDialog({title, text, danger, reason})` | Returns a promise of `{ok, reason}`. With `reason: true` it needs at least 10 characters |
| `detailPanel({title, body, footer})` | Right-hand side panel. Escape or the scrim closes it, and focus returns to where it was |
| `activityTimeline(items)` | History list |
| `saveState()` | "Unsaved changes / Saving… / Saved / Not saved" |
| `formSection(title, …)` | Titled fieldset for long forms. Existing `openForm` keeps autosave drafts, inline validation and server error mapping |
| `filterBar({filters, onChange})` | Search, dropdowns, Clear and count |
| `serverTable({url, columns, filters, defaultSort, exportName, onRow})` | Server register (see §4) |
| `recordLayout({title, ref, status, actions, utility, tabs, side, onTab})` | Record page. Tabs support arrow keys |
| `initNavGroups`, `initScopeChip`, `fmtDay`, `Prefs` | Shell helpers. `Prefs` keeps per-device choices (collapsed groups, hidden columns, page size) and fails safely when storage is blocked |

## 4. Register API contract (`app/core/paging.py`)

`GET /api/<register>?page=1&page_size=25&sort=-updated_at&q=text&<filters>` returns:

```json
{"items": [...], "total": 123, "page": 1, "page_size": 25, "sort": "-updated_at"}
```

- `page_size` must be at most 100. Unknown `sort` keys, `page=0` and oversize pages are refused with 422; they are not ignored.
- **Authorization happens before paging.** Rows the user may not read are removed first, so counts and pages never reveal hidden records.
- Export fetches the same query page by page, so it carries the same permissions and filters.

New endpoints:

| Endpoint | Rows | Filters | Sort keys |
|---|---|---|---|
| `GET /api/audits/register` | Ref, title, stream, port, plan, lead, planned dates/quarter, budget hours, status, approval, open/total findings, working papers, report status, updated | `q`, `status`, `audit_type`, `port_id`, `plan_id`, `mine` | ref, title, status, audit_type, port, plan, lead, planned_start, open_findings, updated_at |
| `GET /api/audit-logs/register` (Admin) | When, user (name), IP, action | `q`, `user_id`, `date_from`, `date_to` | timestamp, user |

The audit register still applies the existing record-access rules in Python before paging; they become SQL filters when port/unit scope is enforced (Prompt 4). The audit log pages in SQL. The old list endpoints are unchanged, so nothing else breaks.

## 5. Tests actually run

| Suite | Result |
|---|---|
| Backend pytest (MySQL), including new `tests/test_registers.py` (paging, sort, search, filters, 422s, auditee sees only assigned audits, audit log admin-only) | **130 passed** |
| Browser tests `tests/ui/test_ui_smoke.py` (Chromium): every visible screen opens with no JavaScript error and no failed API call; breadcrumbs, group collapse surviving reload, scope chip with Escape; register search, filtered empty state, Clear, sort, column chooser, page size; record page tabs visible without scrolling, arrow-key tabs; confirm dialog, side panel, states, save indicator; tablet 768 px and phone 375 px with no sideways scroll | **7 passed** |
| `ruff check .` and `node --check` on every script | Clean |

Screenshots of all 36 screens at 1440 px, plus the audits register at 768 px and 375 px, came from the browser run. They are not committed.

## 6. Known gaps and next steps

- **Other registers:** about 30 lists still use the older client-side table. Each moves to `serverTable` with its module's prompt (4–13).
- **Plan page:** has breadcrumbs but not yet the record layout (Prompt 6).
- **Scope chip:** shows the workplace, but it does not restrict records. Port/unit read enforcement is Prompt 4.
- **Saved views:** the existing `savedViewsControl` is not yet wired into `serverTable`.

**Acceptance: PASS.** The shared shell and components work, all existing routes still open, and the tests above pass.

**Next: Prompt 3** (dashboard, My Work, notifications, search, profile, help).
