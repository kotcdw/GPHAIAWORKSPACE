---
title: "GIAW — Governance, Administration and Operations Manual"
subtitle: "Ownership, decisions, change control, support, data governance, go-live and continuity"
author: "GPHA Internal Audit Department"
date: "Version 1.0 · 16 October 2026"
---

# Document control

| Item | Value |
|-----------|---------------------------------------------|
| Document | Governance, Administration and Operations Manual |
| Version | 1.0 (draft for GPHA approval) |
| Audience | GM Audit, system owner, project sponsor, GPHA IT management, Audit Committee secretariat |
| Status | **Draft.** Items marked *GPHA to decide* need formal approval. |

> This manual sets out how GIAW is owned, changed, supported and kept safe. It does not replace GPHA policies. Where a GPHA policy exists, that policy governs and this manual should reference it.

# 1. Purpose and objectives of GIAW

GIAW replaces the retired *Audit Manager* application. It gives GPHA Internal Audit one controlled system for:

- risk-based planning and Audit Committee approval of the annual plan;
- executing and documenting engagements, with review and sign-off evidence;
- issuing reports and following up management actions to verified closure;
- consolidated reporting for HQ, Tema and Takoradi, the Audit Committee and the IAA;
- quality assurance (QAIP) and professional practice records.

# 2. Governance structure and responsibilities

| Role | Who (*GPHA to name*) | Responsibilities |
|------------------------------------|-----------------------------|---------------------------------------------|
| Project sponsor | GM Audit (CAE) | Owns the business case; approves scope, go-live and major changes; chairs the steering meeting |
| System owner | Senior Internal Audit officer | Day-to-day ownership; prioritises changes; approves configuration changes and user access; keeps the decision register |
| Super Administrators (2) | Named IA staff | Roles & permissions, app customization, appointing administrators |
| Administrators | Named IA / IT staff | Users, configuration, reference data, backups, logs |
| GPHA IT (infrastructure) | IT Department | Server, database, network, certificate, patching, off-server backups, monitoring |
| Information security | IT Security | Security review before go-live; vulnerability management; incident handling |
| Legal / data protection | Legal Department | Data-protection and records-retention position |
| Developer / maintainer | Internal or contracted | Changes, fixes, releases, technical documentation |
| Super users (one per port / HQ unit) | Named auditors | First-line help, training support, feedback collection |
| Audit Committee | Committee members | Receives plan, reports and follow-up outputs (via the Committee pack) |

**RACI for key activities** (R = responsible, A = accountable, C = consulted, I = informed)

| Activity | Sponsor | System owner | Super Admin | IT | Developer | Users |
|-------------------------|-----------|------------|-----------|-----------|-----------|-----------|
| Approve scope and go-live | A | R | C | C | C | I |
| Configuration change | I | A | R | – | C | I |
| New user / role change | – | A | R | – | – | I |
| Software release | I | A | C | R (deploy) | R (build) | I |
| Backup and restore test | I | A | C | R | – | – |
| Security incident | I | A | C | R | C | I |
| Training | A | R | C | – | C | R (attend) |

# 3. Decision register

The decisions below come from `mainBLUEPRINT.md` §13 and the QA report of 15 October 2026. The system has working defaults, but each one needs a formal GPHA decision before production.

| # | Decision needed | Current default in GIAW | Decided by | Status |
|-----------|---------------------------------------------|---------------------------------------------|----------------------|-----------|
| D1 | Official HQ / Tema / Takoradi hierarchy and authoritative org data | Configurable entity types; demo data | GM Audit | Open |
| D2 | Roles, delegated approval authority, separation-of-duties rules | 5 job roles; review levels Unit Head, Manager, PIA, CAE | GM Audit | Open |
| D3 | Audit Committee approval recording and plan distribution authority | Committee decision recorded on plan; GM Audit distributes | GM Audit / Committee | Open |
| D4 | Risk scoring scales and thresholds | 5×5 likelihood × impact; High/Medium thresholds configurable | GM Audit | Open |
| D5 | Fiscal year and planning calendar | Configurable | GM Audit / Finance | Open |
| D6 | Engagement types and report templates | Default audit types; Word templates | GM Audit | Open |
| D7 | Confidentiality classifications and auditee access model | Public / Internal / Confidential / Restricted; auditees see only assigned audits and published issues | GM Audit / Legal | Open |
| D8 | Retention, legal hold and disposal schedule | Closed audit files kept N years (configurable) | Legal / Records | Open |
| D9 | Hosting, identity provider, e-mail relay, storage, recovery objectives (RPO/RTO) | Windows server; local accounts or AD; SMTP optional | IT / GM Audit | Open |
| D10 | Migration sources and data quality rules | None loaded | System owner | Open |
| D11 | Integrations and AI use cases / data boundaries | AI off; no integrations | GM Audit / IT Security | Open |
| D12 | UAT sign-off owners and production support contacts | – | Sponsor | Open |
| D13 | Should Audit Committee members have read-only accounts? (QA-03) | Not possible today | GM Audit | Open |
| D14 | Rule for two people editing the same record (QA-02) | Last save wins | System owner | Open |
| D15 | Is third-party risk management (TPRM) in scope? | Basic third-party register only | GM Audit | Open |
| D16 | Sign-off levels, password on sign-off, dropped screens (blueprint decision 21) | Five levels; password optional | GM Audit | Open |

