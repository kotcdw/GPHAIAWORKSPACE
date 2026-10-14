# GPHA INTERNAL AUDIT WORKSPACE (GIAW)

## Research-led product, UX, workflow, data, API and implementation blueprint

**Document:** `giaw.md`\
**Prepared:** 14 October 2026\
**Purpose:** Build a configurable internal audit management workspace
for Ghana Ports and Harbours Authority (GPHA), informed by publicly
documented Diligent One Platform / HighBond workflows and API patterns.

> **Research and intellectual-property note.** This is an original
> implementation specification based on public documentation and GPHA
> requirements. It is not a copy of Diligent's source code, private
> internal architecture, or proprietary UI assets. Diligent One Platform
> was formerly called Diligent HighBond. The public help site documents
> user-facing behavior; the API reference documents supported API
> contracts. Neither source establishes the vendor's complete internal
> technology stack. Every GIAW design choice below that goes beyond
> documented behavior is a recommendation for GPHA, not a claim about
> Diligent's implementation.

------------------------------------------------------------------------

## 1. Executive summary

GIAW should be a **modular, integrated platform**: one product, one
identity and authorization foundation, one shared audit data model, and
separately bounded domain modules. Begin with a **modular monolith**
rather than many independently deployed microservices. Keep clear module
boundaries and API contracts so selected modules can be extracted into
services later if scale or operational needs justify it.

GIAW must support the GPHA structure:

-   Audit Committee
-   Director General (DG)
-   General Manager, Audit (GM Audit)
-   Port Internal Auditor --- Tema (PIA Tema)
-   Port Internal Auditor --- Takoradi (PIA Takoradi)
-   Audit Managers
-   Unit Heads / Supervisors
-   Senior Auditors
-   Auditors
-   Audit Clerks / Audit Assistants

The organization must be configurable: HQ, Tema Port, Takoradi Port,
departments, units, reporting lines, and future entities must not be
hard-coded into application logic.

### Recommended first release

1.  Organization, users, roles and permissions
2.  Audit Universe and risk assessment
3.  Annual Assurance Plan creation, consolidation, submission, review,
    approval and controlled publication
4.  Engagement / audit project setup and planning
5.  Fieldwork, workpapers, tests, evidence and review notes
6.  Findings, management responses, actions, remediation and retesting
7.  Three-tier reporting: Unit Head consolidated reports → Port Internal
    Auditor consolidated reports → GM Audit / HQ final consolidated
    report
8.  Audit trail, document versioning, notifications and dashboard
9.  Import/export and a documented internal REST API

### Core design principles

-   One authoritative record per business object; avoid duplicate copies
    of the same finding or plan item.
-   Use explicit workflow states and server-side transition rules.
-   Keep a complete audit trail for sensitive changes and approvals.
-   Separate *who can see a record* from *who can change it* and *who
    can approve it*.
-   Preserve versions of submitted/approved plans and reports.
-   Do not silently overwrite concurrent edits.
-   Treat uploaded documents as untrusted files; validate, scan and
    authorize every download.
-   Build configurable terminology and custom fields, but keep stable
    internal identifiers.
-   Make the platform usable on desktop and tablet, with responsive
    layouts.
-   Use AI only as an assistive drafting/classification tool; never
    silently approve audit conclusions.

------------------------------------------------------------------------

## 2. Source research and confidence boundaries

### 2.1 Primary sources

1.  Diligent One Platform Help Center index:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/global_topics/index.htm
2.  Diligent One Platform API reference / Making requests:\
    https://docs-apis.highbond.com/#section/Making-requests
3.  API reference landing page:\
    https://docs-apis.highbond.com/public.html
4.  Projects overview / workflow concepts:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/getting_started/projects_in_a_nutshell.htm
5.  Projects planning:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/planning_projects.html
6.  Creating projects:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/creating_projects/creating_projects.html
7.  Evidence Hub concepts:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/evidence_hub/concepts/what-is-evidence-hub.htm
8.  Creating and sending evidence requests:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/evidence_hub/tasks/create-and-send-an-evidence-request.htm
9.  Assurance Plans overview:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/defining_assurance_plans.htm
10. Assurance Plans getting started:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/assurance-plans-get-started.htm
11. Gathering, evaluating and documenting evidence:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/fieldwork/gathering_evaluating_evidence.htm
12. Issue management and remediation:\
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/fieldwork/managing_issues/managing_issues_and_remediation.html

### 2.2 Documented behavior observed in public documentation

-   The help index groups capabilities across areas including Risk &
    Strategy, Internal Controls, Compliance & Ethics, Audit & Analytics,
    Issues & Reporting, Evidence Hub, Assurance Plans, Projects,
    Frameworks, Issue Tracker, Scheduler, Timesheets, and
    reporting-related apps.
-   Projects is documented as a lifecycle for planning, managing,
    executing and reporting work.
-   Project concepts include projects, objectives, narratives, risks,
    controls, test plans, walkthroughs, tests, issues and remediation
    actions.
-   Project workflows include Workplan and Internal Control; available
    components depend on workflow type.
-   Planning records can include background/context, purpose,
    scope/high-level activities and planning files.
-   The public help notes that terminology, fields and tabs may be
    configurable.
-   Project side panels provide contextual access to issues, requests,
    to-dos and time entries.
-   Evidence Hub uses an Evidence Record as a central work item for
    requests, responses, files, participants, decisions and activity
    history.
-   Evidence collection includes request, response, review and
    acceptance/rejection; permissions govern discovery, reading and
    downloads.
-   The API uses REST and JSON:API conventions, bearer-token
    authentication, HTTP verbs, sparse fieldsets, relationship inclusion
    and pagination.
-   The public API reference describes request limits (generally up to
    six requests/second, with stricter limits for users and groups) and
    HTTP status classes/errors.
-   The API documentation warns that some public API endpoints may be
    under active development and directs production users to
    customer-facing documentation.
-   The API docs state that the legacy `highbond.com` endpoints are
    scheduled for deprecation after **16 December 2026**. GIAW should
    not depend on those vendor endpoints unless it has a specific
    integration need; its own API should use a GPHA-controlled domain.

### 2.3 What is not established by public help pages

Do not treat any of the following as known facts about Diligent's
internals unless verified separately:

-   Its complete backend/frontend framework and exact versions
-   Internal source code, private event bus, internal service boundaries
    or deployment topology
-   Hidden database schema beyond API-exposed resource contracts
-   Proprietary design tokens, private screen components or unexposed
    product logic
-   Every customer-specific configuration, field, role, integration or
    UI variant

Accordingly, the GIAW architecture, schema and screen descriptions below
are **proposed GPHA requirements** informed by public behavior, not
reverse-engineered proprietary internals.

------------------------------------------------------------------------

## 3. Product architecture

### 3.1 Recommended architecture: modular monolith first

``` mermaid
flowchart TB
  U[GPHA users] --> WEB[Responsive web UI]
  WEB --> API[Application API / authorization middleware]
  API --> ID[Identity, organization and RBAC]
  API --> WF[Workflow and approvals]
  API --> AUD[Audit planning and engagements]
  API --> EVD[Evidence and document service]
  API --> FIND[Findings and remediation]
  API --> REP[Reporting and analytics]
  API --> NOTIF[Notifications and task inbox]
  ID --> DB[(Relational database)]
  WF --> DB
  AUD --> DB
  FIND --> DB
  REP --> DB
  EVD --> OBJ[(Private object storage)]
  EVD --> DB
  API --> LOG[Immutable audit event log]
  NOTIF --> MAIL[Email / in-app notification provider]
  REP --> EXP[PDF / XLSX / DOCX export workers]
```

**Meaning:** Modules share the same deployable application initially,
but have separate domain services, permission checks, database ownership
rules and tests. Avoid uncontrolled cross-module writes. Use application
events or an outbox table for reliable notifications and background
tasks.

### 3.2 Logical module boundaries

  -----------------------------------------------------------------------
  Module                  Owns                    Main connections
  ----------------------- ----------------------- -----------------------
  Platform &              Organization tree,      All modules
  Administration          users, roles, settings, 
                          dictionaries            

  Audit Universe          Auditable entities,     Risk, plans,
                          processes, units, audit engagements
                          universe records        

  Risk Management         Risk register, scoring, Universe, plans,
                          risk appetite           controls
                          references, mitigations 

  Assurance Planning      Annual plan, proposed   Risk, organization,
                          audits, capacity,       reports
                          review/approval         
                          versions                

  Engagements / Projects  Audit engagements,      Workpapers, evidence,
                          objectives, scope,      findings
                          team, milestones        

  Fieldwork & Testing     Procedures,             Controls, evidence,
                          walkthroughs, samples,  workpapers
                          tests, results          

  Workpapers              Workpaper index,        Engagements, evidence,
                          narratives, references, findings
                          preparer/reviewer       
                          sign-off                

  Evidence Hub            Evidence requests,      Workpapers, tests,
                          files, respondents,     findings
                          review decisions,       
                          access                  

  Findings & Issues       Observations, criteria, Engagements, actions,
                          condition, cause,       reports
                          effect, risk,           
                          recommendation          

  Remediation             Management action       Findings, notifications
                          plans, owners, due      
                          dates, validation,      
                          retesting               

  Reporting               Unit, port and HQ       Plans, engagements,
                          report packs; metrics;  findings
                          export snapshots        

  Scheduler & Timesheets  Schedule, resource      Plans, engagements,
                          allocation, time        dashboards
                          entries                 

  Task / Notification     Assigned tasks, due     All workflow modules
  Center                  dates, reminders,       
                          in-app alerts           

  Audit Trail             Append-only security    All modules
                          and business events     

  Integration & API       Versioned REST          Approved external
                          endpoints, imports,     systems
                          exports, integration    
                          logs                    
  -----------------------------------------------------------------------

### 3.3 Deployment environments

-   Local development
-   Automated test environment
-   User acceptance testing (UAT)
-   Production
-   Optional training/demo environment with synthetic data

Promotion between environments should use version-controlled migrations
and configuration. Never copy real production evidence into developer
environments unless approved, minimized and protected.

### 3.4 Recommended implementation stack (not a Diligent stack claim)

Select a stack the GPHA team can maintain. A viable default is:

-   **Frontend:** React + TypeScript; accessible component library;
    responsive CSS
