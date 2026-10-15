# GIAW UI Redesign: Step-by-Step Prompt Playbook

**Governing documents:** `mainBLUEPRINT.md` (10 modules / 20 phases) and `giaw-fastAPI.md` (titled `giaw.md` inside) (detailed functional specification and initial screen inventory).  
**Stack (recorded decision, 15 October 2026):** FastAPI + MySQL; SQLAlchemy 2.x, Alembic, Pydantic v2. Front end: the existing plain JavaScript single-page app in `app/static` (no build step) with the GIAW design system (`ui.js`, CSS tokens). Do **not** introduce React, TypeScript, Vite or Tailwind.  
**Architecture:** One integrated modular monolith with clear domain boundaries, shared identity, shared records and explicit module contracts.  
**Reference boundary:** Use publicly documented Diligent One / HighBond behavior and available public screenshots as research references. Build an original GPHA interface; do not claim access to private source code or undocumented internals.

## How to use this playbook

Paste one prompt at a time into your repository-aware coding assistant. Start with Prompt 0. Review its findings, approve the next step, run the tests, inspect the UI, and checkpoint changes before proceeding. Never allow a single prompt to rewrite the whole application. Do not change the approved stack, delete files without evidence they are unused, invent GPHA approval authority, or present mock data as production data.

## Non-negotiable UI rules

- Shared shell: GPHA/GIAW identity, active organization scope, global search, notifications, help, profile, persistent domain navigation, breadcrumbs and clear page titles.
- Consistent design system: typography, spacing, page widths, field sizes, table density, buttons, status labels, focus states, borders and responsive breakpoints.
- Each screen has meaningful loading, empty, error, success and access-denied states.
- Registers use server-side pagination, filtering, sorting and search; column chooser/saved views where appropriate; stable record IDs; useful row actions; visible result count; responsive row expansion.
- Exports must enforce the same server-side permissions and filters as the list. Bulk actions must validate permission and workflow state for every record.
- Forms show required fields, inline validation, server errors, save state, unsaved-change warnings and clear Save Draft / Submit / Return / Approve distinctions.
- Approved/finalized records are immutable except through an approved amendment or reopen/version workflow. Prevent silent overwrites using version checks/concurrency controls.
- Server-side authorization is mandatory: role + organization scope + record relationship + sensitivity + workflow state. Hiding a button is not security.
- No fake metrics, dead buttons, hard-coded production records, insecure evidence links, or unsupported fields. If functionality is absent, implement it end-to-end or mark it clearly unavailable.
- Accessible keyboard navigation, visible focus, labels, contrast, non-color status cues and responsive layouts are required.

## Standard contract required before coding every screen

For each screen, document: screen ID/name; user purpose; roles and scope; entry/exit routes; layout; table columns; form fields and types; required rules and validation; field source (entered/inherited/calculated/synchronized); row actions; API endpoints and request/response contracts; database entities; incoming/outgoing links; workflow states/transitions; sensitivity/version rules; loading/empty/error/access states; responsive/accessibility behavior; source reference and documented-vs-proposed behavior; acceptance tests. Resolve policy gaps as open questions instead of guessing.

---

## Prompt 0 — Repository discovery (do not modify code)

> Act as lead UI/UX and full-stack engineer for the existing GPHA Internal Audit Workspace (GIAW). Read `mainBLUEPRINT.md`, `giaw.md`, README files, package manifests, routes, components, styles, API client, FastAPI routes, Pydantic schemas, SQLAlchemy models, Alembic migrations, tests and Git status.
>
> Do not modify files or install packages yet. Report the actual stack; all current routes/screens; which are functional, partial, mock-only or broken; existing shared components; API-to-screen mappings; database entities; failing tests; console errors; duplicate components; security risks; and discrepancies between code and the two project documents. Make a dependency map of screens and shared components. Identify possible cleanup candidates but do not delete anything. Distinguish verified facts from assumptions. Recommend a safe implementation sequence and baseline test plan. Wait for approval before changing code.

**Gate:** Repository inventory and risks reviewed.

## Prompt 1 — Research public HighBond/Diligent references (no code changes)

