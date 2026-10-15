# GIAW UI redesign – Prompt 1: public reference matrix (Diligent One / HighBond)

**Date:** 15 October 2026 · **Code changed by this step:** none

`H/` = `https://help.diligentoneplatform.com/helpdocs/d1p/en-us/Content/`. Confidence: **D** documented in the source text · **S** seen in a public screenshot on the help site · **I** inferred · **P** proposed GPHA adaptation.

The help screenshots were opened and inspected directly. Most have empty alt text, so only what is visible is described. No vendor assets are copied: GIAW keeps GPHA branding and original styling.

## 1. Look and feel observed in public screenshots (S)

| Pattern | What the screenshots show | Source image | GIAW adaptation (P) |
|---|---|---|---|
| Shell | Thin dark top bar with app-switcher grid, organization name, help and profile icons; white content on a light grey canvas | `H/images/highbond/Screenshot/Project_Manager_Dashboard.png` | Same structure with the GPHA navy bar, GPHA logo and a scope chip (HQ/Tema/Takoradi) |
| Record header | Breadcrumb ("Org / Projects"), project title with a switcher caret, horizontal tabs directly under the title (Dashboard, Planning, Fieldwork, Controls, Reviews, Results, Issues); utility links on the right (Progress, To-dos, Requests, Timesheets, Settings) and "Search this project" | `Project_Manager_Tabs.png` | Audit page: tabs straight under the title. Overview, independence and closure readiness move into a right-hand panel / Dashboard tab |
| Dashboard tab | "My work status" table: Section · Prepared · Detail review · General review, with count chips (e.g. 3/37) and a ✓ when complete; "Show all fieldwork" toggle. Right column cards: My Tasks (Requests, To-dos, Reviews, Issues) and Project Overview (collaborators, name, description, status, deadline) | `Project_Manager_Dashboard.png` | Audit Dashboard tab: sign-off progress per RCM area / working paper by GPHA level (Prepared · Unit Head · Audit Manager · PIA) |
| Registers | Compact rows, grey header row, blue link titles, small type; filter dropdowns above the table (Status, Severity, Owner) plus "Search list…" and "Clear" | `Issues_Tab_Visualizations.png` | One shared table: search, filter dropdowns, Clear, result count, server paging |
| Sign-off cues | Sign-offs column with small numbered circles (filled = signed); sign-off line "Detail Reviewer · Simon M., 09/21/2017 · Remove sign-off" | `Issues_Tab_Visualizations.png`, `Detail_Reviewer_Sign_Off.png` | Same cue for the GPHA chain: one circle per level (Unit Head, Audit Manager, PIA, GM Audit) |
| Charts | Donuts "By Issue Type" / "By Severity" above the issues list; Issue Tracker KPI tab "Issue Count by Project / by Issue Type" | `Issues_Tab_Visualizations.png`, `Issue_Tracker_Visualizations.png` | Small donuts above the findings register only; no decorative KPI tiles |
| Plan coverage | Table: Project (with unlink ×) · Status · Hours · Progress (green bar with %) · one column per entity with ✓ where covered | `Assurance_Plan_Entities_Example.png` | Plan "Coverage" tab: engagements × entities/ports with ✓, hours and a progress bar |
| Progress | "Overall progress: 44%" thin green bar | `Overall_Progress_Chart.png` | Plan and audit progress bars |
| Actions | Action · Owner · Due Date · Status (coloured text, e.g. "Remediated - Awaiting Verification") · View/Discuss | `Action_Item_Example.PNG` | Remediation register uses the same column order |

## 2. Behaviour matrix (D unless marked)