-   **Backend:** Laravel/PHP or a supported TypeScript backend; choose
    one and enforce consistent conventions
-   **Database:** PostgreSQL or MySQL; use relational constraints and
    transactions for workflow integrity
-   **Files:** private S3-compatible object storage or an equivalent
    controlled file service
-   **Authentication:** organization-approved identity provider where
    available; otherwise secure local authentication with MFA
-   **Background jobs:** queue worker for notifications, exports, scans
    and scheduled reminders
-   **Testing:** unit, integration, API contract, authorization and
    browser end-to-end tests
-   **Observability:** structured logs, error tracking, metrics, backups
    and restore tests

Do not run both Laravel and a second backend framework for the same
business domains without a clear reason. The database is the source of
truth for transactional workflow state.

------------------------------------------------------------------------

## 4. GPHA organization, roles and authorization

### 4.1 Configurable organization hierarchy

``` text
GPHA
├── Audit Committee
├── Director General (DG)
├── General Manager, Audit (GM Audit / HQ)
└── Internal Audit Department
    ├── HQ
    │   └── configurable departments / units
    ├── Tema Port (PIA Tema)
    │   ├── Audit Managers
    │   ├── Unit Heads / Supervisors
    │   ├── Senior Auditors
    │   ├── Auditors
    │   └── Audit Clerks / Assistants
    └── Takoradi Port (PIA Takoradi)
        ├── Audit Managers
        ├── Unit Heads / Supervisors
        ├── Senior Auditors
        ├── Auditors
        └── Audit Clerks / Assistants
```

This is a configurable reporting model, not a fixed tree in source code.
Model organization nodes and effective-dated reporting relationships. A
person may have a primary role and separately granted project-specific
responsibilities.

### 4.2 Suggested role matrix

  -------------------------------------------------------------------------------------------------------------------------------------
  Capability         Auditor /     Senior     Unit        Audit                PIA         GM Audit         DG / Audit     System Admin
                         Clerk    Auditor     Head      Manager                                              Committee 
  ------------- -------------- ---------- -------- ------------ ------------------ ---------------- ------------------ ----------------
  View assigned            Yes        Yes      Yes          Yes                Yes              Yes   Summary/approved   Support access
  engagements                                                                                                    packs             only

  Prepare           Limited by        Yes   Review       Review          Oversight        Oversight No routine editing       No routine
  workpapers        assignment                                                                                                  editing

  Submit unit               No         No      Yes    Delegated                Yes              Yes                 No               No
  report                                                                                                               

  Consolidate               No         No       No      Prepare     Approve/submit             View                 No               No
  port report                                                                                                          

  Consolidate               No         No       No   Contribute         Contribute   Prepare/submit Approve/receive as               No
  HQ report                                                                                                     policy 

  Approve                   No         No       No    Recommend   Review/recommend           Submit  Approval per GPHA               No
  annual                                                                                                       charter 
  assurance                                                                                                            
  plan                                                                                                                 

  Manage users              No         No       No           No                 No               No                 No              Yes
  and roles                                                                                                            

  View audit      Own/relevant   Relevant     Unit     Assigned         Port scope         HQ scope     Approved scope   Security-admin
  trail                records    records    scope         port                                                                   scope
  -------------------------------------------------------------------------------------------------------------------------------------

**Important:** Final approval authority must follow GPHA's approved
charter and delegations. The matrix is a starting proposal, not a claim
that every role has already been formally authorized.

### 4.3 Authorization model

Implement role-based access control (RBAC) plus scope-based checks:

-   **Role:** what action a user may perform (read, create, edit,
    submit, review, approve, export, administer).
-   **Scope:** which records the action applies to (own, assigned
    engagement, unit, port, HQ, organization).
-   **Relationship:** whether the user is a preparer, reviewer, owner,
    respondent or approver on that record.
-   **State:** whether the record is currently editable or the requested
    transition is allowed.
-   **Sensitivity:** whether the evidence/report is restricted or
    confidential.

Every API endpoint must authorize at the server, not merely hide buttons
in the UI. Use deny-by-default behavior. Enforce separation of duties
for preparation, review and approval where required.

------------------------------------------------------------------------

## 5. Screen and interface inventory

The following is a proposed initial screen inventory. It is not a claim
that Diligent uses these exact screens or names. Each screen should
share a consistent layout and common interaction rules.

### 5.1 Global application shell

**Layout regions**

1.  Header: GPHA/GIAW identity, active organizational context, global
    search, help, notifications, user profile.
2.  Left navigation: module navigation grouped by work domain.
3.  Breadcrumb row: current module → record list → selected record.
4.  Main content: page title, contextual actions, filters, content
    table/cards/forms.
5.  Optional right-side context panel: comments, tasks, evidence,
    activity or metadata.
6.  Footer/status region: save status, last updated, version or
    environment label.

**Global navigation proposal**

-   Home / Dashboard
-   My Tasks
-   Organization
-   Audit Universe
-   Risk Register
-   Annual Assurance Plan
-   Engagements
-   Fieldwork & Testing
-   Workpapers
-   Evidence Hub
-   Findings & Issues
-   Remediation
-   Reports & Consolidation
-   Scheduler & Timesheets
-   Notifications
-   Administration
-   Audit Trail

### 5.2 Screen inventory by module

  --------------------------------------------------------------------------------------------------------------
  ID             Screen              Route suggestion                  Primary users         Main purpose
  -------------- ------------------- --------------------------------- --------------------- -------------------
  GIAW-001       Sign in             `/login`                          All                   Authenticate users

  GIAW-002       Dashboard           `/dashboard`                      All                   Role-scoped work
                                                                                             summary

  GIAW-003       My Tasks            `/tasks`                          All                   Work queue and due
                                                                                             dates

  GIAW-004       Notifications       `/notifications`                  All                   In-app alerts and
                                                                                             history

  GIAW-005       Organization tree   `/admin/organization`             Admin, GM Audit       Maintain
                                                                                             HQ/port/unit
                                                                                             hierarchy

  GIAW-006       Users               `/admin/users`                    Admin                 User lifecycle and
                                                                                             assignments

  GIAW-007       Roles & permissions `/admin/roles`                    Admin                 Configure grants
                                                                                             and scope

  GIAW-008       Audit Universe list `/audit-universe`                 Audit leadership      Browse auditable
                                                                                             entities

  GIAW-009       Audit Universe      `/audit-universe/:id`             Audit leadership      Profile, risks,
                 detail                                                                      history

  GIAW-010       Risk Register       `/risks`                          Auditors, managers    Assess and monitor
                                                                                             risk

  GIAW-011       Risk detail/editor  `/risks/:id`                      Authorized roles      Score, owner,
                                                                                             mitigation

  GIAW-012       Annual plan list    `/assurance-plans`                GM Audit, PIA,        Plan periods and
                                                                       managers              status

  GIAW-013       Annual plan         `/assurance-plans/:id`            Plan team             Plan items,
                 workspace                                                                   capacity, coverage

  GIAW-014       Plan                `/assurance-plans/:id/review`     Reviewers/approvers   Comments and
                 submission/review                                                           decision

  GIAW-015       Plan version        `/assurance-plans/:id/versions`   Authorized roles      Compare approved
                 history                                                                     versions

  GIAW-016       Engagement register `/engagements`                    Audit team            Filterable audit
                                                                                             portfolio

  GIAW-017       Create engagement   `/engagements/new`                Manager               Create from
                 wizard                                                                      template or blank

  GIAW-018       Engagement overview `/engagements/:id`                Assigned team         Scope, status,
                                                                                             team, milestones

  GIAW-019       Planning            `/engagements/:id/planning`       Assigned team         Background,
                                                                                             purpose, scope,
                                                                                             files

  GIAW-020       Objectives / audit  `/engagements/:id/objectives`     Assigned team         Objectives and
                 program                                                                     procedures

  GIAW-021       Risk-control matrix `/engagements/:id/rcm`            Assigned team         Risks, controls and
                                                                                             mappings

  GIAW-022       Fieldwork work      `/engagements/:id/fieldwork`      Auditors              Procedures,
                 queue                                                                       samples, results

  GIAW-023       Control test detail `/tests/:id`                      Auditor/reviewer      Test steps and
                                                                                             conclusions

  GIAW-024       Workpaper index     `/engagements/:id/workpapers`     Assigned team         Evidence-backed
                                                                                             workpapers

  GIAW-025       Workpaper editor    `/workpapers/:id`                 Preparer/reviewer     Narrative,
                                                                                             references,
                                                                                             sign-off

  GIAW-026       Evidence request    `/evidence/requests`              Audit team            Track requests and
                 list                                                                        responses

  GIAW-027       Evidence record     `/evidence/:id`                   Assigned participants Request, files,
                 detail                                                                      review decision

  GIAW-028       Evidence repository `/evidence/library`               Authorized users      Search and reuse
                                                                                             permitted evidence

  GIAW-029       Findings register   `/findings`                       Audit team/management Track exceptions
                                                                                             and severity

  GIAW-030       Finding detail      `/findings/:id`                   Authorized users      Criteria,
                                                                                             condition, cause,
                                                                                             effect

  GIAW-031       Management response `/findings/:id/response`          Finding owner         Response and action
                                                                                             plan

  GIAW-032       Remediation tracker `/remediation`                    Management/audit      Action due dates
                                                                                             and validation

  GIAW-033       Retesting detail    `/remediation/:id/retest`         Auditor/reviewer      Test remediation
                                                                                             effectiveness

  GIAW-034       Unit consolidated   `/reports/unit`                   Unit Head             Unit-level report
                 report                                                                      pack

  GIAW-035       Port consolidated   `/reports/port`                   PIA                   Port roll-up and
                 report                                                                      certification

  GIAW-036       HQ final report     `/reports/hq`                     GM Audit              Organization-wide
                                                                                             final consolidation

  GIAW-037       Report builder      `/reports/builder`                Authorized roles      Filters, sections,
                                                                                             templates

  GIAW-038       Report              `/reports/:id/preview`            Authorized roles      Review and export a
                 preview/export                                                              snapshot

  GIAW-039       Schedule/resource   `/schedule`                       Managers              Timelines and
                 planner                                                                     assignments

  GIAW-040       Timesheets          `/timesheets`                     Audit team            Time spent, submit
                                                                                             and approve

  GIAW-041       Template library    `/admin/templates`                Admin/GM Audit        Plan, engagement
                                                                                             and report
                                                                                             templates

  GIAW-042       Custom              `/admin/configuration`            Admin                 Configurable fields
                 fields/settings                                                             and dictionaries

  GIAW-043       Audit trail         `/admin/audit-trail`              Auditor/security      Search security and
                                                                       admin                 business events

  GIAW-044       Integration/API     `/admin/integrations`             Technical admin       API clients,
                 settings                                                                    imports, health

  GIAW-045       Data import center  `/admin/imports`                  Authorized admin      Validate and import
                                                                                             approved datasets
  --------------------------------------------------------------------------------------------------------------