> Research the public documentation below and inspect available public screenshots/images where accessible:
>
> - https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/global_topics/index.htm
> - https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/projects-landing-page.htm
> - https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/creating_projects/workflows_and_project_types.html
> - https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/defining_assurance_plans.htm
> - https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/assurance-plans-get-started.htm
> - https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/planning_projects.html
> - https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/fieldwork/gathering_evaluating_evidence.htm
> - https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/fieldwork/managing_issues/managing_issues_and_remediation.html
> - https://docs-apis.highbond.com/#section/Making-requests
>
> Create a source-linked matrix: GIAW screen, reference URL, documented behavior, visual pattern observed (only if actually visible), GPHA adaptation, affected entities, confidence (documented/inferred/proposed), open questions. Do not copy proprietary assets or claim access to private internals. Compare results with `giaw.md`. Do not modify code.

**Gate:** Reference matrix completed; assumptions labeled.

## Prompt 2 — Shared design system and application shell

> Run baseline tests and record current behavior. Then improve the shared design foundation before redesigning individual screens. Reuse the existing frontend stack and libraries where possible. Create/refine tokens for typography, spacing, borders, radii, focus rings, status states, responsive breakpoints and restrained professional colors. Implement reusable components where needed: AppShell, TopBar, SidebarNavigation, Breadcrumbs, PageHeader, ScopeIndicator, StatusBadge, DataTable, FilterBar, Pagination, EmptyState, LoadingState, ErrorState, ConfirmDialog, FormSection, FieldError, DetailPanel, ActivityTimeline and SaveStateIndicator.
>
> Preserve routes and business behavior. Ensure accessibility and responsive behavior. Add component tests. Show browser evidence and report changed files and test results.

**Gate:** Shared shell/components work without breaking existing routes.

## Prompt 3 — Dashboard, global navigation and shared pages

> Redesign the global shell and relevant UI-001–UI-007 screens in `giaw.md`: Sign In, Dashboard, My Work, Notifications, Global Search, User Profile and Help/Release Notes. Navigation should group the ten GIAW modules as one integrated platform and respect role/scope. Show the active authorized context (HQ/Tema/Takoradi/unit), global search, notifications, help and profile.
>
> Dashboard cards and work queues must use real authorized API data: pending approvals, annual plan progress, assigned engagements, overdue evidence, actions due and recent activity only where applicable to the user. Each metric must link to a filtered list and disclose its period/freshness where relevant. No hard-coded production values. Test navigation, empty/error states, responsive layouts, keyboard use and unauthorized search results.

**Gate:** All visible navigation destinations work; dashboard is data-backed.

## Prompt 4 — Module 1: Organization, users, roles and audit trail

> Implement the organization/security screens from `giaw.md`: organization tree/detail, users, roles, scope assignments, lookups/settings and audit trail. Support configurable HQ → Tema Port / Takoradi Port → departments → units, without hard-coding the hierarchy. Specify columns and actions for each list; fields, validation and permissions for each form.
>
> Distinguish role, organizational scope and record relationship. Treat the `giaw.md` role matrix as provisional until GPHA formally confirms delegations. Enforce deny-by-default, least privilege, separation of duties, server-side scope checks and audit logging. Prevent hierarchy cycles and duplicate codes. Test cross-port access denial, unauthorized privilege changes, audit event creation and invalid hierarchy changes.

**Gate:** Organization configuration works safely; server authorization is tested.

## Prompt 5 — Module 2: Audit Universe, Risk and Controls

> Redesign the entity register, risk register/assessment, and controls library as connected screens. Entity columns may include code, name, type/category, organizational path, owner, inherent risk, last audit, next review and coverage where the schema supports them. Risk fields may include title/reference, entity, category, likelihood, impact, inherent/residual score, owner, assessment date, reviewer and status. Controls should link to entities/processes and risks, and show owner, objective, frequency, type, evidence requirement and last assessment where approved.
>
> Do not invent the GPHA risk scoring formula. Use the approved policy; if it is not confirmed, flag it as an open decision and make the formula configurable. Link authoritative entities/risks/controls instead of duplicating records. Implement validated import, filters, audit history and bidirectional navigation. Test score calculations, duplicate codes, scope permissions and entity → risk → control relationships.

**Gate:** Planning can select authoritative entities, risks and controls.

## Prompt 6 — Module 3: Annual Assurance Plan

