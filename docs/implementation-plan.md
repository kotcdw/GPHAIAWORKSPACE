# PROJECTBLUEPRINT implementation plan

Source: `PROJECTBLUEPRINT.md` (21 October 2026) and its companion interface walkthroughs.
Target: this repository, the GPHA Internal Audit Workspace (GIAW).

This file is the durable progress record for the blueprint build. Update the status column and the evidence log as each slice lands.

## 1. Detected stack and conventions

| Area | What the repository uses |
|------------------|-------------------------------------------------------------------------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 ORM, Alembic migrations, MySQL 8 (`pymysql`) |
| Frontend | Plain JavaScript single-page app in `app/static` (no build step), served by FastAPI |
| Auth | Server-side sessions (HttpOnly cookie + double-submit CSRF), TOTP two-step, optional LDAP |
| Authorization | Job roles and permissions in `app/core/permissions.py`, enforced by `require_perm` / `ensure_perm` and port/team scoping in `app/core/access.py` |
| Audit trail | Append-only `audit_logs` (`log_action`) and `record_history`; tamper protection via triggers |
| Package manager | `uv` (`pyproject.toml`, `uv.lock`) |
| Tests | `pytest` against an isolated MySQL test database; Playwright UI smoke tests in `tests/ui` |
| Lint / security | `ruff`, `bandit`, `pip-audit`, `semgrep` |
| Deployment | Docker image + Caddy (VPS), Windows/Laragon kit; nothing is deployed from this build |

Run commands are in section 7.

## 2. How the blueprint modules map to GIAW

The blueprint describes Diligent One concepts. GIAW already implements most of the lifecycle under GPHA's own names. The table maps each blueprint module to the existing GIAW module and states what this build adds.

Evidence labels (blueprint section 2): **D** documented in public help · **W** workflow interpretation · **I** interface reconstruction · **T** tenant-dependent / GPHA configuration.

| Blueprint module | GIAW module(s) | Status before this build | Added by this build | Label |
|------------------|----------------|--------------------------|---------------------|-------|
| Platform Administration | Administration, Configuration, Users & access, Roles & permissions, Audit trail, Data import, Backups | Present | **User groups** with membership, used for report sharing (6.1) | D/T |
| Org structure and entity tagging | Org Structure; Audit universe (units, processes, auditable entities); entity links on audits and plan engagements | Present | – | D |
| Users, roles, access | Job roles + approval levels, permission matrix, port/team scope | Present | Groups (above); explicit Project Creator rule on plans (D) | D/T |
| Frameworks | Frameworks (standard controls), Project Library (programmes of objectives/risks/controls/tests) | Present | Objective **import** (many) from an audit or programme, and **clone** (one) | D |
| Strategy | Risk Manager (risks, objectives, assessments, KRIs, heat maps) | Present, without treatment links to assurance work | **Treatment** links from a strategic risk to audit objectives; **Assurance** roll-up (controls passing/failing/not tested, issue trend, overall assurance) | D/W |
| Assurance Plans | Assurance Plans (create, add/link/roll forward, coverage, strategic risks, progress, resources, 100-project cap) | Present; any auditor could add or link engagements | Permission split: link = plan role; create / roll forward = plan role **and** Project Creator (`audit.create`); remaining / overage hours; **next-cycle planning signals** | D |
| Projects and fieldwork | Audits (planning memo, Internal Control and Workplan workflows, evidence requests, sign-offs, review notes, working papers) | Present | Objective import / clone; 500-objective cap per audit | D |
| Results / issues / remediation | Findings, remediation actions, validation, escalation, Results tables | Present; validation of actions, no issue-level retest record | **Remediation status** and **retest information** on the issue; verified closure requires a retest where configured | D/T |
| Reports | Committee pack, register exports, Analytics | No report builder | **Reports app**: Views, columns, filters, grouping, chart, draft/active, private/staff/group access, CSV/Excel export | D/I |
| Dashboards and Presentations | Storyboards (Results interpretations) | Storyboards only | **Dashboards** (saved reports + text tiles) and **Presentations** (ordered slides), draft/active with access | D/I |
| Storyboards and Analytics | Storyboards, Analytics, Results, Robots | Present | – | D |
| AI Reporting | AI drafts for findings, summaries, risks (off by default) | No grounded report generation | **AI Reporting workstreams**: confirmed sources, authorized data only, stored facts separate from generated narrative, human review before publish; works without an AI provider (facts only) | D/W |
| Cycle close | Close year, Archive, committee pack, statutory reports | Present | Planning signals for the next cycle (management decision, not automatic) | W |

