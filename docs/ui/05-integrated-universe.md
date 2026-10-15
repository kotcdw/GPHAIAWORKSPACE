# Integrated audit universe: screen contracts

**Date:** 15 October 2026 · **Source model:** Diligent One (HighBond) Audit app help pages — Integrated audit universe,
Defining audit universe, Navigating a defined audit universe, Settings (assessment factors, scales), Adding /
conducting / concluding audit risk assessment, Include and generate audits in an audit plan, Object library,
Modeling your organizational structure.

## Data flow

```
Org Structure (organizations of the Org Structure types)  ─┐
Process library (processes linked to org units)           ─┴─► Define audit universe ─► auditable entities
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

## 3. Audit universe (Universe, risk & controls > Audit universe)

- Not yet defined: the **Integrated audit universe** card with "View org structure", "Visit Process library" and
  **Let's start**.
- Defined: **Coverage** (percentage of active org units and org-unit processes covered), active and archived counts,
  entities due within 12 months; actions **Audit risk assessment** and **Redefine** (with the archive warning).
- Columns: **Auditable entity** | **Status** | **Org unit** (several: count opening a side sheet) | **Process** |
  **Risk rating** | **Audit frequency** | **Last audited** | **Next due** | **Planned audits**.
  Filters: search, Status (Active default), Risk rating.
- Entities carried over from the earlier universe show "Not mapped" until mapped to an org unit.
- API: `GET /api/audit-universe`.

## 4. Define audit universe

- Left: the org tree with each unit's processes as check boxes and a coverage state per unit (Covered, Partially
  covered, Not covered). Selecting a unit includes everything below it; lower-level boxes are then locked.
- Right: the auditable entities, each with an editable name; **Merge** (entities in the same branch or level; a merged
  group can't be merged again) and **Split**.
- Top: live coverage meter. **Define** saves.
- Redefining keeps entities whose selection is unchanged (with their history) and archives the others; archived
  entities stay on the plans, assessments and audits that used them. (HighBond archives all previous entities; keeping
  unchanged ones is deliberate so history is not split.)
- API: `GET /api/audit-universe/candidates`, `POST /api/audit-universe/coverage`, `POST /api/audit-universe/define`.

## 5. Auditable entity page

- Tabs: **Details** (name, audit frequency — every 1 to 5 years or the default for its rating from the plan audit
  cycle settings — status, risk rating and overall score, last assessed, last audited, next due, defined, archived),
  with **Taxonomy** (org units with their path, processes, entity category); **Audit risk assessments** (overall score,
  rating, priority per assessment); **Audits** (audits and planned engagements); **Findings and actions** (summary and
  list with remediation state). Action: Archive / Reactivate. Unmapped entities: **Map to org unit**.
- API: `GET/PATCH /api/auditable-entities/{id}` and `/assessments`, `/audits`, `/findings`.

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
