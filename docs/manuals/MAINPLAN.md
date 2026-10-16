---
title: "MAINPLAN — GPHA Internal Audit Workspace (GIAW)"
subtitle: "End-to-end project plan and conversion of the GPHA Internal Audit procedures and processes into GIAW · Submitted for approval"
author: "GPHA Internal Audit Department"
date: "Version 1.0 · 16 October 2026"
---

# Document control

| Item | Value |
|------------------|---------------------------------------------|
| Document | MAINPLAN: project plan and process conversion plan for the GPHA Internal Audit Workspace (GIAW) |
| Version | 1.0 (submitted for approval) |
| Date | 16 October 2026 |
| Prepared by | GIAW project team, Internal Audit Department |
| Submitted to | General Manager, Internal Audit (Chief Audit Executive), for approval and onward submission to Management and the Audit Committee as required |
| Controlled process | IMS_PS_004_AU03 (Internal Audit process) |
| Related documents | Documentation set 00 to 07 (`docs/manuals`), QA report of 15 October 2026, `mainBLUEPRINT.md`, `deploy/PRODUCTION.md`, *GPHA Audit Department Overview* |
| Classification | Internal |

**Version history**

| Version | Date | Change | By |
|-----------|-----------|------------------------|-----------------|
| 1.0 | 16 Oct 2026 | First issue for approval | GIAW project team |

# 1. Executive summary

GPHA Internal Audit has used a mix of the retired *Audit Manager* application, Word and Excel working papers, registers kept by individual units, and e-mail to plan, perform, report and follow up audits at Headquarters, Tema and Takoradi. This makes it hard to see the whole audit programme in one place, to prove who reviewed what, and to show the Audit Committee that agreed actions were actually completed.

The **GPHA Internal Audit Workspace (GIAW)** is a web application built for GPHA to replace that arrangement with one controlled system. It follows the GPHA Internal Audit process (IMS_PS_004_AU03), the GPHA review chain and the six audit streams, and it is organised in the familiar "workspace of apps" style used by leading audit software.

**Where the project stands today (16 October 2026)**

- The software is **built and tested**: 31 apps, 5 job roles, 51 permissions, an append-only audit trail, encrypted files and backups, Word report output.
- **159 automated tests pass** (150 system tests and 9 browser tests). An independent-style end-to-end QA review (15 October 2026) found **no Critical or High defects**; 72 of 75 scripted checks passed.
- A complete documentation set has been produced: technical, technology stack, administration, governance and operations, user manual with screenshots, training guide and training slides.

**Approval requested.** Management is asked to:

1. **Approve GIAW** as the official Internal Audit management system of GPHA, replacing the retired Audit Manager.
2. **Approve this plan**: the process conversion in section 6 and the implementation stages and timeline in section 9.
3. **Authorise the next steps**: provide a production server, nominate the project roles (section 11), take the 16 decisions listed in section 7.2, and run a pilot followed by a staged go-live (Headquarters first, then Tema and Takoradi).

# 2. Background and objectives

## 2.1 Background

- GPHA Internal Audit appraises internal controls and gives assurance on the judicious use of resources and financial accountability across the Authority.
- The department works under the controlled process **IMS_PS_004_AU03**. The GM Internal Audit owns the process; the Principal Internal Auditor (PIA) is the deputy.
- Work is carried out by units for Revenue, Expenditure, Operations, Special Duties, the Fishing Harbour and Hospital, and IT Audit, at Headquarters, Tema and Takoradi.
- The previous Audit Manager application is retired. Much of the work now lives in separate files and registers, which weakens version control, review evidence, follow-up and consolidated reporting.

## 2.2 Objectives

| # | Objective | How GIAW meets it |
|-----------|---------------------------------------------|---------------------------------------------|
| O1 | One controlled system for the whole audit lifecycle | Universe → risk assessment → annual plan → engagement → report → follow-up → Committee, in one application |
| O2 | Follow the GPHA process and review chain exactly | Review levels Unit Head, Audit Manager, PIA and GM Audit (CAE); configurable without programming |
| O3 | Evidence of every review and decision | Sign-offs, comments and an append-only audit trail that cannot be edited or deleted |
| O4 | Agreed actions followed up to verified closure | Remediation & Follow-up app with owners, target dates, evidence and auditor verification |
| O5 | Consolidated reporting | Quarterly and annual reporting for HQ, Tema and Takoradi, the Audit Committee and the IAA |
| O6 | Protect audit information | Role-based access, two-step verification, encryption of files and backups, HTTPS |
| O7 | Hosted and owned by GPHA | Runs on a GPHA server; no cloud subscription; no data leaves GPHA |

## 2.3 Expected benefits