## 3. Business rules and how they are implemented

| Rule (blueprint) | Implementation | Checked by |
|------------------|----------------|-----------|
| Plan holds at most 100 projects | `ensure_room` (config `plan_max_projects`, default 100) on create, link, roll forward, start planning | `test_plan_projects.py::test_plan_project_limit` |
| Assurance Plans Admin without Project Creator can link but cannot create or roll forward | Link: `plan.prepare` or `plan.amend`. Create and roll forward: that **and** `audit.create` | `test_blueprint_planning.py` |
| Progress: Not Started 0, In Process 1, Completed 2; 100 % only when every phase is complete | `coverage.engagement_progress` (formula in 3.1) | `test_plan_projects.py` |
| Resource use = sum of budgeted hours vs available hours, with remaining and overage | Plan summary `hours_remaining`, `hours_over` | `test_blueprint_planning.py` |
| Coverage derives from actual entity tags | Coverage grid built from engagement/audit entity links only | `test_fieldwork_issues.py::test_plan_coverage_grid` |
| Strategic risks on a plan come from explicit links | Risk ← entity links, audit-risk `enterprise_risk_id`, and (new) risk treatments → objectives | `test_blueprint_strategy.py` |
| Import (many) vs clone (one at a time) | `POST /api/audits/{id}/objectives/import` (list) and `POST /api/objectives/{id}/clone` (single target) | `test_blueprint_objectives.py` |
| Narratives only where the workflow allows | Narrative create refused unless the audit uses the Internal Control workflow | `test_blueprint_objectives.py` |
| Verified closure; status change alone is not proof | Issue cannot be set Closed until actions are validated Effective and, where retest is required (Configuration › Action plans › *Issue ratings that need a retest*), a retest concluded Effective is recorded. Remediation status is set by management or auditors; *Verified* is set only by the system | `test_blueprint_retest.py` |
| AI Reporting uses only authorized data, shows source/filters/period, separates facts and narrative, needs human review | Sources run through the same scoped Views as Reports with the author's access; facts are stored separately from the narrative (labelled *generated* or *edited*); publishing needs approval by a different person with a review permission who confirms the facts were checked; readers see stored facts only if they could see every source audit | `test_blueprint_reports.py` |
| Sharing never widens data access | Reports, dashboards and presentations always run with the viewer's own access (port/team scope; Risk Manager data needs a risk & compliance permission) | `test_blueprint_reports.py` |
| User groups grant no permissions | Groups are an audience for sharing only | `test_blueprint_groups.py` |
| Audit events for material changes; no hard delete of evidence | `log_action` on every write; groups are deactivated, reports and workstreams archived, never erased | `test_blueprint_groups.py`, `test_blueprint_strategy.py`, `test_blueprint_reports.py` |

### 3.1 Progress formula (decision)

For each project the phases are: planning memo, then each fieldwork step of its workflow (Internal Control: narratives, risk & control matrix, walkthroughs, test plan, testing; Workplan: work programme, execute procedures), then the report. Each phase scores Not Started 0, In Process 1 or Completed 2.

`progress % = round(100 × Σ scores ÷ (2 × number of phases))`

Edge cases:

- A closed audit is 100 %.
- A planned engagement with no audit yet is 0 %.
- A phase that does not apply to the workflow is not counted.
- Plan progress is the mean of its non-cancelled projects.

GIAW tracks phases per engagement rather than per objective, because objectives live inside each phase. This is documented as a **workflow interpretation**.

## 4. Phases, acceptance criteria and status

| Phase | Scope | Acceptance criteria | Status |
|-------|-------|---------------------|--------|
| A | Repository audit, architecture mapping, this plan | Stack, commands, mapping and gaps written down | Done |
| B | Foundation | Existing shell, auth, schema, permissions, audit log and demo seed reused; new tables via Alembic | Done (reused) |
| C | Administration: user groups | Groups CRUD + membership; admin-only; audit events; groups usable as report audience | Done |
| D | Strategy and planning rules | Permission split, overage, signals, treatment links, assurance roll-up | Done |
| E | Project execution: objective import / clone, narrative rule, 500 cap | Import many, clone one, refused across workflows where not allowed | Done |
| F | Issues: remediation status, retest, verified closure | Retest recorded; closure blocked without it where required | Done |
| G | Reports, dashboards, presentations, AI Reporting | Connected, persisted, scoped, exportable, draft/active, human review gate | Done |
| H | Hardening and handoff | All checks pass; security scan clean; docs updated | Done (see evidence log) |
| I | Interface walkthroughs (7 HTML files) | Each matching app uses the walkthrough layout: dark title bar, left sub-navigation, the same pages, tabs, buttons and fields; GIAW branding, header, sidebar and data kept; walkthrough helper text not shown | Done |

## 5. Evidence log

All runs on 21 October 2026 against an isolated MySQL 8 test database.

| Slice | What was built | Evidence |
|-------|----------------|----------|
| C | `app/platform/groups` (models, router); Users & access › **Groups** dialog | `tests/test_blueprint_groups.py` passes |
| D | `plan_editor` / `project_creator` checks on plans, engagements, include/exclude, roll forward and start planning; `hours_remaining` / `hours_over`; `planning/signals.py` and the **Next-cycle signals** dialog on Assurance Plans | `tests/test_blueprint_planning.py` passes; existing plan tests updated to use plan preparers (Managers) instead of ordinary auditors, permissions not weakened |
| D2 | `risk_treatments` table; `grc/risk/assurance.py`; risk record **Treatment and assurance** panel with **Link treatment** | `tests/test_blueprint_strategy.py` passes |
| E | `rcm/copying.py` (import from an audit or a framework programme, clone one objective); `audit_max_objectives` rule (default 500); narratives refused outside the Internal Control workflow; **Import objectives** and **Clone** buttons | `tests/test_blueprint_objectives.py` passes |
| F | Finding remediation and retest columns (migration 0045); `remediation_statuses` and `retest_required_severities` rules; `POST /api/findings/{id}/remediation` and `/retest`; **Remediation** and **Retest** forms on the issue | `tests/test_blueprint_retest.py` passes |
| G | `app/services/reporting` (Views, reports, dashboards, presentations, export, AI Reporting workstreams; migration 0046); **Reports** app (Storyboards became its second tab to keep the sidebar at 30 entries) | `tests/test_blueprint_reports.py` passes |
| H | Full checks | Backend `pytest --ignore=tests/ui`: all pass. Browser `tests/ui`: 12 pass. `ruff check .`: clean. ESLint (`no-undef`) over all SPA scripts: clean. `bandit -ll` on `app/`: no medium/high findings. `semgrep` (p/python, p/javascript) on the new modules: no findings. `gitleaks`: no leaks. Manual browser run of each new screen: no script errors |

| I | Migration 0047 (framework treatments, engagement objectives and entities, report folders/settings/users); `walk.js` application frame used by every record page and the rebuilt apps; see the mapping below | `tests/test_walkthrough_backend.py`, `tests/test_blueprint_*.py` pass; browser `tests/ui`: 13 pass (four tests updated to the new screens, one new Reports test). Screens compared against each walkthrough by screenshot |

