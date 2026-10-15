# GIAW UI redesign – Prompt 0: repository discovery

**Date:** 15 October 2026 · **Commit inspected:** f5f2814 · **Code changed by this step:** none

Governing documents read: `mainBLUEPRINT.md`, `giaw-fastAPI.md` (this is the current `giaw.md`; its header still says `giaw.md` and it holds the UI-001 to UI-120 screen catalogue), `UI_REDESIGN_PROMPTS.md`, `README.md`.

Labels: **[V]** verified by running or reading code; **[A]** assumption.

## 1. Actual stack [V]

| Layer | What is really there | Playbook expectation |
|---|---|---|
| Backend | FastAPI, SQLAlchemy 2, Alembic (head `0027_gpha_templates`), Pydantic v2, MySQL 8 | Same |
| Frontend | **Vanilla JavaScript single-page app** served from `app/static` (16 JS files, about 7,900 lines; one 997-line stylesheet plus a print stylesheet). No build step, no npm, no React/TypeScript/Vite | "React + TypeScript + Vite **if confirmed**" – **not confirmed**. The playbook says keep the established stack, so the redesign stays vanilla JS |
| Icons/fonts | Bootstrap Icons and Inter, vendored locally (no CDN) | – |
| API | 374 route handlers under `/api/...` (no `/api/v1` prefix yet); errors return `{detail, errors[]}` | Blueprint asks for `/api/v1` and an error envelope (still open from the blueprint scan) |
| Tests | 127 backend tests (pytest on MySQL) pass; ruff clean. **No frontend/component tests and no end-to-end suite** in the repo; UI checks so far were ad-hoc Playwright scripts | Component and E2E tests required from Prompt 2 on |

## 2. Screens (routes) and their state [V]

The SPA has 36 sidebar views plus detail screens opened from them. Every view was opened as Super Administrator with Playwright: **no JavaScript errors and no failed API calls on any view** (screenshots kept for comparison).

| Sidebar group | Views | Status |
|---|---|---|
| Overview | Task Manager (portal), Dashboard, GPHA Workspace, Task Center, My Drafts, Governance portal, Port portfolio, Audit Committee, Analytics, Quality (QAIP) | Functional |
| Planning | Assurance Plan (+ plan detail with 10-step cycle), Audit Universe, Scheduler, Capacity & time, Professional practice | Functional |
| Audit work | Audits (+ audit detail with 13 tabs), Remediation & Follow-up, Nonconformance, Evidence requests, Audit programmes, Frameworks & controls, Criteria library | Functional |
| Risk & compliance | Risk Manager, Compliance Maps, Policy Manager, Asset Inventory | Functional (built last session) |
| Administration | Organizations, Stakeholders, Service Feedback, Automations, Configuration, Roles & permissions, Apps & customization, Audit log, Backups, Profile & users | Functional |

Nothing is mock-only. "Partial" items are listed under gaps (§6).

## 3. Why the current UI feels cumbersome [V – measured]

1. **Navigation is one long flat list.** 36 items in a 340 px sidebar that scrolls; the GPHA Workspace page repeats the same list as tiles. There are no breadcrumbs and no scope indicator (HQ / Tema / Takoradi / unit).
2. **Detail pages bury the work.** On the audit page, Overview, Independence declarations and Closure readiness are stacked *above* 13 tabs, so the tabs start below the fold (page height 2,309 px at 1440×900). The plan page is the same: KPI tiles, banner, 10-step cycle grid and distribution table, then the content.
3. **Registers are thin.** The Audits list shows only Ref, Title, Scope, Status and Approval: no lead auditor, port/entity, dates, progress or filters, and no result count.
4. **Everything loads into the browser.** Only 8 back-end lists page on the server; the rest return every row. The audit log renders 200 rows at once (12,443 px tall). Configuration is one 9,095 px page.
5. **Two table styles.** 52 places use the shared `dataTable()` helper (client-side paging, CSV/XLSX export); 33 places build tables by hand. Columns, filters and empty states differ from page to page.
6. **Low information density.** Dark theme, large cards and generous padding. The dashboard shows six number tiles, two of which are "Unfinished drafts" and "Open feedback".
7. **Theme is hard to change.** 218 hard-coded colours outside the `:root` tokens, plus 15 inline styles in JS.

## 4. Shared building blocks that already exist [V]

`el()`, `modal()`, `openForm()/mountForm()` (autosaved drafts, inline validation, server error mapping), `dataTable()`, `viewHeader()`, `badge()`, `iconBtn()`, `toast()`, `eSignModal()`, `reportStepper()`, `importDialog()`, `printNode()`, plus the apps registry (`APPS`, switched-off apps) and the permission helpers (`hasPerm`, `viewAllowed`).

Missing from the playbook's list: AppShell/TopBar split, Breadcrumbs, ScopeIndicator, FilterBar, server Pagination, column chooser and saved views, Empty/Loading/Error/Access-denied states as one component, DetailPanel (side panel), ActivityTimeline component, SaveStateIndicator outside forms, ConfirmDialog (several actions use no confirmation).