- **One source of truth** for the audit universe, plan, engagements, findings and actions at all three locations.
- **Faster reviews and less paper**: online working papers, review notes and sign-offs replace printed files moved between offices.
- **Visible follow-up**: overdue actions and recurring findings are flagged automatically and reported to management and the Audit Committee.
- **Better assurance to stakeholders** (Audit Committee, Board, Ghana Audit Service, IAA, external auditors) through consistent reports and a full trail.
- **Lower cost of ownership**: open-source components, no licence fees for the software itself, hosted on GPHA infrastructure.
- **Compliance support** for the Internal Audit Agency requirements, the IIA Standards (IPPF/QAIP) and the ISO 9001, 14001, 45001 and 27001 management systems.

# 3. Scope

## 3.1 In scope

| Area | Included |
|--------------------|---------------------------------------------|
| Locations | Headquarters, Tema Port, Takoradi Port (including the Fishing Harbour and Hospital units) |
| Audit streams | Expenditure, Revenue, Operations, Special Duties, IT Audit, and other assurance and advisory activities |
| Lifecycle | Audit universe, risk assessment, annual plan and Committee approval, resource allocation, engagement planning, fieldwork, working papers, evidence requests, findings, management responses, reporting, follow-up, Audit Committee reporting, quality assurance (QAIP), records and audit trail |
| Users | Internal Audit staff (all grades), audit clients (auditees) for their own requests and actions, and administrators |
| Supporting registers | Risk register, asset and third-party inventory, frameworks and compliance maps, policies, nonconformances, stakeholders |
| Outputs | Word reports and certificates, Excel registers, Committee packs, dashboards and KPIs |

## 3.2 Out of scope (for this phase)

- Replacing the ERP, the Terminal Operating System (TOS) or other operational systems. GIAW records evidence taken from them; it does not change them.
- Automatic live data feeds from ERP/TOS (possible later, decision D11).
- Full third-party risk management (vendor questionnaires and scoring); only a basic third-party register is included today (decision D15).
- Use of AI assistance. The feature exists but is **switched off** until GPHA approves it (decision D11).
- Migration of the complete historical archive. Only the current plan, open engagements and open findings are loaded (section 10.1).

# 4. The current GPHA Internal Audit process (as is)

## 4.1 Roles

| GPHA role | Responsibility in the process |
|---------------------------------------------|---------------------------------------------|
| GM Internal Audit (CAE) | Process owner; approves the plan and final reports; reports to the DG, Board and Audit Committee |
| Corporate / IT Audit Manager | Manages corporate and IT audit work; reviews reports |
| Principal Internal Auditor (PIA) | Deputy process owner; reviews reports and follow-up for each port |
| Audit Managers | Plan and supervise engagements; review working papers |
| Unit Heads / Supervisors | Lead unit audits; first-level review; discuss findings with management |
| Unit Auditors / Officers / Clerks | Perform fieldwork, prepare working papers and draft findings |
| Audit clients (management) | Provide information; respond to findings with action plans; implement actions |
| DG / Corporate Management, Board and Audit Committee | Receive reports; issue directives; monitor implementation |

## 4.2 Review chain

**Auditor / Clerk → Unit Head / Supervisor → Audit Manager → PIA → GM Audit → DG / Corporate Management → Audit Committee.**
Follow-up runs from the Unit Head / PIA to the GM Audit, who monitors the implementation of Committee directives.

## 4.3 Lifecycle elements in the existing procedure

| Ref | Element | Description |
|-----------|---------------------|---------------------------------------------|
| A | Annual plan | Risk-based annual audit plan, approved by the Audit Committee |
| B | Engagement planning | Planning memorandum, audit programme, risk assessment |
| C | Fieldwork | Interviews, walkthroughs, observation, data extraction, configuration review, reperformance |
| D | Document examination | Revenue, expenditure and IT documents and system records |
| E | Findings discussion | Findings discussed with the Unit Head |
| F | Responses | Audit client and management responses (action plan, responsible officer, target date), confirmed at the exit meeting |
| G | Review and escalation | Review up the chain; escalation of significant matters |
| H | Reporting | Engagement reports and quarterly reports |
| I | Follow-up | Confirm action implemented, evidence provided, risk reduced, then close |

## 4.4 Inputs and outputs

- **Inputs (evidence):** petty cash, payment vouchers, bank statements, cash books, invoices, waybills, delivery orders, tallies, manifests, attendance books, payroll and shift premium records, pay-in slips, cheque registers, requisitions, asset registers, fuel coupons, value books, pilotage cards, and extracts from the ERP and TOS.
- **Outputs:** audit reports, cash-count certificates, endorsed certificates, audited payroll and other registers, reviewed bank reconciliations, quarterly and annual reports.
- **Working paper template:** 14 sections. **Finding format:** Criteria → Condition → Cause → Effect → Recommendation, followed by the management response.