### 5.1 Walkthrough to screen mapping

| Walkthrough | GIAW screen |
|-------------|-------------|
| Assurance app | Audits record page: Overview, Planning, Fieldwork, Results, Issues, Supervision, Requests, Progress, Feedback, Project settings |
| Risk-Based Assurance Planning | Assurance Plans: plan list and create page, Annual Program Overview, + Add to plan (new project in four steps, link, rollforward), Coverage (Entities / Categories), Risks heat table, Progress & resources |
| Project Execution | Fieldwork › Objective list (Go To, import, clone objective), project settings workflow cards, Results cards |
| Issue Follow-up and Remediation | Issues & Actions (Activity Center), Issue Tracker with Details, issue page (Issue Information, Follow-up & Remediation with Add action, Retest Information, Retest & sign-off), action pages |
| Strategy Risk Monitoring | Risk Manager: Risk Profile, Heatmaps, Strategy Map, Risk Library, Metrics, Dashboard, Planning feedback; risk page Details / Assessment / Treatment / Metrics / Assurance |
| Reports | Reports app: Browse (By Folder, Recent, Templates › Make a copy), Report Builder (Report, Data, Charts, Design, Publish), report page (Export Download, Email, Add to dashboard) |
| Dashboards & Presentations | Create › Dashboard (Canvas or Static), Dashboard Builder (Reports, Filters, Text, Images, Properties; tabs; Undo/Redo; Preview Mode; Publish); Create › Present (theme), Present Builder (Slides with drag reorder, Reports, Text, Images, Properties; Preview; Publish); AI Reporting (New report, Reports, Workstreams) |

Demo data: the build adds no seed records. The browser check used records titled `DEMO - …` in a disposable development database only.

## 6. Deferred or out of scope

- **Platform-level items Diligent operates:** subdomains, licence and subscription counts, and SSO invitations. GIAW is self-hosted with administrator-created accounts.
- **Framework sync:** pushing later framework changes into projects that already imported them is not built. Imports are copies, and the source reference is kept.
- **AI Reporting:** an AI provider is optional and off by default. Without one, a workstream produces the stored-facts section only and says so.
- **Presentation export:** presentations run in the browser (Present mode). Exporting a presentation to PowerPoint or PDF is not built; reports export to Excel and CSV.
- **Scheduled report delivery** (Broadcast schedule) is not built. Email sends a report now, only to people it is shared with. Robots and Results cover scheduled checks.
- **Report Builder:** Cross Tab layouts, Sections, drill-down analysis styles and the Design formatting toolbar (font, borders, alignment) are not built; Design shows the print preview.
- **Dashboard widgets:** resizing is by width and height in Properties, not by dragging a corner. Video on slides is not supported (images only).
- **Risk metrics:** automated KRI-driven assessment and per-segment assessments are not built; metrics are linked and shown on the risk.
- **Report Views** cover issues, actions, audits, controls, strategic risks and plan projects. Further Views (evidence requests, working papers, KRIs) can be added in `app/services/reporting/views.py`.
- **Remediation by management:** the auditee owner of a published issue records remediation through the issue form; a dedicated auditee-portal tile is not added.
- **Live deployment:** nothing was deployed. Run the migrations (0045, 0046, 0047) when the release is installed.

## 7. Local setup and commands

```bash
uv sync                                   # install
cp .env.example .env                      # then set database URL and keys
uv run python -m scripts.init_db          # migrations + first administrator
uv run python -m scripts.seed_demo        # optional demo data (clearly labelled)
uv run uvicorn app.main:app --port 8001   # run
uv run pytest -q --ignore=tests/ui        # backend tests (needs MySQL)
uv run --group ui pytest -q tests/ui      # browser smoke tests
uv run ruff check .                       # lint
```