### 5.3 Reusable list-page layout

Every register/list screen should follow a predictable pattern:

-   Page title and concise purpose
-   Primary action (e.g. Create, Add, Submit)
-   Summary metrics, only if meaningful
-   Search box
-   Filter chips or filter drawer
-   Saved views (optional)
-   Sortable table with pagination
-   Row selection and permitted bulk actions
-   Row menu for open, edit, duplicate, archive, export where authorized
-   Empty state with a helpful next step
-   Loading, error, no-results and permission-denied states
-   Responsive mobile/tablet card view when the table cannot fit

### 5.4 Common table conventions

-   Use a stable record number and a readable title.
-   Show status as text plus a neutral visual indicator; do not rely on
    color alone.
-   Use consistent date format configured for GPHA.
-   Default sort should be meaningful (e.g. updated date or planned
    start date).
-   Use server-side filtering, sorting and pagination for large
    datasets.
-   Keep row actions contextual and permission-aware.
-   Preserve filters when users open a record and return to the list.
-   Provide column chooser only where it does not compromise usability.
-   Export only the records the current user is authorized to see.
-   Do not expose sensitive file URLs or secrets in table data.

------------------------------------------------------------------------

## 6. Page columns, rows and form attributes

The following schemas are proposed minimum UI contracts. Every record
should also have internal primary key, created/updated timestamps and
actor references, even where those are not shown to users.

### 6.1 Dashboard

**Summary cards** - My open tasks - Overdue tasks - Active engagements -
Plan completion percentage - Open high/critical findings - Remediation
overdue - Evidence requests awaiting response - Pending approvals

**Dashboard tables** - My tasks: `task_no`, `title`, `record_type`,
`record_no`, `assigned_by`, `due_date`, `priority`, `status`, `action` -
Pending approvals: `record_no`, `record_title`, `submitted_by`,
`submitted_at`, `current_stage`, `age_days`, `action` - Recent activity:
`event_time`, `actor`, `action`, `record_type`, `record_no`, `summary`

Metrics must be scope-filtered. A unit auditor must not see
organization-wide confidential data just because it appears on a
dashboard.

### 6.2 Organization list/tree

**Columns:** `node_code`, `node_name`, `node_type`, `parent_node`,
`port_or_hq`, `head_user`, `effective_from`, `effective_to`, `active`,
`actions`.

**Form attributes:** - `node_code` (required, unique within configured
scope) - `node_name` (required) - `node_type` (HQ, port, department,
unit, team, committee, other configurable type) - `parent_node_id`
(nullable for root) - `head_user_id` (nullable) - `reporting_order`
(integer) - `effective_from`, `effective_to` - `is_active` -
`description` - `custom_attributes` (JSON object with validated schema)

Prevent circular parent-child links. Do not delete an organization node
with historical audit records; deactivate or close its effective dates
instead.

### 6.3 Users

**Columns:** `staff_no`, `full_name`, `email`, `job_title`,
`primary_unit`, `primary_port`, `roles`, `account_status`, `last_login`,
`actions`.

**Form attributes:** `staff_no`, `full_name`, `email`, `phone`
(optional), `job_title`, `organization_node_id`, `manager_user_id`,
`role_assignments[]`, `effective_from`, `effective_to`, `is_active`,
`mfa_status` (read-only from identity provider if integrated).

Avoid storing unnecessary personal information. Enforce uniqueness for
staff number and normalized email.

### 6.4 Audit Universe

**Columns:** `universe_code`, `entity_or_process`, `category`,
`port_or_hq`, `unit`, `process_owner`, `inherent_risk`, `residual_risk`,
`last_audit_date`, `next_review_date`, `audit_frequency`, `status`.

**Form attributes:** `code`, `name`, `description`, `entity_type`,
`organization_node_id`, `process_owner_id`, `strategic_objective`,
`inherent_likelihood`, `inherent_impact`, `control_effectiveness`,
`residual_likelihood`, `residual_impact`, `risk_rating`,
`last_audit_date`, `proposed_frequency_months`, `last_assessed_at`,
`next_review_date`, `active`.

Risk scores should be calculated from a versioned, configurable scoring
matrix. Store component scores and the matrix version used; do not store
only the final label.

### 6.5 Risk Register

**Columns:** `risk_code`, `risk_title`, `risk_category`,
`linked_entity`, `risk_owner`, `likelihood`, `impact`, `inherent_score`,
`control_effectiveness`, `residual_score`, `response_strategy`,
`review_date`, `status`.

**Form attributes:** `risk_code`, `title`, `description`, `cause`,
`event`, `consequence`, `category`, `organization_node_id`,
`universe_item_id`, `risk_owner_id`, `inherent_likelihood`,
`inherent_impact`, `control_effectiveness`, `residual_likelihood`,
`residual_impact`, `risk_appetite_reference`, `response_strategy`,
`mitigation_summary`, `review_date`, `status`, `risk_matrix_version_id`.

### 6.6 Annual Assurance Plan

**Plan header fields** - `plan_no` (system-generated, unique) -
`plan_name` (required) - `planning_year` (required) - `period_start`,
`period_end` (required) - `prepared_by`, `prepared_at` -
`total_available_hours` - `status` - `current_version` - `submitted_at`,
`submitted_by` - `approval_decision`, `approved_by`, `approved_at` -
`approval_comments` - `published_at` - `supersedes_plan_version_id`
(optional)

**Plan item table columns** - `item_no` - `audit_title` -
`audit_universe_item` - `port_hq` - `unit` - `risk_rating` -
`audit_objective` - `proposed_scope` - `planned_start` - `planned_end` -
`estimated_hours` - `lead_auditor` - `team` - `audit_type` -
`mandatory_or_discretionary` - `strategic_alignment` -
`coverage_reason` - `priority` - `item_status`

**Form validation** - Planning period start must precede end. - Hours
must be non-negative and plan totals must reconcile to item estimates. -
Plan item must link to a valid auditable entity or explicitly state an
approved exception. - The same active plan must not contain duplicate
items unless marked as distinct scopes. - Only permitted roles can
submit or approve. - Submitted/approved versions are immutable
snapshots; revisions create a new version.

### 6.7 Engagement register

**Columns:** `engagement_no`, `title`, `audit_type`, `port_hq`, `unit`,
`plan_reference`, `lead_auditor`, `manager`, `planned_start`,
`planned_end`, `actual_start`, `actual_end`, `progress_pct`,
`risk_level`, `status`, `last_updated`.

**Form attributes:** `engagement_no`, `title`, `project_type_id`,
`assurance_plan_item_id`, `organization_node_id`, `audit_objective`,
`background`, `purpose`, `scope`, `out_of_scope`, `criteria`,
`methodology`, `risk_assessment_summary`, `planned_start`,
`planned_end`, `budget_hours`, `lead_user_id`, `manager_user_id`,
`team_user_ids[]`, `status`, `template_id`.

### 6.8 Objectives and audit program

**Columns:** `objective_no`, `objective_title`, `risk_link`,
`procedure_count`, `completed_procedures`, `owner`, `due_date`,
`conclusion_status`.

**Objective fields:** `engagement_id`, `reference`, `title`,
`description`, `audit_assertion`, `risk_links[]`, `assigned_user_id`,
`planned_start`, `planned_end`, `status`, `conclusion`,
`conclusion_status`.

**Procedure fields:** `procedure_no`, `objective_id`, `procedure_title`,
`procedure_type`, `steps`, `population_definition`, `sample_method`,
`sample_size`, `assigned_to`, `due_date`, `result`, `exception_count`,
`review_status`.

### 6.9 Risk-control matrix

**Columns:** `risk_code`, `risk_title`, `control_code`, `control_title`,
`control_owner`, `control_type`, `frequency`, `design_assessment`,
`operating_effectiveness`, `test_status`, `linked_findings`.

**Control fields:** `control_code`, `title`, `description`,
`objective_id`, `owner_user_id`, `control_type`,
`preventive_or_detective`, `manual_or_automated`, `frequency`,
`evidence_expected`, `design_effectiveness`, `status`.

Risk-control relationships should be many-to-many using a join table.
One risk can map to multiple controls; one control can mitigate multiple
risks.

### 6.10 Testing and samples

**Test columns:** `test_no`, `control_or_procedure`, `testing_round`,
`sample_size`, `sampled_by`, `assigned_to`, `planned_date`,
`actual_date`, `exception_count`, `conclusion`, `review_status`.

**Test fields:** `test_plan_id`, `control_id` (optional), `procedure_id`
(optional), `testing_round_no`, `population_description`,
`sampling_method`, `sample_size`, `sample_selection_rationale`,
`test_steps`, `result_summary`, `exceptions_found`, `conclusion_status`,
`prepared_by`, `prepared_at`, `reviewed_by`, `reviewed_at`.

**Sample fields:** `test_id`, `sample_reference`, `selection_basis`,
`population_item_ref`, `test_result`, `exception_flag`,
`evidence_links[]`, `notes`.

Do not use one free-text status field for both test execution and
reviewer approval. Keep separate status dimensions.

### 6.11 Workpapers

**Columns:** `workpaper_ref`, `title`, `engagement_no`, `objective`,
`preparer`, `prepared_at`, `reviewer`, `review_status`,
`evidence_count`, `version`.

**Fields:** `workpaper_ref`, `engagement_id`, `objective_id`, `title`,
`purpose`, `procedure_performed`, `work_performed`, `results`,
`conclusion`, `limitations`, `prepared_by`, `prepared_at`,
`preparer_signoff_at`, `reviewer_id`, `review_status`, `reviewed_at`,
`review_notes`, `version_no`, `parent_version_id`.

