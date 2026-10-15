# GIAW cross-module data flow check against mainBLUEPRINT.md

**Date:** 15 October 2026 · **Commit checked:** 5ffdff9 · **Code changed by this check:** none

Status key: **OK** aligned · **PARTIAL** link exists but incomplete · **GAP** missing or contradicts the blueprint.

Every link below was verified in the models and routers (file references in brackets). Nothing is inferred from screen labels alone.

## 1. Source-of-truth matrix

| # | Flow (blueprint) | What the code does | Status |
|---|---|---|---|
| 1 | Organization & user scope → every protected record | One organization tree exists (`organizations.parent_id`, ports flagged by category). **But all staff (Admin and Auditor tiers) read every record**; only auditees are limited to assigned audits [`app/core/access.py::can_view`, `is_privileged`]. No port/unit scoping, no engagement-team scoping | **GAP** (blueprint Module 1, non-negotiable) |
| 2 | One organization hierarchy | **Two parallel hierarchies.** The Audit Universe uses `locations → entity_units` [`assurance/planning/models.py`], while ports, departments, users' workplace, audit port, plan site and enterprise risks use `organizations`. A universe unit at Takoradi and an audit's port can disagree; nothing links them | **GAP** |
| 3 | Auditable entity → risk → control | Universe unit ↔ enterprise risk ↔ library control are linked through `grc_links` (types unit, risk, control, …). Engagement controls point back to the library (`controls.library_control_id`). Engagement risks (`risks`, per audit objective) have **no link to the enterprise risk or universe risk** they test | **PARTIAL** |
| 4 | Risk scoring configurable, approved policy | Universe score is hard-coded `likelihood × impact` [`EntityUnit.risk_score`]. Thresholds for heat-map bands are fixed in the screen | **GAP** (blueprint: configurable, GPHA decision) |
| 5 | Universe/risk → Assurance Plan | Plan engagements link to universe units (`plan_engagements.entity_unit_id`). Coverage % and "high-risk not planned" use unit scores. Enterprise (strategic) risks do not feed the plan | **PARTIAL** |
| 6 | Plan workflow states | `PlanLifecycle`: Draft, In Review, Submitted, Returned, Approved, Distributed, In Execution, Revised, Closed, Archived. Committee decision, locked approved versions, change requests and distribution records all exist | **OK** |
| 7 | Plan item → engagement (no duplicates) | `start_engagement` creates the audit once, copies plan, unit and site, and stores `plan_engagements.audit_id` [`assurance/planning/router.py`]. Ad-hoc audits can also be created without a plan item | **OK** (decide whether ad-hoc audits need a plan change request) |
| 8 | Lead auditor and team → engagement | The plan's lead auditor stays on the plan engagement. The audit has **no team or assignment record**, so "assigned engagements" and team-based access cannot work | **GAP** |
| 9 | Engagement states | Audit status has 4 values (Planned, In Progress, Review, Closed) plus a separate approval flag and report status. The blueprint asks for 12 states (Proposed … Follow-up, Closed) plus On hold, Cancelled and Reopened with reasons | **PARTIAL** |
| 10 | Engagement → objectives → controls → tests → working papers | Objectives, risks and controls are per audit; tests are per control; working papers link to a test and a finding (`working_papers.test_id`, `finding_id`) with the GPHA review chain | **OK** |
| 11 | Workplan vs Internal Control workflow | Only the RCM (Internal Control) pattern exists. There is no procedures / work-programme execution record with result and conclusion for Workplan audits (Expenditure, Revenue, Operations) | **GAP** |
| 12 | Working paper / test → evidence | Evidence requests link only to the audit (`evidence_requests.audit_id`). An accepted file can be filed as a working paper. A request cannot be linked to a specific test, working paper or finding, and one file cannot be linked to several records | **PARTIAL** |
| 13 | Evidence states and security | Requested → Submitted → Accepted / Returned / Cancelled. Files are SHA-256 checked, encrypted, and downloaded only through authorized endpoints. **No clarification or superseded states, and no malware scanning** | **PARTIAL** |
| 14 | Test / working paper → finding | Findings raised from a failed control test keep `findings.control_id` and `test_id` | **OK** |
| 15 | Finding → management response → action | Audit Client response, then Management response (action plan, officer, target date), then remediation (`capa.source_type="finding"`). The response updates the open action | **OK** |
| 16 | Action → verification / retest → closure (owner cannot close) | On the action: implementer ≠ validator, validation "Effective" required, e-signed close, committee or external-body closure rules [`issues/followup/router.py`, `issues/capa/router.py`]. **But closing the action does not close the finding, and an auditor can set a finding to Closed by editing it, with no verified action** [`audits/findings.py::update_finding`] | **GAP** (blueprint 6.4: closure only after verification) |
| 17 | Finding states | Finding: Open, Remediating, Closed. Action: Open, In Progress, Review, Closed, with implementation and validation fields. The blueprint's Draft → Review → Issued → … → Retest → Closed is split across the two records and **they are not kept in step** | **PARTIAL** |
| 18 | Closed results → next risk assessment | Closing an audit stamps `entity_units.last_audited_at`. Findings, repeat findings and overdue actions do not change universe risk | **PARTIAL** (GPHA "closed planning feedback loop" gap) |
| 19 | Assignment / approved timesheet → engagement, unit, port, HQ reports | Time entries link to an audit (`time_entries.audit_id`), but have **no submission or approval** and are used only by Capacity & time and budget-vs-actual | **GAP** |
| 20 | Unit → Port → GM Audit consolidated reports (snapshots, lineage, missing inputs flagged) | **Not built.** Governance portal, Port portfolio and the Committee pack are live views, not versioned snapshots | **GAP** (blueprint 6.5, Module 9) |
| 21 | Audit report workflow | Draft → Management Review → Unit Head → Audit Manager → PIA → GM Audit approval → Issued, with sign-off trail and separation of duties | **OK** |
| 22 | Committee directives → follow-up | Committee decisions close, extend or escalate recommendations. There is no directive register with owner and status (noted in the GPHA next steps) | **PARTIAL** |
| 23 | Notifications / activity → underlying record | Notifications carry `link_type` / `link_id` and open the record (`openLink`). The audit log and record history are separate from business state | **OK** |
| 24 | Versioned API `/api/v1` and one error envelope | Routes are `/api/...`; errors are `{detail, errors[]}`. Registers now share one paging contract | **PARTIAL** |

