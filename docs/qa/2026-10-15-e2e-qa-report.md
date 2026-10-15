# GIAW end-to-end QA and control assessment — 15 October 2026

> **Read this first.** This is a software quality and control-feature assessment. It is **not** a statement of conformance
> with the IIA Global Internal Audit Standards, Ghana law, IAA manuals or GPHA procedures. The full texts of those sources
> were not retrieved for this run, and no approved GPHA audit procedures exist in the repository. Every item tied to them
> is marked **Unresolved policy question**. `giaw.md` and `AGENTS.md` are **not in the repository**.

## 1. Executive summary

| Item | Value |
|---|---|
| Technical recommendation | **NO-GO for production; fit to continue UAT.** No Critical or High defect is open. Production needs the GPHA decisions in section 9, an optimistic-locking fix (QA-02) and a run on the target MySQL 8.4 / Windows environment. |
| Build tested | `0b1af98` (device repository C:\dev\GPHAIAWORKSPACE), plus the fixes listed in section 7, which were retested |
| Test window | 2026-10-15 19:18 to 19:45 UTC |
| Environment | Isolated cloud sandbox. Python 3.13.16, FastAPI 0.143.0, SQLAlchemy 2.1.4, Pydantic 2.14.1. **MariaDB 10.11.14**, not the MySQL 8.4 production target. Chromium (Playwright). Synthetic data only. |
| Confidence | High for the API, roles and app connections exercised. Medium for the UI (automated checks plus targeted screenshots; no manual screen-reader pass). Low for performance (small dataset) and operations (not executed). |

**What works.**
- 150 backend and 9 UI automated tests pass.
- The 75-check scripted end-to-end run has 72 passes, 1 failure (QA-02, open) and 2 information-only results.
- No JavaScript or server errors appeared on 38 screens at desktop width, and none on the auditee screens at phone width.
- Role denials, object-level access, the CSRF check, account lockout, the per-IP sign-in throttle and session revocation on deactivation all behave.
- The cross-app chains work: Audit → Issue Tracker → Task Tracker → Requests → Remediation, and Risk Manager ↔ Asset Inventory ↔ links.

**What was wrong.**
- **Fixed and retested:**
  - an evidence request returned **500 after saving** when given a time-zone date (duplicate risk);
  - the AI endpoint setting accepted `file://`;
  - the API map was public in production;
  - API responses could be cached;
  - 4 groups of accessibility failures.
- **Open:**
  - two editors on one record silently overwrite each other (QA-02);
  - Audit Committee member accounts cannot be created (QA-03);
  - minor phone-width issues (QA-08).

**Risk Engine / TPRM.**
- **In place:** a risk and control register and a basic third-party register with due diligence.
- **Not in place:** a scored, questionnaire-driven third-party risk engine like SimpleRisk or Fair TPRM. That includes quantification, tiering, a vendor portal, scoring methods and exceptions. See section 5.

## 2. Scope inventory and documents

| Source | Found | Path / version | Used for |
|---|---|---|---|
| `mainBLUEPRINT.md` | Yes | repository root, modified 2026-10-15 | Modules 1-10, workflows 6.1-6.5, security gates (section 9), test layers (section 10), GPHA decisions (section 13) |
| `UI_REDESIGN_PROMPTS.md` | Yes | repository root, modified 2026-10-15 | UI expectations (design reference only) |
| `giaw.md` | **No** | – | `giaw-fastAPI.md` (repository root) exists. It was treated as a companion technical blueprint, not as a substitute. |
| `AGENTS.md` | **No** | – | – |
| GPHA approved procedures, charter, SOPs, retention schedule | **No** | – | All dependent controls are **Unresolved policy questions** |
| "AMS" | Label only | `tests/test_ams_compliance.py` | The standard or edition is not identified, so no AMS compliance finding is made |

**Inventory (from the running build):**
- 390 API paths and 501 operations;
- 38 sidebar and tab screens;
- 5 job roles plus the Committee tier;
- the apps grouped as in the Workspace Apps page.

The full role × endpoint matrix covers 95 parameterless GET routes × 6 roles. It is saved with the run artefacts and summarised in section 4.

## 3. Source register