Review status examples: `draft`, `submitted_for_review`,
`review_notes_open`, `resubmitted`, `reviewed`, `approved`, `locked`.
Define permitted transitions centrally.

### 6.12 Evidence requests and records

**Request list columns:** `request_no`, `subject`, `engagement_no`,
`respondent`, `requested_by`, `requested_at`, `due_date`,
`response_date`, `status`, `reviewer`, `action`.

**Evidence record fields:** `record_no`, `title`, `description`,
`scope_start`, `scope_end`, `engagement_id`, `requester_id`,
`respondent_id`, `alternate_respondent_id`, `reviewer_id`,
`viewer_ids[]`, `due_date`, `response_text`, `status`, `decision`,
`decision_comment`, `submitted_at`, `reviewed_at`.

**Attachment metadata:** `file_id`, `evidence_record_id`,
`original_filename`, `storage_key`, `mime_type`, `size_bytes`,
`sha256_checksum`, `uploaded_by`, `uploaded_at`, `scan_status`,
`classification`, `version_no`, `supersedes_file_id`.

Suggested evidence statuses: `draft`, `awaiting_response`,
`in_progress`, `submitted_for_review`, `changes_requested`, `accepted`,
`rejected`, `cancelled`, `closed`. These are GIAW proposals; finalize
them with GPHA policy.

### 6.13 Findings

**Register columns:** `finding_no`, `title`, `engagement_no`, `port_hq`,
`unit`, `severity`, `risk_rating`, `owner`, `identified_date`,
`target_remediation_date`, `remediation_status`, `retest_status`,
`publication_status`.

**Finding fields:** - `finding_no` (unique, system-generated) -
`title` - `engagement_id` - `objective_id` (optional) - `control_id`
(optional) - `criteria` - `condition` - `cause` - `effect_or_risk` -
`risk_rating` - `severity` - `recommendation` - `evidence_links[]` -
`owner_user_id` - `management_response` -
`management_agreement_status` - `target_remediation_date` -
`identified_at` - `reported_at` - `publication_status` - `status` -
`closed_at`

Keep audit facts and evidence separate from management's response.
Management disagreement must be recorded, not overwritten or hidden.

### 6.14 Remediation and retesting

**Action columns:** `action_no`, `finding_no`, `action_title`,
`action_owner`, `due_date`, `progress`, `evidence_submitted`,
`validated_by`, `validation_status`, `retest_date`, `status`.

**Action fields:** `finding_id`, `action_title`, `action_description`,
`owner_user_id`, `contributor_ids[]`, `due_date`,
`management_milestones`, `progress_status`, `completion_claim`,
`completion_evidence_ids[]`, `submitted_for_validation_at`,
`validated_by`, `validation_result`, `validation_notes`,
`retest_required`, `retest_due_date`, `retest_result`, `closed_at`.

A management assertion that an action is complete is not the same as
auditor validation. Keep these as distinct events.

### 6.15 Consolidated reporting

**Unit report columns:** `unit`, `period`, `planned_audits`,
`completed_audits`, `in_progress_audits`, `overdue_audits`,
`open_findings`, `high_critical_findings`, `overdue_actions`,
`hours_used`, `submitted_by`, `submission_status`.

**Port report columns:** `port`, `period`, `unit_reports_received`,
`unit_reports_pending`, `audit_plan_progress`, `coverage_summary`,
`findings_summary`, `remediation_summary`, `resource_variance`,
`pia_decision`, `submitted_to_hq_at`.

**HQ report columns:** `period`, `tema_submission_status`,
`takoradi_submission_status`, `hq_audit_summary`, `plan_delivery`,
`significant_findings`, `overdue_remediation`, `resource_summary`,
`gm_review_status`, `final_approval_status`, `publication_version`.

**Report header fields:** `report_no`, `report_type`, `period_start`,
`period_end`, `organization_scope`, `version_no`, `source_cutoff_at`,
`prepared_by`, `reviewed_by`, `approved_by`, `status`, `snapshot_hash`,
`generated_at`, `published_at`.

Reports must be reproducible. Store the data cutoff timestamp, template
version, selected filters and a snapshot or sufficient immutable
references to reconstruct what was approved.

### 6.16 Scheduler and timesheets

**Schedule columns:** `engagement_no`, `task`, `assigned_user`,
`planned_start`, `planned_end`, `dependency`, `milestone`, `status`,
`variance_days`.

**Timesheet columns:** `entry_no`, `user`, `work_date`, `engagement_no`,
`activity_code`, `hours`, `description`, `submitted_at`, `approver`,
`approval_status`.

Validate that hours are positive, within configurable limits and not
duplicated unintentionally. Corrections should be traceable.

------------------------------------------------------------------------

## 7. End-to-end workflow specifications

### 7.1 Annual Assurance Plan workflow

GPHA's required core process is preserved:

1.  Audit Managers prepare proposed audits and resource estimates for
    the next year.
2.  Unit Heads review and consolidate relevant proposals.
3.  PIA Tema and PIA Takoradi review their port portfolios and
    consolidate port-level proposals.
4.  GM Audit consolidates HQ, Tema and Takoradi into the
    organization-wide annual Assurance Plan.
5.  GM Audit submits the plan to the Audit Committee for approval,
    following the formally approved GPHA governance rules.
6.  The decision is recorded with approver, timestamp, comments and plan
    version.
7.  If rejected or returned, comments create a revision task; the
    submitted version remains preserved.
8.  After approval, GM Audit publishes the approved plan and distributes
    it to relevant Audit Managers and PIAs.
9.  Each plan item may create or link to an engagement, retaining
    traceability to the approved plan version.
10. Changes after approval use a controlled amendment workflow, with
    reason and reapproval rules based on materiality.

``` mermaid
flowchart TD
  A[Audit Managers draft proposals] --> B[Unit Head reviews/consolidates]
  B --> C[PIA reviews port proposals]
  C --> D[GM Audit consolidates HQ + Tema + Takoradi]
  D --> E[Submit plan for Audit Committee decision]
  E --> F{Decision}
  F -->|Return / reject| G[Record comments and revision tasks]
  G --> D
  F -->|Approve| H[Freeze approved version]
  H --> I[GM Audit publishes and distributes]
  I --> J[Create/link engagements]
  J --> K[Monitor plan delivery and coverage]
```

**Validation rules** - A plan cannot be approved if required fields,
scope, resource totals or mandatory review steps are missing. - Approval
applies to a specific version, not a mutable live form. - Only the
authorized role can make the transition. - Each transition writes an
audit event. - The UI displays who currently owns the next action. -
Approval comments are mandatory for rejection/return and recommended for
approval. - The plan dashboard distinguishes submitted, returned,
approved, published and amended versions.

### 7.2 Engagement lifecycle

`proposed → approved_for_execution → planning → fieldwork → review → draft_reporting → management_response → final_reporting → closed → archived`

The exact transitions and terms should be configurable, but transitions
must be controlled by server-side rules. An engagement may be paused or
cancelled only through defined transitions with a reason.

### 7.3 Workpaper review workflow

1.  Preparer creates or updates a workpaper.
2.  Preparer links procedures, test results and evidence.
3.  Preparer performs completeness checks and signs off.
4.  Workpaper is submitted for review; the submitted version is frozen
    for review.
5.  Reviewer either approves or returns it with comments.
6.  Returned work creates review-note tasks; preparer edits a new
    version and resubmits.
7.  Approval captures reviewer identity, timestamp and version hash.
8.  Material changes after approval invalidate or require renewed
    sign-off according to policy.

### 7.4 Evidence collection workflow

1.  Owner creates a request with description, scope, due date and
    required file types or information.
2.  Owner assigns a respondent and reviewer; optional viewers/alternate
    respondent may be assigned.
3.  Respondent acknowledges the request, enters a response and uploads
    evidence.
4.  Uploads pass file validation and malware scanning.
5.  Respondent submits for review.
6.  Reviewer accepts or returns/rejects with comments.
7.  Every response, file version, reassignment and decision is recorded.
8.  Accepted evidence may be linked to multiple authorized
    workpapers/findings without duplicating the binary file.
9.  Download and reuse are reauthorized at request time.

### 7.5 Findings and remediation workflow

`draft → under_review → agreed_or_disputed → reported → action_planned → in_remediation → submitted_for_validation → retesting (if required) → closed`

Possible side states: `returned_for_revision`, `overdue`,
`risk_accepted`, `cancelled` (only with permission and reason). Keep
`management_agreement_status`, `remediation_status` and `finding_status`
separate.

### 7.6 Three-tier reporting workflow

**Tier 1 --- Unit Heads** - Gather unit engagement updates, workpaper
review status, findings, actions, time/resource data. - Validate
completeness and submit a unit report. - On return, revise without
erasing the previous submission.

**Tier 2 --- PIA Tema / PIA Takoradi** - See unit submissions within
their port scope. - Identify missing units, duplicates, inconsistent
counts and overdue work. - Consolidate and certify the port report. -
Submit the port report to GM Audit.

**Tier 3 --- GM Audit / HQ** - Compare port reports against the approved
plan and HQ work. - Resolve data quality exceptions with a tracked
query/return workflow. - Generate the final consolidated report
snapshot. - Route it for approval/distribution according to GPHA
policy. - Publish the final version and preserve the exact underlying
snapshot.

Never sum percentages directly when their denominators differ. Calculate
aggregate rates from numerator/denominator totals.

------------------------------------------------------------------------

## 8. Workflow engine specification

Implement a central workflow configuration model rather than embedding
approval logic in UI components.

### 8.1 Workflow entities

-   `workflow_definitions`: key, name, version, module, active
-   `workflow_states`: definition_id, state_key, label, terminal_flag
-   `workflow_transitions`: definition_id, from_state, to_state,
    action_key, condition_config, required_permission
-   `workflow_instances`: definition_id, record_type, record_id,
    current_state, version
-   `workflow_tasks`: instance_id, transition_id, assignee_id/group,
    due_at, status
-   `workflow_decisions`: task_id, decision, comment, actor_id,
    decided_at
-   `workflow_history`: instance_id, old_state, new_state, actor_id,
    reason, occurred_at
-   `workflow_delegations`: delegator_id, delegate_id, start_at, end_at,
    scope, approved_by

