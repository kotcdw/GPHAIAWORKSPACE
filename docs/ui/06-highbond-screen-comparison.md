# GIAW against Diligent One (HighBond): screen-by-screen check

**Date:** 15 October 2026 · **Method:** every sidebar page and every record tab was opened in a browser and its page title,
tabs, buttons, filters and column headers were read off the screen (66 screens). The result was compared with the
public Diligent One help pages (help.diligentoneplatform.com) and the Diligent Terraform resource docs. Those pages
describe fields and buttons; they rarely list table columns. Where Diligent does not document something, the table
says so. Pixel styling, logos and brand are not copied.

**Key:** Same = names and order match the documentation · Changed = aligned in this release · Different = kept on
purpose (reason given) · Missing = not built yet.

## 1. App groups (sidebar and Launchpad)

Diligent organises its apps by solution. Its help pages name the solutions (Audit Management, Compliance Management,
Internal Controls, IT Risk, Enterprise Risk, Third-Party Risk) and put Org Structure under Platform settings; they do
not publish the exact sidebar category titles. GIAW now uses one set of groups, in the same order, in the sidebar, the
Launchpad and Apps & customization:

| Group | Apps |
|---|---|
| Home | Dashboard, Launchpad, Task Manager, Task Tracker, My Drafts |
| Audit management | Audit universe, Audit risk assessment, Assurance Plans, Audits, Status Tracker, Project Library, Requests, Issue Tracker, Remediation & Follow-up |
| Resource management | Scheduler, Timesheets & capacity, Professional practice |
| Risk management | Risk Manager, Process library, Asset Inventory |
| Compliance management | Frameworks, Compliance Maps, Policy Manager, Nonconformance |
| Analytics & reporting | Analytics, Results, Storyboards, Robots, Audit Committee, Governance portal, Port portfolio, Quality (QAIP), Service Feedback |
| Platform settings | Org Structure, Organizations, Stakeholders, Profile & Users, Roles & permissions, Configuration, Audit types, Apps & customization, Automations, Activity logs, Backups |

Renamed to the Diligent app names: GPHA Workspace → **Launchpad**, Task Center → **Task Tracker**, Assurance Plan →
**Assurance Plans**, Frameworks & controls → **Frameworks**, Audit Log → **Activity logs**, Capacity & time →
**Timesheets & capacity** (Diligent: Timesheets). Kept: Audit programmes (Diligent: Project Library), Evidence requests
(Diligent: Requests), GPHA-only apps (Port portfolio, Governance portal, Professional practice, Nonconformance,
Criteria library, QAIP, Service Feedback).

## 2. Screen comparison

