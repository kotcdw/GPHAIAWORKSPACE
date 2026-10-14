# GPHA AUDIT WORKSPACE — ProPlan (Modules, Phases, Build Steps)

Reference: `mainPlan.md` (merger of AVCS + FreeQMS extractions into a modular FastAPI / MySQL app).

**Stack:** FastAPI + SQLAlchemy 2 + MySQL 8 (Docker) + Alembic + vanilla-JS SPA.
**Gate:** `pytest` (green, MySQL-backed) + `ruff` (line-length 120, B008/UP042 ignored) + manual smoke on `127.0.0.1:8001`.

---

## Module Map (target layout)

```
app/
  core/
    config.py          # settings (GPHA_DATABASE_URL default -> MySQL)
    database.py        # engine, session, Base, Dialect helpers
    security.py        # bcrypt, tokens, CSRF helpers
    deps.py            # auth deps + require_role + require_module_tier
    audit.py           # immutable audit_log writer
    enums.py           # shared enums (moved from models.py)
    refs.py            # auto-reference-number generator service
    history.py         # record_history + cycle-aware trail writer
    tasksvc.py         # task auto-generation / assignment service
    approvalsvc.py     # e-sign cycle engine (password attestation)
  modules/
    auth/              # register, login, logout, me, profile, password; AVCS UI + FreeQMS register fields
    users/             # user admin + roles + per-module permission tiers
    tasks/             # Task Center (assigned-to-me / by-me / closed)
    audits/            # audits + working_papers + findings + e-closure
    nonconformances/   # NC records + dispositions
    capa/              # corrective/preventive actions
    organizations/     # third parties / auditee entities
    stakeholders/      # customers / service users
    service_feedback/  # complaints register
    history/           # per-record + module-wide history views
    backups/           # snapshot + scheduled backup admin
  approvals/ (subresource of core + modules)
  main.py              # explicit router registry + lifespan (backup scheduler, uploads)
  static/
    index.html         # AVCS auth section + SPA shell + nav
    css/styles.css     # AVCS auth styles + Bootstrap-4 look components
    css/styles_print.css
    js/api.js          # fetch wrapper + CSRF
    js/app.js          # SPA views, renderers, task center, e-sign modal
    img/loginLogo.jpg, loginPattern.jpg
```

Per-module file convention: `models.py`, `schemas.py`, `router.py`, optional `service.py`.

---

## PHASE 0 — Foundations & MySQL migration (no feature work)

**Goal:** App boots on MySQL with all existing 18 tests green.

### Steps
- [x] **0.1** Add `PyMySQL>=1.1` to `pyproject.toml`; `uv lock` / sync env.
- [x] **0.2** Create `docker-compose.yml`: MySQL 8.0, db `gpha_workspace`, user `gpha` (+ password from `.env`), charset `utf8mb4` / collation `utf8mb4_unicode_ci`, port 3306, named volume, healthcheck.
- [x] **0.3** Update `app/config.py`: default `database_url = mysql+pymysql://gpha:...@127.0.0.1:3306/gpha_workspace?charset=utf8mb4`; keep `GPHA_` env overrides; add optional `GPHA_TEST_DATABASE_URL`.
- [x] **0.4** Update `.env.example` + README: DSN, `docker compose up -d`, bootstrap usage.
- [x] **0.5** Rewrite `app/database.py`: drop SQLite `check_same_thread` + PRAGMA hook; add `pool_pre_ping=True`, `pool_recycle=3600`; keep `Dialect`-aware `_is_sqlite` flag.
- [x] **0.6** Make Alembic **dialect-aware**:
  - `alembic/env.py`: `render_as_batch` only when SQLite (already the case).
  - Rewrite `0001_initial` append-only triggers using `op.get_bind().dialect.name` (SQLite `RAISE(ABORT)`) vs MySQL `SIGNAL SQLSTATE '45000' ... FOR EACH ROW`).