## 4.5 Audit streams

| Stream | Typical coverage |
|--------------|---------------------------------------------|
| Expenditure | Payment vouchers, cash counts, bank reconciliations, payroll, staff debtors, procurement, contracts, imprest, statutory payments, creditors, loans |
| Revenue | Daily takings, hospital, tolls, marine, cargo, rents, utilities, licences, Fishing Harbour, investment income, oil and gas |
| Operations | Cargo positioning, service-to-billing, safety, unclaimed cargo |
| Special Duties | Bid opening, vehicles, value books, PPE, fuel, stores, contracts, EHS, quality assurance, system audit |
| IT Audit | Networks, access management, suppliers, incidents, continuity, backup, logging, vulnerabilities, follow-up |

## 4.6 Gaps identified in the current process

| # | Gap | Effect today |
|-----------|---------------------------------------------|---------------------------------------------|
| G1 | No complete audit universe governance method | Coverage of auditable areas cannot be demonstrated |
| G2 | Separate unit procedures rather than one common lifecycle | Inconsistent files, formats and reports across units and ports |
| G3 | Risk assessment method not formalised | Plan priorities hard to justify to the Committee |
| G4 | Exit meeting not consistently recorded | Disputes about agreed findings and dates |
| G5 | Weak follow-up governance | Overdue and recurring findings not escalated in time |
| G6 | Evidence held in paper and personal folders | Risk of loss, forgery and missing support |
| G7 | No feedback loop | Results do not feed the next risk assessment and plan |

Key department risks noted in the overview are slow management responses, forged value books, omissions and inaccurate data, data loss, recurring findings, control failures by heads of department, missed discrepancies and threats to staff. GIAW addresses those that a system can address (sections 6 and 7).

# 5. The target process in GIAW (to be)

GIAW implements one common, 32-step lifecycle for every unit and location, as recommended in the overview document:

| Stage | Steps |
|-----------------------|---------------------------------------------|
| Governance and planning | 1 Audit universe · 2 Enterprise audit risk assessment · 3 Annual assurance plan · 4 Audit Committee approval · 5 Allocation to HQ / Tema / Takoradi |
| Engagement set-up | 6 Engagement assignment · 7 Independence and resource check · 8 Preliminary survey · 9 Risk and control assessment · 10 Planning memorandum / terms of reference · 11 Audit programme |
| Fieldwork | 12 Information (PBC) requests · 13 Fieldwork · 14 Sampling and testing · 15 Working papers · 16 Evidence · 17 Exceptions and potential findings · 18 Supervisor review · 19 Findings validation |
| Agreement and reporting | 20 Exit meeting · 21 Management response and action plan · 22 Draft report · 23 Audit Manager / PIA review · 24 GM Audit review · 25 Final report · 26 DG / Corporate Management · 27 Audit Committee |
| Follow-up and learning | 28 Action tracking · 29 Follow-up testing · 30 Closure, reopening or escalation · 31 Quarterly and annual consolidation · 32 Results feed the next risk assessment |

![GIAW audit lifecycle](images/diagram-lifecycle.png){width=95%}

**Status flows built into the system**

| Record | Status flow |
|------------------|---------------------------------------------|
| Annual plan | Ten states from Draft through review, Audit Committee approval and distribution to Closed |
| Audit (engagement) | Planned → In Progress → Review → Closed |
| Audit report | Draft → Management Review → Manager Review → CAE Approval → Issued |
| Finding (issue) | Open → Remediating → Closed |
| Agreed action | Open → In Progress → Review → Closed (auditor verifies evidence before closure) |

# 6. Process conversion map: GPHA procedure → GIAW

This is the core of the conversion. Each GPHA procedure, document or control is mapped to the app and feature that now carries it.

## 6.1 Planning and governance

| GPHA procedure / document | GIAW app | How it works in GIAW |
|---------------------------------------------|--------------------------------|---------------------------------------------|
| List of auditable areas (units, processes, systems, contracts) | Audit universe | Each auditable entity is recorded with its location, owner, stream, risk rating and last audit date; coverage gaps are visible |
| Departmental and audit risk assessment | Risk Manager, Audit universe | 5 × 5 likelihood × impact scoring with configurable thresholds; ratings feed the plan |
| Annual risk-based audit plan | Assurance Plans | Plan lines linked to universe entities, budgeted days and quarters; ten-state approval cycle |
| Audit Committee approval of the plan | Assurance Plans, Audit Committee | Committee decision, date and minute reference recorded on the plan; GM Audit distributes the approved plan |
| Allocation to HQ, Tema and Takoradi | Organizations, Scheduler | Plan lines and audits carry the location; the scheduler books staff to engagements |
| Staff availability and time | Timesheets & capacity | Available hours, utilisation and timesheets per auditor |
| Independence declarations, CPD and certifications | Professional practice | Annual and per-engagement independence declarations; training and CPD records |