| Screen | Diligent One (documented) | GIAW | Result |
|---|---|---|---|
| Audits list | "New" menu (New Blank Project / New Project from Template), search, filters, sort, favourites, progress bar per project; columns not documented | New audit, search, Status / Stream / Port / Scope filters, Columns, Excel, CSV, paging; Ref, Audit, Stream, Port, Lead, Planned, Status, Open findings, **Progress**, Report, Updated | Changed (Progress column added). Different: no favourites; templates are applied inside the audit (Apply audit programme) |
| Audit record tabs | Dashboard, Planning, Fieldwork, (Controls), Reviews, Results, Issues; Progress, To-dos, Requests, Timesheets, Settings | Dashboard, Planning, Fieldwork, Working papers, **Reviews**, **Results**, Issues, **Requests**, Survey | Changed (Quality review → Reviews, Report → Results, Evidence requests → Requests, order). Different: Working papers and Survey are GPHA additions; project Settings live in Configuration |
| Audit utility toolbar | Issues, Requests, To-dos, Time entries (Add / View all) | Review notes, **Time entries**, **To-dos**, History, Approvals | Changed (Time → Time entries, Tasks → To-dos) |
| Fieldwork, Workplan | Objectives, procedures, Execute Procedures; "Procedure Results"; "Issue(s) noted / No Issues" | Project plan, Execute procedures; results, conclusion, issues noted, sign-offs | Same |
| Fieldwork, Internal Control | Narratives, RCM, Walkthroughs, Test Plan, round tabs "Testing" / "Interim, Final" / "Q1–Q4" | Risk control matrix, Walkthroughs, Test plan, round tabs **Interim, Final** | Changed (round tabs no longer say "round"). Missing: narratives as separate records |
| Control test | In scope this round, User Assigned, sample size, Testing Results, "Did this control operate effectively?" | Tested this round?, Assigned, Sample, Exceptions, Status, Conclusion, Sign-offs, Evidence | Same (Exceptions is a GPHA addition) |
| Sign-offs | Preparer, Detail Reviewer, General Reviewer, Supplemental, Specialty (up to five) | Same five levels (configurable), Next Reviewer, override, remove | Changed in the second pass (section 3) |
| Issues (audit tab and Issue Tracker) | Title, Description, Owner, Issue Type, Date Identified, Severity, Published, Recommendation; Show More: Executive Owner, Risk/Impact, Scope, Escalation, Cause, Effect, Cost Impact; KPI charts by project and type; Sign-offs column | Issue, Status, Severity, Owner, Remediation deadline, Issue type, Published, Sign-offs, Project / Remediation, Responses; List and KPIs tabs; Add issue, Import from Excel, Publish | Same. Different: GIAW keeps Criteria (5C finding format) |
| Actions | Title, Owner, Due date, Priority, CC, reminders, status list Opened … Completed | Remediation & Follow-up register with owner, due, severity, implementation, validation | Same in content; Different layout (separate app) |
| Requests | Requester, Description, Owner, CC, Due Date, Status (Open, Received + custom), reminders | Ref, Audit, **Requester**, **Description**, Linked to, Owner, Due, Status, Files; Request evidence; CC and reminders in the form | Changed (Requester column; "Evidence requested" → Description) |
| Assurance Plans list | Name, Description, Start date, End date, Budgeted hours; columns not documented | Ref, Fiscal year, Title, Status, **Budgeted hours**, Approved; New plan | Changed (Budgeted hours) |
| Assurance Plan page | Table and Timeline views, Budgeted hours, Sum of audit hours, Remaining hours, Include audits, Add audit, Generate; Propose / Approve / Launch / Close | Overview with **Budgeted hours, Sum of audit hours, Remaining hours**, Entities, Risks, Versions & cycle, Change requests, Activities; Revise plan, Close year, Start | Changed (hours summary). Missing: Timeline (Gantt) view and an "Include audits" picker |
| Org Structure | Platform settings; fields not documented | Bulk add, Create organizational unit; Organizational unit, Reference, Type, Processes, Auditable entities | Same (now under Platform settings) |
| Process library | Reached from Audit universe; needs Risk Manager | Bulk add, Add process; Reference, Process, Parent process, Org units, Risks · Controls, Owner, Auditable entities, Status | Same (now under Risk management) |
| Audit universe | Let's start, Define, Redefine; Auditable entity, Status, Org unit, Process | Same buttons; adds Risk rating, Audit frequency, Last audited, Next due, Planned audits | Same |
| Auditable entity | Details, Audit risk assessments, Audits, Findings and actions | Same four tabs; Archive, Edit entity links | Same |
| Audit risk assessment | Add audit risk assessment wizard; Settings (factors, scale); Scoring; Configure; Conclude; Mark as completed; Revert; Export PDF; Start planning | Same buttons and tabs; columns Select, Auditable entity, Overall score, Risk rating, one per factor | Same |
| Timesheets | Project and non-project time; fields not documented | Log time, Team capacity, Skills matrix, Budget vs actual, My time sheet | Same in purpose; GIAW adds capacity |
| To-dos | Description, Assigned to, Due date; Open / Clear / Closed | Task Tracker: New task; Assigned to me, Assigned by me, Closed | Same in purpose |

## 3. Second pass (migration 0032_highbond_parity)

Built from the Diligent One help pages for each screen (Projects, Audit planning, Results, Storyboards, Robots,
project type settings, sign-offs):