- [x] **0.7** New migration **`0002_module_tables`**:
  - Tables: `organizations`, `stakeholders`, `service_feedback`, `nonconformances`, `capa`, `tasks`, `record_history`, `approval_cycles`.
  - `audits` += `approval_status` (nullable) + optional `organization_id` FK.
  - Auto-reference columns where needed (`nc_ref`, `capa_ref`, `org_ref`, `sh_ref`, `sf_ref`) + unique indexes.
  - Enums as `VARCHAR + CHECK` (as today).
- [x] **0.8** Rewrite `tests/conftest.py`:
  - Build test DSN (`GPHA_TEST_DATABASE_URL` or derived `gpha_workspace_test`).
  - Session-autouse fixture: connect to server, `DROP/CREATE DATABASE gpha_workspace_test`, then `alembic upgrade head`.
- [x] **0.9** `scripts/init_db.py`: run migrations + seed admin on MySQL.
- [x] **0.10** Verify: `docker compose up -d && uv run python -m scripts.init_db && uv run pytest`.

> **Phase 0 notes (deviations):** local XAMPP MySQL already owns port 3306, so the
> container binds **3307** (`docker-compose.yml` + config defaults + conftest updated).
> MySQL 8 enables binlog by default, so the container now sets
> `--log-bin-trust-function-creators=1` (else the app user cannot create triggers).
> `test_audit_log_cannot_be_updated_or_deleted` expects `IntegrityError` **or**
> `OperationalError` because MySQL's `SIGNAL` surfaces as errno 1644
> (`OperationalError`), not `IntegrityError`. Result: migrations + seed on MySQL,
> **18/18 tests green**, live smoke (login/create/delete audit) on port 8001.

---

## PHASE 1 — Refactor to modular monolith (no behavior change)

**Goal:** existing features (auth, users, audits, findings, working papers, logs) live in feature packages; 18 tests still green.

### Steps
- [x] **1.1** Create `app/core/`; move `config`, `database`, `security`, `deps`, `audit` into it (update imports).
- [x] **1.2** Split `models.py` -> `core/enums.py` (Role/AuditStatus/RiskRating/FindingStatus + new module enums) and per-module `models.py`.
- [x] **1.3** Split `schemas.py` -> per-module `schemas.py` (moving Auth, Users, Audits, Findings, WorkingPaper, AuditLog schemas).
- [x] **1.4** Move `routers/*` -> `modules/auth/router.py`, `modules/users/router.py`, `modules/audits/router.py` (+ findings, working_papers moved under audits). Keep route paths unchanged (`/api/...`).
- [x] **1.5** Add `history/` module reading existing `audit_logs` (rename SQL-side? no — keep table `audit_logs`; add `record_history` in 0002).
- [x] **1.6** Update `app/main.py` to include all module routers via explicit registry.
- [x] **1.7** Run `pytest` + `ruff`; fix import regressions.

> **Phase 1 notes:** moved `config/database/security/deps/audit` into `app/core/`,
> split models into `modules/{users,auth,audits,history}/models.py` and schemas
> into per-module files, moved routers into module packages. Cross-module ORM
> relationships use string targets resolved via the mapper registry (with
> `TYPE_CHECKING` imports for ruff), so no import cycles. Package `__init__.py`
> files are docstring-only; `main.py` imports routers explicitly. Result:
> **18/18 tests green**, `ruff` clean, live smoke (login/create/list/delete) on 8001.

---

## PHASE 2 — Core engines (shared services)

**Goal:** reusable building blocks all modules consume.

### Steps
- [x] **2.1** `core/refs.py`: sequence-based reference generator (`NC-0001`, `CAPA-0001`, `ORG-`, `SH-`, `SF-`) safe under concurrency.
- [x] **2.2** `core/history.py`: `log_record_history(db, *, record_type, record_id, user, action, cycle_no=None)` writing to `record_history`; helper for "since last cycle" filtering.
- [x] **2.3** `core/tasksvc.py`: `create_task(...)` + `auto_tasks(record_type, record, action)` — system tasks on record create / owner change.
- [x] **2.4** `core/approvalsvc.py`: `sign(...)` — verify password via bcrypt, write `approval_cycles` entry (decision/comment/cycle_no, attestation only), advance cycle, optional status transition callback.
- [x] **2.5** `core/deps.py`: add `require_module_tier(module, *minimum_roles)` dependency; wire to user.role.
- [x] **2.6** Unit tests for refs/history/tasks/approvals logic.

