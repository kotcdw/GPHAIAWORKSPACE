---
title: "GIAW — Documentation Index"
subtitle: "The complete documentation set for the GPHA Internal Audit Workspace"
author: "GPHA Internal Audit Department"
date: "Version 1.0 · 16 October 2026"
---

# 1. Purpose

This index lists every document needed to build, run, govern, use and train people on the GPHA Internal Audit Workspace (GIAW). It shows the purpose, audience, format and status of each, plus the further documents GPHA still has to produce or approve.

# 2. The documentation set (delivered)

All documents are in `docs/manuals/` in the project folder. Each one exists as Markdown (`.md`, for version control) and as a Word document (`.docx`, for reading, printing and approval). The training deck is a PowerPoint file.

| No. | Document | Purpose | Main audience | Files | Status |
|-----------|---------------------------------------------|---------------------------------------------|---------------------------------------------|-------------------------------------------|-----------------------|
| 00 | Documentation Index (this document) | Map of the whole set | Everyone | `00-Documentation-Index.md` / `.docx` | Issued |
| 01 | Technical Documentation | Architecture, modules, workflows, data model, security, API, background jobs, engineering practice, known limitations | Developers, IT, security reviewers | `01-Technical-Documentation.md` / `.docx` | Issued |
| 02 | Technology Stack | Components and versions, runtime topology, sizing, environments, what is not used and why, upgrade policy | IT management, infrastructure | `02-Technology-Stack.md` / `.docx` | Issued |
| 03 | Administration Guide | Installation (development and production), `.env` settings, users and roles, reference data, configuration, apps & customization, security operations, backups and restore, monitoring, troubleshooting, scripts | Super Administrators, Administrators, GPHA IT | `03-Administration-Guide.md` / `.docx` | Issued |
| 04 | Governance, Administration & Operations Manual | Ownership and RACI, decision register, change control and release procedure, support model, data governance, routine operations, continuity, UAT and go-live checklist, templates | GM Audit, system owner, IT management | `04-Governance-and-Operations.md` / `.docx` | Draft for GPHA approval |
| 05 | User Manual (illustrated) | Screen-by-screen guide with 55 screenshots: getting started, lists and forms, audit management, resources, risk, compliance, analytics and reporting, auditees, FAQ, quick reference cards | All users | `05-User-Manual.md` / `.docx` | Issued |
| 06 | Training Guide | Learning outcomes, six training tracks, session plan, facilitator preparation, 20 hands-on exercises (reusable as UAT scripts), knowledge check with answers, evaluation and completion forms | Trainers, participants | `06-Training-Guide.md` / `.docx` | Issued |
| 07 | Training deck | Slides for instructor-led training, with screenshots and speaker notes | Trainers | `07-GIAW-Training-Deck.pptx` | Issued |
| – | Images | Screenshots and diagrams used by the documents | – | `images/` | – |

# 3. Existing project documents (already in the repository)

| Document | Location | Purpose |
|----------------------|-------------------------------------|---------------------------------------------|
| Main project blueprint | `mainBLUEPRINT.md` | 10 modules, 20 phases, workflows, security gates, test strategy, GPHA decisions |
| Technical blueprint | `giaw-fastAPI.md` | Detailed engineering specification |
| UI redesign prompts | `UI_REDESIGN_PROMPTS.md` | Interface design guidance |
| README | `README.md` | Developer quick start and feature reference |
| Production setup | `deploy/PRODUCTION.md` | Step-by-step production installation |
| Go-live checklist | `deploy/GO-LIVE-CHECKLIST.md` | Readiness checks |
| UI design notes | `docs/ui/00` to `06` | Inventory, reference matrix, design system, data flow, screen contracts, universe, HighBond comparison |

# 4. Documents GPHA still needs to produce or approve

These cannot be written by the developer alone. They need GPHA owners and decisions.

| Document | Why it is needed | Owner (suggested) | Template / source |
|---------------------------------------------|---------------------------------------------|--------------------------|-----------------------------------------|
| Signed decision register (D1 to D16) | Production defaults must be formally approved | GM Audit | Governance manual §3 |
| Internal Audit Charter and methodology manual (GPHA-approved) | GIAW configuration must follow the approved methodology | GM Audit / Audit Committee | IIA GIAS, IAA RBIA Manual |
| Records-retention and disposal schedule | Retention setting and disposal | Legal / Records | Governance manual §6 |
| Data-protection assessment | Personal data in audit records | Legal | Ghana Data Protection Act, 2012 (Act 843) |
| IT security assessment and sign-off | Required before go-live | IT Security | Technical Documentation §6 |
| Hosting and DR plan with RPO/RTO | Recovery objectives | GPHA IT | Governance manual §8 |
| UAT plan, scripts and sign-off | Acceptance | System owner | Training Guide §4, Governance manual §9 |
| Data migration plan | Loading org structure, universe, plan, open findings | System owner | Administration Guide §5 |
| Service level agreement (support) | Support expectations | Sponsor / IT | Governance manual §5 |
| Release notes (per release) | Record of changes | Developer | Change request form |
| Quick reference cards (printable, per role) | Day-one support | System owner | User Manual §11 |

# 5. Keeping the documentation current

- Update documents 01, 03, 05, 06 and 07 at every release that changes screens or behaviour; 02 at every major release; 04 every year.
- Edit the Markdown file first, then regenerate the Word file (`pandoc`, see §6) so the two never drift apart.
- Refresh the screenshots when screens change (`GPHA_UI_SHOTS` in the browser tests, or the documentation screenshot script).
- Record each new version in the document's *Document control* table.

# 6. How the Word files are produced

From the `docs/manuals` folder:

```
pandoc 05-User-Manual.md -o 05-User-Manual.docx --reference-doc=reference.docx --toc --resource-path=.
```

`reference.docx` holds the GPHA styles: fonts, heading colours and table style.