| Item | What GIAW now has |
|---|---|
| Sign-offs | Configurable levels (default Preparer, Detail Reviewer, General Reviewer, Supplemental Reviewer, Specialty Reviewer; Configuration > Audit methodology). The preparer signs first; a reviewer signs when set as **Next Reviewer** ("Set and Notify Reviewer"); an Audit Manager can **Override Sign-off**; **Remove sign-off** removes later ones too; signed-off pages are read-only. Pages: procedures, narratives, walkthroughs and tests, test plans, the risk control matrix (per objective) and issues. Optional password on every sign-off. Existing prepared / reviewed records were carried over. Report approval keeps the GPHA review chain (Diligent has no report sign-off). |
| Narratives | Internal Control fieldwork > **Narratives**: Title (60), Description, controls described (up to 100), sign-offs, attributes; "Add new narrative", "Delete Narrative". |
| Progress | Audit tab **Progress**: Audit Procedures Completed (Not Started / In Process / Completed), Time to Deadline, budget and time spent; **Fieldwork status** (Sign-off #1 to #5 per page: Not started, In progress, Completed, Not applicable) and the **Progress board** (Not started, Prepared, In review, Signed off). |
| Status Tracker | Audit management > **Status Tracker**: Audit, Time Expired, Work Completed, Budget, Time Spent, Status; favourites first. |
| Favourites | Star on the Audits list and Status Tracker; "Show favorites first". |
| Audit types | Platform settings > **Audit types**: **Terms** (17 terms per type: Audit, Planning, Fieldwork, Objective, Narrative, Risk control matrix, Risk, Control, Walkthrough, Test plan, Testing, Procedure, Execute procedures, Issue, Request, Results, Reviews) and **Custom attributes** (Short answer, Dropdown, Date, Paragraph, Number, Yes/No; up to 10 per page per type) on objectives, narratives, risks, controls, procedures, walkthroughs and tests, and issues. Terms relabel the audit tabs and fieldwork views. |
| Plan Timeline / Include audits | Plan > All audits: **Table** / **Timeline** (bars from planned dates or quarter, colour-coded swimlanes by category, quarter, lead or status; milestones: Audit Committee meetings, plan approval; today line). **Include audits** (search, select, quarter; an approved plan records each inclusion as a plan change with a reason) and **Exclude from audit plan**. |
| Results | Analytics & reporting > **Results**: collections > tables; records with Record ID, the analytic's columns, Priority (Low, Medium, High, Critical), Status (New, Open, Under Review, Closed, False Positive), Assignee, Published; **Interpretations** (bar, donut, metric, summary table; group by and filter); **Triggers** (ALL / ANY conditions on priority and status; Assign, Notify, Status, Priority; Run). |
| Storyboards | **Add Storyboard**, Edit toggle, Add Text / Add Chart / Add Metric, move, half / full width; **Share Storyboard** read-only with chosen users or all staff. |
| Robots | **+ Create**, **Create task** (selected analytic, parameters, "Put your task on a schedule": daily / weekly / monthly, Starting at, Beginning on, "Send notifications on failure"), **Run now**, turn off; **Task runs** (Task, Started, Duration, Run method, User, Status, Records). Tasks run fixed, read-only analytics (open High issues, overdue actions, tests with exceptions, overdue requests, audits over budget, entities overdue for audit, unpublished issues); no scripts run on the server. |
| Renames | Audit programmes → **Project Library**; Evidence requests → **Requests**. |
| GPHA additions dropped from the screens | Issue form: Criteria and the criterion picker removed; fields now Title/Headline, Severity, Issue type, Status, Owner, Description, Recommendation, then Effect and Cause. Criteria library removed from the sidebar and Launchpad. Working papers tab removed: working papers appear under **Results > Supporting workpapers**. Survey tab removed (auditee surveys still feed Quality (QAIP)). The data is kept; nothing was deleted. |

## 4. Still different

- Robots run a fixed catalogue of analytics, not uploaded ACL / Python scripts (no server-side code execution).
- Results tables come from robots or are created empty; Diligent's file and API imports into tables are not built.
- Questionnaires on Results records, storyboard public links and the AI request generator are not built.
- Report approval stays on the GPHA review chain; the Results tab keeps the GPHA report.