> **Phase 2 notes:** added a `reference_sequences` table (migration `0003`)
> seeded with `ORG/SH/NC/CAPA/SF`, plus ORM models `ReferenceSequence` (core),
> `Task` (tasks), `ApprovalCycle` (approvals), `RecordHistory` (history). New
> module enums live in `core/enums.py`. `sign()` coerces the decision to
> `ApprovalDecision`; a rejection opens the next cycle. **24 tests pass** (6 new),
> ruff clean, migration applied to dev DB.

---

## PHASE 3 — New module backends 1: records

**Goal:** full CRUD + workflows for the five record modules.

### Steps
- [x] **3.1** `modules/organizations/` — models (name, category, contact, status Pending/Approved, evaluation_end_date, approved_by/at), schemas, router (list/search/filter, create, get, patch, delete admin, `/{id}/copy`, `/{id}/approve` via approvalsvc, `/{id}/set_pending`).
- [x] **3.2** `modules/stakeholders/` — same core CRUD w/o approval cycle (name, type, contact, status).
- [x] **3.3** `modules/nonconformances/` — models (ref, title, description, severity, disposition, audit_id FK, owner_email, status Open/Remediating/Closed, linked_nc/capa), router + copy + link + auto task.
- [x] **3.4** `modules/capa/` — models (ref, title, root_cause, corrective/preventive plans, effectiveness_check, source polymorphic link, severity, disposition status, due_date, closed_by/at), router + copy + link + e-sign closure.
- [x] **3.5** `modules/service_feedback/` — models (ref, subject, description, received_date, source, status, owner, linked_nc/capa), router + copy + link + auto task.
- [x] **3.6** Extend `modules/audits/` — `approval_status` field surfaced in schema/router; `/{id}/close` via approvalsvc (e-closure) transitioning to Closed.

> **Phase 3 notes:** all five record modules built as `models.py` + `schemas.py` +
> `router.py`. Every write path writes both the global `audit_logs` and the
> per-record `record_history`. Ref numbers come from `next_reference`
> (`ORG/SH/NC/CAPA/SF`). Auto tasks raised on NC/CAPA/service-feedback create.
> E-sign approve on organizations, e-sign close on CAPA (also closes the linked
> NC) and audits. Cross-module FKs (NC↔CAPA) are two independent MANYTOONE
> relationships (they cannot be a `back_populates` pair). New third client fixture
> `client2` added for two-user tests; MySQL REPEATABLE-READ snapshot handled via
> `db.rollback()`. **30 tests pass**, ruff clean, live smoke green (create all
> five records; e-sign approve org → Approved; bad password → 400).

---

## PHASE 4 — New module backends 2: tasks, approvals, backups

**Goal:** cross-cutting engines exposed as routes.

### Steps
- [x] **4.1** `modules/tasks/router.py`: `GET /api/tasks?assigned_to_me/by_me/status`, `POST` (assign), `PATCH` (status/due/notes), `GET /api/tasks/{id}`.
- [x] **4.2** `modules/approvals/router.py`: `POST /api/approvals/sign` `{record_type, record_id, decision, comment, password}`; verify + attest + transition; reject path.
- [x] **4.3** `modules/history/router.py`: `GET /api/records/{type}/{id}/history` (optional `?cycle=` filter); `GET /api/records/{type}/{id}/approval-cycles`.
- [x] **4.4** `modules/backups/`: `POST /api/admin/backup` (snapshot MySQL via `mysqldump`/`flush tables` or SQLAlchemy copy to `backups/`), `GET /api/admin/backups` (list), retention purge; scheduler in `main.py` lifespan (daily).
- [x] **4.5** Wire new routers in `main.py`.
- [x] **4.6** Backend tests for all new endpoints.