## 2. What is aligned

- **Planning:** the plan lifecycle and approvals.
- **Plan to engagement:** the plan engagement becomes an audit without duplicate records.
- **Fieldwork chain:** engagement controls trace back to the library, and test → working paper → finding is linked.
- **Responses and actions:** finding responses and actions, with separation of duties on validation.
- **Report review:** the GPHA report review chain.
- **Notifications:** every notification opens the record it is about.

## 3. Gaps, in recommended fix order

1. **Port/unit scope on reads** (rows 1, 8). Add an engagement team (lead, members, roles) to audits, copied from the plan's lead. Scope reads by home port/unit plus team membership. HQ / GM Audit keep the wide view.
2. **One organization tree** (row 2). Attach each universe unit to an `organizations` node (its port/department) and derive the audit port from it. Keep `locations` only as a compatibility view, then retire it. *Decision required:* is the Audit Universe the same as the organization tree, or a separate list of auditable areas mapped onto it?
3. **Finding closure follows verified remediation** (rows 16, 17). Refuse a manual "Closed" while any linked action is open or unvalidated. Closing the last action moves the finding to Closed. Show one combined status.
4. **Timesheet submission and approval** (row 19). Make approved hours the only hours used in reports.
5. **Three-level consolidated reports** (row 20). Snapshots, reconciliation, missing-input flags.
6. **Engagement lifecycle states** (row 9) and the **Workplan procedure record** (row 11).
7. **Evidence:** link to test, working paper or finding; clarification state; scanning dependency (rows 12, 13).
8. **Engagement risks link** to enterprise or universe risks; configurable scoring (rows 3, 4, 5).
9. **Feedback loop:** open, repeat and overdue findings raise universe risk for next year (row 18). *Recommended; GPHA to approve the rule.*
10. **Committee directive register** (row 22) and **`/api/v1`** (row 24).