## 6.2 Engagement planning and fieldwork

| GPHA procedure / document | GIAW app | How it works in GIAW |
|---------------------------------------------|----------------------------------|---------------------------------------------|
| Engagement assignment and team | Audits | Audit created from the plan line; team, lead and reviewer assigned |
| Planning memorandum / terms of reference, engagement letter | Audits | Planning section with objectives, scope and timing; engagement letter produced in Word |
| Audit programme for each stream | Project Library, Audits | Reusable work programmes for Expenditure, Revenue, Operations, Special Duties and IT; copied into each audit and adjusted |
| Risk and control matrix (RACM) | Audits, Frameworks | Risks and controls linked to programme procedures and to frameworks (for example ISO 27001 for IT audit) |
| Information / PBC requests to the audit client | Requests | Requests sent to named auditees with due dates; auditees upload documents; the auditor accepts or returns them |
| Fieldwork techniques (interview, walkthrough, observation, reperformance, data extraction) | Audits (working papers), Results | Each procedure records the work done, sample, result and conclusion; data analyses can be stored in Results tables |
| 14-section working paper template | Audits (working papers) | Working paper sections are fields of the procedure record; attachments are encrypted; every change is logged |
| Cash counts, payroll audit, bank reconciliation review, value book checks | Project Library programmes, Audits | Standard programmes per stream; certificates and endorsed registers attached as evidence |
| Daily task follow-up within the team | Task Tracker | Personal priorities, to-dos and open requests in one place |
| Supervisor review of working papers | Audits (sign-offs) | Preparer and reviewer sign-offs per procedure; review notes must be cleared before sign-off |

## 6.3 Findings, responses and reporting

| GPHA procedure / document | GIAW app | How it works in GIAW |
|---------------------------------------------|------------------------------------------|---------------------------------------------|
| Finding format: Criteria, Condition, Cause, Effect, Recommendation | Audits (Issues) | Each issue has these five fields plus rating, owner and linked evidence |
| Discussion with the Unit Head | Audits (Issues) | Issue status and comments record the discussion |
| Exit meeting | Audits | Exit meeting date, attendees and agreed points recorded before the report is issued |
| Management response: action plan, responsible officer, target date | Audits (Issues), Remediation & Follow-up | The audit client enters the response online; actions are created with owner and target date |
| Review chain Unit Head → Audit Manager → PIA → GM Audit | Audits (report review chain) | Report moves Draft → Management Review → Manager Review → CAE Approval → Issued; review levels are configurable |
| Final audit report | Audits | Word report generated from the audit record using the GPHA template |
| DG / Corporate Management and Audit Committee reporting | Audit Committee, Governance portal | Committee pack (plan progress, reports, overdue actions, directives) produced in Word; read-only governance view |
| Quarterly and annual consolidated reports | Analytics, Audit Committee, Port portfolio | Coverage and results by port and stream; statutory and Committee reports |

## 6.4 Follow-up, quality and records

| GPHA procedure / document | GIAW app | How it works in GIAW |
|---------------------------------------------|------------------------------------|---------------------------------------------|
| Follow-up of agreed actions | Remediation & Follow-up | Owners update progress and upload evidence; the auditor verifies before closure; overdue actions are flagged |
| Follow-up of Audit Committee directives | Audit Committee | Directives recorded with owner and due date and tracked to closure |
| Closure, reopening and escalation | Remediation & Follow-up, Automations | Actions can be closed, reopened or escalated; reminder and escalation rules are configurable |
| Recurring findings and feedback to the next plan | Audit universe, Analytics | Open and recurring issues update the entity's risk view for the next risk assessment |
| KPIs (irregularities, lapses, cycle time, non-adherence, close-out rate, reports realised vs planned) | Analytics | KPI tiles, trends and heat maps; configurable targets |
| Client satisfaction / service feedback | Service Feedback | Post-engagement survey to the audit client |
| Quality assurance and improvement programme (IIA Standards) | Quality (QAIP) | Internal assessments, file reviews and improvement actions |
| ISO nonconformances raised by audits | Nonconformance | Nonconformance register linked to issues and actions |
| Policies and procedures (including IMS_PS_004_AU03) | Policy Manager | Controlled copies, versions and attestations |
| Stakeholders and interested parties (Ghana Audit Service, GRA, ICAG, PAC, IAA, PPA, Ministry of Transport, Audit Committee, external auditors) | Stakeholders, Organizations | Contacts and organisations recorded and used in requests and distribution |
| Audit file retention and audit trail | All apps (platform) | Append-only audit trail; retention period configurable; encrypted backups |