Record every decision with the date, decision-maker, reference (memo or minutes) and the configuration change it causes.

# 4. Change control

## 4.1 Types of change

| Type | Examples | Approval | Path |
|---------------------|---------------------------------------------|---------------------------------------------|---------------------------------------------|
| Configuration | A business rule, list value, KPI target, holiday | System owner | Done on screen by an administrator; logged automatically |
| Access | New user, role change, leaver | System owner (or line manager for auditees) | Users screen |
| Minor software change | Label, small fix, report wording | System owner | Developer → test → staging → release |
| Major software change | New module, workflow change, data model change | Sponsor (steering) | Change request → impact assessment → build → test → UAT → release |
| Emergency fix | Security issue, data-loss bug | System owner (with retrospective sponsor approval) | Hot-fix release; record afterwards |

## 4.2 Change request form (template)

| Field | Entry |
|--------------------------------------------|------------------------------|
| Reference | CR-YYYY-NNN |
| Requested by / date | |
| Description of the change | |
| Reason / benefit | |
| Affected apps, roles and data | |
| Risk if not done | |
| Impact (data, security, training, documents) | |
| Priority | Critical / High / Medium / Low |
| Approved by / date | |
| Released in version / date | |

## 4.3 Release procedure

1. Every change is made in source control on a branch and reviewed.
2. Automated checks must pass:
   - `uv run pytest -q --ignore=tests/ui` (150 tests);
   - the browser tests;
   - `ruff`;
   - `pip-audit`.
3. Deploy to **staging**. The system owner or a super user confirms the change.
4. Agree a release window and announce it to users.
5. Back up production, deploy (Administration Guide §2.3), then smoke-test:
   - sign in;
   - open Audits and Task Tracker;
   - check `/health`.
6. Update the release notes, the documentation and the decision register.
7. **Rollback:** restore the previous code version (`git checkout <previous tag>`, `uv sync --frozen`) and, if a migration ran, the pre-release backup.

# 5. Support model

| Level | Who | Handles | Target response (*provisional, GPHA to agree*) |
|--------------|--------------------------------|---------------------------------------------|---------------------------------------------|
| L1 | Super users and the system owner | How-to questions, forgotten password, account unlock, access requests | Same working day |
| L2 | Administrators | Configuration, data corrections through the screens, report questions | 1 working day |
| L3 | Developer / maintainer | Defects, errors, performance, releases | Critical: 4 h; High: 1 working day; others: next release |
| Infrastructure | GPHA IT | Server down, database, network, certificate, backups | Per GPHA IT service levels |

**Severity definitions (for incidents)**

| Severity | Definition | Example |
|-----------|---------------------------------------------|-----------------------------|
| Critical | System unavailable for all users, data loss, or a security breach | Server down; data exposed |
| High | A key workflow blocked for many users with no workaround | Cannot issue reports |
| Medium | A function impaired, workaround exists | Export fails for one register |
| Low | Cosmetic or minor | Label wording |

**Reporting a problem:** users send the screen name, what they did, what they expected, what happened, the time, and a screenshot (with no confidential content) to the support contact named by GPHA.

# 6. Data governance

| Area | Rule in GIAW | GPHA action |
|--------------|---------------------------------------------|---------------------------------------------|
| Classification | Classification printed on every Word document footer (configurable); assets carry a data classification | Confirm the scheme (D7) |
| Access | Least privilege by job role; auditees see only assigned audits and published issues; port scoping | Quarterly access review (§7) |
| Personal data | Names, e-mails and job roles of staff and auditees; audit evidence may contain personal data | Legal to confirm the position under Ghana's Data Protection Act, 2012 (Act 843) |
| Retention | "Keep closed audit files for (years)" setting; records are never hard-deleted once progressed | Approve the schedule (D8) and the disposal procedure |
| Integrity | Append-only audit trail; e-signatures; SHA-256 file hashes; versions frozen on issue | – |
| Encryption | Files and backups encrypted at rest; HTTPS in transit | Protect `GPHA_ENCRYPTION_KEY` |
| AI | Off by default; if enabled, personal data is redacted and requests are logged | Approve use cases (D11) |
| Exports | Excel, CSV and Word exports follow the user's access | Users handle exports under GPHA information-handling rules |

