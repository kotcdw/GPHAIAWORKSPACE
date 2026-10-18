# Integrated audit universe: screen contracts

**Date:** 15 October 2026 · **Source model:** Diligent One (HighBond) Audit app help pages — Integrated audit universe,
Defining audit universe, Navigating a defined audit universe, Settings (assessment factors, scales), Adding /
conducting / concluding audit risk assessment, Include and generate audits in an audit plan, Object library,
Modeling your organizational structure.

## Data flow

```
Org Structure (organizations of the Org Structure types)  ─┐
Process library (processes linked to org units)           ─┴─► review units and processes ─► auditable entities
auditable entities + assessment factors + rating scale ─► Audit risk assessment (scores, overall = average)
   ─► Conclude (prioritised entities, notes, conclusion) ─► Mark as completed (rates the entities)
   ─► Start planning (add or link a draft Assurance Plan; one engagement per prioritised entity)
   ─► audits (port taken from the entity's org unit) ─► findings and actions shown on the entity page
```

## 1. Org Structure (Universe, risk & controls > Org Structure)

- Header actions: **Bulk add** (Excel template: Name, Type, Parent, Address) and **Create organizational unit**.
- Tree table: **Organizational unit** (indented, expand / collapse) | **Reference** | **Type** | **Processes** |
  **Auditable entities** | Add unit · Edit. Filters: search, Type.
- Only organizations whose type is listed under Configuration > Organizations > "Entity types that make up the Org
  Structure" (default Port, Head Office, Department, Unit, Section) appear; vendors and regulators stay out.
- API: `GET /api/org-structure`, `POST/PATCH /api/organizations`, `POST /api/import/orgunits`.

## 2. Process library (Universe, risk & controls > Process library)

- Header actions: **Bulk add** (Process, Description, Parent process, Owner email, Org units separated by ;) and
  **Add process**.
- Columns: **Reference** | **Process** | **Parent process** | **Org units** | **Owner** | **Auditable entities** |
  **Status** | Edit. Filters: search, Status (Active default).
- API: `GET/POST /api/processes`, `PATCH /api/processes/{id}`, `POST /api/import/processes`.

## 3. Audit universe (Audit management > Audit universe)

One page with four tabs; source records stay in the Org Structure and the Process library (nothing is copied).

- **Overview**: setup flow (review units > review processes > define entities > assess risk), counts (org units,
  processes, defined entities, needs review) and coverage (units included, processes mapped, entities ready).
  API: `GET /api/audit-universe/overview`.
- **Units**: Org Structure units with filters (type, parent, location, owner, status, processes), selection,
  **Include selected** and **Not included…** (reason required). Status: Included (in an entity or reviewed in),
  Not included, Needs review. Side panel: details, processes, risks and controls, entities, audits and findings,
  link to the Org Structure. API: `GET /api/audit-universe/units`, `GET /api/audit-universe/units/{id}`,
  `POST /api/audit-universe/units/review`.
- **Processes**: processes with the units that perform them, owner, linked risks and mapping status (Mapped /
  Unmapped); **Map to units** and **New entity** for selected processes; units with no processes listed below.
  Mapping writes the Process library itself. API: `GET /api/audit-universe/processes`,
  `POST /api/audit-universe/processes/map`.
- **Entities**: register (name, type, org units, processes, business owner, linked risks, last audit, status) with
  filters, export and **New entity**. API: `GET /api/audit-universe/entities`.

## 4. New / edit auditable entity

- Fields: name, type (Configuration > Audit methodology > Auditable entity types), status, organizational units,
  processes (a process with no unit chosen takes the units that perform it), business owner, effective dates, scope
  statement, objectives, rationale, risks and controls. A live panel shows the relationships before saving.
- Status is about the definition, never risk: **Draft**, **Needs review**, **Ready** (business owner and scope
  required; only Ready entities join an audit risk assessment), **Retired** (= archived; kept on the plans,
  assessments and audits that used it).
- A possible duplicate (same units and processes as an active entity) asks before saving; names must be unique among
  active entities. Leaving with unsaved changes asks first.
- An entity used by an audit, assessment or plan cannot be deleted, only retired.
- API: `GET /api/audit-universe/entity-options`, `POST /api/auditable-entities`,
  `PATCH /api/auditable-entities/{id}`, `DELETE /api/auditable-entities/{id}`.

## 5. Auditable entity page

- Tabs: **Overview** (definition, relationships, scope and objectives, risks and controls), **Risk assessment**
  (Start / Open risk assessment; a rating appears only once an assessment is completed), **Audits**, **Findings**,
  **History** (who changed what, with before and after values).