## 5. Screen catalogue (giaw-fastAPI.md §7.2) against what exists

Status: **F** functional · **P** partial · **M** missing.

| Area | Catalogue screens | Where it is today | Status |
|---|---|---|---|
| A Platform | UI-001 Sign in, 002 Dashboard, 003 My Work, 004 Notifications, 005 Global search, 006 Profile, 007 Help | Sign-in with MFA; Dashboard; Task Manager + Task Center (two "My Work" screens); notification bell drawer; top search; Profile & users; help panel (`insight.js`) | F; 003 duplicated; 004 has no full-page list; 007 has no release notes |
| B Organization & security | UI-010–018 | Organizations (flat list with port/unit fields, no tree view), users inside Profile, Roles & permissions (matrix), Audit log, Configuration | P: no tree, no access review (016), user list is not its own register |
| C Universe, risk, controls | UI-020–028 | Audit Universe, Risk Manager, Frameworks & controls, Analytics heat map | P: risk-to-plan coverage (028) only as the "high-risk not planned" banner |
| D Assurance planning | UI-030–039 | Assurance Plan list/detail, cycle, distribution, change requests, committee approval | F for workflow; P for coverage matrix (034) and resources tab (035) |
| E Engagements | UI-040–049 | Audits list/detail, engagement letter, programmes (templates), history tab | P: no create wizard, no team tab (043), no roll-forward (048) |
| F Fieldwork | UI-050–061 | RCM tab with control tests, Working Papers (GPHA template, review chain), Review Notes | P: no separate walkthrough record (053), sampling worksheet (060) |
| G Evidence | UI-070–078 | Evidence requests (PBC), working-paper files with SHA-256 | P: no Evidence Hub (070), review queue (076), access log page (078) |
| H Findings & actions | UI-080–089 | Findings tab per audit, Remediation & Follow-up register, follow-up testing, repeat findings in Analytics | P: no cross-audit findings register (080); retest is inside the action |
| I Scheduling & reporting | UI-090–105 | Scheduler, Capacity & time (timesheets), report per audit, Committee pack, Analytics, automations (scheduled jobs) | P: no timesheet approval (093), **no consolidated Unit/Port/GM reports (096–098)**, no report versions (100) |
| J Admin & integrations | UI-110–120 | Frameworks, custom fields, configuration lookups, automations, AI service with request log | P: no API client tokens (116), no system health page (118) |

## 6. Dependency map (simplified) [V]

```
api.js (fetch, CSRF, badge) ─► forms.js (openForm, drafts) ─► app.js (shell, navigate, modal, dataTable users)
                                                             ├► planning.js / plancycle.js / planchanges.js  (plans, universe, findings form)
                                                             ├► workflow.js (dataTable, reportStepper, openLink)
                                                             ├► engagement.js, entities.js, resources.js, compliance.js
                                                             ├► grc.js (risk, compliance, policies, assets, portal)
                                                             ├► roles.js (permission helpers, Roles page)  ◄─ used by every view for visibility
                                                             └► apps.js (switched-off apps), insight.js (help, analytics, import)
```

Backend modules and screens map one-to-one through `app/platform`, `app/domains/{audit,assurance,issues,grc}` and `app/services`.

## 7. Security observations [V]

- The server checks every action (permissions, tier, separation of duties, CSRF, sessions). Hiding buttons is only cosmetic.
- **Open risk:** port/unit scope is not enforced on reads yet. A Tema auditor can list Takoradi audits. This is the blueprint's first priority and also item 3 of the GPHA next steps.
- Evidence is downloaded through authorized endpoints only, with a SHA-256 check and encryption at rest. There are no public file URLs.
- No malware scanning on upload ([V] none configured). This must be reported as a dependency in Prompt 9.

## 8. Cleanup candidates (not deleted) [V]

- Two "My Work" screens: Task Manager (portal) and Task Center overlap.
- The GPHA Workspace tile page duplicates the sidebar.
- 33 hand-built tables that should move to the shared table.
- The `LEGACY_ROLES` mapping in `permissions.py` is only needed for old data. Keep it until production data is migrated.

## 9. Recommended sequence

1. **Prompt 2 – design system and shell first.** This gives the biggest visible gain with the least risk:
   - Light, dense, professional theme on CSS tokens; remove the hard-coded colours.
   - Top bar with breadcrumbs, scope chip, search, notifications and help.
   - Sidebar grouped into the 10 blueprint modules, collapsible.
   - One `DataTable` with server paging, filters, column chooser and result count.
   - Detail-page layout: title row, then tabs immediately, with summary and readiness in a right-hand panel.
2. Add server-side pagination/filter/sort to the list endpoints as each register is converted.
3. Then the screens, module by module (Prompts 3–13). Do port-scope read enforcement before or together with Prompt 4.

**Baseline test plan:** the 127 pytest tests, plus a Playwright smoke suite committed to the repo (`tests/ui/`) that opens every view, fails on any JS error or failed API call, and saves screenshots. This replaces the ad-hoc scripts.