> Build the Assurance Plan experience using public Assurance Plan documentation as a behavior reference and GPHA's approved approval chain as authority. Provide plan list/detail, plan period, name/description, available hours, proposed engagements, risk rationale, entity coverage, priorities, estimated effort, timing, resource totals, gaps and version history according to the approved model.
>
> Workflow: Audit Managers prepare next-year proposals → validate and consolidate → authorized review/return with comments → approval by the authority confirmed in the GPHA charter/delegation → plan returned to GM Audit → GM Audit distributes approved version to relevant Audit Managers/ports. Use explicit states and backend-enforced transitions. Record decision, approver, timestamp, comments, version and recipients. Prevent self-approval where required. Approved plans are locked; changes create a controlled amendment/version. Link plan items to authoritative entities, risks, controls and engagements. Test return/resubmit, unauthorized approval, duplicate submit, version locking, resource totals and distribution history.

**Gate:** Full plan workflow passes with traceable approvals and distribution.

## Prompt 7 — Module 4: Engagements, planning and frameworks

> Redesign engagement/project list, create wizard, detail dashboard, planning, objectives, risk/control matrix, milestones, assignments and framework selection. Lists should include authorized scope, plan year, entity, engagement type, lead auditor, status, dates and progress where supported. Creation should link an approved plan item when relevant, choose entity scope, objectives, workflow type, team, schedule and template/framework.
>
> Implement workflow-aware structures: a simple workplan may emphasize procedures and outcomes; an internal-control engagement may require narratives, walkthroughs and design/operating-effectiveness tests. Adapt public Diligent patterns to GPHA terminology. Show only applicable tabs by project type, status and permission. Test plan linkage, assignments, template use, state transitions and downstream updates.

**Gate:** Plan items become linked engagements without duplicate records.

## Prompt 8 — Module 5: Fieldwork, testing and workpapers

> Redesign procedures, narratives, walkthroughs, control tests, sampling, workpapers, review notes and sign-off. Define each field from the approved schema: objective, linked risk/control, steps, population/sample where relevant, expected/actual result, exceptions, conclusion, preparer, reviewer, status, dates and evidence links.
>
> Workflow: open assigned engagement → select objective/procedure/control → execute test → record result → link evidence → raise finding if warranted → submit for review → resolve review notes → sign off. Keep workplan and internal-control workflows distinct when data requirements differ. Do not allow silent editing of signed-off work; use controlled reopen/versioning. Test evidence requirements, reviewer rights, concurrency, invalid transitions and cross-engagement access.

**Gate:** Test-to-evidence-to-review chain is traceable.

## Prompt 9 — Module 6: Evidence, documents and collaboration

> Redesign Evidence Hub, evidence requests, respondent upload, evidence details/version history, evidence links, review outcomes, comments and activity timeline. Requests should link to engagement/workpaper/test/finding and include title, description, owner/respondent, due date, confidentiality, requested format, status and distribution scope.
>
> Use private object storage and MySQL metadata/references. Validate file type/size, scan uploads, compute checksum, create immutable version metadata, authorize every download and log access. Never expose evidence using guessable public URLs. Support accepted/rejected/clarification outcomes with comments and version lineage. Link one evidence item to multiple authorized records without duplicating it. Test unsupported files, scan failures, expired requests, unauthorized downloads, cross-port access and version integrity. If secure storage/scanning is not configured, report the dependency honestly.

**Gate:** Secure upload, review, versioning and linking work end-to-end.

## Prompt 10 — Module 7: Findings and remediation

> Redesign finding register/detail, recommendation, management response, action, retest, verification and closure. Use approved fields such as reference, title, engagement, entity, condition, criteria, cause, effect/risk, rating, recommendation, owner, management response, due date, status and evidence links.
>
> Implement approved transitions such as Draft → Submitted for Review → Approved/Issued → Action Assigned → In Progress → Submitted for Verification → Verified/Returned → Closed, adjusted to the approved state model. Overdue should normally be a calculated flag. Management action owners may submit updates but must not independently verify/close their own findings where separation of duties applies. Retests record tester, date, objective, evidence, result, reviewer, recommendation and rationale. Use one authoritative finding across fieldwork, register and reports. Test return/retest/reopen, reminders, permissions and audit trail.

