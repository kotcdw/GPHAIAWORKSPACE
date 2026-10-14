# GPHA Internal Audit Workspace

An enterprise audit-management workspace (FastAPI + MySQL) with a plain
HTML/JavaScript single-page front end. It combines a GPHA-branded sign-in shell with
the FreeQMS-style audit module set: schedule audits, capture findings and
working papers, raise nonconformances and remediation actions, manage organizations and
stakeholders, log service feedback, drive a unified task center, sign records
with electronic attestations, and keep a strict, immutable audit trail.

> Built by merging two extractions (AVCS auth/branding + FreeQMS module set)
> into one modular monolith, migrated to MySQL 8, to replace the retired
> Microsoft LightSwitch *Audit Manager* application.

## Stack

| Layer      | Choice                                            |
| ---------- | ------------------------------------------------- |
| Runtime    | Python 3.12 (managed by [uv](https://docs.astral.sh/uv/)) |
| Web server | FastAPI + Uvicorn                                 |
| ORM        | SQLAlchemy 2.0 + Alembic                          |
| Database   | MySQL 8 (Docker) via PyMySQL                      |
| Auth       | Server-side sessions in an HttpOnly cookie + CSRF |
| Front end  | Static HTML/CSS/JS calling a JSON API             |
| Tests      | pytest + httpx (run against a MySQL test database) |

## Features

- **Audit Universe** — Admin-managed locations (e.g. Tema, Takoradi) and
  their entity units (e.g. GJT, Fishing Harbour), each with an inherent risk
  assessment (likelihood x impact, 1-25) and last-audited date.
- **Assurance Plan** — the annual audit plan that opens the fiscal year:
  planned engagements per entity unit with quarter, budget hours and lead
  auditor; coverage and "high-risk units not planned" analysis; e-signed
  approval by an Admin who did not prepare it; approved plans are frozen
  (reopen = back to Draft, re-approval required). **Starting** an engagement
  creates the audit project linked to the plan and entity.
- **Risk & Control Matrix (per audit)** — objectives -> risks (inherent and
  residual rating) and controls (type, nature, frequency, key, owner), mapped
  many-to-many -> control tests (walkthrough, test of design, test of
  operating effectiveness) with sample-size guidance and reproducible random
  sample selection, results, conclusion and an e-signed reviewer sign-off by
  someone other than the performer. Coverage gaps (risks without controls,
  untested key controls) are flagged. An audit cannot be signed off while any
  test is unreviewed.
- **Issues & actions** — an ineffective test raises an issue (finding)
  pre-filled with criteria/condition/effect and the worst linked risk rating;
  issues carry the IIA attributes (criteria, condition, cause, effect,
  recommendation), a 5 Whys root-cause analysis and the auditee's management
  response; "Raise action" creates the remediation action.
- **Never-lost data entry** — every form autosaves what you type as a draft:
  instantly on your device and, a second later, on the server (so it follows
  you to another computer). Drafts survive validation errors, closed windows,
  network drops and database outages, are restored when you reopen the form
  ("Restored your unsaved entries ... / Discard draft"), and are listed under
  **My Drafts** with *Continue* / *Discard*. Only a successful save removes a
  draft. Passwords are never stored in drafts.
- **Data accuracy** — fields are validated as you type and again on the server:
  required values, no blank/multi-line titles, valid e-mails (stored
  lower-case, internal domains allowed), reference codes (upper-cased),
  number ranges, due dates not in the past, sensible fiscal years, and
  cross-field rules (sample <= population, exceptions <= items tested, an
  "Effective" conclusion cannot have exceptions, duplicate plan engagements
  are refused). Server errors come back per field (`422 {"errors": [{field,
  message}]}`) and are shown under the offending field.
- **Save safety net** — `run.ps1` installs dependencies and migrates the
  database before starting (and refuses to start if MySQL is unreachable);
  the app applies pending migrations at start-up, `/health` reports whether
  saving is possible, and the UI shows a red banner when it is not. A database
  outage returns `503` with a clear message instead of a bare `500`.
- **Users & roles** — Admin, Auditor, Auditee. Self-registration captures
  FreeQMS fields (first/last name, company) and is approval-gated (new accounts
  are inactive until an Admin enables them). Per-module permission tiers are
  planned; access is currently role-based.
- **Audits** — title, description, scope and a `Planned -> In Progress ->
  Review -> Closed` workflow. `Closed` is reached **only** through an
  e-signed sign-off by an Admin who did not prepare the audit (segregation of
  duties); closed audits, their findings and working papers are locked.
- **Auditee access** — Auditees see only the audits they are assigned to
  ("Auditees with access" on the audit page) plus the NCs/remediations/feedback they
  own; organizations and stakeholders are internal.
- **Findings** — risk ratings (Low/Medium/High), status and assigned owner.
- **Working papers** — file upload with automatic per-title versioning,
  extension allow-list, size limit, SHA-256 integrity hash and encryption at
  rest. Papers are never physically deleted: an Admin can *withdraw* one.
- **Nonconformance (NC)** — auto reference `NC-0001`, severity, disposition,
  `Open -> Remediating -> Closed`, remediation linking, auto task generation.
- **Remediation** (formerly CAPA; new refs `REM-0001`, older `CAPA-####` refs are kept) — corrective/preventive actions, root cause, effectiveness check,
  e-signature closure from `Review` by someone other than the preparer (also
  closes a linked NC).
- **Organizations** — third parties/auditee entities with `Pending -> Approved`
  status and e-signature approval (`ORG-####`).
- **Stakeholders** — customers/service users (`SH-####`).
- **Service feedback** — complaints register (`SF-####`) that can link to
  NC/remediation.
- **Task Center** — assigned-to-me / assigned-by-me / closed, with
  system-generated (auto) task badges.
- **Approval cycles** — every e-signature is an attested decision (password
  verified and **never stored**); a rejection opens the next cycle.
- **Record history & dashboard** — per-record history and approval-cycle views,
  plus multi-module dashboard stats.
- **Automated backups** — on-demand + scheduled snapshots with retention,
  encrypted at rest (`*.enc`); restore with `scripts/restore_backup.py`.
- **Immutable trail** — every login and write is recorded; `audit_logs`,
  `record_history` and `approval_cycles` are append-only, enforced by database
  triggers (UPDATE/DELETE are rejected). Records that have progressed, been
  linked or been signed cannot be deleted; users with activity are deactivated,
  not deleted.
- **Audit reports** — one report per audit: draft → management comments →
  Audit Manager review (e-sign) → CAE approval (e-sign) → issued. Segregation
  of duties at each level, findings frozen at issue, Word and print/PDF export.
- **Follow-up** — action owners record implementation evidence, a different
  auditor validates it (Effective / Not Effective → reopened); a remediation can only
  be closed once validated. Overdue actions escalate automatically: owner →
  Audit Managers (14 days) → CAE (30 days). Follow-up tab on the "Remediation & Follow-up" page lists them.
- **Notifications** — in-app bell for task assignments, reviews, report
  stages, validations and escalations; optional e-mail through GPHA SMTP.
- **Review levels** — Admin assigns Audit Manager / CAE review levels to staff.
- **Two-step verification** — optional TOTP (authenticator app) per user,
  mandatory per role via `GPHA_MFA_REQUIRED_ROLES`; admin can reset it.
- **System Configuration** (Admin) — business rules editable on screen, no
  restart: closure gates, management-response rule, fieldwork notices, action
  due-date SLAs by severity, escalation thresholds, MFA roles, sign-in
  throttle, report letterhead and default methodology. Every change is logged.
- **Audit lifecycle enforcement** — closure-readiness checklist on each audit
  (in Review, tests reviewed, report issued, responses and agreed actions);
  the e-signed close is refused until it passes. Auditees and the entity owner
  are notified when fieldwork starts; one-click Word engagement letter.
- **Action SLAs** — actions raised without a due date get one from the
  configured SLA (High 30 / Medium 60 / Low 90 days by default).
- **Audit Committee pack** — plan delivery, reports issued and ratings, open
  findings by risk and age, action status and the most overdue actions, with
  a Word pack for the committee.
- **Lists** — sortable columns (business order for risk/status), paging,
  keyboard-accessible rows, **saved views** (named filter sets per user) and
  **Excel (.xlsx) and CSV export** on every register.
- **Planning memo** (GIAS 13) — background, objectives, scope, key risks,
  approach, team, timeline and budget per audit; submitted to an Audit Manager
  or the CAE and e-signed (approve / return). Fieldwork cannot start until it is
  approved (configurable). Word export.
- **Capacity & time** — auditor grade, skills, certifications and available
  hours; daily time sheets (quarter hours, audit time must name the audit,
  24 h/day cap); planned load per auditor from the Assurance Plan; budget versus
  actual hours per audit.
- **Analytics** — 5×5 inherent-risk heat map of the audit universe, findings
  raised per month by rating, repeat-finding detection across audits, common
  themes, and KPIs against targets set on the Configuration screen (plan
  delivery, remediation closed on time, overdue actions, days to report,
  auditee satisfaction, audit-time utilisation).
- **Quality (QAIP)** — 12-point engagement quality checklist mapped to the IIA
  GIAS with system evidence hints, done by someone other than the preparer;
  post-audit satisfaction survey sent to auditees at closure; yearly QAIP summary
  with the weakest checklist areas.
- **Global search** (top bar, press `/`) across audits, findings, remediation,
  reports, nonconformances, feedback and registers, respecting each user's access.
- **Excel import** — Audit Universe (Admin) and findings into an audit, with a
  downloadable template, row-by-row validation and preview; nothing is saved
  if any row has a problem.
- **GIAS completion** — Audit Committee approval of the plan (meeting date and
  minute reference) and a documented plan-change log (engagements added,
  re-timed, re-budgeted or cancelled after approval, each with a reason) in the
  Committee pack; a **criteria library** picked from the finding form; supervisory
  **review notes** (raise → answer → clear, open notes block closure);
  working-paper index references, links to tests/findings and reviewer sign-off;
  **exit meeting** record on the report; follow-up testing recorded on every
  Effective validation; a fourth escalation level to the **Audit Committee**; a
  **skills matrix**; and the yearly **internal assessment report** (Word) from the
  QAIP page.
- **Configurable entities (Organizations)** — every port, head office, department,
  unit and external party is an entity with a type (the list is edited on the
  Configuration screen), a parent ("Part of") and an address. Types marked as
  ports / sites file every entity under its port; lists filter by type, port or
  "My port". Admins add custom fields (text, number, date, drop-down, yes/no,
  required or optional). Each user sets **Where I work** in their profile or with
  "Set as where I work" on any entity.
- **In-app help** — context help for each page (the ? button).
- **Accessibility (WCAG 2.2 AA)** — skip link, labelled dialogs with focus
  trap and focus return, `aria-current` navigation, sortable headers with
  `aria-sort`, labelled filters, keyboard rating controls, screen-reader
  announcements for toasts, reduced-motion support, contrast checked.
- **Active Directory sign-in** (optional) — staff use their GPHA network
  password (LDAP bind; never stored); first sign-in creates a pending account
  for an Admin to approve; the bootstrap admin keeps a local break-glass password.
- **Clean, responsive UI** — grouped navigation, standard page headers with
  in-place status changes, KPI dashboards, and a drawer layout on phones and
  small tablets.
- **Sign-in protection** — per-computer rate limiting, strict
  Content-Security-Policy, self-hosted fonts and icons (no external CDNs),
  account lockout after repeated failures (Admin can
  unlock); password change, deactivation, role change and password reset end
  the user's other sessions.

### Roles & responsibilities (job roles and permissions)

Every account has an access tier (Admin / Auditor / Auditee / Committee) and a **job role** that maps to
fine-grained permissions (`app/core/permissions.py`). The Platform Administrator edits the matrix on
**Roles & permissions** and assigns job roles under **Profile & Users** (the role sets the tier and review level).

| Job role | Main responsibilities in the system |
|---|---|
| Platform Administrator | Configuration (security, workflow), users, roles & permissions, reference data, organization entities, backups and audit log |
| Audit Administrator | Audit types, audit programmes, plan configuration (risk thresholds, audit cycle), universe and criteria library, reporting configuration |
| GM Audit (CAE) | Plan approval and amendments, Audit Committee approval, portfolio across ports, report approval, audit closure, QAIP, governance reporting |
| PIA | Own-port portfolio, resource allocation, memo approval, report review, quality review, follow-up |
| Audit Manager | Engagement planning, team allocation, supervision, review notes, findings, report preparation and review |
| Unit Head / Supervisor | Working-paper review, review notes, quality checks, assignment monitoring |
| Senior Auditor | Fieldwork, testing, working papers, findings, review support |
| Auditor | Planning support, fieldwork, tests, evidence requests, working papers, findings |
| Audit Clerk / Assistant | Working-paper filing and evidence-request administration |
| Management / Auditee | Evidence requests (upload and submit), finding responses, action plans, remediation updates |
| Audit Committee / Executive Reviewer | Read-only governance portal: approved plans, issued reports, KPIs, committee pack, port portfolio |

Related modules: **Audit programmes** (`/api/audit-programs`, applied to an audit's RCM), **Evidence requests**
(`/api/audits/{id}/evidence-requests`, `/api/evidence-requests`), **Governance portal** (`/api/governance/overview`)
and **Port portfolio** (`/api/portfolio/ports`). Audits carry an audit type and a port.

### Annual planning cycle

The Assurance Plan page walks the plan through ten recorded stages:
Planning preparation (checklist) → Risk / universe review (snapshot of ratings and units due under the audit
cycle) → Audit Managers' planning meeting (date, attendees, minutes) → Draft plan → Internal review (GM Audit
e-signature, or return with comments) → Submission to the approving authority → Audit Committee decision
(Approved / Approved with amendments / Deferred / Returned) → Approved version (numbered, frozen snapshot with a
Word "controlled copy") → GM Audit controlled distribution (named PIAs and Audit Managers, receipt acknowledged)
→ PIA / Manager execution (engagements started, by site and by lead).
Each engagement has a **responsible site** (Head Office or a port). The GM Audit distributes the approved version
by destination. Destinations are **set up by administrators** on the Organizations register (tick "Receives the
approved Assurance Plan" and give a label such as HQ, PIA Tema, PIA Takoradi; needs the reference-data
permission) - nothing is hard-coded. Each copy goes to the PIA / Audit Managers
registered there ("Where I work"); each destination gets its own Word controlled copy with its engagements, and
every recipient acknowledges receipt. Audits started from an engagement belong to its site. Two switches under Configuration › Plan configuration
control enforcement: `plan_cycle_enforced` and `plan_distribution_before_execution` (both on by default).
Plan statuses shown to users: **Draft, In Review, Submitted, Returned, Approved, Distributed, In Execution,
Revised, Closed, Archived** (`lifecycle_status`, kept in step automatically; Archived = a closed year archived
by the GM Audit, read-only and hidden from the default list).
API: `/api/assurance-plans/{id}/cycle…`, `/api/assurance-plans/{id}/versions/{n}[/export.docx]`.

### Changes to an approved plan

An approved plan is never edited in place (the old direct amendment endpoints now refuse). Every change is a
**plan change request** (`PCR-nnnn`): title and reason, the affected plan items (add / change / cancel
engagements), the computed **resource impact** (hours vs budget, by quarter and by lead) and **coverage impact**
(universe coverage, high-risk units gained or lost), the **requester**, an independent **reviewer** (endorse or
return), and the GM Audit's **approval** by e-signature (approve or reject; requester cannot approve).
Approval applies the changes, logs each one under Plan changes with the PCR reference, freezes a **new version**
(snapshot + Word controlled copy) and re-distributes it to the holders of the previous version for
acknowledgement. **Significant** changes (an engagement added or cancelled, planned hours moved by at least
`plan_change_significant_hours_pct` (default 10%), hours over budget, a high-risk unit left uncovered, or marked
significant by the reviewer) then go to the **Audit Committee** for approval, as IIA GIAS 9.4 requires; minor
changes are approved by the CAE and reported in the Committee pack. Each approved version records its submission
to the **Internal Audit Agency** (date and letter reference). A request raised against an older version cannot be
approved. A full revision ("Revise plan")
needs a reason and goes back through internal review and the Audit Committee.
API: `/api/assurance-plans/{id}/change-requests[/impact]`, `/api/plan-change-requests/{id}/review|approve|withdraw|resubmit`.

## Quick start

```powershell
# 1. Start the MySQL server (Docker) - binds host port 3307
docker compose up -d

# 2. Install dependencies (creates .venv automatically)
uv sync

# 3. Create the database schema and the bootstrap admin
uv run python -m scripts.init_db

# 4. Run the app  (http://127.0.0.1:8001) - also syncs deps and migrates
.\run.ps1
# or: uv run uvicorn app.main:app --reload --port 8001
```

Open <http://127.0.0.1:8001>. Sign in with the bootstrap administrator
(`admin` / `Admin@12345` by default — change it in `.env`), or register a new
account and have an administrator approve it.

> **Two people are needed to close an audit.** The preparer of an audit (or
> remediation, or organization) cannot sign it off. Create a second Admin account for
> sign-off before running a full audit cycle.

### Production checklist

Set `GPHA_ENVIRONMENT=production`; the app then refuses to start until:
`GPHA_SECRET_KEY` is a random 32+ character value, `GPHA_ENCRYPTION_KEY` is
set (and backed up — encrypted files are unreadable without it),
`GPHA_ADMIN_PASSWORD` is not the default, `GPHA_COOKIE_SECURE=true` (HTTPS),
and the database is MySQL. In development the same problems are logged as
warnings.

> The Docker MySQL binds **3307** because a local MySQL (e.g. XAMPP) usually
> already owns 3306. The container sets `--log-bin-trust-function-creators=1`
> so the app user can create the append-only triggers.

## Configuration

Copy `.env.example` to `.env` and adjust. Settings use the `GPHA_` prefix:

| Variable                 | Default                     | Purpose                       |
| ------------------------ | --------------------------- | ----------------------------- |
| `GPHA_ENVIRONMENT`       | `development`               | `production` enables the startup guard |
| `GPHA_SECRET_KEY`        | `dev-secret-change-me`      | Application secret            |
| `GPHA_ENCRYPTION_KEY`    | derived from secret key     | Encrypts backups + working papers |
| `GPHA_LOGIN_MAX_ATTEMPTS` / `GPHA_LOGIN_LOCKOUT_MINUTES` | `5` / `15` | Sign-in lockout |
| `GPHA_MAX_UPLOAD_MB` / `GPHA_UPLOAD_ALLOWED_EXTENSIONS` | `25` / office, PDF, image, mail, audio | Upload limits |
| `GPHA_DATABASE_URL`      | `mysql+pymysql://gpha:*@127.0.0.1:3307/gpha_workspace` | Database connection |
| `GPHA_MYSQL_*`           | `gpha` / `gpha_dev_pass`    | DSN parts when `GPHA_DATABASE_URL` is unset |
| `GPHA_SESSION_TTL_HOURS` | `12`                        | Session lifetime              |
| `GPHA_COOKIE_SECURE`     | `false`                     | Set `true` behind HTTPS       |
| `GPHA_ADMIN_*`           | `admin` / `Admin@12345`     | Bootstrap administrator       |
| `GPHA_BACKUP_DIR`        | `./backups`                 | Snapshot directory            |
| `GPHA_BACKUP_RETENTION`  | `7`                         | Snapshots to keep             |
| `GPHA_BACKUP_INTERVAL_HOURS` | `24`                   | Scheduled backup interval (0 disables) |
| `GPHA_SMTP_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_FROM` / `_STARTTLS` | empty / `25` | E-mail notifications (empty host = in-app bell only) |
| `GPHA_APP_BASE_URL`      | `http://127.0.0.1:8001`     | Link used in notification e-mails |
| `GPHA_ESCALATE_MANAGER_DAYS` / `GPHA_ESCALATE_CAE_DAYS` | `14` / `30` | Overdue action escalation thresholds |
| `GPHA_ESCALATION_CHECK_MINUTES` | `60`                 | How often overdue actions are checked (0 disables) |
| `GPHA_LOGIN_RATE_LIMIT_PER_MINUTE` | `10`              | Sign-in attempts per computer per minute (0 disables) |
| `GPHA_MFA_REQUIRED_ROLES` | empty                      | e.g. `Admin,Auditor` to make two-step verification mandatory |
| `GPHA_REQUIRE_REPORT_TO_CLOSE` / `GPHA_REQUIRE_FINDINGS_ACTIONED_TO_CLOSE` | `true` / `true` | Audit closure gates |

> Most business rules can also be changed by an Admin on the **Configuration**
> screen; a value saved there overrides the `.env` default.

## API overview

| Method(s)                    | Path                                          | Access            |
| ---------------------------- | --------------------------------------------- | ----------------- |
| POST                         | `/api/auth/register` `/login` `/logout`       | public / session  |
| GET / PATCH                  | `/api/auth/me`                                | authenticated     |
| POST                         | `/api/auth/me/password`                       | authenticated     |
| GET/POST/PATCH/DELETE        | `/api/users`                                  | Admin             |
| POST                         | `/api/users/{id}/unlock`                      | Admin             |
| GET/POST/PATCH/DELETE        | `/api/audits`                                 | Auditor/Admin (write) |
| POST                         | `/api/audits/{id}/in-approval`                | Auditor/Admin     |
| POST                         | `/api/audits/{id}/close` (e-sign, from Review, not the preparer) | Admin |
| GET/POST/DELETE              | `/api/audits/{id}/auditees` `/api/audits/auditee-candidates` | Auditor/Admin |
| GET/POST                     | `/api/audits/{id}/findings`                   | Auditor/Admin (write) |
| PATCH/DELETE                 | `/api/findings/{id}`                          | Auditor/Admin     |
| GET/POST                     | `/api/audits/{id}/working-papers`             | Auditor/Admin (write) |
| GET                          | `/api/working-papers/{id}/download`           | authenticated     |
| GET/POST/PATCH/DELETE        | `/api/nonconformances` `/api/capa` `/api/organizations` `/api/stakeholders` `/api/service-feedback` | Auditor/Admin (write) |
| POST                         | `/api/{module}/{id}/copy` `/link-*`           | Auditor/Admin     |
| POST                         | `/api/organizations/{id}/approve` `/api/capa/{id}/close` (e-sign) | Admin |
| GET/POST/PATCH               | `/api/tasks`                                  | authenticated     |
| POST                         | `/api/approvals/sign`                         | Auditor/Admin     |
| GET                          | `/api/records/{type}/{id}/history` `/approval-cycles` | authenticated |
| GET                          | `/api/audit-logs`                             | Admin             |
| GET/POST/DELETE              | `/api/admin/backup` `/backups`                | Admin             |
| GET / POST / PATCH           | `/api/locations` `/api/entity-units`          | read Auditor/Admin, write Admin |
| GET/POST/PATCH               | `/api/assurance-plans` (+ `/{id}/engagements`) | Auditor/Admin     |
| POST                         | `/api/assurance-plans/{id}/approve` (e-sign) `/reopen` `/close` | Admin |
| POST/PATCH/DELETE            | `/api/plan-engagements/{id}` `/start` `/cancel` | Auditor/Admin (cancel: Admin) |
| GET                          | `/api/audits/{id}/rcm` (matrix + coverage summary) | Auditor/Admin |
| POST/PATCH/DELETE            | `/api/audits/{id}/objectives` `/api/objectives/{id}` `/risks` `/controls` | Auditor/Admin |
| PUT                          | `/api/controls/{id}/risks` (risk mapping)     | Auditor/Admin     |
| POST/GET/PATCH/DELETE        | `/api/controls/{id}/tests` `/api/control-tests/{id}` `/sample` `/sample-recommendation` | Auditor/Admin |
| POST                         | `/api/control-tests/{id}/review` (e-sign) `/raise-issue` | Auditor/Admin |
| POST                         | `/api/findings/{id}/raise-action` (remediation)      | Auditor/Admin     |
| POST                         | `/api/findings/{id}/response` (management response) | anyone who can see the finding |
| GET/PUT/DELETE               | `/api/drafts` `/api/drafts/{form_key}`        | own drafts only   |
| GET                          | `/health` (incl. database status, `can_save`) | public            |

Read endpoints apply record-level scoping: Auditees get `404` for records
outside their assignment.

Interactive docs are available at `/docs` while the server is running.

## Going live

1. `uv run python scripts/production_check.py --secrets` - prints fresh secrets and a readiness report.
2. In `.env`: `GPHA_ENVIRONMENT=production`, the printed `GPHA_SECRET_KEY` and `GPHA_ENCRYPTION_KEY`,
   a new `GPHA_ADMIN_PASSWORD`, `GPHA_COOKIE_SECURE=true`. The app refuses to start in production while
   any of these is unsafe.
3. HTTPS: run the app on `127.0.0.1:8001` with `--proxy-headers` and put Caddy in front using
   `deploy/Caddyfile` (GPHA certificate, or `tls internal`).
4. E-mail: set `GPHA_SMTP_*` for the GPHA Exchange relay or Microsoft 365 (examples in `.env.example`).
5. Optional: `GPHA_LDAP_*` for Active Directory sign-in.
6. Re-run the check until it reports "Ready for production".

## Tests

Tests run against a dedicated MySQL database (`gpha_workspace_test`, created
automatically by `tests/conftest.py`). The Docker MySQL is required; the test
DB is dropped/recreated and migrated on every pytest invocation.

```powershell
docker compose up -d
uv run pytest
uv run ruff check .
```

## Backups

Backups are written to `GPHA_BACKUP_DIR` (default `./backups`). The module
prefers `mysqldump` when available (native, restorable) and otherwise writes a
portable JSON dump of every table. Retention keeps the newest
`GPHA_BACKUP_RETENTION` snapshots. A scheduler runs in the app lifespan every
`GPHA_BACKUP_INTERVAL_HOURS` (set to `0` to disable, as the tests do).

Every snapshot is encrypted with `GPHA_ENCRYPTION_KEY` and saved as
`backup_<stamp>.json.enc` or `.sql.enc`; login sessions are never included.

```powershell
# Decrypt a snapshot (writes a plaintext file - delete it afterwards)
uv run python -m scripts.restore_backup backups\backup_20261013_101500.json.enc --decrypt-only
# Restore a JSON snapshot into a NEW, empty database (point GPHA_DATABASE_URL
# at it first; the script applies the migrations itself - skip scripts.init_db)
uv run python -m scripts.restore_backup backups\backup_20261013_101500.json.enc --yes
```

## Layout

```
app/
  core/            config, database, security, deps, audit, enums,
                   refs, history, tasksvc, approvalsvc, access (record
                   scoping + deletion rules), crypto (encryption at rest)
  modules/
    auth/          register/login/logout/me/profile/password
    users/         user admin + roles
    planning/      audit universe + Assurance Plan + engagements
    rcm/           objectives, risks, controls, tests, sampling, issues -> actions
    drafts/        autosaved per-user form drafts
    audits/        audits + findings/issues + working papers (+ e-closure)
    nonconformances/  NC records + dispositions
    capa/          corrective/preventive actions
    organizations/ third parties / auditee entities
    stakeholders/  customers / service users
    service_feedback/ complaints register
    tasks/         Task Center
    approvals/     generic e-sign attestation endpoint
    history/       audit logs + per-record history views
    backups/       snapshot + scheduled backup admin
  main.py          explicit router registry + lifespan (backup scheduler)
  static/          HTML/CSS/JS front end (index.html, css/, js/, img/)
alembic/versions/  migrations 0001 initial .. 0007 form drafts
mysql/init/        init SQL mounted into the Docker container at first boot
scripts/           init_db.py (migrate + seed admin), seed_demo.py, restore_backup.py
tests/             pytest suite (runs on MySQL)
uploads/           uploaded working papers (git-ignored)
backups/           database snapshots (git-ignored)
```