# 7. Routine operations calendar

| Frequency | Task | Owner |
|-----------|---------------------------------------------|------------|
| Daily | Check that the newest backup exists; copy backups and uploads off-server | IT |
| Weekly | Review the notifications backlog and overdue actions report | System owner |
| Monthly | Apply Windows and MySQL patches (after staging); review Activity logs for unusual activity | IT / Admin |
| Quarterly | Access review (export users, confirm with managers, deactivate leavers); `verify_backup` restore test; dependency check (`pip-audit`) | Admin / IT |
| Annually | Review configuration against approved methodology; review this manual; disaster-recovery exercise; refresher training | System owner |

# 8. Business continuity and disaster recovery

| Scenario | Response |
|-----------------------|---------------------------------------------|
| Application crash | NSSM restarts the service automatically; check the logs |
| Database unavailable | Users see a red banner and nothing is saved; the app recovers and migrates automatically when the database returns |
| Server lost | Build a new server (Administration Guide §2.2); restore the newest encrypted backup and `uploads\`; restore `.env` and the encryption key from secure storage |
| Ransomware / compromise | Isolate the server; follow GPHA incident procedure; restore from an off-server backup taken before the incident; rotate secrets |
| Key staff unavailable | At least two Super Administrators; documented procedures (this pack) |

Recovery objectives (RPO and RTO) are **GPHA to decide** (D9). With daily backups the default RPO is up to 24 hours.

# 9. User acceptance testing (UAT) and go-live

## 9.1 UAT approach

- Run one real engagement end to end in a pilot (recommended: one HQ or Tema audit), with 3 to 5 auditors and one auditee unit.
- Use the scenarios in the Training Guide (06) as test scripts.
- Log every issue with its severity. Critical and High issues must be fixed before go-live.

## 9.2 UAT sign-off form (template)

| Field | Entry |
|-------------------------------------|----------------------------------|
| Scope tested (apps, roles, scenarios) | |
| Test period | |
| Open issues (number by severity) | Critical: · High: · Medium: · Low: |
| Accepted with conditions? | Yes / No: conditions: |
| Signed (system owner) / date | |
| Signed (GM Audit) / date | |

## 9.3 Go-live checklist

| # | Item | Done |
|-----------|---------------------------------------------|-----------|
| 1 | Decisions D1 to D16 recorded | ☐ |
| 2 | Production server built; HTTPS working; readiness check OK | ☐ |
| 3 | Backup restore proven (`verify_backup` output filed) | ☐ |
| 4 | Encryption key and `.env` stored securely, separately from backups | ☐ |
| 5 | At least two Super Administrators; bootstrap password cleared | ☐ |
| 6 | Reference data loaded (org structure, processes, universe, current plan, open findings) | ☐ |
| 7 | Users created with correct job roles and workplaces | ☐ |
| 8 | Configuration reviewed and approved by the GM Audit | ☐ |
| 9 | Training delivered to every role; quick guides issued | ☐ |
| 10 | Support contacts announced | ☐ |
| 11 | Two-step verification enforced for the agreed roles | ☐ |
| 12 | IT security review completed | ☐ |
| 13 | UAT signed off | ☐ |

# 10. Documentation set

| No. | Document | Format | Audience | Owner | Review |
|-----------|---------------------------------------------|-----------|------------------------|------------|------------------|
| 00 | Documentation Index | .md / .docx | All | System owner | Each release |
| 01 | Technical Documentation | .md / .docx | Developers, IT, security | Developer | Each release |
| 02 | Technology Stack | .md / .docx | IT management | Developer | Each major release |
| 03 | Administration Guide | .md / .docx | Administrators, IT | System owner | Each release |
| 04 | Governance, Administration & Operations Manual (this document) | .md / .docx | Sponsor, owner, IT | System owner | Annually |
| 05 | User Manual (illustrated) | .md / .docx | All users | System owner | Each release |
| 06 | Training Guide | .md / .docx | Trainers, participants | System owner | Each release |
| 07 | Training deck | .pptx | Trainers | System owner | Each release |
| – | QA and test reports | .md | Owner, IT | Developer | Each test cycle |
| – | `mainBLUEPRINT.md`, `giaw-fastAPI.md` | .md | Project | Sponsor | On change |