**Gate:** Finding lifecycle from identification through verified closure is auditable.

## Prompt 11 — Module 8: Scheduling, resources and timesheets

> Redesign resource calendar, engagement allocations, capacity, milestones, timesheet entry/submission/approval and history. Show user, period, engagement, activity code if supported, planned/actual hours, notes, status and approver. Distinguish estimates, allocation and approved actual hours. Flag over-allocation, conflicts, missing entries and overdue approvals with links to records.
>
> Connect assignments to planning and approved hours to reporting. Preserve correction history, prevent duplicate submissions and avoid double-counting across engagement/unit/port/HQ reports. Test date boundaries, invalid hours, approval separation, corrections and reconciliation. Do not add payroll features without approval.

**Gate:** Resource data reconciles with engagement and reporting totals.

## Prompt 12 — Module 9: Reports and three-level consolidation

> Implement report catalogue, report builder, preview, metrics, version history and the mandatory consolidation hierarchy.
>
> **Level 1 — Unit Heads:** authorized unit activity, engagements, planned vs actual hours, findings by severity, overdue actions, risks and management responses; distinguish period activity from cumulative open items.
>
> **Level 2 — Port Internal Auditors:** consolidate approved unit reports for Tema or Takoradi; show coverage, progress, severity, overdue remediation, resource utilization, emerging risks, exceptions, reconciliation totals and source lineage.
>
> **Level 3 — GM Audit/HQ:** consolidate authorized HQ and both port reports; show annual plan delivery, universe coverage, major/repeat findings, overdue actions, risk themes, resources and issues requiring executive/committee attention. Restrict drill-downs by permission.
>
> Issued reports must be reproducible snapshots storing definition/version, filters, period, cutoff, source IDs/version references, generation time and approving/issuing user. Corrections create new versions. Missing source reports are flagged, never silently treated as zero. Define every metric and trace it to source records. Exports must enforce the same server-side permissions. Test reconciliation, missing inputs, snapshot stability and export consistency.

**Gate:** Unit → Port → HQ reports reconcile with preserved source lineage.

## Prompt 13 — Module 10: Integrations, operations and optional AI

> Redesign import/migration, API clients, integration jobs, scheduled jobs, system health, notification settings and optional AI assistance. Follow existing versioned FastAPI/OpenAPI conventions. Jobs should show owner, source/destination, schedule, last/next run, result, rows, errors and authorized retry/pause controls. Make retries safe and observable; keep secrets out of UI/logs.
>
> AI may draft or summarize only authorized source material, show source citations, identify generated output and require human verification. AI cannot approve plans, sign off workpapers, set final audit ratings or close findings. If required infrastructure/policy is absent, mark the feature unavailable rather than pretending it works. Test import validation, duplicate detection, retry safety, API scopes, job failure and AI source permissions.

**Gate:** Operations are observable and AI remains optional and human-reviewed.

## Prompt 14 — Cross-module dataflow audit

> Audit every inter-module relationship and build a source-of-truth matrix. Trace:
> organization/scope → every protected record;
> entity → risk → control → Assurance Plan;
> plan item → engagement → objectives/procedures/tests/workpapers;
> workpaper/test → evidence → finding;
> finding → management response → action → retest → closure;
> assignment/approved timesheet → engagement/unit/port/HQ reports;
> unit snapshot → port snapshot → GM Audit snapshot;
> notifications/activity/audit events → underlying record.
>
> For each relationship record source table/entity, link key, source module, consumer, write owner, update behavior, status propagation, snapshot/version rule, permission and test. Fix duplicated authoritative records, dead links, fake totals, stale data and inconsistent IDs. Build an integration test that follows a realistic record from entity/risk through final consolidated report. Live views may update as intended; issued snapshots must not change.

**Gate:** End-to-end cross-module scenario passes.

## Prompt 15 — Screen-by-screen table and form audit

> Compare every route in the repository with the screen catalogue in `giaw.md`. Produce an inventory with screen ID, route, module, implementation status (missing/mock/partial/functional), roles, source entities, endpoints, columns, fields, row actions, workflow states, incoming/outgoing links and test status.
>
> For every table test server-side pagination, filtering, sorting, search, column behavior, result count, empty/error/loading states, authorization-aware exports and responsive behavior. For every form test required fields, server validation, unsaved changes, duplicate-submit protection, workflow restrictions, permissions and audit trail. For detail screens test relationships, scope, version, activity and allowed transitions. Mark unsupported functions as gaps; never fake completion. Fix high-risk defects and rerun inventory.