### 8.2 Transition execution algorithm

Within one database transaction:

1.  Load the record and workflow instance.
2.  Verify the record version to prevent lost updates.
3.  Verify the actor's identity, role, scope and relationship to the
    record.
4.  Confirm the current state and requested transition are valid.
5.  Validate required fields and attached evidence.
6.  Apply domain changes and transition.
7.  Record immutable workflow history and audit event.
8.  Create next tasks and an outbox notification event.
9.  Commit.
10. Deliver notifications asynchronously and retry safely on transient
    failures.

The server must not trust a client-supplied role, approval result, owner
or state.

### 8.3 Concurrency and idempotency

-   Use optimistic locking (`version_no`) or equivalent row-version
    checks.
-   A stale save returns a conflict response with a refresh/compare
    option; do not silently overwrite.
-   Use idempotency keys for retryable create/submit/export requests.
-   Notification delivery must not cause duplicate workflow transitions.
-   Bulk operations must report per-record success/failure and must not
    bypass permission checks.

------------------------------------------------------------------------

## 9. Data model and ERD

### 9.1 Core relationships

``` mermaid
erDiagram
  ORGANIZATION_NODE ||--o{ ORGANIZATION_NODE : parent_of
  ORGANIZATION_NODE ||--o{ USER_ORG_ASSIGNMENT : includes
  USER ||--o{ USER_ORG_ASSIGNMENT : assigned_to
  USER ||--o{ ROLE_ASSIGNMENT : granted
  ROLE ||--o{ ROLE_ASSIGNMENT : assigned
  ORGANIZATION_NODE ||--o{ UNIVERSE_ITEM : scopes
  UNIVERSE_ITEM ||--o{ RISK : identifies
  ASSURANCE_PLAN ||--o{ ASSURANCE_PLAN_VERSION : versions
  ASSURANCE_PLAN_VERSION ||--o{ PLAN_ITEM : contains
  PLAN_ITEM }o--o| UNIVERSE_ITEM : covers
  PLAN_ITEM ||--o| ENGAGEMENT : realizes
  ENGAGEMENT ||--o{ OBJECTIVE : contains
  OBJECTIVE ||--o{ PROCEDURE : defines
  OBJECTIVE ||--o{ RISK : evaluates
  OBJECTIVE ||--o{ CONTROL : organizes
  RISK }o--o{ CONTROL : mitigated_by
  CONTROL ||--o{ CONTROL_TEST : tested_by
  ENGAGEMENT ||--o{ WORKPAPER : documents
  WORKPAPER ||--o{ WORKPAPER_VERSION : versions
  EVIDENCE_RECORD ||--o{ EVIDENCE_FILE : contains
  WORKPAPER }o--o{ EVIDENCE_RECORD : cites
  ENGAGEMENT ||--o{ FINDING : raises
  FINDING ||--o{ REMEDIATION_ACTION : addressed_by
  REMEDIATION_ACTION ||--o{ RETEST : verified_by
  WORKFLOW_INSTANCE ||--o{ WORKFLOW_TASK : creates
  USER ||--o{ AUDIT_EVENT : performs
```

### 9.2 Database conventions

-   Use UUIDs or non-guessable public IDs for externally exposed record
    references; internal numeric keys are acceptable where operationally
    justified.
-   Every mutable business table should have `created_at`, `created_by`,
    `updated_at`, `updated_by`, and `version_no` where appropriate.
-   Use foreign keys, unique constraints, check constraints and indexes.
-   Use UTC timestamps in storage and localize display to GPHA settings.
-   Use soft deletion only where it fits retention policy; never make
    soft deletion a way to erase audit history.
-   Use explicit join tables for many-to-many relationships.
-   Use relational columns for fields used in joins, authorization,
    filters and reports. JSON fields are for validated configurable
    attributes, not a substitute for the core schema.
-   Store large files outside the relational database; persist metadata,
    checksums and access relationships in the database.
-   Record schema migrations in version control.

### 9.3 Suggested tables and core attributes

#### Identity and organization

**`users`** `id`, `public_id`, `staff_no`, `full_name`,
`email_normalized`, `job_title`, `is_active`,
`identity_provider_subject`, `created_at`, `updated_at`.

**`organization_nodes`** `id`, `code`, `name`, `node_type`, `parent_id`,
`head_user_id`, `sort_order`, `effective_from`, `effective_to`,
`is_active`, `custom_attributes`.

**`user_org_assignments`** `id`, `user_id`, `organization_node_id`,
`assignment_type`, `effective_from`, `effective_to`, `is_primary`.

**`roles`** `id`, `role_key`, `name`, `description`, `is_system_role`.

**`permissions`** `id`, `permission_key`, `module_key`, `action_key`,
`description`.

**`role_permissions`** `role_id`, `permission_id`, `scope_type`,
`constraints_json`.

**`role_assignments`** `id`, `user_id`, `role_id`, `scope_type`,
`scope_id`, `effective_from`, `effective_to`, `granted_by`.

#### Universe and risk

**`universe_items`** `id`, `code`, `name`, `description`, `entity_type`,
`organization_node_id`, `process_owner_id`, `strategic_objective`,
`audit_frequency_months`, `last_audit_date`, `next_review_date`,
`status`, `custom_attributes`.

**`risk_matrix_versions`** `id`, `name`, `version_no`,
`likelihood_scale_json`, `impact_scale_json`, `rating_rules_json`,
`effective_from`, `effective_to`, `approved_by`.

**`risks`** `id`, `risk_code`, `title`, `description`, `cause`, `event`,
`consequence`, `category`, `universe_item_id`, `organization_node_id`,
`owner_user_id`, `inherent_likelihood`, `inherent_impact`,
`inherent_score`, `control_effectiveness`, `residual_likelihood`,
`residual_impact`, `residual_score`, `risk_matrix_version_id`,
`response_strategy`, `review_date`, `status`.

#### Assurance planning

**`assurance_plans`** `id`, `plan_no`, `name`, `planning_year`,
`period_start`, `period_end`, `status`, `current_version_id`,
`created_by`.

**`assurance_plan_versions`** `id`, `plan_id`, `version_no`,
`description`, `total_available_hours`, `prepared_by`, `submitted_by`,
`submitted_at`, `decision`, `decided_by`, `decided_at`,
`decision_comments`, `published_at`, `snapshot_hash`,
`supersedes_version_id`.

**`plan_items`** `id`, `plan_version_id`, `item_no`, `title`,
`universe_item_id`, `organization_node_id`, `risk_rating_snapshot`,
`objective`, `scope_summary`, `audit_type`, `priority`, `planned_start`,
`planned_end`, `estimated_hours`, `lead_user_id`, `coverage_reason`,
`status`.

**`plan_item_team_members`** `plan_item_id`, `user_id`,
`assignment_role`, `estimated_hours`.

#### Engagement, testing and workpapers

**`engagements`** `id`, `engagement_no`, `title`, `plan_item_id`,
`organization_node_id`, `project_type_id`, `background`, `purpose`,
`scope`, `out_of_scope`, `criteria`, `methodology`, `planned_start`,
`planned_end`, `actual_start`, `actual_end`, `budget_hours`,
`lead_user_id`, `manager_user_id`, `status`, `version_no`.

**`engagement_members`** `engagement_id`, `user_id`, `member_role`,
`start_at`, `end_at`.

**`objectives`** `id`, `engagement_id`, `reference`, `title`,
`description`, `assigned_user_id`, `planned_start`, `planned_end`,
`conclusion`, `conclusion_status`, `position`.

**`procedures`** `id`, `objective_id`, `procedure_no`, `title`, `steps`,
`population_definition`, `sampling_method`, `planned_sample_size`,
`assigned_user_id`, `due_date`, `status`.

**`controls`** `id`, `objective_id`, `control_code`, `title`,
`description`, `owner_user_id`, `control_type`, `frequency`, `method`,
`status`.

**`risk_control_links`** `risk_id`, `control_id`, `relationship_type`,
`rationale`.

**`control_tests`** `id`, `control_id`, `procedure_id`,
`testing_round_no`, `sample_size`, `result_summary`, `exceptions_found`,
`conclusion_status`, `prepared_by`, `reviewed_by`, `review_status`,
`planned_date`, `actual_date`.

**`test_samples`** `id`, `control_test_id`, `sample_reference`,
`population_item_ref`, `selection_basis`, `result`, `exception_flag`,
`notes`.

**`workpapers`** `id`, `workpaper_ref`, `engagement_id`, `objective_id`,
`title`, `current_version_id`, `review_status`, `owner_user_id`.

**`workpaper_versions`** `id`, `workpaper_id`, `version_no`, `purpose`,
`procedure_performed`, `work_performed`, `results`, `conclusion`,
`prepared_by`, `prepared_at`, `submitted_at`, `reviewer_id`,
`reviewed_at`, `review_notes`, `content_hash`.

#### Evidence and documents

**`evidence_records`** `id`, `record_no`, `title`, `description`,
`scope_start`, `scope_end`, `engagement_id`, `requester_id`,
`respondent_id`, `alternate_respondent_id`, `reviewer_id`, `due_date`,
`response_text`, `status`, `decision`, `decision_comment`,
`submitted_at`, `reviewed_at`.

**`evidence_participants`** `evidence_record_id`, `user_id`,
`external_email`, `participant_role`, `assigned_at`, `revoked_at`.

**`files`** `id`, `storage_key`, `original_filename`, `safe_filename`,
`mime_type`, `size_bytes`, `sha256_checksum`, `uploaded_by`,
`uploaded_at`, `scan_status`, `classification`, `retention_class`,
`deleted_at`.

**`evidence_file_links`** `evidence_record_id`, `file_id`, `version_no`,
`supersedes_file_id`, `caption`.

**`record_file_links`** `file_id`, `record_type`, `record_id`,
`relationship_type`, `linked_by`, `linked_at`.

**`evidence_citations`** `id`, `evidence_record_id`, `record_type`,
`record_id`, `citation_text`, `page_or_section`, `created_by`.

#### Findings and remediation

**`findings`** `id`, `finding_no`, `engagement_id`, `objective_id`,
`control_id`, `title`, `criteria`, `condition`, `cause`,
`effect_or_risk`, `severity`, `risk_rating`, `recommendation`,
`owner_user_id`, `management_response`, `management_agreement_status`,
`identified_at`, `target_remediation_date`, `status`,
`publication_status`, `closed_at`.

