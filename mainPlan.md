# FINAL PLAN — Merger of AVCS + FreeQMS into a modular FastAPI / MySQL project

**Identity:** keep **GPHA AUDIT WORKSPACE** name/brand.
**Database:** MySQL (tests run on MySQL too).
**Architecture:** feature-package modular monolith.

## 1. Comparison & merge strategy

- **AVCS extraction** = brand/auth shell (logo card, `ADVANCED VESSEL CLEARING SYSTEM`, floating bg, `SIGN IN TO YOUR ACCOUNT`, Reset/Verify buttons) -> becomes the **experience layer** (kept as-is).
- **FreeQMS extraction** = capability layer (Audits, CAPA, Nonconformance, Suppliers -> Organizations, Customers -> Stakeholders, Complaints -> Service Feedback, Task Center, Approval Cycles w/ Part-11 e-sign, Dispositions, Copy, Links, Backups, print) -> becomes the **feature layer**, GPHA-named.
- Merge point: AVCS-styled auth outside; FreeQMS-style functional workspace inside; one modular FastAPI app.

## 2. MySQL infrastructure (Docker MySQL 8, fresh DB)

- **`docker-compose.yml` (new):** MySQL 8.0, db `gpha_workspace`, user `gpha`, pass from `.env`, charset `utf8mb4 / utf8mb4_unicode_ci`, named volume, port 3306; healthcheck.
- **Dependency:** add `PyMySQL>=1.1` to `pyproject.toml`.
- **`core/config.py`:** default `database_url` -> `mysql+pymysql://gpha:...@127.0.0.1:3306/gpha_workspace?charset=utf8mb4`; dev/test override via `GPHA_DATABASE_URL`.
- **`core/database.py`:** remove SQLite `check_same_thread` hook; add `pool_pre_ping=True`, `pool_recycle=3600`; keep `_is_sqlite` flag (used only for Alembic batch mode / convenience).
- **`.env.example` + README:** document DSN, `docker compose up -d`, bootstrap notes.
- Existing SQLite dev DB is abandoned (only held the seed admin); `scripts/init_db.py` re-seeds admin on MySQL.

## 3. Migrations (re-baselined for MySQL)

- Rewrite `0001_initial` triggers **dialect-aware** via `op.get_bind().dialect.name`: SQLite `RAISE(ABORT)` **and** MySQL `SIGNAL SQLSTATE '45000' ... FOR EACH ROW` -> append-only `audit_logs` enforced on both.
- New **`0002_module_tables`**: `organizations`, `stakeholders`, `service_feedback`, `nonconformances`, `capa`, `tasks`, `record_history`, `approval_cycles`; `audits` += approval-status + optional FKs; auto reference numbers (`ORG-`, `SH-`, `SF-`, `NC-`, `CAPA-`). Enums remain `VARCHAR+CHECK` (MySQL 8.0.16+ enforces) — no type changes needed.
- `alembic/env.py`: already reads settings URL; keep `render_as_batch` SQLite-only.

## 4. Modular structure (feature packages)

```
app/
  core/          config, database, security, deps (per-module-tier perms), audit, shared enums/services
  modules/
    auth/          register/login/logout/me/profile/password (AVCS UI, FreeQMS register fields)
    users/         user admin + roles + per-module permissions
    tasks/         Task Center + system-task auto-generation
    approvals/     e-sign cycle engine (password attestation only)
    audits/        audits + working_papers + findings (moved/extended w/ e-closure)
    nonconformances/
    capa/
    organizations/
    stakeholders/
    service_feedback/
    history/       per-record + module-wide record_history
    backups/       snapshot + scheduled backup
  main.py          explicit router registry
  static/          SPA (nav, list/detail/task renderers, e-sign modal, print CSS)
```

Each module owns `models.py`, `schemas.py`, `router.py`, optional `service.py`; existing flat `models.py`/`schemas.py`/`routers/*` are split into packages with **no behavior change** during migration.

## 5. Tests (must run on MySQL)

- `tests/conftest.py`: build test DSN from env (`GPHA_TEST_DATABASE_URL` or derived `gpha_workspace_test`); session-autouse fixture connects to server, `DROP/CREATE` the **test DB**, then `alembic upgrade head` (validates migrations on MySQL).
- Keep all 18 existing tests green on MySQL; add per-module suites (CRUD, status transitions, **e-sign requires valid password + attestation logged**, copy/link integrity, task auto-generation, permission tiers, history immutability via trigger).
- `pytest` + `ruff` (line-length 120, existing ignores) stay the gate.

## 6. Feature matrix (single full pass)

AVCS login kept; register becomes FreeQMS-style (Email, Password + Django-style hints, Confirm, First Name, Last Name, Company) -> pending-admin approval. Nav order: **Task Center (top-left)  Audits  Corrective/Preventive Actions  Nonconformance  Organizations  Stakeholders  Service Feedback  Users  Audit Log**. Modules: CRUD + transitions + copy + links + history + auto numbers. Cross-cutting: unified Task Center (assigned-to-me/by-me/closed + auto tasks), Approval Cycles (password e-sign, re-approval = new cycle), Dispositions, print-to-PDF, automated backups, dashboard multi-module stats, no-hidden-areas.

## 7. Execution order

1. `docker-compose` + PyMySQL + config/db/env + rewritten `0001` & `0002` migrations + MySQL conftest -> `init_db` + smoke against MySQL.
2. Split existing code into `core/` + feature packages (18 tests green on MySQL).
3. Build new module backends (models/schemas/routes/services) + tasks/approvals engines.
4. Frontend: nav, shared renderers, e-sign modal, print CSS, dashboard, register form.
5. New test suites + full `pytest`/`ruff`; manual smoke on port 8001.