## 6.5 Inputs and outputs in GIAW

| GPHA input or output | Where it lives in GIAW |
|---------------------------------------------|---------------------------------------------|
| Source documents (vouchers, bank statements, cash books, invoices, waybills, manifests, payroll, value books, fuel coupons, pilotage cards and similar) | Uploaded through Requests or attached to working papers; encrypted at rest |
| ERP and TOS extracts | Uploaded as evidence or loaded into Results tables for analysis |
| Audit reports, engagement letters, Committee packs | Generated as Word documents |
| Cash-count and endorsed certificates, audited registers, reviewed reconciliations | Attached to the procedure as evidence; listed in the report |
| Registers (findings, actions, risks, plan) | Exported to Excel at any time |

# 7. Gaps closed and decisions needed

## 7.1 How GIAW closes the gaps

| Gap | Closed by |
|-----------------------|---------------------------------------------|
| G1 Universe governance | Audit universe app with owners, risk ratings and coverage history |
| G2 One lifecycle | One common lifecycle and status flows for all units and ports |
| G3 Risk method | Configurable 5 × 5 scoring used in the universe, risk register and plan |
| G4 Exit meeting | Exit meeting recorded on the audit before report issue |
| G5 Follow-up governance | Remediation & Follow-up with verification, reminders, escalation and Committee reporting |
| G6 Evidence governance | Requests with acceptance, encrypted storage, audit trail, no deletion of signed work |
| G7 Feedback loop | Open and recurring issues feed the universe and the next risk assessment |

## 7.2 Decisions GPHA must take before production

The system has working defaults for each item, but each needs a formal decision (recorded with date, decision-maker and memo or minute reference).

| # | Decision | Default in GIAW | Decided by |
|-----------|---------------------------------------------|---------------------------------------------|----------------------|
| D1 | Official HQ / Tema / Takoradi hierarchy and organisation data | Configurable entity types | GM Audit |
| D2 | Roles, delegated approval authority, separation of duties | 5 job roles; review levels Unit Head, Manager, PIA, CAE | GM Audit |
| D3 | Recording of Audit Committee approval and plan distribution | Decision recorded on plan; GM Audit distributes | GM Audit / Committee |
| D4 | Risk scoring scales and thresholds | 5 × 5, thresholds configurable | GM Audit |
| D5 | Fiscal year and planning calendar | Configurable | GM Audit / Finance |
| D6 | Engagement types and report templates | Default types; Word templates | GM Audit |
| D7 | Confidentiality classes and auditee access | Public / Internal / Confidential / Restricted; auditees see only their own items | GM Audit / Legal |
| D8 | Retention, legal hold and disposal | Configurable number of years | Legal / Records |
| D9 | Hosting, sign-in (Active Directory), e-mail relay, recovery objectives | GPHA Windows server; local accounts or AD | IT / GM Audit |
| D10 | Data to migrate and quality rules | Current plan, open audits and findings | System owner |
| D11 | Integrations and AI use | AI off; no live integrations | GM Audit / IT Security |
| D12 | UAT sign-off owners and support contacts | – | Sponsor |
| D13 | Read-only accounts for Audit Committee members | Not available yet | GM Audit |
| D14 | Rule when two people edit the same record | Fix planned (stale save rejected) | System owner |
| D15 | Is full third-party risk management in scope? | Basic third-party register | GM Audit |
| D16 | Sign-off levels and password confirmation on sign-off | Five levels; password optional | GM Audit |

# 8. System overview

## 8.1 Apps (31 apps, shown by area)

| Group | Apps |
|-----------------------|---------------------------------------------|
| Home | Workspace Apps, My Drafts |
| Audit management | Audit universe, Assurance Plans, Audits, Project Library, Task Tracker, Requests, Remediation & Follow-up |
| Resources | Scheduler, Timesheets & capacity, Professional practice |
| Risk and compliance | Risk Manager, Asset Inventory, Frameworks, Compliance Maps, Policy Manager, Nonconformance |
| Reporting and analytics | Analytics, Audit Committee, Governance portal, Port portfolio, Quality (QAIP), Results, Storyboards, Robots, Service Feedback |
| Settings and services | Organizations, Stakeholders, Automations, AI assistance (off) |

Administrators also have Users, Roles & permissions, Configuration (12 rule groups), Reference data, Backups and Logs.

## 8.2 Users and roles