> **Phase 4 notes:** `record_history`/`approval_cycles` readers exposed under
> `/api/records/...` (new `records_router`). Task Center enforces "not your task"
> (403) unless Admin/assignee/assignor; closing stamps `completed_at`. Generic
> `/api/approvals/sign` attests against any record (module routes add their own
> status transitions). Backups prefer `mysqldump` (native, restorable) and fall
> back to a portable JSON dump; retention keeps the newest `GPHA_BACKUP_RETENTION`
> (default 7). A daily scheduler runs in the lifespan when
> `GPHA_BACKUP_INTERVAL_HOURS > 0` (tests set it to 0). **33 tests pass**, ruff
> clean, live smoke green (task create, generic sign cycle 1, audit history, backup
> snapshot 11.5 KB).

---

## PHASE 5 — Frontend shell & shared UI

**Goal:** FreeQMS-style workspace UI around the existing AVCS auth.

### Steps
- [x] **5.1** `index.html`: expand `#sidebarNav` (order: Dashboard, Task Center, Audits, CAPA, Nonconformance, Organizations, Stakeholders, Service Feedback, Profile, Users, Audit Log, Backups); keep AVCS auth section untouched; add icons (bootstrap-icons) + `#toastHost`/`#modalRoot` hosts + print stylesheet link.
- [x] **5.2** `styles.css`: add Bootstrap-4 look — `.view-head`, `.toolbar`, table card, `.tabs`/`.tab`, `.kv`, `.ref`, `.pill`, badges, e-sign `.modal`, `.toast`, `.empty`, `.comment-row`, `.stat`/`.grid`; keep existing `auth-*`/`ant-*`/`.sign-in-div` rules.
- [x] **5.3** `css/styles_print.css` + `@media print` wiring (loaded `media="print"`) for detail pages (print-to-PDF).
- [x] **5.4** `js/app.js`: shared helpers — `renderList(module)`, `openRecord()` detail tabs, `badge()`, `toast()`, `modal()`, `field()`/`inputFor()`/`readForm()`, `eSignModal()`, `tabBar()`, `linkPicker()`.
- [x] **5.5** `navigate()` registry: map nav buttons to module renderers (generic + special-case dashboard/tasks/audits/profile/users/logs/backups).

> **Phase 5 notes:** the SPA (`app.js`, 1155 lines) was rewritten with a `MODULES`
> registry driving generic list/detail/create for the five record modules, plus
> bespoke views for dashboard, Task Center, audits (findings + working papers),
> profile, users, audit log and backups. AVCS auth handlers preserved untouched.
> Verified with `node --check` and a live smoke on 8001: static assets serve;
> login works; every API the SPA calls responds with the expected field shapes
> (`*_ref`, `source_type`/`source_id`, `system_generated`, history `user_id`/
> `cycle_no`, approval-cycle `decision`/`approver_id`, backup `size_bytes`).
> **Fixed two blocking JS syntax errors** (unbalanced `card.append(el("table"...))`
> in `renderList` and `renderPapers`) that would have prevented the whole bundle
> from parsing, plus a `canWriteModule()` logic bug that hid write actions from
> Auditors, and added the missing `.form-grid` CSS rule.

---

## PHASE 6 — Frontend feature screens

**Goal:** every module has list + detail + workflow.

### Steps
- [x] **6.1** Task Center view: 3 tabs (Assigned to me / Assigned by me / Closed), row status changes, auto-task badges.
- [x] **6.2** List views for each module: search/filter toolbar, create button (role-gated), status badges, click-to-detail.
- [x] **6.3** Detail views: Information / Tasks / History / Approval Cycles tabs (+ Audit: Findings & Working Papers; CAPA/NC specifics in Information). Copy-record + link pickers.
- [x] **6.4** E-sign modal: password field, comment, Approve; signs via module path or generic `/api/approvals/sign`; success -> toast + refresh.
- [x] **6.5** Dashboard: multi-module stats (audits open/total, NC open, CAPA open, feedback open, my tasks) + recent audits + my open tasks.
- [x] **6.6** Register form: FreeQMS layout (Email, Password + Django-style hints, Confirm, First Name, Last Name, Company) inside AVCS shell -> pending-admin message. Backend extended (`users.first_name/last_name/company`, migration `0004`).
- [x] **6.7** Profile/Users/Log screens: refreshed to new card/table styles. Per-module tier editing **deferred** (role-based access retained; `require_module_tier` left ready for the matrix).