**`finding_evidence_links`** `finding_id`, `evidence_record_id`,
`relationship_type`.

**`remediation_actions`** `id`, `action_no`, `finding_id`, `title`,
`description`, `owner_user_id`, `due_date`, `status`,
`completion_claim`, `submitted_for_validation_at`, `validated_by`,
`validation_result`, `validation_notes`, `retest_required`,
`retest_due_date`, `closed_at`.

**`remediation_action_evidence`** `action_id`, `file_id`,
`evidence_record_id`, `added_by`, `added_at`.

**`retests`** `id`, `action_id`, `retest_no`, `tested_by`, `tested_at`,
`procedure`, `result`, `conclusion`, `reviewed_by`, `reviewed_at`.

#### Reports, workflow and audit trail

**`report_runs`** `id`, `report_no`, `report_type`, `scope_type`,
`scope_id`, `period_start`, `period_end`, `source_cutoff_at`,
`template_version`, `filter_snapshot_json`, `data_snapshot_json`,
`snapshot_hash`, `generated_by`, `generated_at`, `status`.

**`report_approvals`** `id`, `report_run_id`, `stage_key`,
`approver_id`, `decision`, `comments`, `decided_at`.

**`workflow_definitions`**, **`workflow_states`**,
**`workflow_transitions`**, **`workflow_instances`**,
**`workflow_tasks`**, **`workflow_decisions`**, **`workflow_history`**:
as defined in Section 8.

**`audit_events`** `id`, `event_uuid`, `occurred_at`, `actor_user_id`,
`actor_type`, `action_key`, `record_type`, `record_id`,
`organization_node_id`, `request_id`, `ip_address` (subject to policy),
`before_hash`, `after_hash`, `reason`, `metadata_json`,
`previous_event_hash`, `event_hash`.

**`notification_outbox`** `id`, `event_key`, `recipient_id`, `channel`,
`payload_json`, `idempotency_key`, `status`, `attempt_count`,
`next_attempt_at`, `sent_at`, `last_error`.

**`comments`** `id`, `record_type`, `record_id`, `author_id`, `body`,
`visibility_scope`, `created_at`, `edited_at`, `deleted_at`.

**`review_notes`** `id`, `record_type`, `record_id`, `version_id`,
`raised_by`, `assigned_to`, `note_text`, `status`, `due_date`,
`resolved_by`, `resolved_at`.

**`time_entries`** `id`, `user_id`, `engagement_id`, `work_date`,
`activity_code`, `hours`, `description`, `submitted_at`, `approved_by`,
`approved_at`, `status`.

**`system_settings`** `id`, `setting_key`, `setting_value_json`,
`scope_type`, `scope_id`, `updated_by`, `updated_at`.

This core model can be expanded through migrations and module-specific
tables. Do not try to design 500 arbitrary fields in advance; define
stable domain entities first, then add documented, justified attributes
and validated custom-field definitions.

------------------------------------------------------------------------

## 10. Document and evidence management

### 10.1 File lifecycle

`selected → upload_pending → validated → malware_scanning → available → linked_to_record → superseded_or_archived → retained_or_disposed`

Files that fail validation or scanning must remain inaccessible to
ordinary users. Do not mark a file available until scanning and metadata
checks pass.

### 10.2 Required controls

-   Private object storage; no public bucket or predictable permanent
    URL.
-   Short-lived signed download links or an authenticated streaming
    endpoint.
-   Server-side authorization on every preview and download.
-   Allowlist file extensions and verify actual MIME/content signatures.
-   Enforce configurable file-size and total-upload limits.
-   Malware scanning and quarantine.
-   Calculate SHA-256 checksum and record uploader/time.
-   Store original name as metadata but generate safe storage keys.
-   Version files; do not overwrite approved evidence in place.
-   Track superseded files and preserve references used in signed-off
    workpapers.
-   Log upload, download, preview, sharing, deletion, classification
    changes and permission changes where required.
-   Apply retention, legal hold and disposal rules approved by GPHA.
-   Prevent external evidence respondents from browsing unrelated
    records.
-   Treat OCR/extracted text as potentially sensitive and apply the same
    access rules as the source file.

### 10.3 Document metadata

Minimum attributes: `file_id`, `original_filename`, `safe_filename`,
`mime_type`, `extension`, `size_bytes`, `checksum_sha256`,
`storage_key`, `uploaded_by`, `uploaded_at`, `classification`,
`scan_status`, `retention_class`, `version_no`, `supersedes_file_id`,
`linked_record_type`, `linked_record_id`, `access_policy_id`.

### 10.4 Document editor strategy

Use rich-text editing for narrative fields, audit observations, scope,
work performed, conclusions and responses. Store normalized content in a
controlled format and sanitize HTML on the server. For attachments such
as DOCX/XLSX/PDF, retain the original binary and provide preview/export
where technically supported. Avoid pretending a binary document is
natively editable unless an actual editor integration exists.

### 10.5 Versioning and sign-off

A sign-off must reference the exact content version/hash reviewed. If
content changes after sign-off, either: - automatically return it to a
draft/re-review state, or - create a new version while preserving the
previously approved version.

Which approach applies should be configurable by record type and policy,
but never silently keep a sign-off attached to changed content.

------------------------------------------------------------------------

## 11. API architecture informed by HighBond API conventions

### 11.1 Design principles

The HighBond public API is REST-based and uses JSON:API conventions.
GIAW can adopt familiar principles while using a GPHA-owned namespace
and schema.

Suggested base URL: `/api/v1`

Examples: - `GET /api/v1/organization-nodes` -
`GET /api/v1/audit-universe` - `GET /api/v1/risks` -
`GET /api/v1/assurance-plans` - `POST /api/v1/assurance-plans` -
`POST /api/v1/assurance-plans/{id}/submit` -
`POST /api/v1/assurance-plans/{id}/decisions` -
`GET /api/v1/engagements` - `GET /api/v1/engagements/{id}/workpapers` -
`POST /api/v1/evidence-records` -
`POST /api/v1/evidence-records/{id}/submit` - `POST /api/v1/findings` -
`POST /api/v1/remediation-actions/{id}/submit-for-validation` -
`POST /api/v1/reports/{id}/generate` - `GET /api/v1/audit-events`

### 11.2 HTTP methods

-   `GET`: retrieve; must not mutate business state.
-   `POST`: create or invoke a domain command.
-   `PUT`: replace a resource only where full replacement is intended.
-   `PATCH`: update selected attributes.
-   `DELETE`: use sparingly; prefer archival/controlled deactivation for
    audit records.

Workflow commands should be explicit (`submit`, `approve`, `return`,
`publish`, `close`) rather than allowing arbitrary status patches.

### 11.3 Headers and payload conventions

Recommended headers: - `Authorization: Bearer <access-token>` or secure
session authentication as approved - `Content-Type: application/json` -
`Accept: application/json` - `Idempotency-Key: <unique-value>` for
retryable writes - `If-Match` / version token for optimistic concurrency
where supported - `X-Request-ID` for support and audit correlation

Never embed a production API secret in frontend JavaScript, source
control, prompts or client-side environment variables.

### 11.4 JSON:API-inspired response shape

A compatible style can use `data`, `attributes`, `relationships`,
`meta`, `links` and structured `errors`. Example:

``` json
{
  "data": {
    "type": "assurance-plans",
    "id": "plan_01J...",
    "attributes": {
      "plan_no": "GIAW-AP-2027-001",
      "name": "Annual Assurance Plan 2027",
      "status": "draft",
      "version_no": 1
    },
    "relationships": {
      "items": {
        "links": {
          "related": "/api/v1/assurance-plans/plan_01J.../items"
        }
      }
    }
  },
  "meta": {
    "request_id": "req_...",
    "schema_version": "1"
  }
}
```

This is an illustrative GIAW contract, not a vendor response sample.

### 11.5 Filtering, sorting and pagination

Support allowlisted filters, e.g.:

`GET /api/v1/engagements?status=fieldwork&organization_node_id=tema-unit-01&sort=-updated_at&page[size]=25&page[cursor]=...`

For small and medium datasets, page-number pagination can be acceptable;
cursor pagination is often safer for changing large datasets. Document
the selected convention and apply it consistently. Never accept
arbitrary column names or raw SQL from query parameters.

### 11.6 API error model

Use standard HTTP semantics:

-   `400` invalid request syntax or missing required parameter
-   `401` unauthenticated
-   `403` authenticated but not authorized
-   `404` not found or intentionally concealed due to access policy
-   `409` state conflict or duplicate operation
-   `412` stale version / failed precondition
-   `413` upload too large
-   `415` unsupported media type
-   `422` field validation or business-rule failure
-   `429` rate limit
-   `500` unexpected internal failure
-   `503` temporary service unavailability

Return stable machine-readable error codes, a safe user message,
field-level validation details where appropriate, and a request ID. Do
not expose stack traces, SQL, secrets or private record content.

### 11.7 API security and throttling

-   Use short-lived access tokens where possible; rotate/revoke
    credentials.
-   If service accounts are needed, give each one a distinct identity
    and least-privilege scope.
-   Apply endpoint-specific rate limits.
-   Enforce authorization at object level to prevent insecure direct
    object reference (IDOR).
-   Validate all request fields and file metadata.
-   Log sensitive actions without logging tokens or full confidential
    evidence.
-   Use CSRF protection if cookie-based sessions are used.
-   Restrict CORS to approved origins.
-   Maintain API versioning and contract tests.
-   Use an outbox/retry pattern for integration events.
-   Add import preview, validation report and explicit commit for bulk
    data imports.

### 11.8 Integrations

Potential integrations should be evaluated with GPHA IT/security: -
Corporate identity provider / directory - Approved email service -
Document storage - Finance/procurement or HR reference data where
authorized - Reporting tools - Existing GPHA document-management systems

Do not assume that Diligent's API or product subscription is required to
run GIAW. Integrate with Diligent only if GPHA has a lawful, approved
use case and valid credentials.

------------------------------------------------------------------------

## 12. Dataflows and events

### 12.1 Assurance Plan dataflow