| Job role | Typical GPHA holder | Access |
|-------------------|-----------------------------------------|---------------------------------------------|
| Super Administrator | Two named IA officers | Everything, including roles, permissions and app customisation |
| Administrator | IA / IT administrators | Users, configuration, reference data, backups, logs |
| Manager | GM Audit, PIA, Audit Managers, Unit Heads | Plan, assign, review, approve and report |
| Auditor | Unit auditors and officers | Perform assigned audits, working papers, findings, requests |
| Audit Client | Management and staff of audited units | Only their own requests, issues and actions |

Access is controlled by **51 permissions in 9 categories**, which a Super Administrator can adjust without programming. Users are also limited to their workplace (HQ, Tema or Takoradi) where configured.

## 8.3 Security and control features

- HTTPS only; strict security headers; no external internet calls from the browser.
- Passwords hashed with bcrypt; optional two-step verification (authenticator app); optional Active Directory sign-in; sign-in rate limiting and account lockout.
- Role- and record-level access checks on every request.
- Uploaded files and backups are **encrypted** with a GPHA-held key.
- **Append-only audit trail** protected by database triggers: entries cannot be edited or deleted.
- Signed-off work is locked; changes need a recorded reopening.
- Daily encrypted backups with a restore-verification tool.

## 8.4 Technology and hosting

| Item | Choice |
|------------------|---------------------------------------------|
| Application | Python 3.12+ with FastAPI, SQLAlchemy and Alembic |
| Database | MySQL 8.4 LTS (104 tables, 34 versioned migrations) |
| User interface | Plain HTML, CSS and JavaScript; works in Edge or Chrome on PCs, tablets and phones |
| Documents | Word (python-docx) and Excel (openpyxl) output |
| Hosting | GPHA Windows server behind Apache or Caddy (HTTPS), run as a Windows service |
| Recommended server | Windows Server 2022, 4 vCPU, 8 GB memory, 200 GB disk, plus an off-server backup location |
| Licences | All components are open source; no software licence fees |

![GIAW production deployment](images/diagram-deploy.png){width=95%}

# 9. End-to-end implementation plan

## 9.1 What has been done (Stages 1 to 3)

| Stage | Work | Status |
|----------------------------|---------------------------------------------|-----------|
| 1. Discovery and design | Review of IMS_PS_004_AU03, the department overview, the review chain, streams, templates and gaps; blueprint with 10 modules and 20 build phases | Complete |
| 2. Build | Platform (sign-in, roles, audit trail, encryption, backups), all 31 apps, Word and Excel outputs, configuration without programming, GPHA branding | Complete |
| 3. Testing and documentation | 150 system tests and 9 browser tests passing; end-to-end QA (75 checks, 72 pass); security scans; accessibility checks (0 issues on 38 desktop screens); full documentation and training set | Complete |

## 9.2 What remains (Stages 4 to 9)

Timeline assumes approval by the end of October 2026. Dates move with the approval date and server availability.

| Stage | Activities | Target timing | Responsible | Exit criterion |
|--------------------------------|---------------------------------------------|---------------------------------------------|------------------------|---------------------------------------------|
| 4. Approval and decisions | Approve this plan; appoint project roles; take decisions D1 to D16 | Weeks 1 to 2 (by 30 Oct 2026) | GM Audit, Management | Signed approval; decision register completed |
| 5. Final fixes and configuration | Fix QA-02 (concurrent editing) and QA-08 (phone layout); add Committee role if D13 = yes; configure templates, risk scales, review levels and calendar to the decisions | Weeks 2 to 4 | Developer, system owner | Retest passes; configuration approved by GM Audit |
| 6. Production environment | GPHA IT builds the server, MySQL 8.4, HTTPS certificate, backups and monitoring; security review; restore test | Weeks 3 to 6 | GPHA IT, IT Security | Readiness check OK; restore proven; security review signed |
| 7. Pilot (UAT) | One real engagement end to end at HQ or Tema with 3 to 5 auditors and one audit client unit | Weeks 6 to 9 | System owner, pilot team | UAT sign-off; no open Critical or High issues |
| 8. Data load and training | Load organisation structure, universe, current plan, open audits and open findings; train every role; issue quick guides; name super users | Weeks 8 to 11 | System owner, trainers | Data reconciled and signed; all users trained |
| 9. Go-live and support | Go-live at Headquarters, then Tema, then Takoradi; hypercare for 4 weeks; then normal support | Weeks 11 to 16 (about mid-January to February 2027) | All | All three locations live; post-implementation review held |

**Summary timeline**

| Month | Main activity |
|-------------|---------------------------------------------|
| October 2026 | Approval, project roles, decisions |
| November 2026 | Fixes, configuration, server build, security review |
| December 2026 | Pilot engagement (UAT), data preparation |
| January 2027 | Data load, training, Headquarters go-live |
| February 2027 | Tema and Takoradi go-live, hypercare, post-implementation review |