> **Phase 6 notes:** most feature screens were delivered as part of the Phase 5
> rewrite; this phase added the FreeQMS register fields end-to-end. `RegisterRequest`
> now accepts `first_name`/`last_name`/`company`; `full_name` is derived from the
> names when left blank. `users` gained `first_name`, `last_name`, `company`
> (migration **`0004_user_profile_fields`**, applied to the dev DB), surfaced in
> `UserOut`/`UserCreate`/`UserUpdate` and the admin Users screen. Register handler
> validates password match + min length and shows Django-style guidance.
> Live smoke: register -> pending (login 403) -> admin approves -> login as
> Auditee; first/last/company persisted and `full_name` derived. **33 tests pass**,
> ruff clean, `node --check` clean.

---

## PHASE 7 — Hardening & delivery

**Goal:** releasable, documented, fast.

### Steps
- [x] **7.1** Full test pass: `uv run pytest` (MySQL test DB) — all suites green (33 → 35 tests, added 2 for FreeQMS register fields).
- [x] **7.2** `uv run ruff check .` clean.
- [x] **7.3** Manual smoke on port 8001: seed admin login, register (pending) + approve, create org/stakeholder/NC/CAPA/feedback, e-sign audit closure, confirm task auto-generation + history + printable detail; all API shapes verified.
- [x] **7.4** Seed data script (optional `scripts/seed_demo.py`) for realistic demo records.
- [x] **7.5** Update README: architecture, module map, run/test instructions, MySQL bootstrap, backup/restore notes.
- [x] **7.6** Update this doc checkboxes as completed; `mainPlan.md` remains as reference (merger plan).

> **Phase 7 notes:** README and .env.example updated to cover the modular MySQL
> app, backups, and the new register fields; `.gitignore` now ignores `backups/`.
> Two new tests exercise FreeQMS fields (register captures them; admin create also
> persists them) and use `db.rollback()` to correctly read rows written by the
> request (MySQL REPEATABLE-READ). **35 tests pass**, ruff clean. Live smoke
> verified end-to-end (pending register → admin approve → successful login).

---

## PHASE 8 — Controls hardening (scan findings, 13 Oct 2026)

**Goal:** close the defects and control weaknesses found by the full project scan.

### Steps
- [x] **8.1** Config: `.env` no longer overrides MySQL with SQLite; migration `0002` made SQLite-safe (`batch_alter_table`).
- [x] **8.2** Workflow: audits start `Planned`; `Closed` only via e-signed `/close` from `Review`; `/in-approval` only from `Review`; closed audits/findings/papers locked. CAPA closes only via e-sign from `Review`.
- [x] **8.3** Segregation of duties: the record's preparer (`created_by`) cannot e-sign it (audit close, CAPA close, org approve, generic sign; generic sign 404s on unknown records).
- [x] **8.4** Evidence retention: deletes allowed only for untouched records (Planned/Open/Pending, unlinked, never signed); working papers are *withdrawn* (soft delete, file kept); users with activity cannot be deleted (deactivate instead).
- [x] **8.5** Migration `0005_controls_hardening`: `audit_auditees`, user lockout columns, working-paper soft-delete/encryption/SHA-256 columns, append-only triggers on `record_history` and `approval_cycles`.
- [x] **8.6** Auditee scoping (`app/core/access.py`): auditees see only assigned audits (+ their findings/papers/history), NCs/CAPA/feedback they own or that hang off an assigned audit, never organizations/stakeholders; Task Center scoped to participants. UI: "Auditees with access" card on the audit page.
- [x] **8.7** Authentication: lockout after `GPHA_LOGIN_MAX_ATTEMPTS` (423), admin unlock, password change / deactivation / role change / reset revoke sessions.
- [x] **8.8** Data at rest: backups encrypted (`*.enc`, sessions excluded, mysqldump password via env), `scripts/restore_backup.py`; working papers streamed, extension allow-list, SHA-256, encrypted; `cryptography` dependency.
- [x] **8.9** Production guard (`GPHA_ENVIRONMENT=production` refuses insecure defaults), security headers, init_db masks the DB password.
- [x] **8.10** Tests: `tests/test_controls.py` (+ updated suites) — 54 tests green on MySQL; ruff clean.