| ID | Source | Authority / status | Applicability decision | Retrieved |
|---|---|---|---|---|
| S1 | `mainBLUEPRINT.md` | Project requirement (GPHA project document; approval status not recorded in the file) | Used as the project requirement baseline | 2026-10-15 |
| S2 | IIA Global Internal Audit Standards (2024) | Verified standard text **not retrieved** | Not mapped; Unresolved | – |
| S3 | IAA Act 2003 (Act 658), 2025 RBIA Manual, IAA MDA Manual | **Not retrieved** | Not mapped; Unresolved | – |
| S4 | SimpleRisk installer `simplerisk-setup.sh` (GitHub, simplerisk/setup-scripts, main) | Vendor script, read only, **not executed** | Benchmark for risk-engine features (**Recommendation**) | 2026-10-15 |
| S5 | SimpleRisk risk scoring methodologies and Risk Management pages | Vendor documentation | Benchmark (**Recommendation**) | 2026-10-15 |
| S6 | fairtprm.com (Fair TPRM 2.6.2, open source; not affiliated with the FAIR Institute) | Vendor web page | Benchmark (**Recommendation**) | 2026-10-15 |
| S7 | WCAG 2.2 AA (via axe-core 4.10.2 rules) | Recommendation / acceptance target only | No GPHA or legal source establishes it | 2026-10-15 |

## 4. Test strategy, commands and results

**Safeguards.**
- Disposable dev database plus the suite's own `gpha_workspace_test` database.
- Synthetic users and records tagged `QA<hhmmss>`, with e-mails at `giaw-qa.com`.
- No real e-mail, integrations, production data or deployment.
- Temporary scripts live outside the repository: `e2e.py`, `uiwalk.py`, `axe1.py`.
- No tests were added to the repository.

| Category | Command / tool | Result |
|---|---|---|
| Lint | `uv run ruff check .` | Pass |
| Backend suite (150 tests) | `uv run pytest -q -p no:warnings --ignore=tests/ui` | Pass (before and after fixes; about 4 min) |
| UI suite (9) | `GPHA_UI_BROWSER=/opt/pw-browsers/chromium uv run --group ui pytest tests/ui` | Pass |
| SAST | `bandit -r app scripts` | 0 High. 2 Medium: one false positive (`requests` is a dict), one real (QA-04, fixed). 7 Low. |
| Dependencies | `pip-audit` on the exported lock (108 packages) | No known vulnerabilities |
| Secrets | `git grep` patterns, tracked `.env`, history | None found; `.env`, `/backups/` and `/uploads/` are ignored |
| Scripted E2E (75 checks) | `e2e.py` against a local uvicorn | 72 pass, 1 fail (QA-02), 2 info |
| Account lockout | 8 wrong passwords on a synthetic user | Locked (423) after 5; correct password refused while locked |
| Sign-in throttle | 13 attempts from one IP, default settings | 429 from the 11th attempt |
| UI walk + axe | `uiwalk.py` as admin at 1440 and 390, auditee at 1440 and 390, committee at 1440 | Before fixes: 41 axe nodes at desktop. After: **0 on all 38 desktop screens**. 3 Low nodes remain at 390 (QA-08). No JS errors, no 5xx, no blank screens. |
| Keyboard | Tab through the shell | Focus ring visible on every stop; all controls named |
| Performance (indicative) | 20 sequential GETs on 10 list endpoints, small dataset | p95 11-36 ms. **Provisional only**: no approved SLO, no load test. |
| **Not executed** | Load test, backup/restore drill, migration downgrade, deployment and rollback, MFA end-to-end with a real authenticator, manual screen reader, MySQL 8.4 | Blocked: these need the target environment or owner approval |

**Role results.**

| Role | Denied (expected) | Allowed | Data scoping |
|---|---|---|---|
| Audit Client | Users, Roles, Configuration, Activity logs, Backups, Risk Manager, Asset Inventory, Robots, Governance | 25 of 95 GET routes | Audits, actions, requests, stakeholders and tasks return **0** rows until assigned. After assignment, only that audit and the published issue are visible. |
| Committee | Same as Audit Client | Same as Audit Client | **QA-03** |
| Auditor / Manager | Users, Configuration, Activity logs, Backups | Audit work | – |
| Admin (not Super) | – | Administration | Cannot grant Super Administrator |

## 5. Risk Engine and third-party risk (TPRM) check

**Question:** is a third-party risk and control management engine (Risk Engine) in place? The benchmarks were SimpleRisk (S4, S5) and Fair TPRM (S6). **Neither is a GIAW requirement.** No project document asks for TPRM; it is a **Recommendation** pending a GPHA decision.

