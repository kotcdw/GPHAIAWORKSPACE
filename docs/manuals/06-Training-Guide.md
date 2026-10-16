---
title: "GIAW — Training Guide"
subtitle: "Training programme, facilitator notes, hands-on exercises, assessment and evaluation"
author: "GPHA Internal Audit Department"
date: "Version 1.0 · 16 October 2026"
---

# 1. About this training

| Item | Detail |
|-----------|---------------------------------------------|
| Programme | GIAW end-user and administrator training |
| Goal | Every user can do their own GIAW tasks confidently and correctly on day one of go-live |
| Format | Instructor-led, hands-on, in a training copy of GIAW with demonstration data |
| Materials | This Training Guide (facilitator and participant), the training slide deck (PowerPoint), the User Manual, the quick reference cards |
| Class size | 6 to 12 participants, one computer each |

## 1.1 Learning outcomes

By the end of their track, participants can:

1. sign in securely, find their way around GIAW and get help;
2. use lists, forms, drafts, exports and saved views;
3. perform their role's part of the audit cycle: plan, fieldwork, evidence, issues, report, remediation;
4. understand sign-offs, electronic signatures and segregation of duties;
5. use Task Tracker to manage their daily work;
6. (managers) approve, review and report, including to the Audit Committee;
7. (auditees) respond to requests, issues and actions;
8. (administrators) manage users, configuration and backups safely.

# 2. Training tracks and schedule

| Track | Audience | Duration | Sessions |
|----------------|------------------------------------------|-----------|---------------------------------------------|
| A. Foundations | Everyone | 1 h 30 | A1 to A3 |
| B. Auditor | Senior Auditors, Auditors, Audit Clerks | 1 day (6 h) | A + B1 to B6 |
| C. Manager | Unit Heads, Audit Managers, PIAs, GM Audit | 1 day (6 h) | A + C1 to C6 (plus the B sessions as a refresher) |
| D. Auditee | Heads of department, action owners, staff | 2 h | A1, A2 + D1 to D3 |
| E. Administrator | Super Administrators, Administrators, IT | 1 day (6 h) | A + E1 to E6 |
| F. GRC | Risk, compliance and policy owners | 2 h | A1, A2 + F1 to F3 |

## 2.1 Session plan

| Session | Topic | Time | Method | Slides |
|-----------|---------------------------------------------|-----------|-----------------|--------------------|
| A1 | Why GIAW; the audit cycle in one picture | 20 min | Presentation | Introduction section |
| A2 | Signing in, two-step verification, the screen, help, notifications | 30 min | Demo + Exercise 1 | Getting started |
| A3 | Lists, forms, drafts, exports, e-signatures | 40 min | Demo + Exercise 2 | Working with GIAW |
| B1 | Audit universe and risk assessment (overview) | 30 min | Demo | Planning |
| B2 | The audit page, team, auditees, planning memo | 45 min | Exercise 3 | Audits |
| B3 | Fieldwork: RCM, tests, procedures, sign-offs | 90 min | Exercise 4 | Fieldwork |
| B4 | Evidence requests | 45 min | Exercise 5 | Requests |
| B5 | Issues and publishing | 45 min | Exercise 6 | Issues |
| B6 | Remediation, validation and Task Tracker | 45 min | Exercise 7 | Follow-up |
| C1 | Assurance Plan cycle and distribution | 60 min | Exercise 8 | Planning |
| C2 | Plan change requests and the timeline | 30 min | Demo | Planning |
| C3 | Reviewing work: sign-offs, review notes, quality review | 60 min | Exercise 9 | Review |
| C4 | Report review chain and issue | 45 min | Exercise 10 | Reporting |
| C5 | Closing an audit | 30 min | Exercise 11 | Reporting |
| C6 | Status Tracker, Analytics, Committee pack, QAIP | 60 min | Demo + discussion | Oversight |
| D1 | Your Priorities list | 30 min | Exercise 12 | Auditees |
| D2 | Submitting evidence | 30 min | Exercise 13 | Auditees |
| D3 | Responses and action updates | 30 min | Exercise 14 | Auditees |
| E1 | Installation, service, HTTPS (IT) | 60 min | Walk-through | Administration |
| E2 | Users, job roles, permissions | 60 min | Exercise 15 | Administration |
| E3 | Org Structure and reference data | 45 min | Exercise 16 | Administration |
| E4 | Configuration and Apps & customization | 60 min | Exercise 17 | Administration |
| E5 | Backups, restore test, updates | 45 min | Exercise 18 | Administration |
| E6 | Activity logs, security operations, troubleshooting | 30 min | Discussion | Administration |
| F1 | Risk Manager and KRIs | 45 min | Exercise 19 | GRC |
| F2 | Compliance Maps and Policy Manager | 45 min | Demo | GRC |
| F3 | Asset Inventory and third-party due diligence | 30 min | Exercise 20 | GRC |

