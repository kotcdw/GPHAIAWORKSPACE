# GIAW screen contracts: HighBond-aligned fieldwork, issues and plan coverage

**Date:** 15 October 2026 · **Stack:** FastAPI + MySQL + plain JavaScript (no build step)

Each screen below lists where it lives, the HighBond screen it follows, its exact columns and fields, the API it reads
and writes, and the rules the server enforces. Labels in quotes are the words shown on screen.

## 1. Audit > Fieldwork tab

The tab shows a workflow strip ("Workflow", "Testing rounds", "Apply audit programme") and a segmented sub-navigation.
The summary panel on the right is hidden on this tab so the work tables use the full width.

| Setting | Values | Rule |
|---|---|---|
| Workflow | Workplan, Internal Control | Default from the audit type (Configuration > Audit methodology > "Audit types that use the Workplan workflow"). Changeable only while the audit has no procedures and no controls. |
| Testing rounds | 1 (Testing), 2 (Interim, Final), 4 (Q1–Q4) | Internal Control only. Fixed once any operating-effectiveness test exists. |

API: `GET/PATCH /api/audits/{id}/fieldwork`, `GET /api/audits/{id}/assignees` (engagement team, for every "Assigned" picker).

### 1.1 Workplan > "Project plan" (HighBond: Workplan > Objectives / Risks / Procedures)

- Stats: Objectives, Risks, Procedures (reviewed · prepared), Issues noted. A warning lists risks with no procedure.
- One card per objective (actions "+ Risk", "+ Procedure", "Edit"), table **Risk | Rating | Procedures**. Each procedure
  is a chip (ref, title, status) that opens the execute panel. Procedures with no risk are listed on their own row.
- Procedure form: Procedure, Steps, Risks addressed (checklist), Assigned to (team members only), Due date.
- API: `GET /api/audits/{id}/procedures`, `POST /api/objectives/{id}/procedures`, `PATCH /api/procedures/{id}`.
- Rules: procedures only on Workplan audits; controls refused on Workplan audits (409); risks must belong to the audit.

### 1.2 Workplan > "Execute procedures" (HighBond: Execute Procedures)

- Filters: Search, Status, Issues (No Issues / Issue(s) noted / Not answered), Assigned (Me / each person).
- Columns: **Ref | Procedure | Risks | Assigned | Due | Status | Issues identified | Sign-offs | Evidence**.
  Overdue due dates are shown in red with "overdue". Sign-offs are two dots (Prepared, Reviewed).
- Side panel: Objective, Risks, Assigned, Due, Status; "Steps"; "Procedure results"; "Were issues identified?"
  (No Issues / Issue(s) noted); "Sign-offs"; "Issues"; "Evidence requests".
  Actions: Save · Sign off as prepared · Reopen · Review (e-sign) · Raise issue · Request evidence · Edit plan.
- Status flow: Not Started → In Progress (on the first result) → Prepared → Reviewed. Reject sends it back to In Progress.
- Rules: Prepared needs results and an answer; a Prepared procedure is read-only until reopened; the preparer cannot
  review (segregation of duties, password e-signature); Raise issue only when "Issue(s) noted", once per procedure.
- API: `PATCH /api/procedures/{id}`, `POST /api/procedures/{id}/review`, `POST /api/procedures/{id}/raise-issue`.

### 1.3 Internal Control > "Risk control matrix"

Unchanged matrix (objectives, risks, controls, tests, residual rating). Control form now also carries the test plan.

### 1.4 Internal Control > "Walkthroughs" (HighBond: Walkthroughs)

- Stats: Controls, Designed appropriately, Design failure, Not walked through.
- Columns: **Control | Key | Owner | Walkthrough | Status | Is the control designed appropriately? | Sign-offs | actions**.
- Answers: Effective → "Designed appropriately", Ineffective → "Design failure", none → "Not walked through".
- Actions: Start walkthrough (creates the walkthrough test, pre-filled with the test steps), Open, Review (e-sign).
- API: `GET /api/audits/{id}/walkthroughs`, `POST /api/controls/{id}/tests`.

### 1.5 Internal Control > "Test plan" (HighBond: Test Plan)

- Columns: **Control | Key | Frequency | Nature | Testing method | Total sample size | Test steps | Edit**.
- Testing method: Inquiry, Observation, Inspection, Re-performance, Data analytics. Empty sample size = the default for
  the control frequency (Configuration > Audit methodology > default sample sizes, e.g. Monthly=3).
- API: `PATCH /api/controls/{id}` (`test_method`, `total_sample_size`, `test_steps`).

### 1.6 Internal Control > one tab per testing round (HighBond: Testing rounds)