## 9.3 Go-live checklist

| # | Item |
|-----------|---------------------------------------------|
| 1 | Decisions D1 to D16 recorded |
| 2 | Production server built; HTTPS working; readiness check OK |
| 3 | Backup restore proven and the result filed |
| 4 | Encryption key and configuration file stored securely, separately from backups |
| 5 | At least two Super Administrators; initial password replaced |
| 6 | Reference data loaded and reconciled |
| 7 | Users created with correct job roles and workplaces |
| 8 | Configuration approved by the GM Audit |
| 9 | Training delivered to every role |
| 10 | Support contacts announced |
| 11 | Two-step verification enforced for the agreed roles |
| 12 | IT security review completed |
| 13 | UAT signed off |

# 10. Data migration, testing, training and documentation

## 10.1 Data migration

| Data | Source | Method | Check |
|---------------------------------------------|-----------------------------|---------------------------|--------------------------------------------|
| Organisation structure (HQ, Tema, Takoradi, departments, units) | HR / organogram | Excel import | Count and hierarchy signed by system owner |
| Users | HR list and Active Directory | Created by administrators | Each user confirms access at training |
| Audit universe and risk ratings | Unit lists, IA Strategic Plan | Excel import | Reviewed by Audit Managers |
| Current annual plan | Approved 2026 plan | Entered or imported | Agrees to the approved plan |
| Open engagements | Current files | Entered by the audit team | Lead auditor confirms |
| Open findings and actions | Follow-up registers | Excel import | Reconciled to the register total; signed off |
| Historical closed reports | Archive | Optional: attach PDF copies | Kept read-only |

The production system starts empty. Demonstration data is never loaded into production.

## 10.2 Testing and quality assurance

| Test layer | Result to date |
|---------------------------------------------|---------------------------------------------|
| Automated system tests (API, rules, permissions, workflows) | 150 passing |
| Browser tests (screens, roles, review chain) | 9 passing |
| Scripted end-to-end QA (75 checks) | 72 pass, 1 open (QA-02), 2 information only |
| Security: static analysis, dependency audit, access matrix across all roles | No High findings; four issues found and fixed (QA-01, 04, 05, 06) |
| Accessibility (WCAG 2.2 AA target) | 0 issues on 38 desktop screens; 3 low issues at phone width (QA-08) |
| Still to do | Run on the target GPHA server; UAT pilot; IT security review |

**Open QA items:** QA-02 concurrent editing (fix planned in Stage 5), QA-03 Audit Committee accounts (decision D13), QA-08 minor phone-width issues (fix planned in Stage 5).

## 10.3 Training

| Audience | Content | Duration |
|---------------------------------------------|---------------------------------------------|-----------|
| Super Administrators and Administrators | Users, roles, configuration, backups, logs, support | 1 day |
| Managers (GM Audit, PIA, Audit Managers, Unit Heads) | Universe, plan, assignment, review and approval, Committee pack, analytics | 1 day |
| Auditors | Audits, programmes, working papers, requests, issues, follow-up | 1.5 days |
| Audit Clients | Responding to requests and issues; updating actions | 1 hour |
| Super users (one per location) | All of the above plus first-line support | 2 days |

Materials: Training Guide (Word) with exercises and assessment, training slide deck (PowerPoint), User Manual with screenshots.

## 10.4 Documentation delivered

| # | Document | Format |
|-----------|---------------------------------------------|-----------------|
| 00 | Documentation index | Word and Markdown |
| 01 | Technical documentation | Word and Markdown |
| 02 | Technology stack | Word and Markdown |
| 03 | Administration guide | Word and Markdown |
| 04 | Governance and operations (decisions, change control, support, UAT, go-live) | Word and Markdown |
| 05 | User manual with screenshots | Word and Markdown |
| 06 | Training guide | Word and Markdown |
| 07 | Training deck | PowerPoint |
| – | QA report (15 October 2026) | Markdown |
| – | Production deployment guide (13 steps) | Markdown |
| – | This MAINPLAN | Word and Markdown |

# 11. Governance, risks, resources and support

## 11.1 Project governance

| Role | Holder (GPHA to name) | Responsibility |
|------------------------|--------------------------------------|---------------------------------------------|
| Project sponsor | GM Internal Audit (CAE) | Approves scope, decisions, go-live and major changes |
| System owner | Senior Internal Audit officer | Day-to-day ownership, priorities, configuration approval, decision register |
| Super Administrators (2) | Named IA officers | Roles, permissions, app settings |
| GPHA IT | IT Department | Server, database, network, certificate, patching, backups, monitoring |
| IT Security | IT Security unit | Security review and incident handling |
| Legal / Records | Legal Department | Data protection and retention (D7, D8) |
| Developer / maintainer | Internal or contracted | Fixes, changes, releases |
| Super users | One per location | First-line help and feedback |
| Steering meeting | Sponsor, system owner, IT, super users | Every two weeks until go-live, then quarterly |