| Capability | SimpleRisk | Fair TPRM | GIAW (evidence) | Status |
|---|---|---|---|---|
| Risk register with owners, status, categories | Yes | Yes | Risk Manager. Categories configurable (`app/domains/grc/risk`, `erm_risk_categories`). | **Present** |
| Inherent / residual / target scoring | Classic L×I and others | L×I | 5×5 L×I with inherent, residual and target. Bands use configurable thresholds (`grc/common.py band`). | **Present** (one method only) |
| Other scoring methods (CVSS, DREAD, OWASP, custom, contributing) | Yes | – | None | **Missing** |
| Quantified loss in money (FAIR: ALE, insurance coverage) | – | Yes | None | **Missing** |
| Risk appetite, treatment (mitigate, accept, transfer, avoid) | Yes | – | Configurable lists, recorded per risk | **Partial**: appetite is a label and is not compared with the score |
| Mitigation plan with dates and effort | Yes | Remediation tasks | Free-text treatment plan; audit actions in Remediation | **Partial** |
| Periodic management review with recorded decision | Yes | Annual reviews | Assessment history (scores, control effectiveness, comment); review cycle; overdue flag; owner's Task Tracker priority | **Present** |
| Risk acceptance / exceptions with approver and expiry | Yes | – | Treatment "Accept" only; no approval or expiry | **Missing** |
| KRIs with thresholds and readings | – | – | KRIs (amber/red, frequency, readings, owner reminders) | **Present** |
| Controls library and risk ↔ control ↔ requirement links | Governance product | 170+ questions, 9 frameworks | Frameworks library, Compliance Maps, `grc_links` (risk, control, requirement, policy, asset, unit, process); RCM and control tests in audits | **Present** |
| Compliance testing / audits | Compliance product | Audits and findings | Full audit lifecycle, control tests, issues, actions | **Present** |
| Third-party register (contract, dates, criticality, owner) | Assets | Vendor onboarding | Asset Inventory "Third party / Vendor" and "Contractor" types with contract reference and dates, criticality, data classification | **Present** |
| Due-diligence assessments and re-assessment cycle | Questionnaires (Extra) | Yes | Assessment records (rating, outcome, areas, findings); re-assess every N months; owner reminder | **Partial**: free-text, no questionnaire |
| Structured, scored vendor questionnaires; vendor self-service portal | Yes (Extra) | Yes (170+ questions) | None. Third parties have no access. | **Missing** |
| Vendor tiering from criticality and data access | – | Tier-based rescoring | Criticality is set by hand; no tier rules | **Missing** |
| Gaps feed the risk register automatically | – | Yes | Manual link only | **Missing** |
| Continuous external scanning (Shodan, UpGuard) | – | Optional | None (no network integrations by design) | **Missing** (Module 10 decision) |
| Reporting and audit trail | Yes | Yes | Heat maps, risk summary, Activity logs, record history | **Present** |

**Conclusion.** GIAW has an integrated risk and control register: Risk Manager, KRIs, Frameworks, Compliance Maps, Asset Inventory and links. It also has a **basic** third-party register with due diligence. It does **not** have a dedicated TPRM / Risk Engine with:
- scored questionnaires;
- vendor tiering;
- exception approval with expiry;
- alternative or quantitative (FAIR) scoring;
- a third-party portal.

Installing SimpleRisk or Fair TPRM beside GIAW is not recommended without a GPHA decision:
- both are PHP/Apache stacks, against blueprint section 3's stack decision;
- the SimpleRisk installer runs a full system upgrade, opens firewall ports, adds a once-a-minute cron job and writes database passwords to a file.

If TPRM is required, build it inside GIAW as an extension of Asset Inventory and Risk Manager (section 10, next actions).

## 6. Traceability matrix