> **Phase 8 notes:** closing an audit now needs **two people** (preparer + a
> different Admin). The bootstrap admin alone cannot sign off audits it created
> — create a second Admin account. Not covered by code: malware scanning of
> uploads (hook point is `upload_working_paper`) and an object-storage backend.

---

## PHASE 9 — Planning & risk-control layer (HighBond flow)

**Goal:** Assurance Plan -> projects -> objectives -> risks -> controls -> tests -> issues -> actions.

### Steps
- [x] **9.1** Migration `0006_planning_rcm`: `locations`, `entity_units`, `assurance_plans`, `plan_engagements`, `objectives`, `risks`, `controls`, `risk_controls`, `control_tests`; `audits.plan_id/entity_unit_id`; finding issue attributes + control/test links; `AP/OBJ/RSK/CTL/TST` sequences.
- [x] **9.2** `modules/planning`: universe (Admin-managed), Assurance Plan CRUD, coverage summary, e-signed approval with SoD, reopen/close, engagements, *start engagement -> audit project*.
- [x] **9.3** `modules/rcm`: objectives/risks/controls with many-to-many mapping (same-audit only), inherent/residual ratings, control effectiveness, tests with sampling guidance + seeded random selection, completion rules, e-signed review (reviewer != performer, reject = rework), raise issue from ineffective test, raise CAPA from issue, deletion only without evidence, matrix locked when audit closed.
- [x] **9.4** Audit close gate: no unreviewed control tests; closing stamps the entity unit's `last_audited_at`.
- [x] **9.5** Issues: criteria/condition/cause/effect/recommendation, 5 Whys, management response (auditee can respond on assigned audits).
- [x] **9.6** UI: *Assurance Plan* and *Audit Universe* views; *Risk & Control Matrix* tab on the audit page; issue modal; e-sign modal with Approve/Reject. Browser-tested end to end.
- [x] **9.7** Tests: `tests/test_planning_rcm.py` — 60 tests green on MySQL, ruff clean; migration up/down verified on SQLite.

> **Phase 9 notes:** still open from the target design — Preparer -> Manager -> CAE
> multi-level review chain (only one reviewer level today), time-based
> escalations, auditor skills/capacity, analytics/NL queries, AI monitoring,
> ERP/IdP integrations, offline sync, per-module permission tiers.

---

## PHASE 10 — Reliable data entry & data accuracy

**Goal:** users can always save what they type; data is validated for accuracy.

### Steps
- [x] **10.1** Root cause of "cannot save": the running server was still on the half-migrated SQLite file (500s in `server_stdout.log`). `run.ps1` now syncs deps + migrates and refuses to start without a database; start-up auto-migrates (`GPHA_AUTO_MIGRATE`); `/health` reports `can_save`; UI banner; DB outages -> 503 with a clear message; CSRF check no longer touches the DB on GET.
- [x] **10.2** Drafts: migration `0007_form_drafts`, `/api/drafts` (private, 256 KB, secrets stripped), `static/js/forms.js` framework (device + server autosave, restore/discard, Save draft, keep-on-error, My Drafts with Continue).
- [x] **10.3** Validation: `app/core/validators.py` (Title, OptEmail, Code, FutureDate), structured 422 `errors[]` (schema + business rules via `FieldValidationError`), fiscal-year/budget ranges, control-test number consistency, duplicate/inactive engagement checks.
- [x] **10.4** All forms converted (records, audits, tasks, issues, plans, engagements, universe, RCM, users, profile, password) and new **Edit** forms for records, audits, plans, engagements and objectives.
- [x] **10.5** Tests: `tests/test_data_entry.py` (68 tests green); browser-tested autosave, restore, inline + server errors, server outage, database outage, My Drafts resume.