**Gate:** Every screen has an honest status and verified contract.

## Prompt 16 — Visual refinement against public references

> Use the source-linked reference matrix to refine the UI. For screenshots that are actually available, compare broad patterns: information hierarchy, navigation, density, filters, table readability, tabs, context panels and workflow affordances. Record the source URL and adaptation. Do not claim pixel-perfect parity or copy vendor assets.
>
> Review desktop, tablet and mobile screenshots. Fix inconsistent spacing, oversized cards, awkward wrapping, excessive empty space, overloaded toolbars, unclear primary actions, poor column widths, inaccessible colors and inconsistent detail layouts. Prefer a compact professional workspace: tables for registers, timelines for history, guided steps for complex flows, and KPI cards only when useful. Avoid decorative clutter. Retest affected screens after shared component changes.

**Gate:** Screens are visually consistent and functionality remains intact.

## Prompt 17 — Security, accessibility, performance and regression

> Test server-side authorization, role/scope/state/sensitivity checks, cross-unit/port isolation, export permission, secure evidence downloads, validation, session protections, safe errors, secret handling and audit logging. Test keyboard-only use, focus order, labels, contrast, semantic tables, dialogs and zoom. Inspect query counts, indexes, pagination, payload sizes, unnecessary renders and large file handling. Test timeouts, network errors, expired sessions, duplicate submissions, concurrency, migrations and recovery.
>
> Run backend tests, frontend tests, type checks, lint, build, migration checks and end-to-end tests. Report only tests actually run. Block release for critical access leaks, data loss, broken approvals or inaccurate report reconciliation.

**Gate:** Critical defects are resolved and test results recorded.

## Prompt 18 — GPHA UAT and rollout

> Prepare UAT cases with scenario ID, preconditions, role/scope, steps, expected result, evidence, actual result, pass/fail and defect. Include: configure hierarchy; prepare plan; return/revise/resubmit; record authorized approval; GM Audit distribution; create linked engagement; complete test and evidence; reviewer sign-off; issue finding; management response and independent retest; unit report; port reconciliation; GM Audit final report; unauthorized cross-scope access/export/download denied and logged.
>
> Prepare rollout checklist: backup, migrations, access provisioning, support contacts, incident process, training, data import validation, rollback plan, known limitations and go-live approval. Do not release until required GPHA policy owners approve the workflows and UAT results.

**Gate:** Authorized stakeholders sign off UAT and rollout plan.

## Prompt 19 — Safe cleanup and documentation

> Identify candidate unused files, duplicate components, dead routes, obsolete styles, redundant dependencies, debug logs and unreachable code. Prove each item is unused through import/reference searches, route registries, dynamic imports, build configuration and tests before deletion. Do not delete migrations, historical docs, fixtures, configuration examples or assets merely because a simple search finds no reference.
>
> Update README/developer docs with setup, environment variables, migrations, tests, routes/screens, design system, API contracts, workflow states, permissions and deployment. Run the full test suite/build before and after cleanup. Report every deletion and why safe, dependencies removed, results and remaining technical debt.

**Gate:** Repository is cleaner and remains functional.

---

## Reusable prompt — one individual screen

> Implement/redesign **[SCREEN ID — NAME]**, route **[ROUTE]**, module **[MODULE]**. First inspect the current code, `mainBLUEPRINT.md`, `giaw.md`, API/model and public reference **[URL]**. Purpose: **[USER JOB]**. Roles/scope: **[ROLES]**. Incoming data: **[SOURCES]**. Outputs/actions: **[DESTINATIONS]**. Columns: **[COLUMNS]**. Fields: **[FIELDS]**. Allowed states/actions: **[STATES]**. Related screens: **[ROUTES]**.
>
> Before coding, provide the screen contract: layout, fields/types, required rules, columns, row actions, endpoints, entities, loading/empty/error/denied states, responsive behavior and acceptance tests. Then implement using shared components and real API data. Preserve unrelated routes. Enforce server-side permissions. Do not use fake metrics or inert buttons. Run tests and report changed files, API/schema changes, test results, browser evidence, gaps and upstream/downstream links. Do not mark complete until acceptance tests pass.