# 3. Facilitator preparation

| # | Task | When |
|-----------|---------------------------------------------|----------------|
| 1 | Set up a **training copy** of GIAW (never production) with demonstration data (`scripts.seed_demo`) | 1 week before |
| 2 | Create training accounts: `trainee01`… with the job roles of the track, plus one Manager and one Auditee account for role-play | 1 week before |
| 3 | Check every exercise works end to end in the training copy | 2 days before |
| 4 | Book a room with a projector and one PC per participant; test the network and browser | 2 days before |
| 5 | Print the quick reference cards and the evaluation forms | 1 day before |
| 6 | Reset the training data after each class (restore the training backup) | After each class |

**Facilitator tips**

- Show, then let participants do it. Keep slides short and spend most of the time in the system.
- Pair a manager with an auditor for the approval exercises, so that segregation of duties can be seen working.
- Collect every question and problem on a flip chart. They feed the FAQ and the change backlog.

# 4. Hands-on exercises

Each exercise lists its steps and the expected result. The facilitator ticks **Done** when the participant shows the result. The same exercises can be used as UAT test scripts (Governance manual §9).

## Exercise 1 — Sign in and find your way (A2)

| Step | Action | Expected result |
|-----------|---------------------------------------------|-----------------------------------------|
| 1 | Sign in with your training account | Workspace Apps page opens |
| 2 | Open the help (?) | Help for the page appears |
| 3 | Open the bell | Your notifications list |
| 4 | Fold and unfold *Risk management* in the sidebar | The group collapses and expands |
| 5 | Press `/` and search for "revenue" | Matching audits and issues you can see |
| 6 | Open your profile; set **Where I work** | Saved; the workplace shows in the top bar |

## Exercise 2 — Lists, drafts and export (A3)

| Step | Action | Expected result |
|-----------|---------------------------------------------|---------------------------------------------|
| 1 | Open **Audits**; filter Status = Planned; sort by *Updated* | The list updates |
| 2 | Select **Columns**, hide *Stream*; select **Excel** | The Excel file contains the visible columns |
| 3 | Select **New audit**; type a title; close the browser tab | – |
| 4 | Reopen GIAW and select **New audit** | "Restored your unsaved entries"; the title is back |
| 5 | Open **My Drafts**; discard the draft | The draft is removed |

## Exercise 3 — Set up an audit (B2)

| Step | Action | Expected result |
|-----------|---------------------------------------------|-------------------------|
| 1 | Open the training audit *Payroll Controls Review (Head Office)* | Audit page, Dashboard tab |
| 2 | Add yourself to the **Engagement team** as Auditor | You appear in the team |
| 3 | Add the auditee account under **Auditees with access** | The auditee chip appears |
| 4 | Open **Planning**; complete the memo; submit for approval | Memo status: submitted |
| 5 | Complete your **independence declaration** | Declaration recorded |

## Exercise 4 — Fieldwork (B3)

| Step | Action | Expected result |
|-----------|---------------------------------------------|---------------------------------------------|
| 1 | Fieldwork › Risk control matrix › add an **objective** | The objective appears |
| 2 | Add two **risks** (one High) and two **controls** (one key) | Counts update; a coverage gap shows the untested key control |
| 3 | Testing: add a test of operating effectiveness; population 250 | The sample size suggestion appears |
| 4 | Record 1 exception; conclusion **Ineffective** | Test completed |
| 5 | Sign off as **Preparer** | First sign-off circle filled |
| 6 | Select **Raise issue** from the test | An issue is pre-filled from the test |