1.  Universe and risk data provide prioritization context.
2.  Managers propose plan items and estimates.
3.  Unit and port consolidation preserves the original proposals and
    records changes.
4.  GM Audit creates the organization-wide plan version.
5.  Approval decision freezes the approved version.
6.  Published plan items are linked to engagements.
7.  Engagement status, hours, findings and remediation metrics feed
    delivery dashboards.
8.  The next report run stores its data cutoff and plan version.

### 12.2 Evidence dataflow

1.  Request created → task assigned → notification outbox.
2.  Respondent uploads file → validation → quarantine/scanning.
3.  Scan passes → file metadata saved → evidence record submitted.
4.  Reviewer decision → workflow event and audit event.
5.  Accepted evidence is linked to workpapers/tests/findings.
6.  Downloads recheck permissions and emit an audit event.
7.  Retention process flags records for review; disposal requires policy
    authorization and logged outcome.

### 12.3 Reporting dataflow

1.  Operational tables remain authoritative.
2.  Reporting query layer calculates aggregates using scoped access.
3.  Data-quality rules detect missing/duplicate/out-of-scope items.
4.  Authorized user generates report snapshot.
5.  Reviewer/approver approves that snapshot.
6.  Export worker creates PDF/XLSX/DOCX from the approved snapshot and
    template version.
7.  Generated file, hash, source cutoff and approval history are stored.
8.  Subsequent changes create a new run/version, not a silent change to
    the prior report.

### 12.4 Suggested domain events

-   `assurance_plan.created`
-   `assurance_plan.submitted`
-   `assurance_plan.returned`
-   `assurance_plan.approved`
-   `assurance_plan.published`
-   `engagement.created`
-   `workpaper.submitted_for_review`
-   `workpaper.review_returned`
-   `workpaper.approved`
-   `evidence.requested`
-   `evidence.submitted`
-   `evidence.accepted`
-   `finding.created`
-   `finding.reported`
-   `remediation.overdue`
-   `remediation.submitted_for_validation`
-   `remediation.retest_failed`
-   `report.submitted`
-   `report.approved`
-   `report.published`
-   `permission.changed`
-   `file.downloaded`

Events should contain IDs and minimal metadata, not confidential file
contents.

------------------------------------------------------------------------

## 13. Notifications and collaboration

### 13.1 Notification channels

-   In-app notification center
-   Email notification
-   Daily/weekly digest (optional)
-   Dashboard task queue

Use SMS/WhatsApp only if formally approved for confidentiality, consent,
cost and operational reasons. Do not send sensitive audit details in
notification subjects or unsecured channels.

### 13.2 Notification triggers

-   Assignment or reassignment
-   Upcoming due date
-   Overdue task
-   Submission for review
-   Review returned with notes
-   Approval/rejection
-   Evidence request / response
-   Finding owner assigned
-   Management action approaching deadline
-   Remediation submitted for validation
-   Port report awaiting consolidation
-   HQ report awaiting decision
-   Access or delegation changes

### 13.3 Collaboration features

-   Record-level comments with visibility scope
-   Review notes linked to exact record version
-   Assignment and due date
-   @mentions only for authorized users
-   Activity timeline
-   Version comparison
-   Reviewer/preparer sign-off
-   Delegation with start/end dates and scope
-   Clear separation between internal audit notes and management-visible
    responses

Do not present a comment thread as a formal approval record. Formal
decisions must use the workflow engine.

------------------------------------------------------------------------

## 14. Reporting and analytics specification

### 14.1 Core metrics

**Plan** - Planned audit count - Completed/in-progress/not-started
count - Plan completion by count and weighted hours - Risk coverage by
entity/unit - Planned vs actual resource hours - Approved plan
amendments

**Engagement** - Engagements by stage - Schedule variance - Workpaper
review backlog - Testing completion and exceptions - Evidence requests
outstanding - Report issuance timeliness

**Findings/remediation** - Findings by severity/risk rating - Findings
by port/unit/category - Actions overdue - Median remediation age -
Retesting pass/fail - Repeat findings

**Governance** - Pending approvals by role and age - Rejected/returned
submissions - Changes to approved plans - Access review exceptions -
Audit trail events requiring investigation

### 14.2 Report templates

-   Annual Assurance Plan
-   Unit monthly/quarterly report
-   Port consolidated report
-   GM Audit / HQ consolidated report
-   Individual engagement report
-   Findings register
-   Remediation status report
-   Audit universe risk coverage
-   Resource utilization / timesheet report
-   Workpaper review status
-   Evidence request tracker

### 14.3 Report integrity

-   Each export has a report ID, version, generated timestamp and source
    cutoff.
-   Include a clear "draft" watermark until formally approved.
-   Approved report files are immutable; corrections produce a new
    version.
-   Record recipients/distribution if reports are confidential.
-   Use permission-filtered data queries and validate export scope
    server-side.
-   Prevent spreadsheet formula injection in exported text values.
-   Keep a copy of the exact template and data snapshot used for
    approval.

------------------------------------------------------------------------

## 15. Security, privacy and governance

### 15.1 Minimum security baseline

-   MFA or GPHA-approved enterprise authentication
-   Least-privilege RBAC and scope enforcement
-   Secure session/token management
-   TLS in transit and encryption at rest
-   Secret management outside source code
-   Strong password policy if local passwords are used
-   Session timeout and account disablement
-   Protection against CSRF, XSS, SQL injection, SSRF, IDOR and unsafe
    uploads
-   Rate limiting and brute-force controls
-   Audit trail for approvals, exports, access changes and sensitive
    file access
-   Encrypted backups and tested restoration
-   Dependency scanning and patch management
-   Separate production/test environments
-   Security review before production
-   Incident response and breach escalation process
-   Retention and disposal policy
-   Access reviews for privileged roles

### 15.2 Audit log integrity

Audit events should be append-only at the application level and
protected from ordinary administrators' editing. For stronger tamper
evidence, chain events using hashes or export to a separately controlled
log destination. Hash chaining alone does not prove integrity if an
attacker can rewrite the entire chain and its anchor; protect anchors
and backups separately.

### 15.3 Separation of duties

-   A preparer should not approve their own work where policy requires
    independent review.
-   An action owner should not be the sole auditor validating the action
    if independence rules prohibit it.
-   Administrators should not gain automatic business approval
    privileges.
-   Emergency access must be time-limited, justified and logged.
-   Delegation must not bypass approval authority or scope restrictions.

### 15.4 AI controls

AI may assist with drafting audit objectives, summarizing permitted
evidence, suggesting risk categories, identifying duplicate evidence or
drafting report language. It must: - respect the user's existing record
permissions; - disclose when content is AI-generated; - cite source
record/file references where possible; - allow human verification and
editing; - avoid inventing evidence or conclusions; - never approve
plans, workpapers, findings or reports autonomously; - avoid training
external models on GPHA confidential data unless expressly approved; -
log relevant AI actions without unnecessarily retaining sensitive
prompts.

------------------------------------------------------------------------

## 16. Non-functional requirements

  -----------------------------------------------------------------------
  Area                                Initial requirement
  ----------------------------------- -----------------------------------
  Availability                        Set a GPHA-approved target after
                                      operational needs analysis

  Performance                         Common list/detail screens should
                                      feel responsive under expected
                                      load; measure with realistic data

  Accessibility                       Keyboard navigation, labels,
                                      contrast, focus visibility and
                                      accessible validation

  Responsive UI                       Desktop-first for audit-heavy
                                      tables; usable tablet layout;
                                      essential mobile tasks supported

  Data integrity                      Transactions and constraints for
                                      critical state transitions

  Recoverability                      Documented RPO/RTO, encrypted
                                      backups and tested restore
                                      procedure

  Scalability                         Indexed queries, pagination,
                                      asynchronous exports and file
                                      streaming

  Maintainability                     Modular boundaries, code review,
                                      typed contracts and migrations

  Observability                       Structured logs, metrics,
                                      correlation IDs and actionable
                                      alerts

  Localization                        Configurable date, time, number and
                                      language formatting

  Auditability                        Traceable approvals, versions,
                                      evidence links and data exports
  -----------------------------------------------------------------------

Avoid promising numerical service-level targets until the number of
users, file volume, concurrency, infrastructure and budget are known.

------------------------------------------------------------------------

## 17. Testing strategy

### 17.1 Test layers

1.  Unit tests for scoring, calculations and workflow transitions.
2.  Integration tests for database transactions, permissions, file
    storage and notification outbox.
3.  API contract tests for payloads, validation, pagination and errors.
4.  Authorization tests across every role/scope combination.
5.  Workflow tests for valid and invalid transitions.
6.  File-upload security tests (wrong extension, spoofed MIME, oversize,
    malware fixture, unauthorized download).
7.  Concurrency tests for simultaneous edits and approval conflicts.
8.  Report reconciliation tests for unit → port → HQ totals.
9.  Browser end-to-end tests for high-priority journeys.
10. Backup restore, migration and recovery tests.
11. Accessibility and responsive layout tests.
12. User acceptance testing with auditors from HQ, Tema and Takoradi.

### 17.2 Critical acceptance tests

-   A Tema auditor cannot view a restricted Takoradi engagement unless
    explicitly authorized.
-   An unapproved plan cannot be marked published by direct API request.
-   An approver cannot approve a stale version after the plan has
    changed.
-   A rejected plan preserves its prior submitted snapshot and decision
    comments.
-   A workpaper edit after sign-off triggers the configured re-review
    behavior.
-   A user cannot download an evidence file by guessing its ID.
-   An evidence respondent cannot view another respondent's record.
-   A management completion claim does not automatically close a
    finding.
-   Unit, port and HQ reports reconcile to the same source cutoff and
    scope.
-   Exporting filtered results does not bypass the user's access
    permissions.
-   A deactivated staff account cannot sign in or approve new work.
-   An admin role does not automatically become an audit approval role.
-   Duplicate requests caused by a network retry do not create duplicate
    plan submissions.
-   An organization reorganization does not rewrite historical report
    scope without versioned rules.

------------------------------------------------------------------------

## 18. Implementation roadmap

### Phase 0 --- Confirm policy and data

-   Validate the GPHA reporting hierarchy and formal approval authority.
-   Inventory existing Word/Excel forms and report templates.
-   Agree status definitions, risk matrix, report periods and retention
    rules.