- API: `GET /api/auditable-entities/{id}` and `/assessments`, `/audits`, `/findings`, `/history`.

## 6. Audit risk assessment (Assurance planning > Audit risk assessment)

- **Assessments** tab columns: **Assessment** | **Status** (Draft, In progress, Completed) | **Rating scale** |
  **Auditable entities** | **Assessment factors** | **Scoring** (progress) | **Created on** | **Completed** |
  **Audit plan**.
- **Add audit risk assessment**: four steps — **Name** (unique) > **Auditable entities** (include toggles, all
  excluded at first) > **Assessment factors** (include toggles) > **Rating scale** (default from Settings) > Finish
  (status Draft).
- **Settings** tab: **Assessment factors** (search by ID or name, add, edit — applies everywhere — delete; a factor
  used in a completed assessment is retired instead) and **Scales** (Low- to High-risk: Low, Medium, High; Very low-
  to Very high-risk: five levels; the default is a Configuration rule).
- Assessment page tabs:
  - **Scoring**: the scoring matrix, entity rows × factor drop-downs, **Overall score** (average of factor scores)
    and **Risk rating** on the scale; saves at once; first score moves Draft to In progress; **Configure** (entities,
    factors, name; earlier scores kept).
  - **Conclude** (needs every cell scored): entities ranked by overall score with a **Select** toggle; the
    **Prioritized auditable entities for audit** list (drag or arrows to re-rank, one note per entity, Remove, Remove
    all); **Conclusion** (autosaved); **Mark as completed** (permanent record; rates the entities); **Revert to in
    progress** until the assessment feeds a plan; **Export PDF** (print).
  - **Start planning**: **Add audit plan** (year) or **Link to existing audit plan** (draft); **Generate and include**
    adds one engagement per prioritised entity not already in the plan, named after the entity, with the default
    budget hours, its port as responsible site, quarters spread by priority and the note in the rationale.
- API: `/api/assessment-factors`, `/api/audit-risk-assessments` (+ `/scores`, `/priorities`, `/notes/{entity}`,
  `/conclusion`, `/complete`, `/revert`, `/start-planning`).

## 7. Effects elsewhere

- The plan's "high-risk units not planned" and the coverage grid use each entity's latest completed assessment rating
  (Very high / High = High, Very low / Low = Low), falling back to likelihood × impact for entities never assessed.
- Starting an engagement takes the audit's port from the entity's org unit when the engagement names no site.
- The entity category on the plan coverage grid is the port or office the entity's org unit sits in.

## 8. Data (migration 0030_integrated_universe)

New tables `processes`, `process_org_units`, `entity_org_units`, `entity_processes`, `assessment_factors`,
`audit_risk_assessments`, `ara_entities`, `ara_factors`, `ara_scores`; new `entity_units` columns `org_unit_id`,
`audit_frequency_months`, `archived_at`, `defined_at`, `assessed_score`, `assessed_rating`, `assessed_at`,
`assessment_id`. Existing units are mapped to the org unit whose name matches their location where one exists; six
starter assessment factors are added (administrators rename or delete them).

## 9. Not included

Diligent platform services (Robots analytics scripts, the AI assistant in the Add workflow) are not reproduced.

## 10. Connections (migration 0031_connected_universe)

| From | To | How |
|---|---|---|
| Process / auditable entity | Enterprise risks (Risk Manager) and standard controls (Frameworks & controls) | Object library links: Process library > **Risks & controls**; entity page > **Risks and controls** > Edit entity links. An org-unit entity covers the processes performed in its unit and below. |
| Auditable entities | Audit | Fieldwork tab > **Auditable entities** strip > **Choose entities** (several per audit; the first is the primary entity from the plan). Issues inherit them; the entity page, the Issue Tracker "Entity" filter and audit close (last audited date) follow them. |
| Entity's risks and controls | Audit fieldwork | **Scope from entities** (detailed scoping): one objective per process (or per entity); risks linked to their enterprise risk; Internal Control: controls copied from the library, mapped to the risks, with their test steps as the test plan; Workplan: a procedure per control (or per risk when none). Preview first; repeatable without duplicates. |
| Audit risk | Enterprise risk | Risk form: "Tests enterprise risk (Risk Manager)"; shown under the risk in the matrix. |
| Audit records | Risk assessment | Automatic factors: **Time since last audit** (months since the last audit against the entity's audit frequency; never audited = highest) and **Prior audit results** (open High finding or overdue action = highest, open Medium = upper middle, open Low = lower middle, none = lowest), mapped onto the assessment's scale. Filled when the assessment is added; **Refresh automatic scores** recomputes; the auditor can still change any cell. |