- Stats: Key controls, Tested this round, Completed (reviewed), Effective, Ineffective.
- "Prepare … round" creates one test per key control that has none, with the test steps and sample size from the plan.
- Columns: **Control | Tested this round? | Assigned | Sample | Exceptions | Status | Conclusion | Sign-offs | Evidence | actions**.
- "Tested this round?" can be switched off only before testing starts; the assignee must be on the engagement team.
- API: `GET /api/audits/{id}/testing/{round}`, `POST /api/audits/{id}/testing/{round}/prepare`, `PATCH /api/control-tests/{id}`.

## 2. Audit > "Issues" tab

- Actions: "Publish N to the auditee", "Import from Excel", "Add issue".
- Columns: **Issue | Status | Severity | Owner | Remediation deadline | Issue type | Published | Sign-offs | Remediation | Responses**.
- Issue form adds "Issue type" (configurable list), a publication line, the sign-off dots and the actions Publish,
  Sign off (review chain) and Request evidence.

## 3. Findings & remediation > "Issue Tracker" (HighBond: Results > Issue Tracker)

- Tabs: **List** and **KPIs**.
- List: donuts "By Issue Type" and "By Severity" plus "At a glance" (Open, Overdue, Unpublished); they follow the list
  filters. Register filters: Search, Status, Severity, Owner, Issue type, Published, Deadline (Overdue).
- Columns: **Issue | Status | Severity | Owner | Remediation deadline | Issue type | Published | Sign-offs | Project**
  (Remediation and Source can be added with "Columns"). Server-paged, sortable, Excel and CSV export.
- KPIs: Issues, Open, Overdue, Unpublished; bar lists by project, issue type, severity and status.
- API: `GET /api/findings/register`, `GET /api/findings/register/summary`, `GET /api/findings/issue-types`,
  `POST /api/findings/{id}/publish`, `POST /api/findings/{id}/review`.
- Rules: audit staff only, filtered by port / engagement-team scope. Auditees see only published issues. Publishing
  notifies the owner. Sending the draft report to management, or recording the exit meeting, publishes the audit's
  issues. Review sign-offs follow the working paper review chain; the preparer never signs.

## 4. Evidence requests (from any record)

- "Request evidence" on a procedure, a control test (round table), an issue, or the Evidence requests tab.
- Form (HighBond request): What is needed, Description, Owner, Due date, CC (auditees and team), Notification
  (Send now only / daily reminder / weekly reminder), Message.
- Evidence register adds **Linked to**; the request detail shows Linked to, CC, the reminder setting,
  "Send reminder now" and the last reminder time.
- API: `POST /api/audits/{id}/evidence-requests` (`target_type`, `target_id`, `cc_user_ids`, `reminder`, `message`),
  `PATCH /api/evidence-requests/{id}/reminder`, `POST /api/evidence-requests/{id}/remind`,
  `GET /api/audits/{id}/evidence-requests?target_type=&target_id=`.
- Rules: the target must belong to the audit; CC people must be staff or the audit's auditees; reminders are sent by
  the background watcher until the evidence is submitted; accepted files filed as working papers keep the link.

## 5. Assurance plan record

Tabs: **Overview | Entities | Risks | Versions & cycle | Change requests | Activities**.

- Entities (HighBond: Assurance plan > Entities): Overall progress bar; Hours planned / available (green up to the
  available hours, red above); Actual hours charged. Filters: Entity category, "Entities not covered (#)", Clear.
  Grid: **Project | Status | Hours | Progress | one column per entity** with a tick where the engagement covers it,
  and a Coverage row (Covered / Not covered). Entity headers show the risk rating.
- Risks: entities by risk score with rating and "Covered by the plan".
- Activities: Plan changes, History, Approval cycles.
- API: `GET /api/assurance-plans/{id}/coverage?category=&not_covered=`.
- Progress formula (decision 19 in mainBLUEPRINT.md): not started 0 %, Planned 10 %, In Progress 25 % + up to 50 % for
  fieldwork signed off, Review 85 %, Closed 100 %.

## 6. Configuration added (Configuration > Audit methodology)

| Rule | Default |
|---|---|
| Audit types that use the Workplan workflow | Financial, Operational, Performance / Value for Money, Special investigation, Follow-up |
| Default sample size by control frequency | Annual=1, Quarterly=2, Monthly=3, Weekly=10, Daily=25, Multiple Daily=40, Ad Hoc=25 |
| Issue types | Deficiency, Significant Deficiency, Material Weakness, Management Recommendation |

## 7. Data (migration 0029_fieldwork_issues)

`audits.workflow`, `audits.testing_rounds`; `controls.test_method`, `total_sample_size`, `test_steps`;
`control_tests.round_no`, `in_scope`, `assigned_to`; new `procedures` and `procedure_risks`;
`evidence_requests.target_type`, `target_id`, `cc_user_ids`, `reminder`, `last_reminded_at`;
`findings.procedure_id`, `issue_type`, `published`, `published_at`, `published_by`, `review_stage`, `review_trail`,
`reviewed_at`. Existing operating-effectiveness tests move to round 1 and existing findings are marked published, so
auditees keep seeing what they saw before.