| GIAW screen | Reference | Documented behaviour | GPHA adaptation (P) | Entities | Conf. | Open question |
|---|---|---|---|---|---|---|
| UI-002/003 Dashboard, My Work | `H/projects/getting_started/getting_started.html` | "Priorities" lists items assigned to/by you: Actions, Certifications, Issues, Requests, Reviews, Tests, To-dos; red dot = new, clock = overdue, count | Merge Task Manager and Task Center into one My Work with these item types | tasks, capa, findings, requests, review notes | D | – |
| UI-030 Plans list | `H/projects/planning_projects/assurance-plans-get-started.htm` | Sorted by planning period then name; "+ Create plan" side panel: name (255), description, total available hours, planning period | Same columns plus GPHA status and version | assurance_plans | D | – |
| UI-032–035 Plan tabs | same | Tabs Entities, Categories, Risks, Activities; "+ Add to plan" (new, link active, roll forward); coverage ✓ matrix; progress = sum of phase scores ÷ maximum; hours bar green to budget, red above; Word/PowerPoint export | Tabs: Overview, Engagements, Coverage, Risks, Resources, Approvals & distribution, History. Keep the GPHA approval chain (not in Diligent) | plans, plan engagements, universe | D | Progress formula for GPHA (phases vs status)? |
| UI-040 Engagement list | `getting_started.html` | New blank / from template; search by name; sort per column; filters persist in URL; favourites; progress bar; load more after 50 | Filters in URL, progress column, "New from programme" | audits | D (columns not documented) | Columns: we use the UI-040 list |
| Project types | `H/projects/creating_projects/workflows_and_project_types.html` | Two workflows: **Workplan** (objectives → risks → procedures → execute procedures) and **Internal Control** (narratives, RCM, walkthroughs, test plan, test rounds) | GPHA stream drives the workflow: Expenditure/Revenue/Operations use Workplan; IT Audit and ICFR use Internal Control | audits.audit_type, programmes | D | GPHA to confirm which streams use which workflow |
| UI-044/050 Planning | `H/projects/planning_projects/planning_projects.html` | Planning tab: Background, Purpose/Objective, Scope, Attributes, Entity coverage; Planning Files (title, ID ≤ 8, rich text, planned/actual dates, files) | Planning Memo tab keeps the GPHA fields; adds planned/actual milestone dates | planning memo | D | – |
| UI-045/052 RCM | `H/projects/planning_projects/defining_risks_controls.htm` | Risk: title, ID, impact, likelihood, custom factors. Control: ID, owner, frequency, type, prevent/detect, method, status, assertions, weight | Our RCM already has most; add prevent/detect and method if GPHA wants | rcm risks, controls | D | – |
| UI-053/054 Walkthrough & tests | `H/projects/fieldwork/procedures_walkthroughs_tests/testing_controls.htm` | Walkthrough answer "designed appropriately?"; test rounds (1 / Interim-Final / Q1–Q4); default sample sizes by frequency; conclusion "operating effectively?" | Add walkthrough record and default sample sizes (configurable) | control_tests | D | GPHA sample-size policy |
| UI-058 Sign-off | `H/projects/fieldwork/reviews/reviewing_work_and_signing-off.html` | Up to 5 levels (Preparer, Detail, General, Supplemental, Specialty); sign-off locks the page; remove clears later sign-offs; override by manager | Already built as the GPHA chain (Preparer → Unit Head → Audit Manager → PIA → GM Audit). Show it with the circle cue | review_trail | D | – |
| UI-073–075 Requests | `H/projects/fieldwork/requests/adding_requests.html` | Fields: requester, description, owner (user/contact/email), CC, due date, email subject/message, reminder frequency; owner replies by attachment or comment through a link | Our PBC requests: add CC and a reminder frequency | evidence requests | D | Statuses not documented |
| UI-080–088 Issues & remediation | `H/projects/fieldwork/managing_issues/managing_issues_and_remediation.html`, `recording_issues.html`, `remediating_and_retesting_issues.html`, `recording_actions.html` | Issue fields (title, description, owner, type, date identified, severity, published, recommendation, cause, effect, escalation level…); publish gate; Follow-up & Remediation (status, plan, deadline, actual date); Retest Information (deadline, actual, results); actions with reminders 28/14/7/2/1 days | Findings register across audits; "published" = released to the auditee; retest section on the action; reminder schedule configurable | findings, capa | D | Is an issue "published" to the auditee at draft-report stage? |
| UI-099 Results | `H/projects/concluding_maintaining/concluding_and_maintaining_projects.html` | Results tab: Issues by Type / Severity charts, conclusion/rating, management response, results files | Audit Report tab keeps GPHA report workflow; add the two small charts | audit_reports | D | – |
| Consolidated reports UI-096–098 | – | Not documented by Diligent | GPHA-specific (Unit → Port → GM) per blueprint Prompt 12 | new | P | Needs GPHA template |
| API conventions | `https://docs-apis.highbond.com/customer.yml` | `/v1/orgs/{id}/…`; Bearer token; JSON:API (`data`, `attributes`, `relationships`); `page[size]` (max 100) / `page[number]`; `filter[...]`; `sort=-field`; errors `{errors:[{status, code, title, detail}]}`; 6 requests/s rate limit | For our `/api/v1`: `page`, `page_size` (≤ 100), `sort`, `q`, `filter.*`; one error envelope | all lists | D | – |

## 3. Data flow between apps (D, with GPHA notes)

```
Strategy risks ─► Framework objectives ─► Assurance Plan (coverage by entity) ─► Projects
Project: Planning ─► Fieldwork (RCM / procedures ─► walkthroughs ─► tests) ─► Issues ─► Actions ─► Retest ─► Results
Task Tracker / Issue Tracker aggregate across projects;  entity tags on everything drive plan coverage
```

GIAW equivalent (already wired): Universe → Plan → Engagement (audit) → RCM / control tests → Working papers (GPHA template, review chain) → Findings → Management response → Remediation (CAPA) → Follow-up testing → Report → Committee. **Missing:** consolidated Unit/Port/GM reports, and feeding closed findings back into the universe risk scores.

## 4. Comparison with giaw-fastAPI.md

- Its catalogue (UI-001 to UI-120) is consistent with the references. Diligent has no equivalents for: GPHA approval chain and distribution, three-level consolidation, timesheet approval rules, QAIP, independence declarations. These are GPHA additions and are labelled P.
- Diligent uses tabs straight under the record title and side panels for issues, requests and to-dos. GIAW uses stacked cards and modals. This is the main structural change for the redesign.
- Not documented publicly: projects-list columns, request statuses, a "workpapers" module, and report generation. GIAW keeps its own designs for these.