-   Decide stack, hosting, identity and backup approach.
-   Establish data classification and role-scope matrix.

### Phase 1 --- Platform foundation

-   Organization tree
-   Users and roles
-   Navigation, shell and task center
-   Audit trail
-   Configuration dictionaries
-   API conventions and migrations

### Phase 2 --- Universe, risk and annual plan

-   Audit Universe
-   Risk register and scoring matrix
-   Plan items and resource estimates
-   Unit/port/HQ consolidation
-   Approval/versioning/publishing
-   Plan reports and dashboard

### Phase 3 --- Engagements and fieldwork

-   Engagement register and templates
-   Planning pages
-   Objectives and procedures
-   Risk-control matrix
-   Tests, samples and workpapers
-   Review notes and sign-off

### Phase 4 --- Evidence, findings and remediation

-   Evidence requests and file management
-   Evidence review and reuse
-   Findings register
-   Management responses
-   Actions, validation and retesting

### Phase 5 --- Reporting and operational management

-   Unit/port/HQ consolidated reports
-   Report snapshots and exports
-   Scheduler and timesheets
-   Notification digests
-   Portfolio analytics

### Phase 6 --- Hardening and rollout

-   Security testing
-   Data migration and reconciliation
-   UAT at HQ, Tema and Takoradi
-   Training and operating procedures
-   Production monitoring and recovery rehearsal

Do not start by generating hundreds of disconnected pages. Build the
shared record model, permissions, workflow transitions and audit trail
first; then implement each end-to-end workflow.

------------------------------------------------------------------------

## 19. Vibe-coding prompts for implementation

Use these prompts one phase at a time. Keep the blueprint and acceptance
tests in the repository. Ask the coding agent to inspect the existing
codebase before making changes.

### Prompt A --- Architecture and repository inspection

> You are the lead software architect for GPHA Internal Audit Workspace
> (GIAW). Read `giaw.md` fully before coding. Inspect the existing
> repository, identify the actual stack, routes, modules, database
> schema, authentication and tests. Do not assume files or dependencies
> exist. Produce an architecture map and a gap analysis against the
> blueprint. Recommend a modular-monolith structure with clear domain
> boundaries. Do not rewrite the whole project or introduce a second
> backend framework without approval. List risks, migrations and the
> smallest safe implementation plan first.

### Prompt B --- Shared platform foundation

> Implement the GIAW application shell, configurable organization
> hierarchy, users, roles, permission scopes, audit events and workflow
> foundation described in `giaw.md`. Enforce authorization server-side
> for every endpoint and record. Add database constraints and
> migrations, seed only synthetic demo data, and write tests for
> positive and negative permission cases. Keep domain modules separated.
> Do not add fake controls that merely hide buttons; the backend must
> enforce them. Report files changed, migrations, tests and unresolved
> assumptions.

### Prompt C --- Annual Assurance Plan

> Implement the full GPHA Annual Assurance Plan workflow in `giaw.md`:
> manager proposals → unit consolidation → PIA Tema/PIA Takoradi
> consolidation → GM Audit organization-wide consolidation → Audit
> Committee decision according to configured policy → immutable approved
> version → publication and distribution. Build list, detail, item
> editor, review, version history and dashboard interfaces. Validate
> hours, dates, duplicate items and required approvals. Preserve every
> submitted version and return comments. Implement server-side state
> transitions, audit events, notifications and tests for
> unauthorized/stale approvals. Do not invent formal authority where
> GPHA policy is not confirmed; make approval routing configurable.

### Prompt D --- Engagement, workpapers and fieldwork

> Implement engagements, planning, objectives, procedures, risk-control
> matrix, control tests, samples, workpapers and review notes using the
> schemas in `giaw.md`. Support draft → submit → return with review
> notes → resubmit → approve. Link evidence by reference, not by copying
> file binaries. Use optimistic locking and version-specific sign-off.
> Add filterable tables, accessible forms, loading/empty/error states
> and responsive behavior. Write integration and browser tests.

### Prompt E --- Evidence and document controls

> Implement evidence requests, respondent/reviewer roles, secure file
> upload, quarantine/scanning integration points, file metadata,
> checksum, versioning, private storage, short-lived authorized
> downloads and a full activity history. Enforce record-level
> permissions on every preview/download. Do not expose storage keys or
> public permanent URLs. Preserve evidence linked to signed-off
> workpapers. Add tests for unauthorized access, invalid files, stale
> links and respondent isolation.

### Prompt F --- Findings and remediation

> Implement findings with criteria, condition, cause, effect/risk,
> recommendation, evidence links and management response. Add
> remediation actions, due dates, owner updates, evidence submission,
> auditor validation and retesting. Keep management completion separate
> from auditor closure. Add overdue calculations, notification events,
> change history and tests for rejected validation and failed retesting.

### Prompt G --- Consolidated reporting

> Implement the three GPHA reporting tiers: Unit Heads consolidated
> reports, PIA Tema/PIA Takoradi consolidated reports, and GM Audit/HQ
> final consolidated report. Calculate totals from scoped source records
> and preserve a common data cutoff. Detect missing unit reports,
> inconsistent counts, duplicate records and resource variances. Support
> review/return/approval, immutable report snapshots and PDF/XLSX
> export. Test aggregate reconciliation and confirm exports enforce the
> same permissions as the UI.

### Prompt H --- Cleanup and performance

> Review the repository against `giaw.md`. Identify unused files, dead
> code, duplicate components, inefficient queries, unbounded lists,
> repeated authorization logic, missing indexes, broken routes, unused
> dependencies and accessibility problems. First produce a list grouped
> by severity and risk. Remove only items proven unused; preserve
> migrations, history, configuration and deployment files. Add
> regression tests before risky refactors. Optimize using profiling and
> query plans rather than guesswork. Run all tests/build checks and
> report exactly what changed.

### Prompt I --- Security review

> Perform a threat-oriented review of GIAW. Check IDOR, broken
> object-level authorization, privilege escalation, CSRF/XSS/SQL
> injection, unsafe uploads, token leakage, overbroad exports, workflow
> bypass, insecure direct status updates, stale approval, concurrency,
> audit-log tampering, sensitive logging, backup exposure and dependency
> vulnerabilities. For each issue, provide reproduction steps, severity
> and a minimal fix. Add regression tests and never weaken permissions
> to make a test pass.

### Prompt J --- Code quality gate

> Before declaring this feature complete, run the project's actual
> formatter, linter, type checker, unit tests, integration tests and
> production build. Do not claim a check passed unless it ran
> successfully. Fix errors introduced by this change. Summarize changed
> files, database migrations, API routes, permission rules, test results
> and remaining risks. Do not remove or replace working features outside
> the requested scope.

------------------------------------------------------------------------

## 20. Definition of done

A module is not complete merely because its page renders. It is done
only when:

-   UI, API and data model agree.
-   Permission checks are enforced on the server.
-   Required fields and business rules are validated.
-   Workflow transitions and audit events are implemented.
-   Loading, empty, error and unauthorized states exist.
-   Tables support appropriate search/filter/sort/pagination.
-   Attachments and exports enforce access rules.
-   Tests cover valid, invalid and unauthorized cases.
-   Relevant dashboard/report calculations reconcile.
-   Documentation describes routes, schema, permissions and decisions.
-   UAT users can complete the intended workflow end-to-end.

------------------------------------------------------------------------

## 21. Key open decisions for GPHA

These require a decision from GPHA management, Internal Audit leadership
or IT/security before production:

1.  Final authority and routing for annual plan approval, report
    approval and amendments.
2.  Whether Audit Committee members require accounts or receive
    controlled report distributions.
3.  Identity provider, MFA and account provisioning method.
4.  Hosting location, data residency and approved cloud/on-premises
    arrangements.
5.  Record classification, retention periods, legal hold and disposal
    rules.
6.  Formal risk scoring matrix and severity thresholds.
7.  Required audit report templates and signatures.
8.  Whether management users will log in to respond to findings or use
    controlled external response links.
9.  Approved integrations with HR, finance, document management and
    email.
10. Expected user count, evidence volume, availability and recovery
    objectives.
11. Whether custom fields/statuses are configurable by System Admin or
    only by controlled change request.
12. Which reports may be exported, shared externally or distributed by
    email.

------------------------------------------------------------------------

## 22. References

### Diligent One Platform Help Center

-   Main help index:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/global_topics/index.htm
-   Projects overview and lifecycle:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/getting_started/projects_in_a_nutshell.htm
-   Planning projects:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/planning_projects.html
-   Creating projects:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/creating_projects/creating_projects.html
-   Projects navigation:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/getting_started/getting_started.html
-   Gathering/evaluating/documenting evidence:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/fieldwork/gathering_evaluating_evidence.htm
-   Issue management/remediation:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/fieldwork/managing_issues/managing_issues_and_remediation.html
-   Assurance Plans overview:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/defining_assurance_plans.htm
-   Assurance Plans getting started:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/projects/planning_projects/assurance-plans-get-started.htm
-   Evidence Hub overview:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/evidence_hub/concepts/what-is-evidence-hub.htm
-   Evidence request creation:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/evidence_hub/tasks/create-and-send-an-evidence-request.htm
-   Evidence response and submission:
    https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/evidence_hub/tasks/respond-to-and-submit-evidence.htm

### Diligent One Platform API

-   API reference / Making requests:
    https://docs-apis.highbond.com/#section/Making-requests
-   API reference public page:
    https://docs-apis.highbond.com/public.html
-   Customer-facing API documentation (recommended by vendor docs for
    production API usage): https://docs-apis.diligentoneplatform.com

------------------------------------------------------------------------

## 23. Final implementation recommendation

Build GIAW as a **configurable modular platform**, not a collection of
disconnected CRUD pages and not a premature microservices system. The
first end-to-end vertical slice should be the **Annual Assurance Plan**,
because it exercises organization scope, risk/universe links, roles,
consolidation, approvals, versioning, notifications, audit trail and
reporting. Once that is reliable, connect approved plan items to
engagements, workpapers, evidence, findings and remediation.

Use this document as the living baseline. Update it whenever GPHA
approves a policy decision, a schema changes, or an implemented workflow
differs from the intended behavior. The result should be a maintainable
GPHA-owned system inspired by documented product capabilities, not an
unverified claim of exact replication of proprietary internals.