## Exercise 5 — Request evidence (B4)

| Step | Action | Expected result |
|-----------|---------------------------------------------|---------------------------------------------|
| 1 | Requests tab › **Request evidence** to the auditee; due in 5 days; link to your test | Request `ER-…` created; the auditee is notified |
| 2 | *(Auditee partner)* upload a file and **Submit** | Status: Submitted |
| 3 | **Return** it with a comment | Status: Returned; the auditee sees the comment |
| 4 | *(Auditee)* resubmit; *(you)* **Accept** | Status: Accepted |

## Exercise 6 — Issues and publishing (B5)

| Step | Action | Expected result |
|-----------|---------------------------------------------|-------------------------------|
| 1 | Complete the issue from Exercise 4: severity, owner = the auditee, recommendation | Saved; status Open |
| 2 | *(Auditee)* look for the issue | **Not visible** (not published) |
| 3 | **Publish** the issue | Published |
| 4 | *(Auditee)* open it and add the management response | Response recorded |

## Exercise 7 — Remediation and Task Tracker (B6)

| Step | Action | Expected result |
|-----------|---------------------------------------------|---------------------------------------------|
| 1 | Raise a **remediation action** from the issue; owner = the auditee | Action `REM-…`; default due date set by severity |
| 2 | *(Auditee)* open **Task Tracker › Priorities** | The action is listed |
| 3 | *(Auditee)* try to close the action | Refused: owners cannot close actions |
| 4 | *(Auditee)* mark *Fully implemented* with evidence | Status updated |
| 5 | *(Another auditor)* **Validate**: Effective | Ready for closure |

## Exercise 8 — Assurance Plan cycle (C1)

| Step | Action | Expected result |
|-----------|---------------------------------------------|------------------------------------|
| 1 | Open the draft plan; add an engagement (entity, quarter, hours, lead) | Hours summary updates |
| 2 | Record the preparation, universe review and planning meeting stages | Cycle stages ticked |
| 3 | Submit for internal review; *(GM Audit role)* approve | Plan approved and version frozen |
| 4 | Distribute to the destinations; *(recipient)* acknowledge | Distribution recorded |
| 5 | **Start** the engagement | Audit created and linked to the plan |

## Exercise 9 — Review work (C3)

| Step | Action | Expected result |
|-----------|---------------------------------------------|-------------------------------|
| 1 | Open Exercise 4's test; sign as **Detail Reviewer** | Second circle filled |
| 2 | Try to review a test you prepared yourself | Refused (segregation of duties) |
| 3 | Raise a **review note**; *(auditor)* answer it; clear it | Note cleared |
| 4 | Reviews tab: complete two checklist items | Saved |

## Exercise 10 — Report review chain (C4)

| Step | Action | Expected result |
|-----------|---------------------------------------------|------------------------------------|
| 1 | Results tab: draft the report; send to management | Response deadline set (working days) |
| 2 | Record the exit meeting; move to Manager Review; approve | Next stage |
| 3 | *(CAE role)* approve and **issue** | Report issued; issues frozen |

## Exercise 11 — Close the audit (C5)

| Step | Action | Expected result |
|-----------|---------------------------------------------|----------------------------------|
| 1 | Dashboard › **Closure readiness**: read each red item | You know what is missing |
| 2 | Complete the missing items; move the audit to **Review** | Checklist green |
| 3 | *(A different authorised manager)* close with an electronic signature | Status Closed; the audit is locked |

## Exercises 12 to 14 — Auditee (D1 to D3)

| Step | Action | Expected result |
|-----------|---------------------------------------------|---------------------------------|
| 1 | Open **Task Tracker › Priorities** | Your waiting items, with counts |
| 2 | Open an evidence request; upload; **Submit** | Status Submitted |
| 3 | Open a published issue; add the response, responsible officer and target date | Saved |
| 4 | Open an action; add a progress update with evidence | Saved; Internal Audit is notified |

## Exercises 15 to 18 — Administrator (E2 to E5)