| ID | Source class | Source and clause | Requirement / recommendation | Module / screen / API | Risk | Test | Evidence | Result | Gap | Owner / action |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | Project requirement | S1 §4 Module 1 acceptance | Users reach only authorised screens and records | All roles; 95 GET routes | High | Role matrix, IDOR | e2e JSON matrix | Pass | QA-03 | – |
| T2 | Project requirement | S1 §9 | Deny by default; CSRF; output escaping; security headers | `security_headers`, `csrf_protect` | High | Headers, no-CSRF POST | e2e A/G | Pass | – | – |
| T3 | Project requirement | S1 §4 Module 7 | Action owners cannot close findings alone | `/api/capa/{id}` | High | Owner PATCH Closed | 403 | Pass | – | – |
| T4 | Project requirement | S1 §6.3 | Evidence workflow: request → submit → accept; approval separate from conclusion | `/api/evidence-requests` | High | Full chain, self-acceptance, double acceptance | e2e C | Pass after QA-01 fix | – | – |
| T5 | Project requirement | S1 §4 Module 6 | Files not retrievable by guessing; access logged | evidence files | High | Existing suite (`test_fieldwork_issues`) | pytest | Pass | Malware scan not in scope | GPHA §13.9 |
| T6 | Project requirement | S1 §9 | Privileged changes logged | Activity logs | Medium | Synthetic actions found | e2e G | Pass | – | – |
| T7 | Project requirement | S1 §4 Module 2 | Configurable likelihood/impact scales and approved scoring | Risk Manager, plan config | Medium | Config review | `appconfig.py` | Partial: thresholds configurable, 5×5 fixed | Scale approval | GPHA §13.4 |
| T8 | Recommendation | Master prompt §5 D | Lost-update prevention for concurrent edits | `/api/audits/{id}` PATCH | Medium | Two editors, stale save | e2e D | **Fail** | QA-02 | Dev TBD |
| T9 | Project requirement | S1 §4 Module 1 (roles) | Audit Committee read-only access | Users, Governance | Medium | Create a Committee user | e2e, `/api/auth/me` | **Fail** | QA-03 | GPHA decision |
| T10 | Recommendation | S7 | WCAG 2.2 AA (target) | 38 screens | Low | axe plus keyboard | ui-*.json | Pass at desktop; 3 Low nodes at phone width | QA-08 | Dev TBD |
| T11 | Recommendation | S4-S6 | Third-party risk engine | Asset Inventory, Risk Manager | Medium | Feature mapping, TPRM API chain | section 5 | Partial | QA-11 | GPHA decision |
| T12 | Unresolved policy question | S2, S3 | IIA / IAA / Act 658 mapping | – | – | Not executed | – | Not evidenced | Sources not retrieved | IA function / GPHA |

## 7. Findings, most severe first

No Critical or High findings.

| ID | Severity | Status | Finding | Fix / action | Retest |
|---|---|---|---|---|---|
| QA-01 | Medium | **Fixed** | `POST /api/audits/{id}/evidence-requests` with a time-zone date (`…+00:00`) **saved the request and notified the assignee, then returned 500**: `can't compare offset-naive and offset-aware datetimes` in `evidence/router.py _out`. A client retry would create a duplicate request. Any API caller could hit this; the UI sends plain dates. | `app/core/database.py`: a `before_flush` hook stores every date-time as naive UTC, so the rule applies to all modules. | Pass (e2e run QA193008); backend suite passes |
| QA-02 | Medium | **Open** | No optimistic locking. Two people editing the same audit both get 200 and the second, stale save silently wins (`A=200 B=200`, final title = B). The same pattern is likely on other PATCH and PUT records. | Add a version (or `updated_at`) check: send it with the edit and return 409 with "changed by X". Start with audits, issues, actions and plans. | Retest: stale save returns 409 and both values are kept |
| QA-03 | Medium | **Open / policy** | Audit Committee member accounts cannot be created. `role: "Committee"` is overwritten to Auditee by the job-role model (`TIER_DEFAULT_ROLE`, `apply_role`). Committee users therefore get 403 on `/api/governance/overview` and cannot see the Governance portal. The UI's committee navigation (`isCommittee`, `COMMITTEE_VIEWS`) is unreachable. | GPHA to decide whether committee members get accounts. If yes, add a "Committee member" job role with `governance.view` and read-only portfolio access. | Retest: a committee user reaches Governance and Port portfolio, and nothing else |
| QA-04 | Low | **Fixed** | The AI endpoint setting (Super Administrator) accepted `file://…`, so urllib could read local files. Confirmed in the sandbox. | `app/services/ai/providers.py`: only http and https are allowed. | Pass: `file://` rejected with a clear message |
| QA-05 | Low | **Fixed** | `/docs` and `/openapi.json` (the full map of 390 API paths) were served without sign-in, also in production. | `app/main.py`: disabled when `GPHA_ENVIRONMENT=production`. | Pass (development keeps them) |
| QA-06 | Low | **Fixed** | API responses had no `Cache-Control`, so audit data could be kept by the browser or a proxy. | `app/main.py`: `Cache-Control: no-store` on `/api/*`. | Pass |
| QA-07 | Low | **Fixed** | Accessibility (axe): invalid grid ARIA on both heat maps (critical); progress-bar labels and Draft / Not started badges and warning chips below 4.5:1 contrast; 5 selects without names. | `insight.js`, `grc.js`, `compliance.js`, `app.js`, `styles.css`. | Pass: 0 axe violations on 38 desktop screens |
| QA-08 | Low | Open | At 390 px: the Assurance Plans table and the Scheduler timeline scroll without being keyboard-focusable, and Configuration overflows horizontally by a few pixels. | Make the scroll wrappers focusable (`tabindex=0` plus a label) and tighten the Configuration cards on small screens. | axe at 390 px reports 0 |
| QA-09 | Info | – | A `next_review_date` sent when creating a risk is ignored; the date always comes from `erm_review_months`. | Confirm this is intended, or allow an earlier date. | – |
| QA-10 | Info | – | `/api/organizations/entities` (20 names of ports and departments) is readable by every signed-in user, including auditees. It is used for dropdowns. | Confirm the classification is acceptable (GPHA §13.7). | – |
| QA-11 | Info / policy | – | The TPRM engine is partial (section 5). | GPHA decision. | – |
| QA-12 | Info | – | The test database was MariaDB 10.11, not MySQL 8.4, and the dataset was small. | Repeat on staging with production-like volume. | – |