---

## PHASE 11 — UI clean-up

**Goal:** a clean, consistent, responsive interface.

### Steps
- [x] **11.1** `styles.css` rewritten: design tokens, Inter font, full-width content (was squeezed to ~860px), consistent cards, tables, badges, buttons (secondary / danger-ghost / icon), stat tiles, callouts, chips.
- [x] **11.2** Navigation grouped into Overview / Planning / Audit work / Registers / Account; staff-only sections hidden from Auditees; active item follows the open record.
- [x] **11.3** Standard page headers (back, title, ref + status badges, actions); in-place "Move to" status control; two-column detail layout with long text shown separately.
- [x] **11.4** Dashboard redesigned (KPIs, recent audits, my tasks, plan progress, drafts); Profile split into My details / Change password / User accounts.
- [x] **11.5** Plan, audit and RCM screens: KPI tiles, coverage callouts, secondary "+ Risk / + Control / + Test" buttons, aligned test tables, plan name shown on audits, Ref column on the audit list.
- [x] **11.6** Responsive: drawer navigation and top bar below 860px, low-priority columns hidden below 560px; checked at 1440px and 390px.
- [x] **11.7** Server password-strength rules (`password_problems`) matched by the on-screen hints.

---

## PHASE 12 — Reporting, follow-up, notifications and security

**Goal:** close the P1 gaps from the 13 Oct 2026 assessment.

### Steps
- [x] **12.1** Notifications: `notifications` table, bell with unread count, every task assignment notifies; optional SMTP e-mail sent only after commit.
- [x] **12.2** Audit report module (`app/modules/reports`): draft → management comments → manager e-sign → CAE e-sign → issued; blockers (rating, summary, opinion, management responses); SoD; issued snapshot; Word (python-docx) and print/PDF export.
- [x] **12.3** Review levels on users (Audit Manager / CAE), set by Admin in user management.
- [x] **12.4** Follow-up (`app/modules/followup`): implementation evidence, auditor validation with SoD, reopen on Not Effective, CAPA close gated on Effective; hourly escalation owner → manager → CAE; Follow-up page.
- [x] **12.5** Security: TOTP two-step verification (stdlib), role-mandatory MFA, per-IP sign-in throttle, CSP + Permissions-Policy, self-hosted Inter font and Bootstrap Icons.
- [x] **12.6** Migration `0008_reports_followup`; tests `tests/test_reports_followup.py` (74 tests green); browser walkthrough of the full report and follow-up flow.
- [ ] **12.7** Still open (need decisions): HTTPS + server host, GPHA SSO/AD, Exchange relay settings, GPHA report template wording.

---

## PHASE 13 — Configuration, lifecycle enforcement, committee reporting

**Goal:** configure the workflows and business rules to AMS / IIA practice.

### Steps
- [x] **13.1** System Configuration: `app_config` table (migration 0009), rule registry `app/core/appconfig.py`, Admin screen; consumers (escalation, MFA, throttle, reports, closure gates) read live values.
- [x] **13.2** Audit lifecycle: closure-readiness checklist + gated e-signed close; fieldwork-start notification to auditees and entity owner; Word engagement letter.
- [x] **13.3** Action SLAs: default due date by severity for CAPA created manually or raised from a finding.
- [x] **13.4** Audit Committee pack page + Word export (plan delivery, reports and ratings, findings by risk/age, actions, top overdue).
- [x] **13.5** Lists: sortable columns, paging, keyboard rows, CSV export.
- [x] **13.6** Tests `tests/test_configuration_lifecycle.py`; browser walkthrough.

---

## Dependency / ordering notes