| Step | Action | Expected result |
|-----------|---------------------------------------------|-------------------------------------|
| 15.1 | Users › add a user with job role **Auditor**, workplace Tema | The user can sign in |
| 15.2 | Roles & permissions: view the Auditor column; *(do not save)* | The matrix of 51 permissions is shown |
| 15.3 | Lock a training account (5 wrong passwords); **Unlock** it | Sign-in works again |
| 16.1 | Org Structure: add a unit under a department | It appears in the tree |
| 17.1 | Configuration › Action plans: change the High due days to 21; save | Change logged in Activity logs |
| 17.2 | Apps & customization: rename *Status Tracker* to *Project Status Tracker*; save; then **Discard** or revert | The sidebar label changes |
| 18.1 | Backups › **Run backup now** | A new encrypted backup is listed |
| 18.2 | *(IT)* run `scripts.verify_backup` on the training server | "Restore verified" output |

## Exercises 19 to 20 — GRC (F1, F3)

| Step | Action | Expected result |
|-----------|---------------------------------------------|---------------------------------------------|
| 19.1 | Risk Manager › **+ Risk**; set inherent 4×5, residual 3×4, target 2×2 | Scores and bands shown; warning that residual is above target |
| 19.2 | Add a KRI (amber 10, red 20); record a reading of 22 | The KRI shows Red |
| 20.1 | Asset Inventory › add a *Third party / Vendor* with a contract end date | Third party listed; due diligence due |
| 20.2 | Record a due-diligence assessment; link the third party to a risk | Assessment saved; link shown on both records |

# 5. Knowledge check

Use this at the end of each track. The pass mark is 8 out of 10 for the track's questions.

| # | Question | Answer |
|-----------|---------------------------------------------|---------------------------------------------|
| 1 | Where do you see everything waiting for you? | Task Tracker › Priorities |
| 2 | Your browser closed while you were typing a finding. What do you do? | Reopen the form and restore the draft, or open My Drafts |
| 3 | Can you approve a test you performed? | No: a different authorised person must review it |
| 4 | Why can the auditee not see your new issue? | It is not published yet |
| 5 | What must be true before you can request evidence from an auditee? | The auditee is on the audit's *Auditees with access* |
| 6 | Who closes a remediation action? | An authorised auditor or manager after validation, never the owner |
| 7 | How is an approved Assurance Plan changed? | Through a plan change request (PCR), with Audit Committee approval if significant |
| 8 | What does the *Closure readiness* list do? | It shows what must be completed before the audit can be closed |
| 9 | What happens after five wrong passwords? | The account is locked for 15 minutes |
| 10 | Where do you check who changed a configuration rule? | Activity logs |
| 11 | *(Admin)* What must never be lost and must be stored apart from backups? | The encryption key (`GPHA_ENCRYPTION_KEY`) and `.env` |
| 12 | *(Manager)* Where do you get the Audit Committee's Word pack? | Audit Committee › Committee pack › Download |

# 6. Training evaluation form

Rate each statement from 1 (strongly disagree) to 5 (strongly agree).

| # | Statement | 1 | 2 | 3 | 4 | 5 |
|-----------|----------------------------------------|-----------|-----------|-----------|-----------|-----------|
| 1 | The objectives were clear | ☐ | ☐ | ☐ | ☐ | ☐ |
| 2 | The exercises reflected my real work | ☐ | ☐ | ☐ | ☐ | ☐ |
| 3 | I can now do my GIAW tasks on my own | ☐ | ☐ | ☐ | ☐ | ☐ |
| 4 | The facilitator explained things well | ☐ | ☐ | ☐ | ☐ | ☐ |
| 5 | The materials (manual, cards) are useful | ☐ | ☐ | ☐ | ☐ | ☐ |

What should be improved in GIAW or in this training?

\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

# 7. Attendance and completion record

| Name | Department / port | Track | Date | Exercises done | Knowledge check score | Facilitator signature |
|-----------|-----------------|-----------|-----------|--------------|---------------------|---------------------|
| | | | | | | |
| | | | | | | |
| | | | | | | |

A participant **completes** the track when all of the track's exercises are done and the knowledge-check score is at least 8 out of 10.