## 8. Acceptance gates

| # | Gate | Result | Evidence |
|---|---|---|---|
| 1 | Scope and requirements | Pass, with gaps | Sections 2-3; `giaw.md`, `AGENTS.md` and GPHA procedures missing |
| 2 | Functional and data integrity | **Fail** | QA-02 open (lost updates); QA-01 fixed |
| 3 | Access and security | Pass for this build | No open Critical or High; QA-03 is an access gap, not a leak |
| 4 | Auditability and reporting | Not evidenced / blocked | Logs pass; report reconciliation (blueprint §6.5) not exercised here; policies unresolved |
| 5 | Accessibility and usability | Pass at desktop; Low items at phone width | QA-07, QA-08 |
| 6 | Reliability and performance | Not evidenced | No SLO, no load test, no failure injection |
| 7 | Deployment and operations | Not evidenced | Backup/restore, rollback and MySQL 8.4 not executed |
| 8 | Remediation | Pass for Critical/High (none); Medium open with owner TBD | Section 7 |
| 9 | Standards / policy traceability | Not evidenced | S2/S3 not retrieved; nothing claimed |

## 9. Decisions and questions for GPHA and IAA policy owners

1. Should Audit Committee members have their own read-only GIAW accounts (QA-03)? If yes, which screens: Governance portal, Port portfolio, committee pack?
2. Is a third-party risk management capability in scope? If yes:
   - which tiering rule;
   - which questionnaire;
   - should vendors respond in GIAW;
   - is quantified (FAIR) loss needed?
3. When two people edit the same record, which rule applies: block the second save, or merge field by field (QA-02)?
4. Which edition of the 2025 RBIA Manual and its templates applies to GPHA? What is "AMS" (framework and edition)?
5. The open items in blueprint section 13: scales, retention, recovery objectives, identity provider and the other listed decisions.

## 10. Go / no-go rationale and next actions

**NO-GO** for production now. Gates 2, 4, 6, 7 and 9 are not met or not evidenced, and the section 9 decisions are open. There is no Critical or High defect, so **UAT can continue**.

**Next actions, in priority order:**
1. QA-02: optimistic locking on audits, issues, actions and plans.
2. QA-03, after the GPHA decision.
3. Run this suite on a staging copy (Windows, MySQL 8.4), including a backup/restore drill and a migration from the previous release.
4. QA-08 (phone-width scrolling).
5. If GPHA wants TPRM, extend Asset Inventory into a scored third-party module:
   - questionnaire templates;
   - tiering rules;
   - exceptions with approver and expiry;
   - gaps feeding the risk register.
   Optional FAIR-style annualised-loss fields can follow later.
6. Agree provisional performance targets and run a load test.

*Synthetic run IDs: QA192813, QA192907, QA193008. The temporary scripts and JSON results are kept outside the repository.*