## Reusable prompt — table/register

> Audit the table on **[SCREEN/ROUTE]**. Define each column's label, source field, type, formatting, sensitivity, visibility, sort/filter support and responsive priority. Implement server-side pagination, deterministic sorting, filtering and search; validate parameters; authorize before pagination/aggregation; show count and empty/error/loading states. Export must use identical permission/filter rules. Add tests for pagination, sorting, invalid parameters, cross-scope isolation and export. Do not fetch all rows to the browser.

## Reusable prompt — form/workflow

> Audit the **[RECORD TYPE]** form/workflow. Define source of truth, required/optional fields, validation, defaults, state transitions, role/scope rules, separation of duties, audit events, version/concurrency behavior, notifications and downstream consumers. Group fields logically; show inline errors; prevent duplicate submission; warn about unsaved changes; distinguish Save Draft/Submit/Return/Approve/Reject/Close as applicable. Backend must reject invalid transitions even if called directly. Finalized records require an approved amendment/reopen/version workflow. Test positive and negative transitions and permissions.

---

## Source-of-truth / dataflow matrix

| Object | Authoritative module | Consumers | Rule |
|---|---|---|---|
| Organization and user scope | Platform / Organization | All modules | Server authorizes every read/write |
| Auditable entity | Audit Universe | Risk, Controls, Planning, Engagements, Reports | One entity identity |
| Risk assessment | Risk | Assurance Plan, Engagements, Reports | Approved configurable scoring policy |
| Control | Controls | Risk, Fieldwork, Testing, Findings | Tests link to authoritative control |
| Assurance Plan/item | Planning | Engagements, Scheduling, Reports | Approved versions traceable |
| Engagement | Engagements | Fieldwork, Evidence, Findings, Timesheets, Reports | Stable ID and authorized assignments |
| Workpaper/test | Fieldwork | Evidence, Findings, Review, Reports | Controlled sign-off/versioning |
| Evidence/version | Evidence Hub | Workpapers, Findings, Reports | Private storage and authorized references |
| Finding | Findings | Remediation, Reports, Activity | One shared record |
| Action/retest | Remediation | Findings, Notifications, Reports | Authorized independent verification |
| Approved timesheet | Scheduling | Engagement and consolidated reports | No double-counting; preserve corrections |
| Unit report snapshot | Reporting | Port consolidation | Preserve source IDs and cutoff |
| Port snapshot | Reporting | GM Audit consolidation | Reconcile approved unit inputs |
| GM Audit snapshot | Reporting | Executive/committee distribution | Versioned and reproducible |
| Activity/audit event | Shared services | Activity Center, record detail | Do not substitute for business state |

## Required phase completion report

At the end of each prompt, the coding agent must report:
1. Phase and scope.
2. What changed.
3. Screens/routes completed.
4. API/database changes.
5. Upstream/downstream flows verified.
6. Permissions and workflow transitions tested.
7. Tests actually run and results.
8. Screenshots/browser verification.
9. Known defects and open GPHA decisions.
10. Files changed.
11. Checkpoint/rollback.
12. Acceptance status: PASS / FAIL / BLOCKED.
13. Next prompt.

If acceptance fails, fix it before moving forward.

## Public reference links

- Diligent One Help Center: https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/global_topics/index.htm
- Projects landing page: https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/projects-landing-page.htm
- Workflows and project types: https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/creating_projects/workflows_and_project_types.html
- Assurance Plans overview: https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/defining_assurance_plans.htm
- Assurance Plans setup: https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/assurance-plans-get-started.htm
- Project planning: https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/planning_projects.html
- Evidence workflow: https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/fieldwork/gathering_evaluating_evidence.htm
- Issues/remediation: https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/fieldwork/managing_issues/managing_issues_and_remediation.html
- API reference: https://docs-apis.highbond.com/#section/Making-requests

Public documentation supports documented behavior and selected UI patterns; it does not establish every screen, image, private implementation detail or vendor technology choice. Validate GIAW against GPHA policy and the actual repository.