- PHASE 0 must finish before anything touches the DB; run `init_db` + smoke.
- PHASE 1 is pure refactor — keep it green before PHASE 2.
- PHASE 2 services must exist before PHASE 3/4 routes use them.
- PHASE 5 can start in parallel with PHASE 3/4 (static is independent of new routers until API calls), but the generic renderers need final API shapes.
- Backups (4.4) depend on unknown MySQL TLS/path config — default to host-storage snapshots.

## Definition of Done

- MySQL-backed app boots from a fresh DB via `scripts/init_db.py`.
- All tests run on MySQL and pass; ruff clean.
- Manual smoke checklist in 7.3 completed.
## Phase 14 - Rename CAPA to Remediation

- [x] **14.1** User-facing name changed from "CAPA" to "Remediation" (sidebar, module title, dashboard, link pickers, "Raise remediation", notifications, auto-task titles, API messages, audit-log action codes `REMEDIATION_*`).
- [x] **14.2** New references use `REM-0001` (migration `0010_remediation_refs` seeds the `REM` sequence); existing `CAPA-####` references are unchanged. Internal identifiers (`/api/capa`, table `capa`, record type `capa`) are unchanged so links, history and backups keep working.
- [x] **14.3** Remediation and Follow-up merged into one sidebar page, "Remediation & Follow-up": a **Register** tab (all remediation actions, search/filters/CSV) and, for audit staff, a **Follow-up** tab (overdue actions, escalation levels, awaiting validation, admin "Run escalation check"). Auditees see the register only. Old `followup` links open the Follow-up tab.

## Phase 15 - GPHA Workspace hub

- [x] **15.1** Sidebar OVERVIEW: "GPHA Workspace" button under Dashboard. Opens a launch page with every module grouped as Overview / Planning / Audit work / Registers / Account & administration, each tile with a short description and a live count (open items; overdue remediation shown in red), plus quick actions (Start an audit, New remediation, New nonconformance). Tiles follow the user's role (auditees see only their modules; admin tiles for admins only).

## Phase 16 - Backlog build-out (assessment items 5, 8-15)

- [x] **16.1** Planning memo with e-signed approval and fieldwork gate (`app/modules/memos`, rule `require_memo_approval_for_fieldwork`).
- [x] **16.2** Capacity & time sheets (`app/modules/capacity`): profiles, time entries, capacity summary, budget vs actual.
- [x] **16.3** Analytics (`app/modules/insights`): heat map, findings trend, repeat findings, themes, KPIs with configurable targets.
- [x] **16.4** QAIP (`app/modules/qaip`): engagement quality checklist with evidence hints, post-audit survey (invited on close), yearly summary.
- [x] **16.5** Global search, Excel import (universe, findings) with template/preview, Excel export of any list, saved views (`app/modules/dataio`, `app/modules/views`).
- [x] **16.6** WCAG 2.2 AA pass: dialogs (role, label, focus trap/return), skip link, aria-current, labelled filters, toasts announced, reduced motion, contrast.
- [x] **16.7** Go-live readiness: optional Active Directory sign-in (`app/core/directory.py`), Caddy HTTPS config, `scripts/production_check.py`, Exchange/M365 SMTP examples.
- [ ] **16.8** Waiting on GPHA decisions: server host and certificate, SSO vs app MFA, SMTP relay details, ERP data feed for analytics.
- Migration `0011_backlog_modules`; tests `test_backlog_modules.py`, `test_directory_auth.py` (84 passing).

## Phase 17 - Configurable entities (Organizations)

- [x] **17.1** Entity types (`organization_categories`) and port types (`port_categories`) as Configuration lists; category validated (retired values kept on existing records).
- [x] **17.2** Hierarchy (`parent_id`, loop-proof), derived port per entity, address; list filters by type, port, parent and "My port"; delete blocked while entities sit under it.
- [x] **17.3** Custom fields (`app/modules/customfields`): Admin-defined text/longtext/number/date/select/yes-no fields, validated and stored on the record; retire instead of delete.
- [x] **17.4** User workplace (`users.work_entity_id`): profile "Where I work", "Set as where I work" on an entity, `/api/organizations/entities` picker for all roles.
- Migration `0012_entities_custom_fields`; tests `test_entities.py` (86 passing).