## 11.2 Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|-----------|---------------------------------------------|-----------|-----------|---------------------------------------------|
| R1 | Decisions D1 to D16 delayed | Medium | High | Decision workshop in week 1; defaults already working |
| R2 | Production server not ready in time | Medium | High | Early request to IT; sizing already defined |
| R3 | Low user adoption / preference for paper files | Medium | High | Role-based training, super users, GM Audit directive that GIAW is the system of record |
| R4 | Poor quality of migrated data | Medium | Medium | Limit to open items; reconcile and sign off each load |
| R5 | Loss of the encryption key or backups | Low | High | Key held by two officers in a sealed or vaulted store, separate from backups; restore tested |
| R6 | Dependence on a single developer | Medium | Medium | Full technical documentation, automated tests, plain technology choices; named backup maintainer |
| R7 | Unauthorised access to audit information | Low | High | Role and record checks, two-step verification, audit trail, IT security review |
| R8 | Network outages at Tema or Takoradi | Medium | Medium | Drafts autosave; works on low bandwidth; offline paper fallback procedure |
| R9 | Scope creep (TPRM, integrations, AI) | Medium | Medium | Change control through the steering meeting (decisions D11, D15) |

## 11.3 Resources and costs (GPHA to confirm)

| Item | Need | Cost note |
|-----------------|---------------------------------------------|-------------------------------------------|
| Server | One Windows Server 2022 virtual machine (4 vCPU, 8 GB, 200 GB) plus backup storage | Existing GPHA infrastructure where possible |
| Software licences | None for GIAW components (open source); Windows Server licence under the GPHA agreement | No new licence fees expected |
| TLS certificate | GPHA internal or public certificate | Minimal |
| Staff time | System owner (part time), 2 Super Administrators, IT support, pilot team, trainers | Internal |
| Training | Venue and time at HQ, Tema and Takoradi | Internal |
| Maintenance | Developer / maintainer for fixes and changes | GPHA to decide: internal or contracted |

## 11.4 Support after go-live

| Level | Who | What |
|-----------|-----------------------------|---------------------------------------------|
| 1 | Super users | How-to questions, first check of problems |
| 2 | Administrators / system owner | Accounts, configuration, data corrections |
| 3 | Developer and GPHA IT | Defects, server, database, security incidents |

Routine operations: daily backups and log checks, monthly patching and access review, quarterly restore test and upgrade cycle, annual review of configuration, roles and this documentation. All changes follow the change control procedure in document 04.

## 11.5 Success measures

| Measure | Target (first year) |
|---------------------------------------------|---------------------------------------------|
| Engagements performed and documented in GIAW | 100% of new engagements from go-live |
| Agreed actions tracked in GIAW | 100%, with overdue actions reported quarterly to the Audit Committee |
| Plan completion (reports realised against planned) | Reported monthly; target set by the GM Audit |
| Report cycle time (fieldwork end to final report) | Measured from go-live; reduced against the baseline |
| Action close-out rate and recurring findings | Measured and reported quarterly |
| Users trained before access | 100% |
| Availability during working hours | 99% |
| Audit trail completeness and backup restore tests | 100% of quarterly tests successful |

# 12. Recommendation

GIAW converts the GPHA Internal Audit procedures (IMS_PS_004_AU03), the review chain, the six streams and the finding and working paper standards into one controlled, secure and GPHA-hosted system. It is built, tested and documented. The remaining work is mainly organisational: decisions, a server, a pilot, data loading and training.

It is recommended that Management **approve GIAW and this plan**, nominate the project roles and authorise Stages 4 to 9, with go-live at Headquarters targeted for January 2027 and at Tema and Takoradi in February 2027.

# 13. Approval

| Role | Name | Decision (Approved / Approved with conditions / Not approved) | Signature | Date |
|---------------------------------------------|-----------|---------------------------------------------|-----------|-----------|
| Prepared by: GIAW project team / system owner | | | | |
| Reviewed by: Principal Internal Auditor | | | | |
| Reviewed by: Head of IT | | | | |
| Approved by: General Manager, Internal Audit (CAE) | | | | |
| Endorsed by: Director-General / Corporate Management | | | | |
| Noted by: Audit Committee (Chair) | | | | |

**Conditions or comments:**

&nbsp;

&nbsp;

&nbsp;
