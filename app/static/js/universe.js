// GPHA Audit Workspace - integrated audit universe (Diligent One / HighBond Audit model).
//
//   Org Structure            the internal org tree (ports, offices, departments, units), bulk add
//   Process library          business processes and the org units that perform them, bulk add
//   Audit universe           coverage + auditable entities; Define / Redefine audit universe
//   Auditable entity page    Details | Audit risk assessments | Audits | Findings and actions
//   Audit risk assessment    assessments list, Add (Name > Auditable entities > Assessment factors > Rating scale),
//                            scoring matrix, Conclude (prioritise, notes, conclusion), Mark as completed,
//                            Start planning; Settings (assessment factors, scale)
// Loaded after fieldwork.js and before app.js.

const UNIVERSE_EDIT = () => hasPerm("method.library", "system.reference");
const PLANNING_EDIT = () => hasPerm("plan.prepare", "plan.amend", "method.library");

function coverageMeter(cov, label = "Coverage") {
  return el("div", { class: "cov-meter" },
    el("div", { class: "cov-meter-head" }, el("span", { class: "l" }, label), el("strong", null, `${cov.percent}%`)),
    progressBar(cov.percent, cov.percent >= 80 ? "" : "warn"),
    el("div", { class: "muted small" }, `${cov.org_units_covered} of ${cov.org_units} org units · ${cov.processes_covered} of ${cov.processes} processes`));
}

function covBadge(stateText) {
  const tone = { Covered: "ok", "Partially covered": "warn", "Not covered": "bad" }[stateText] || "";
  return el("span", { class: `cov-state ${tone}` }, stateText);
}

function ratingBadge(r) {
  if (!r) return el("span", { class: "muted" }, "Not assessed");
  const tone = { "Very high": "risk-high", High: "risk-high", Medium: "risk-medium", Low: "risk-low", "Very low": "risk-low" }[r] || "";
  return el("span", { class: `badge badge-${tone}` }, r);
}

// ==================================================================== Org Structure

async function renderOrgStructure() {
  clear(viewRoot);
  const can = UNIVERSE_EDIT();
  viewRoot.append(viewHeader("Org Structure", el("div", { class: "actions" },
    can ? btn("Bulk add", () => importDialog({ title: "Bulk add organizational units", templateKind: "orgunits", path: "/api/import/orgunits",
      intro: "Create or update org units in one file. Units are matched on name; Parent can name a unit higher up in the same file.", onDone: () => renderOrgStructure() }), "secondary") : null,
    can ? btn("Create organizational unit", () => orgUnitForm(null)) : null),
  { sub: "The structure of GPHA used to define the audit universe: ports and offices, departments and units" }));
  const body = el("div");
  viewRoot.append(body);
  body.append(loadingState());
  let data;
  try { data = await API.get("/api/org-structure"); } catch (err) { clear(body); body.append(errorState(err, renderOrgStructure)); return; }
  clear(body);
  if (!data.items.length) {
    body.append(emptyState({ icon: "diagram-3", title: "No organizational units yet", text: `Create the root unit (e.g. Ghana Ports and Harbours Authority), then ports, departments and units. Types used: ${data.types.join(", ")}.`,
      action: can ? btn("Create organizational unit", () => orgUnitForm(null)) : null }));
    return;
  }
  const collapsed = new Set();
  const table = el("div");
  const fb = filterBar({ placeholder: "Search org units…", filters: [{ key: "category", label: "Type", options: data.types }], onChange: () => paint() });
  body.append(el("div", { class: "card" }, fb.root, table));
  const byId = Object.fromEntries(data.items.map((r) => [r.id, r]));
  const hiddenByCollapse = (r) => { let p = r.parent_id; while (p) { if (collapsed.has(p)) return true; p = byId[p] ? byId[p].parent_id : null; } return false; };
  function paint() {
    const v = fb.values();
    const filtering = !!(v.q || v.category);
    const rows = data.items.filter((r) => (!v.category || r.category === v.category)
      && (!v.q || `${r.name} ${r.org_ref}`.toLowerCase().includes(v.q.toLowerCase())) && (filtering || !hiddenByCollapse(r)));
    fb.setCount(`${rows.length} of ${data.items.length}`);
    clear(table);
    table.append(el("div", { class: "table-wrap" }, el("table", { class: "dense tree-table" },
      el("thead", null, el("tr", null, ...["Organizational unit", "Reference", "Type", "Processes", "Auditable entities", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rows.map((r) => el("tr", { class: "no-click" },
        el("td", { class: "col-wide", "data-label": "Organizational unit" },
          el("span", { class: "tree-cell", style: `padding-left:${filtering ? 0 : r.depth * 20}px` },
            r.children && !filtering ? el("button", { class: "tree-toggle", type: "button", "aria-expanded": collapsed.has(r.id) ? "false" : "true",
              "aria-label": `${collapsed.has(r.id) ? "Expand" : "Collapse"} ${r.name}`, onclick: () => { if (collapsed.has(r.id)) collapsed.delete(r.id); else collapsed.add(r.id); paint(); } },
            el("i", { class: `bi bi-chevron-${collapsed.has(r.id) ? "right" : "down"}` })) : el("span", { class: "tree-spacer" }),
            el("span", { class: "cell-title" }, r.name), r.children ? el("span", { class: "muted small" }, ` (${r.children})`) : null)),
        el("td", { class: "ref", "data-label": "Reference" }, r.org_ref),
        el("td", { "data-label": "Type" }, r.category || "-"),
        el("td", { class: "small", "data-label": "Processes" }, r.processes.length ? r.processes.map((p) => p.name).join(", ") : el("span", { class: "muted" }, "-")),
        el("td", { class: "num", "data-label": "Auditable entities" }, r.entities ? String(r.entities) : "-"),
        el("td", null, can ? el("div", { class: "actions" }, btn("Add unit", () => orgUnitForm(null, r), "secondary"), btn("Edit", () => orgUnitForm(r), "secondary")) : null)))))));
  }
  paint();
}

async function orgUnitForm(unit, parent = null) {
  const data = await safeGet("/api/org-structure", { items: [], types: [] });
  const options = data.items.filter((r) => !unit || r.id !== unit.id).map((r) => ({ value: r.id, label: `${"  ".repeat(r.depth)}${r.name}` }));
  openForm({
    title: unit ? `Edit ${unit.name}` : "Create organizational unit", draftable: false, width: 640,
    fields: [
      { name: "name", label: "Name", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "category", label: "Type", type: "select", required: true, options: data.types },
      { name: "parent_id", label: "Parent unit", type: "select", emptyLabel: "- top level -", options },
    ],
    initial: unit ? { name: unit.name, category: unit.category, parent_id: unit.parent_id } : { parent_id: parent ? parent.id : null, category: data.types[2] || data.types[0] },
    submitLabel: unit ? "Save" : "Create",
    onSubmit: (v) => {
      const b = { name: v.name, category: v.category, parent_id: v.parent_id ? Number(v.parent_id) : null };
      return unit ? API.patch(`/api/organizations/${unit.id}`, b) : API.post("/api/organizations", b);
    },
    onDone: () => { toast("Organizational unit saved"); renderOrgStructure(); },
  });
}

// ==================================================================== Process library

async function renderProcessLibrary() {
  clear(viewRoot);
  const can = UNIVERSE_EDIT();
  viewRoot.append(viewHeader("Process library", el("div", { class: "actions" },
    can ? btn("Bulk add", () => importDialog({ title: "Bulk add processes", templateKind: "processes", path: "/api/import/processes",
      intro: "Create or update processes and the org units that perform them (names or references separated by ;).", onDone: () => renderProcessLibrary() }), "secondary") : null,
    can ? btn("Add process", () => processForm(null)) : null),
  { sub: "Business processes and where they are performed. Org units and their processes make up the audit universe." }));
  const body = el("div");
  viewRoot.append(body);
  body.append(loadingState());
  let rows;
  try { rows = await API.get("/api/processes"); } catch (err) { clear(body); body.append(errorState(err, renderProcessLibrary)); return; }
  clear(body);
  if (!rows.length) {
    body.append(emptyState({ icon: "diagram-2", title: "No processes yet", text: "Add the processes GPHA performs (e.g. Revenue collection, Procurement, Payroll) and link them to the org units that perform them.",
      action: can ? btn("Add process", () => processForm(null)) : null }));
    return;
  }
  const box = el("div");
  const fb = filterBar({ placeholder: "Search processes…", filters: [{ key: "status", label: "Status", options: ["Active", "Archived"] }], values: { status: "Active" }, onChange: () => paint() });
  body.append(el("div", { class: "card" }, fb.root, box));
  function paint() {
    const v = fb.values();
    const list = rows.filter((p) => (!v.status || p.status === v.status) && (!v.q || `${p.ref} ${p.name} ${p.description}`.toLowerCase().includes(v.q.toLowerCase())));
    fb.setCount(`${list.length} of ${rows.length}`);
    clear(box);
    box.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Reference", "Process", "Parent process", "Org units", "Owner", "Auditable entities", "Status", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...list.map((p) => el("tr", { class: "no-click" },
        el("td", { class: "ref", "data-label": "Reference" }, p.ref),
        el("td", { class: "col-wide", "data-label": "Process" }, el("div", { class: "cell-title" }, p.name), p.description ? el("div", { class: "muted small" }, clip(p.description, 90)) : null),
        el("td", { "data-label": "Parent process" }, p.parent || "-"),
        el("td", { class: "small", "data-label": "Org units" }, p.org_units.length ? p.org_units.map((o) => o.name).join(", ") : el("span", { class: "muted" }, "Not linked")),
        el("td", { class: "small", "data-label": "Owner" }, p.owner_email || "-"),
        el("td", { class: "num", "data-label": "Auditable entities" }, p.entities ? String(p.entities) : "-"),
        el("td", { "data-label": "Status" }, statusBadge(p.status)),
        el("td", null, can ? btn("Edit", () => processForm(p, rows), "secondary") : null)))))));
  }
  paint();
}

async function processForm(p, all = null) {
  const [tree, procs] = await Promise.all([safeGet("/api/org-structure", { items: [] }), all ? Promise.resolve(all) : safeGet("/api/processes", [])]);
  openForm({
    title: p ? `Edit ${p.ref} ${p.name}` : "Add process", draftable: false, width: 720,
    fields: [
      { name: "name", label: "Process", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "description", label: "Description", type: "textarea", maxLength: 20000, full: true },
      { name: "parent_id", label: "Parent process", type: "select", emptyLabel: "- none -", options: procs.filter((x) => !p || x.id !== p.id).map((x) => ({ value: x.id, label: x.name })) },
      { name: "owner_email", label: "Process owner email", type: "email" },
      { name: "org_ids", label: "Performed in (org units)", type: "checklist", full: true, emptyLabel: "Create the Org Structure first.",
        options: tree.items.map((o) => ({ value: o.id, label: `${"  ".repeat(o.depth)}${o.name}` })) },
      ...(p ? [{ name: "status", label: "Status", type: "select", required: true, options: ["Active", "Archived"] }] : []),
    ],
    initial: p ? { ...p, org_ids: p.org_units.map((o) => o.id) } : { org_ids: [] },
    submitLabel: p ? "Save" : "Add process",
    onSubmit: (v) => {
      const b = { name: v.name, description: v.description || "", parent_id: v.parent_id ? Number(v.parent_id) : null,
        owner_email: v.owner_email || null, org_ids: (v.org_ids || []).map(Number), ...(p ? { status: v.status } : {}) };
      return p ? API.patch(`/api/processes/${p.id}`, b) : API.post("/api/processes", b);
    },
    onDone: () => { toast("Process saved"); renderProcessLibrary(); },
  });
}

// ==================================================================== Audit universe

async function renderUniverse() {
  clear(viewRoot);
  const can = UNIVERSE_EDIT();
  const body = el("div");
  viewRoot.append(body);
  body.append(loadingState());
  let u;
  try { u = await API.get("/api/audit-universe"); } catch (err) { clear(body); body.append(errorState(err, renderUniverse)); return; }
  clear(body);
  const actions = el("div", { class: "actions" },
    btn("Audit risk assessment", () => navigate("riskassess"), "secondary"),
    can && u.defined ? btn("Redefine", async () => {
      const ok = await confirmDialog({ title: "Redefine the audit universe", danger: true, confirmLabel: "Redefine",
        text: "Entities you leave unchanged are kept. Every other active entity is archived: it stays on the plans, assessments and audits that used it but is no longer offered for new ones. Redefine after significant changes to the Org Structure or the Process library." });
      if (ok.ok) renderDefineUniverse();
    }, "secondary") : null,
    can && !u.defined ? btn("Define audit universe", () => renderDefineUniverse()) : null);
  body.append(viewHeader("Audit universe", actions, { sub: "Auditable entities built from the Org Structure and the Process library" }));
  if (!u.entities.length) {
    body.append(el("div", { class: "card intro-card" },
      el("h3", null, "Integrated audit universe"),
      el("p", null, "The audit universe is made of the org units of the Org Structure and the processes linked to them. Check both, then define the auditable entities."),
      el("div", { class: "intro-steps" },
        el("button", { class: "intro-step", type: "button", onclick: () => navigate("orgstructure") }, el("i", { class: "bi bi-diagram-3" }), el("strong", null, "View org structure"), el("span", { class: "muted small" }, "Ports, offices, departments and units")),
        el("button", { class: "intro-step", type: "button", onclick: () => navigate("processes") }, el("i", { class: "bi bi-diagram-2" }), el("strong", null, "Visit Process library"), el("span", { class: "muted small" }, "Processes and the units that perform them"))),
      can ? el("div", { class: "actions" }, btn("Let's start", () => renderDefineUniverse())) : null));
    return;
  }
  const unmapped = u.entities.filter((e) => e.status === "Active" && !e.mapped).length;
  body.append(el("div", { class: "cov-summary" },
    el("div", { class: "cov-box" }, coverageMeter(u.coverage)),
    el("div", { class: "cov-box" }, el("div", { class: "l" }, "Auditable entities"), el("strong", null, String(u.entities.filter((e) => e.status === "Active").length)),
      el("span", { class: "muted small" }, `${u.entities.filter((e) => e.status === "Archived").length} archived`)),
    el("div", { class: "cov-box" }, el("div", { class: "l" }, "Due for audit within 12 months"),
      el("strong", null, String(u.entities.filter((e) => e.next_due && new Date(e.next_due) <= new Date(Date.now() + 365 * 864e5)).length)),
      el("span", { class: "muted small" }, "from audit frequency and last audit"))));
  if (unmapped) body.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-exclamation-triangle" }),
    el("div", null, `${unmapped} entit${unmapped === 1 ? "y comes" : "ies come"} from the earlier universe and ${unmapped === 1 ? "is" : "are"} not mapped to the Org Structure. Open ${unmapped === 1 ? "it" : "each"} and choose its org unit, or redefine the universe.`)));
  const box = el("div");
  const fb = filterBar({ placeholder: "Search auditable entities…", values: { status: "Active" },
    filters: [{ key: "status", label: "Status", options: ["Active", "Archived"] }, { key: "rating", label: "Risk rating", options: ["Very high", "High", "Medium", "Low", "Very low", { value: "none", label: "Not assessed" }] }],
    onChange: () => paint() });
  body.append(el("div", { class: "card" }, fb.root, box));
  function paint() {
    const v = fb.values();
    const list = u.entities.filter((e) => (!v.status || e.status === v.status) && (!v.rating || (v.rating === "none" ? !e.rating : e.rating === v.rating))
      && (!v.q || [e.name, e.code, ...e.org_units.map((o) => o.name), ...e.processes.map((p) => p.name)].join(" ").toLowerCase().includes(v.q.toLowerCase())));
    fb.setCount(`${list.length} of ${u.entities.length}`);
    clear(box);
    if (!list.length) { box.append(emptyState({ icon: "funnel", title: "No entities match", text: "Change or clear the filters." })); return; }
    const many = (items, what) => (items.length === 0 ? el("span", { class: "muted" }, what === "Org unit" ? "Not mapped" : "-")
      : items.length === 1 ? (items[0].path || items[0].name)
        : el("button", { class: "link-btn", type: "button", onclick: () => detailPanel({ title: `${what}s`, width: 420, body: el("ul", { class: "plain-list" }, ...items.map((i) => el("li", null, i.path || i.name))) }) }, `${items.length} ${what.toLowerCase()}s`));
    box.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Auditable entity", "Status", "Org unit", "Process", "Risk rating", "Audit frequency", "Last audited", "Next due", "Planned audits"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...list.map((e) => el("tr", { tabindex: "0", onclick: () => openEntity(e.id), onkeydown: (ev) => { if (ev.key === "Enter") openEntity(e.id); } },
        el("td", { class: "col-wide", "data-label": "Auditable entity" }, el("span", { class: "ref" }, e.code), " ", el("span", { class: "cell-title" }, e.name)),
        el("td", { "data-label": "Status" }, statusBadge(e.status)),
        el("td", { class: "small", "data-label": "Org unit" }, many(e.org_units, "Org unit")),
        el("td", { class: "small", "data-label": "Process" }, many(e.processes, "Process")),
        el("td", { "data-label": "Risk rating" }, ratingBadge(e.rating)),
        el("td", { class: "small", "data-label": "Audit frequency" }, e.frequency, e.frequency_is_default ? el("span", { class: "muted" }, " (default)") : null),
        el("td", { "data-label": "Last audited" }, e.last_audited_at ? fmtDay(e.last_audited_at.slice(0, 10)) : el("span", { class: "muted" }, "Never")),
        el("td", { "data-label": "Next due" }, e.next_due ? el("span", { class: new Date(e.next_due) < new Date() ? "text-danger" : null }, fmtDay(e.next_due)) : "-"),
        el("td", { class: "num", "data-label": "Planned audits" }, e.planned_audits ? String(e.planned_audits) : "-")))))));
  }
  paint();
}

// ---- Define audit universe

async function renderDefineUniverse() {
  clear(viewRoot);
  setCrumbs(recordCrumbs("universe", "Define audit universe"));
  viewRoot.append(loadingState());
  let cand;
  try { cand = await API.get("/api/audit-universe/candidates"); } catch (err) { clear(viewRoot); viewRoot.append(errorState(err, renderDefineUniverse)); return; }
  clear(viewRoot);
  const nodes = cand.nodes;
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const kids = {};
  nodes.forEach((n) => { (kids[n.parent_id || 0] = kids[n.parent_id || 0] || []).push(n.id); });
  const subtree = (id) => { const out = [id]; (kids[id] || []).forEach((k) => out.push(...subtree(k))); return out; };
  const ancestors = (id) => { const out = []; let p = byId[id] ? byId[id].parent_id : null; while (p) { out.push(p); p = byId[p] ? byId[p].parent_id : null; } return out; };
  const keyName = (k) => { const [kind, a, b] = k.split(":"); if (kind === "o") return byId[a].name; const n = byId[a]; return `${n.name} - ${(n.processes.find((p) => String(p.id) === b) || {}).name}`; };
  const keyBranch = (k) => { const [kind, a] = k.split(":"); return kind === "o" ? `o${byId[a].parent_id || 0}` : `p${a}`; };
  // Each entity: { name, keys: [], custom: bool }
  let entities = cand.selection.map((s) => ({ name: s.name, keys: s.keys, custom: true }));
  const selectedKeys = () => new Set(entities.flatMap((e) => e.keys));
  const coveredByAncestor = (k) => {
    const sel = selectedKeys(); const [kind, a] = k.split(":");
    const orgs = kind === "o" ? ancestors(Number(a)) : [Number(a), ...ancestors(Number(a))];
    return orgs.some((o) => sel.has(`o:${o}`));
  };
  let mergePick = new Set();
  const covBox = el("div", { class: "cov-box" });
  const treeBox = el("div", { class: "define-tree", role: "tree", "aria-label": "Org Structure and processes" });
  const listBox = el("div", { class: "define-list" });
  let covTimer = null;
  let covState = {};

  function toggle(k, on) {
    if (on) {
      const [kind, a] = k.split(":");
      if (kind === "o") { // selecting a higher-level entity includes (and replaces) its lower-level selections
        const sub = new Set(subtree(Number(a)));
        entities = entities.map((e) => ({ ...e, keys: e.keys.filter((x) => { const [kk, aa] = x.split(":"); return !sub.has(Number(aa)) || (kk === "o" && Number(aa) === Number(a)); }) })).filter((e) => e.keys.length);
      }
      entities.push({ name: keyName(k), keys: [k], custom: false });
    } else {
      entities = entities.map((e) => ({ ...e, keys: e.keys.filter((x) => x !== k) })).filter((e) => e.keys.length);
    }
    mergePick = new Set();
    paint();
  }

  function paintTree() {
    clear(treeBox);
    const sel = selectedKeys();
    nodes.forEach((n) => {
      const k = `o:${n.id}`;
      const inherited = coveredByAncestor(k);
      const cb = el("input", { type: "checkbox", id: `def-${n.id}`, checked: sel.has(k) || inherited ? "1" : null, disabled: inherited ? "1" : null });
      cb.addEventListener("change", () => toggle(k, cb.checked));
      treeBox.append(el("div", { class: "define-node", role: "treeitem", style: `padding-left:${n.depth * 18}px` },
        el("label", { class: "check", for: `def-${n.id}` }, cb, el("span", { class: "cell-title" }, ` ${n.name}`), el("span", { class: "muted small" }, ` ${n.category || ""}`)),
        covState[n.id] ? covBadge(covState[n.id]) : null));
      n.processes.forEach((p) => {
        const pk = `p:${n.id}:${p.id}`;
        const inh = coveredByAncestor(pk);
        const pcb = el("input", { type: "checkbox", id: `def-${n.id}-${p.id}`, checked: sel.has(pk) || inh ? "1" : null, disabled: inh ? "1" : null });
        pcb.addEventListener("change", () => toggle(pk, pcb.checked));
        treeBox.append(el("div", { class: "define-node proc", role: "treeitem", style: `padding-left:${n.depth * 18 + 26}px` },
          el("label", { class: "check", for: `def-${n.id}-${p.id}` }, pcb, el("i", { class: "bi bi-gear muted", "aria-hidden": "true" }), ` ${p.name}`)));
      });
    });
    if (!nodes.length) treeBox.append(emptyState({ icon: "diagram-3", title: "The Org Structure is empty", text: "Create org units first.", action: btn("Org Structure", () => navigate("orgstructure")) }));
  }

  function paintList() {
    clear(listBox);
    listBox.append(el("div", { class: "card-head" }, el("h3", null, `Auditable entities (${entities.length})`),
      el("div", { class: "actions" },
        btn(`Merge (${mergePick.size})`, () => {
          const picked = entities.filter((_, i) => mergePick.has(i));
          if (picked.length < 2) { toast("Select two or more entities to merge", "error"); return; }
          const branches = new Set(picked.flatMap((e) => e.keys.map(keyBranch)));
          if (branches.size > 1) { toast("Only entities within the same branch or level can be merged", "error"); return; }
          if (picked.some((e) => e.keys.length > 1)) { toast("A merged group can't be merged again", "error"); return; }
          const keys = picked.flatMap((e) => e.keys);
          entities = entities.filter((_, i) => !mergePick.has(i));
          entities.push({ name: picked.map((e) => e.name).join(" / ").slice(0, 255), keys, custom: false });
          mergePick = new Set(); paint();
        }, "secondary"))));
    if (!entities.length) { listBox.append(el("p", { class: "muted small" }, "Select org units or processes on the left. Selecting a higher-level unit includes all its lower-level units.")); return; }
    listBox.append(el("ul", { class: "define-entities" }, ...entities.map((e, i) => {
      const pick = el("input", { type: "checkbox", "aria-label": `Select ${e.name} to merge`, checked: mergePick.has(i) ? "1" : null });
      pick.addEventListener("change", () => { if (pick.checked) mergePick.add(i); else mergePick.delete(i); paintList(); });
      const name = el("input", { type: "text", value: e.name, maxlength: "255", "aria-label": "Entity name" });
      name.addEventListener("input", () => { e.name = name.value; e.custom = true; });
      return el("li", null, pick, el("div", { class: "de-main" }, name,
        el("div", { class: "muted small" }, e.keys.map(keyName).join(" + "))),
      e.keys.length > 1 ? el("button", { class: "link-btn", type: "button", onclick: () => {
        entities.splice(i, 1, ...e.keys.map((k) => ({ name: keyName(k), keys: [k], custom: false }))); mergePick = new Set(); paint();
      } }, "Split") : null);
    })));
  }

  function refreshCoverage() {
    clearTimeout(covTimer);
    covTimer = setTimeout(async () => {
      try {
        const c = await API.post("/api/audit-universe/coverage", { keys: [...selectedKeys()] });
        covState = c.by_org; clear(covBox); covBox.append(coverageMeter(c)); paintTree();
      } catch { /* coverage is informative */ }
    }, 250);
  }

  function paint() { paintTree(); paintList(); refreshCoverage(); }

  const defineBtn = el("button", { class: "btn", type: "button", onclick: async () => {
    if (!entities.length) { toast("Select at least one org unit or process", "error"); return; }
    try {
      const r = await API.post("/api/audit-universe/define", { entities: entities.map((e) => ({ name: e.name.trim() || null, keys: e.keys })) });
      toast(`Audit universe defined: ${r.created} new, ${r.kept} kept, ${r.archived} archived`);
      navigate("universe");
    } catch (err) { toast(err.message, "error"); }
  } }, "Define");
  viewRoot.append(viewHeader("Define audit universe", el("div", { class: "actions" }, btn("Cancel", () => navigate("universe"), "secondary"), defineBtn),
    { back: () => navigate("universe"), sub: "Choose org units, or processes within them. Merge entities in the same branch; rename them as you like." }),
  el("div", { class: "cov-summary" }, covBox),
  el("div", { class: "define-grid" }, el("div", { class: "card" }, el("h3", null, "Org Structure and processes"), treeBox), el("div", { class: "card" }, listBox)));
  paint();
}

// ---- Auditable entity page

async function openEntity(id, tab = "details") {
  setActiveNav("universe");
  clear(viewRoot);
  viewRoot.append(loadingState());
  let e;
  try { e = await API.get(`/api/auditable-entities/${id}`); } catch (err) { clear(viewRoot); viewRoot.append(errorState(err, () => openEntity(id))); return; }
  clear(viewRoot);
  const can = UNIVERSE_EDIT();
  const layout = recordLayout({
    crumbs: recordCrumbs("universe", e.code), back: () => navigate("universe"),
    title: e.name, ref: e.code, status: e.status, meta: [ratingBadge(e.rating)],
    actions: can ? [btn(e.status === "Active" ? "Archive" : "Reactivate", async () => {
      const ok = await confirmDialog({ title: e.status === "Active" ? "Archive entity" : "Reactivate entity", confirmLabel: e.status === "Active" ? "Archive" : "Reactivate",
        text: e.status === "Active" ? "The entity is no longer offered for new assessments, plans and audits. Its history stays." : "The entity is offered again for assessments, plans and audits." });
      if (!ok.ok) return;
      try { await API.patch(`/api/auditable-entities/${id}`, { status: e.status === "Active" ? "Archived" : "Active" }); openEntity(id); } catch (err) { toast(err.message, "error"); }
    }, "secondary")] : [],
    tabs: [{ key: "details", label: "Details" }, { key: "assess", label: "Audit risk assessments" }, { key: "audits", label: "Audits", count: e.planned_audits || null },
      { key: "findings", label: "Findings and actions", count: e.open_findings || null }],
    side: null,
    onTab: (key, pane) => paintEntityTab(key, pane, e, can),
  });
  viewRoot.append(layout.root);
  layout.select(tab);
}

async function paintEntityTab(key, pane, e, can) {
  if (key === "details") {
    const freq = el("select", { class: "compact", "aria-label": "Audit frequency", disabled: can ? null : "1" },
      el("option", { value: "0" }, `Default for its rating (${e.frequency_is_default ? e.frequency : "by rating"})`),
      ...e.frequencies.map((f) => el("option", { value: f.value, selected: !e.frequency_is_default && f.value === e.frequency_months ? "1" : null }, f.label)));
    freq.addEventListener("change", async () => {
      try { await API.patch(`/api/auditable-entities/${e.id}`, { audit_frequency_months: Number(freq.value) }); toast("Audit frequency saved"); openEntity(e.id); } catch (err) { toast(err.message, "error"); }
    });
    const name = el("input", { type: "text", value: e.name, maxlength: "255", "aria-label": "Name", disabled: can ? null : "1" });
    const save = saveState();
    name.addEventListener("change", async () => {
      save.set("saving");
      try { await API.patch(`/api/auditable-entities/${e.id}`, { name: name.value }); save.set("saved"); } catch (err) { save.set("error"); toast(err.message, "error"); }
    });
    pane.append(el("div", { class: "two-cols" },
      el("div", { class: "card" }, el("h3", null, "Details"),
        el("div", { class: "form-field" }, el("label", null, "Name ", save.node), name),
        el("div", { class: "form-field" }, el("label", null, "Audit frequency"), freq),
        el("dl", { class: "kv" },
          el("dt", null, "Status"), el("dd", null, statusBadge(e.status)),
          el("dt", null, "Risk rating"), el("dd", null, ratingBadge(e.rating), e.score != null ? el("span", { class: "muted small" }, ` overall ${e.score}`) : null),
          el("dt", null, "Last assessed"), el("dd", null, e.assessed_at ? fmtDay(e.assessed_at.slice(0, 10)) : "-"),
          el("dt", null, "Last audited"), el("dd", null, e.last_audited_at ? fmtDay(e.last_audited_at.slice(0, 10)) : "Never"),
          el("dt", null, "Next due"), el("dd", null, e.next_due ? fmtDay(e.next_due) : "-"),
          el("dt", null, "Defined"), el("dd", null, e.defined_at ? fmtDay(e.defined_at.slice(0, 10)) : "Carried over from the earlier universe"),
          e.archived_at ? el("dt", null, "Archived") : null, e.archived_at ? el("dd", null, fmtDay(e.archived_at.slice(0, 10))) : null)),
      el("div", { class: "card" }, el("h3", null, "Taxonomy"),
        el("h4", null, "Org units"),
        e.org_units.length ? el("ul", { class: "plain-list" }, ...e.org_units.map((o) => el("li", null, o.path || o.name)))
          : el("div", null, el("p", { class: "muted small" }, "Not mapped to the Org Structure."), can ? btn("Map to org unit", () => mapEntityForm(e), "secondary") : null),
        el("h4", null, "Processes"),
        e.processes.length ? el("ul", { class: "plain-list" }, ...e.processes.map((p) => el("li", null, p.name))) : el("p", { class: "muted small" }, "The whole org unit (no single process)."),
        el("h4", null, "Entity category"), el("p", null, e.category || "-"))));
  }
  if (key === "assess") {
    const rows = await safeGet(`/api/auditable-entities/${e.id}/assessments`, []);
    pane.append(el("div", { class: "card" }, el("h3", null, "Audit risk assessments"), rows.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Assessment", "Status", "Overall score", "Risk rating", "Priority", "Completed"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rows.map((r) => el("tr", { tabindex: "0", onclick: () => openAssessment(r.id) },
        el("td", { class: "col-wide" }, el("span", { class: "ref" }, r.ref), ` ${r.name}`), el("td", null, statusBadge(r.status)),
        el("td", { class: "num" }, r.overall != null ? String(r.overall) : "-"), el("td", null, ratingBadge(r.rating)),
        el("td", { class: "num" }, r.priority ? `#${r.priority}` : "-"), el("td", null, r.completed_at ? fmtDay(r.completed_at.slice(0, 10)) : "-"))))))
      : emptyState({ icon: "clipboard-data", title: "Not assessed yet", text: "Include this entity in an audit risk assessment." })));
  }
  if (key === "audits") {
    const rows = await safeGet(`/api/auditable-entities/${e.id}/audits`, []);
    pane.append(el("div", { class: "card" }, el("h3", null, "Audits"), rows.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Audit", "Status", "Type", "Quarter"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rows.map((r) => el("tr", r.id ? { tabindex: "0", onclick: () => openAudit(r.id) } : { class: "no-click" },
        el("td", { class: "col-wide" }, r.ref ? el("span", { class: "ref" }, r.ref) : null, ` ${r.title}`), el("td", null, statusBadge(r.status)),
        el("td", null, r.audit_type || "-"), el("td", null, r.quarter || "-"))))))
      : emptyState({ icon: "folder2-open", title: "No audits yet", text: "Audits planned or run on this entity appear here." })));
  }
  if (key === "findings") {
    const d = await safeGet(`/api/auditable-entities/${e.id}/findings`, { summary: {}, items: [] });
    pane.append(el("div", { class: "stats" }, stat(d.summary.findings || 0, "Findings"), stat(d.summary.open || 0, "Open", null, d.summary.open ? "warn" : ""),
      stat(d.summary.high || 0, "Open high", null, d.summary.high ? "danger" : ""), stat(d.summary.open_actions || 0, "Open actions")),
    el("div", { class: "card" }, d.items.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Finding", "Severity", "Status", "Remediation", "Audit"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...d.items.map((f) => el("tr", { tabindex: "0", onclick: async () => { const full = await API.get(`/api/findings/${f.id}`); issueForm(full, f.audit_id, canWriteModule("audits"), () => openEntity(e.id, "findings")); } },
        el("td", { class: "col-wide" }, el("span", { class: "ref" }, `#${f.id}`), ` ${f.title}`), el("td", null, statusBadge(f.severity)), el("td", null, statusBadge(f.status)),
        el("td", { class: "small" }, f.remediation), el("td", { class: "small" }, f.audit))))))
      : emptyState({ icon: "flag", title: "No findings", text: "Findings and remediation actions from audits of this entity appear here." })));
  }
}

async function mapEntityForm(e) {
  const tree = await safeGet("/api/org-structure", { items: [] });
  openForm({
    title: `Map ${e.name} to the Org Structure`, draftable: false, width: 600,
    fields: [{ name: "org_ids", label: "Org units", type: "checklist", full: true, options: tree.items.map((o) => ({ value: o.id, label: `${"  ".repeat(o.depth)}${o.name}` })) }],
    initial: { org_ids: [] }, submitLabel: "Save",
    validate: (v) => ((v.org_ids || []).length ? {} : { org_ids: "Choose at least one org unit" }),
    onSubmit: (v) => API.patch(`/api/auditable-entities/${e.id}`, { org_ids: v.org_ids.map(Number) }),
    onDone: () => { toast("Entity mapped"); openEntity(e.id); },
  });
}

// ==================================================================== Audit risk assessment

async function renderRiskAssessments(tab = state.araTab || "list") {
  state.araTab = tab;
  clear(viewRoot);
  viewRoot.append(viewHeader("Audit risk assessment", PLANNING_EDIT() && tab === "list" ? btn("Add audit risk assessment", () => addAssessmentWizard()) : null,
    { sub: "Score auditable entities on assessment factors, prioritise them for audit and plan from the result" }));
  viewRoot.append(tabBar([{ key: "list", label: "Assessments" }, { key: "settings", label: "Settings" }], tab, (k) => renderRiskAssessments(k)));
  const body = el("div");
  viewRoot.append(body);
  if (tab === "settings") { renderAssessmentSettings(body); return; }
  body.append(loadingState());
  let rows;
  try { rows = await API.get("/api/audit-risk-assessments"); } catch (err) { clear(body); body.append(errorState(err)); return; }
  clear(body);
  if (!rows.length) {
    body.append(emptyState({ icon: "clipboard-data", title: "No audit risk assessments yet", text: "Add one to score the auditable entities of the audit universe.",
      action: PLANNING_EDIT() ? btn("Add audit risk assessment", () => addAssessmentWizard()) : null }));
    return;
  }
  body.append(el("div", { class: "card" }, el("div", { class: "table-wrap" }, el("table", { class: "dense" },
    el("thead", null, el("tr", null, ...["Assessment", "Status", "Rating scale", "Auditable entities", "Assessment factors", "Scoring", "Created on", "Completed", "Audit plan"].map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", null, ...rows.map((a) => el("tr", { tabindex: "0", onclick: () => openAssessment(a.id), onkeydown: (ev) => { if (ev.key === "Enter") openAssessment(a.id); } },
      el("td", { class: "col-wide", "data-label": "Assessment" }, el("span", { class: "ref" }, a.ref), " ", el("span", { class: "cell-title" }, a.name)),
      el("td", { "data-label": "Status" }, statusBadge(a.status)),
      el("td", { class: "small", "data-label": "Rating scale" }, a.scale),
      el("td", { class: "num", "data-label": "Auditable entities" }, String(a.entities)),
      el("td", { class: "num", "data-label": "Assessment factors" }, String(a.factors)),
      el("td", { "data-label": "Scoring" }, progressBar(a.cells ? (100 * a.scored) / a.cells : 0)),
      el("td", { "data-label": "Created on" }, fmtDay(a.created_at.slice(0, 10))),
      el("td", { "data-label": "Completed" }, a.completed_at ? fmtDay(a.completed_at.slice(0, 10)) : "-"),
      el("td", { class: "small", "data-label": "Audit plan" }, a.plan || "-"))))))));
}

async function renderAssessmentSettings(body) {
  const can = PLANNING_EDIT();
  body.append(loadingState());
  let d;
  try { d = await API.get("/api/assessment-factors"); } catch (err) { clear(body); body.append(errorState(err)); return; }
  clear(body);
  const reload = () => { clear(body); renderAssessmentSettings(body); };
  const fb = filterBar({ placeholder: "Search by ID or name", onChange: () => paint() });
  const box = el("div");
  body.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Assessment factors"),
    can ? btn("Add assessment factor", () => factorForm(null, reload)) : null),
  el("p", { class: "muted small" }, "At least one assessment factor is needed to create an audit risk assessment. Changes apply everywhere the factor is used."), fb.root, box));
  function paint() {
    const v = fb.values();
    const list = d.items.filter((f) => !v.q || `${f.ref} ${f.name}`.toLowerCase().includes(v.q.toLowerCase()));
    fb.setCount(`${list.length} of ${d.items.length}`);
    clear(box);
    box.append(list.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["ID", "Assessment factor", "Used in", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...list.map((f) => el("tr", { class: "no-click" },
        el("td", { class: "ref" }, f.ref), el("td", { class: "col-wide" }, el("div", { class: "cell-title" }, f.name), f.description ? el("div", { class: "muted small" }, f.description) : null),
        el("td", { class: "num" }, f.used_in ? `${f.used_in} assessment(s)` : "-"),
        el("td", null, can ? el("div", { class: "actions" }, btn("Edit", () => factorForm(f, reload), "secondary"),
          btn("Delete", async () => {
            const ok = await confirmDialog({ title: "Delete assessment factor", danger: true, confirmLabel: "Delete", text: `${f.name} will be removed. A factor used in a completed assessment is retired instead, so that record stays whole.` });
            if (!ok.ok) return;
            try { const r = await API.del(`/api/assessment-factors/${f.id}`); toast(r.message); reload(); } catch (err) { toast(err.message, "error"); }
          }, "danger-ghost")) : null))))))
      : emptyState({ icon: "sliders", title: "No assessment factors" }));
  }
  paint();
  const scaleBox = el("div", { class: "radio-col" }, ...d.scales.map((s) => {
    const r = el("input", { type: "radio", name: "araScale", id: `scale-${s.name}`, value: s.name, checked: s.name === d.scale ? "1" : null, disabled: isAdmin() ? null : "1" });
    r.addEventListener("change", async () => {
      try { await API.put("/api/config", { values: { audit_risk_scale: s.name } }); toast("Default scale saved"); } catch (err) { toast(err.message, "error"); }
    });
    return el("label", { class: "check", for: `scale-${s.name}` }, r, el("strong", null, ` ${s.name}`), el("span", { class: "muted small" }, ` ${s.levels.join(" · ")}`));
  }));
  body.append(el("div", { class: "card" }, el("h3", null, "Scales"),
    el("p", { class: "muted small" }, "The default scale for new audit risk assessments. Each assessment keeps the scale it was created with. Higher scores mean higher risk."), scaleBox,
    isAdmin() ? null : el("p", { class: "muted small" }, "Only administrators change the default scale (Configuration > Audit methodology).")));
}

function factorForm(f, reload) {
  openForm({
    title: f ? `Edit ${f.ref}` : "Add assessment factor", draftable: false, width: 560,
    intro: f ? "Changes apply everywhere this factor is used." : null,
    fields: [
      { name: "name", label: "Name", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "description", label: "Description (what a high score means)", type: "textarea", maxLength: 5000, full: true },
    ],
    initial: f || {}, submitLabel: f ? "Save" : "Add assessment factor",
    onSubmit: (v) => (f ? API.patch(`/api/assessment-factors/${f.id}`, { name: v.name, description: v.description || "" })
      : API.post("/api/assessment-factors", { name: v.name, description: v.description || "" })),
    onDone: () => { toast("Assessment factor saved"); reload(); },
  });
}

// Add audit risk assessment: Name > Auditable entities > Assessment factors > Rating scale.
async function addAssessmentWizard() {
  const [uni, fac] = await Promise.all([safeGet("/api/audit-universe", { entities: [] }), safeGet("/api/assessment-factors", { items: [], scales: [], scale: "" })]);
  const active = uni.entities.filter((e) => e.status === "Active");
  if (!active.length) { toast("Define the audit universe first", "error"); navigate("universe"); return; }
  const st = { step: 0, name: "", entities: new Set(), factors: new Set(), scale: fac.scale };
  const steps = ["Name", "Auditable entities", "Assessment factors", "Rating scale"];
  const bodyBox = el("div");
  const err = el("div", { class: "field-error", role: "alert" });
  const back = el("button", { class: "btn secondary", type: "button" }, "Back");
  const next = el("button", { class: "btn", type: "button" }, "Next");
  const toggleTable = (items, set, label, render) => {
    const all = el("input", { type: "checkbox", "aria-label": `Include all ${label}`, checked: items.length && items.every((i) => set.has(i.id)) ? "1" : null });
    all.addEventListener("change", () => { items.forEach((i) => (all.checked ? set.add(i.id) : set.delete(i.id))); paint(); });
    return el("div", { class: "table-wrap wizard-table" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, el("th", { scope: "col" }, all, " Include"), ...render.head.map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...items.map((i) => {
        const cb = el("input", { type: "checkbox", class: "switch", "aria-label": `Include ${i.name}`, checked: set.has(i.id) ? "1" : null });
        cb.addEventListener("change", () => { if (cb.checked) set.add(i.id); else set.delete(i.id); paint(); });
        return el("tr", { class: "no-click" }, el("td", null, cb), ...render.cells(i).map((c) => el("td", null, c)));
      }))));
  };
  function paint() {
    clear(bodyBox); err.textContent = "";
    bodyBox.append(el("ol", { class: "wizard-steps" }, ...steps.map((s, i) => el("li", { class: i === st.step ? "current" : i < st.step ? "done" : "" }, el("span", { class: "dot" }, String(i + 1)), ` ${s}`))));
    if (st.step === 0) {
      const name = el("input", { type: "text", maxlength: "255", value: st.name, "aria-label": "Name", placeholder: `e.g. FY${new Date().getFullYear() + 1} audit risk assessment` });
      name.addEventListener("input", () => { st.name = name.value; });
      bodyBox.append(el("div", { class: "form-field" }, el("label", null, "Name", el("span", { class: "req" }, " *")), name, el("div", { class: "help" }, "Must be unique.")));
      setTimeout(() => name.focus(), 20);
    }
    if (st.step === 1) bodyBox.append(el("p", { class: "muted small" }, `${st.entities.size} of ${active.length} included`),
      toggleTable(active, st.entities, "entities", { head: ["Auditable entity", "Org unit", "Process", "Last rating"], cells: (e) => [e.name, e.org_units.map((o) => o.name).join(", ") || "-", e.processes.map((p) => p.name).join(", ") || "-", ratingBadge(e.rating)] }));
    if (st.step === 2) bodyBox.append(el("p", { class: "muted small" }, `${st.factors.size} of ${fac.items.length} included`),
      fac.items.length ? toggleTable(fac.items, st.factors, "factors", { head: ["ID", "Assessment factor"], cells: (f) => [el("span", { class: "ref" }, f.ref), f.name] })
        : el("p", null, "No assessment factors yet. Add them under Audit risk assessment > Settings."));
    if (st.step === 3) bodyBox.append(el("h4", null, "Select rating scale"), el("div", { class: "radio-col" }, ...fac.scales.map((s) => {
      const r = el("input", { type: "radio", name: "wizScale", id: `wiz-${s.name}`, checked: s.name === st.scale ? "1" : null });
      r.addEventListener("change", () => { st.scale = s.name; });
      return el("label", { class: "check", for: `wiz-${s.name}` }, r, el("strong", null, ` ${s.name}`), el("span", { class: "muted small" }, ` ${s.levels.join(" · ")}`));
    })));
    back.disabled = st.step === 0;
    next.textContent = st.step === 3 ? "Finish" : "Next";
  }
  back.addEventListener("click", () => { st.step = Math.max(0, st.step - 1); paint(); });
  next.addEventListener("click", async () => {
    if (st.step === 0 && st.name.trim().length < 3) { err.textContent = "Enter a unique name (at least 3 characters)"; return; }
    if (st.step === 1 && !st.entities.size) { err.textContent = "Include at least one auditable entity"; return; }
    if (st.step === 2 && !st.factors.size) { err.textContent = "Include at least one assessment factor"; return; }
    if (st.step < 3) { st.step += 1; paint(); return; }
    try {
      const a = await API.post("/api/audit-risk-assessments", { name: st.name.trim(), entity_ids: [...st.entities], factor_ids: [...st.factors], scale: st.scale });
      m.close(true); toast("Audit risk assessment added (Draft)"); openAssessment(a.id);
    } catch (e2) { err.textContent = e2.message; if (e2.errors && e2.errors[0] && e2.errors[0].field === "name") { st.step = 0; paint(); err.textContent = e2.message; } }
  });
  const m = modal({ title: "Add audit risk assessment", width: 860, body: el("div", null, bodyBox, err),
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", type: "button", onclick: () => m.close() }, "Cancel"), el("div", { class: "actions" }, back, next)) });
  paint();
}

async function openAssessment(id, tab = null) {
  setActiveNav("riskassess");
  clear(viewRoot);
  viewRoot.append(loadingState());
  let a;
  try { a = await API.get(`/api/audit-risk-assessments/${id}`); } catch (err) { clear(viewRoot); viewRoot.append(errorState(err, () => openAssessment(id))); return; }
  clear(viewRoot);
  const can = PLANNING_EDIT();
  const open = can && a.status !== "Completed";
  const actions = [
    open ? btn("Configure", () => configureAssessment(a), "secondary") : null,
    open && a.status === "Draft" ? btn("Delete", async () => {
      const ok = await confirmDialog({ title: "Delete assessment", danger: true, confirmLabel: "Delete", text: `${a.name} and its scores will be deleted.` });
      if (!ok.ok) return;
      try { await API.del(`/api/audit-risk-assessments/${id}`); toast("Deleted"); navigate("riskassess"); } catch (err) { toast(err.message, "error"); }
    }, "danger-ghost") : null,
    a.status === "Completed" ? iconBtn("printer", "Export PDF", () => window.print()) : null,
    a.status === "Completed" && hasPerm("plan.prepare", "plan.amend") ? btn(a.plan_id ? "Planning" : "Start planning", () => startPlanningDialog(a)) : null,
  ].filter(Boolean);
  const layout = recordLayout({
    crumbs: recordCrumbs("riskassess", a.ref), back: () => navigate("riskassess"), title: a.name, ref: a.ref, status: a.status,
    meta: [el("span", { class: "muted small" }, `${a.scale} · ${a.entities} entities · ${a.factors} factors`), a.plan ? el("span", { class: "chip-mini" }, `Plan ${a.plan}`) : null].filter(Boolean),
    actions, tabs: [{ key: "score", label: "Scoring" }, { key: "conclude", label: "Conclude" }], side: null,
    onTab: (key, pane) => { state.araTabRec = { id, key }; if (key === "score") paintScoring(pane, a, open); else paintConclude(pane, a, open); },
  });
  viewRoot.append(layout.root);
  const remembered = state.araTabRec && state.araTabRec.id === id ? state.araTabRec.key : null;
  layout.select(tab || remembered || (a.status === "Completed" ? "conclude" : "score"));
}

function paintScoring(pane, a, open) {
  const levels = a.levels;
  const progress = el("div", { class: "ara-progress" });
  const setProgress = (scored, cells) => { clear(progress); progress.append(el("span", { class: "muted small" }, `${scored} of ${cells} scores`), progressBar(cells ? (100 * scored) / cells : 0)); };
  setProgress(a.scored, a.cells);
  pane.append(el("div", { class: "fw-strip" }, el("span", { class: "fw-k" }, "Audit risk assessment scoring matrix"), el("span", { class: "grow" }), progress,
    open ? btn("Conclude", () => openAssessment(a.id, "conclude")) : null));
  if (!a.rows.length) { pane.append(emptyState({ icon: "grid-3x3", title: "No entities included", text: "Configure the assessment to include auditable entities." })); return; }
  const cellSel = (r, f) => {
    const sel = el("select", { class: "compact score-sel", "aria-label": `${r.name}: ${f.name}`, disabled: open ? null : "1" },
      el("option", { value: "" }, "-"), ...levels.map((l, i) => el("option", { value: i + 1, selected: r.scores[String(f.id)] === i + 1 ? "1" : null }, `${i + 1} ${l}`)));
    sel.dataset.level = r.scores[String(f.id)] || "";
    sel.addEventListener("change", async () => {
      try {
        const res = await API.put(`/api/audit-risk-assessments/${a.id}/scores`, { entity_id: r.entity_id, factor_id: f.id, score: sel.value ? Number(sel.value) : null });
        sel.dataset.level = sel.value;
        const row = sel.closest("tr");
        row.querySelector(".ov").textContent = res.row.overall != null ? String(res.row.overall) : "-";
        const rt = row.querySelector(".rt"); clear(rt); rt.append(ratingBadge(res.row.rating));
        setProgress(res.scored, res.cells);
        if (a.status === "Draft") { a.status = res.status; }
      } catch (err) { toast("The selected scoring could not be saved", "error"); toast(err.message, "error"); }
    });
    return sel;
  };
  pane.append(el("div", { class: "card" }, el("div", { class: "table-wrap" }, el("table", { class: "dense score-matrix" },
    el("thead", null, el("tr", null, el("th", { scope: "col" }, "Auditable entity"), ...a.factor_list.map((f) => el("th", { scope: "col", title: f.name }, f.name)),
      el("th", { scope: "col", class: "num" }, "Overall score"), el("th", { scope: "col" }, "Risk rating"))),
    el("tbody", null, ...a.rows.map((r) => el("tr", { class: "no-click" },
      el("td", { class: "col-wide", "data-label": "Auditable entity" }, el("div", { class: "cell-title" }, r.name), el("div", { class: "muted small" }, r.org_unit || r.code)),
      ...a.factor_list.map((f) => el("td", { "data-label": f.name }, cellSel(r, f))),
      el("td", { class: "num ov", "data-label": "Overall score" }, r.overall != null ? String(r.overall) : "-"),
      el("td", { class: "rt", "data-label": "Risk rating" }, ratingBadge(r.rating)))))))),
  el("p", { class: "muted small" }, "Scores save automatically. Each entity's overall score is the average of its assessment factor scores; higher scores mean higher risk."));
}

function paintConclude(pane, a, open) {
  const reload = () => openAssessment(a.id, "conclude");
  if (!a.complete) {
    pane.append(emptyState({ icon: "hourglass-split", title: "Scoring is not finished", text: `Score every auditable entity on every assessment factor before concluding (${a.scored} of ${a.cells}).`,
      action: btn("Go to scoring", () => openAssessment(a.id, "score"), "secondary") }));
    return;
  }
  const prioritized = a.rows.filter((r) => r.priority).sort((x, y) => x.priority - y.priority);
  const order = prioritized.map((r) => r.entity_id);
  const save = async (ids) => { try { await API.put(`/api/audit-risk-assessments/${a.id}/priorities`, { entity_ids: ids }); reload(); } catch (err) { toast(err.message, "error"); } };
  const ranked = [...a.rows].sort((x, y) => (y.overall || 0) - (x.overall || 0));
  pane.append(el("div", { class: "card" }, el("h3", null, "Auditable entities"),
    el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Select", "Auditable entity", "Overall score", "Risk rating", ...a.factor_list.map((f) => f.name)].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...ranked.map((r) => {
        const sw = el("input", { type: "checkbox", class: "switch", "aria-label": `Prioritise ${r.name} for audit`, checked: r.priority ? "1" : null, disabled: open ? null : "1" });
        sw.addEventListener("change", () => save(sw.checked ? [...order, r.entity_id] : order.filter((x) => x !== r.entity_id)));
        return el("tr", { class: "no-click" }, el("td", null, sw), el("td", { class: "col-wide" }, r.name), el("td", { class: "num" }, String(r.overall)),
          el("td", null, ratingBadge(r.rating)), ...a.factor_list.map((f) => el("td", { class: "num" }, String(r.scores[String(f.id)] ?? "-"))));
      }))))));
  const list = el("ol", { class: "prio-list" });
  let dragFrom = null;
  prioritized.forEach((r, i) => {
    const move = (d) => { const ids = [...order]; const j = i + d; if (j < 0 || j >= ids.length) return; [ids[i], ids[j]] = [ids[j], ids[i]]; save(ids); };
    const li = el("li", { draggable: open ? "true" : "false", class: "prio-item" },
      el("span", { class: "prio-drag", "aria-hidden": "true", title: "Drag to re-rank" }, el("i", { class: "bi bi-grip-vertical" })),
      el("span", { class: "prio-n" }, `#${r.priority}`),
      el("div", { class: "prio-main" }, el("strong", null, r.name), " ", ratingBadge(r.rating), el("span", { class: "muted small" }, ` overall ${r.overall}`),
        r.note ? el("div", { class: "prio-note" }, el("i", { class: "bi bi-sticky", "aria-hidden": "true" }), ` ${r.note}`, el("span", { class: "muted small" }, ` - ${r.note_by || ""}${r.note_at ? `, ${fmtDate(r.note_at)}` : ""}`)) : null),
      open ? el("div", { class: "actions" },
        iconBtn("arrow-up", "Move up", () => move(-1)), iconBtn("arrow-down", "Move down", () => move(1)),
        btn(r.note ? "Edit note" : "Add note", () => noteDialog(a, r, reload), "secondary"),
        r.note ? btn("Delete note", async () => {
          const ok = await confirmDialog({ title: "Delete note", confirmLabel: "Delete", danger: true });
          if (ok.ok) { try { await API.put(`/api/audit-risk-assessments/${a.id}/notes/${r.entity_id}`, { note: null }); reload(); } catch (err) { toast(err.message, "error"); } }
        }, "danger-ghost") : null,
        btn("Remove", () => save(order.filter((x) => x !== r.entity_id)), "danger-ghost")) : null);
    li.addEventListener("dragstart", () => { dragFrom = i; li.classList.add("dragging"); });
    li.addEventListener("dragend", () => li.classList.remove("dragging"));
    li.addEventListener("dragover", (ev) => ev.preventDefault());
    li.addEventListener("drop", (ev) => { ev.preventDefault(); if (dragFrom === null || dragFrom === i) return; const ids = [...order]; const [x] = ids.splice(dragFrom, 1); ids.splice(i, 0, x); dragFrom = null; save(ids); });
    list.append(li);
  });
  pane.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, `Prioritized auditable entities for audit (${prioritized.length})`),
    open && prioritized.length ? btn("Remove all", async () => { const ok = await confirmDialog({ title: "Remove all", text: "All prioritised entities and their notes are removed. Scores stay.", confirmLabel: "Remove all", danger: true }); if (ok.ok) save([]); }, "danger-ghost") : null),
  prioritized.length ? list : el("p", { class: "muted small" }, "Use Select in the table above to prioritise entities for audit; drag to re-rank.")));
  const box = el("textarea", { rows: "6", maxlength: "50000", "aria-label": "Conclusion", disabled: open ? null : "1" }, a.conclusion || "");
  const ss = saveState();
  let t = null;
  box.addEventListener("input", () => { ss.set("dirty"); clearTimeout(t); t = setTimeout(async () => {
    ss.set("saving");
    try { await API.put(`/api/audit-risk-assessments/${a.id}/conclusion`, { conclusion: box.value }); ss.set("saved"); } catch (err) { ss.set("error"); toast(err.message, "error"); }
  }, 700); });
  pane.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Conclusion ", ss.node)),
    el("p", { class: "muted small" }, "Justify the audit plan's scope, time and resources. Printed on the PDF export."), box,
    el("div", { class: "actions end", style: "margin-top:10px" },
      open ? btn("Mark as completed", async () => {
        const ok = await confirmDialog({ title: "Mark as completed", confirmLabel: "Continue", text: "The assessment becomes a permanent record and rates its auditable entities. You can revert it until it feeds an audit plan." });
        if (!ok.ok) return;
        try { await API.post(`/api/audit-risk-assessments/${a.id}/complete`); toast("Assessment completed"); reload(); } catch (err) { toast(err.message, "error"); }
      }) : null,
      a.status === "Completed" && !a.plan_id && PLANNING_EDIT() ? btn("Revert to in progress", async () => {
        try { await API.post(`/api/audit-risk-assessments/${a.id}/revert`); toast("Back in progress"); reload(); } catch (err) { toast(err.message, "error"); }
      }, "secondary") : null,
      a.status === "Completed" ? el("span", { class: "muted small" }, `Completed ${fmtDate(a.completed_at)} by ${a.completed_by || "-"}`) : null)));
}

function noteDialog(a, r, reload) {
  openForm({ title: `Note: ${r.name}`, draftable: false, width: 560,
    fields: [{ name: "note", label: "Note", type: "textarea", maxLength: 5000, full: true, required: true }],
    initial: { note: r.note || "" }, submitLabel: "Save note",
    onSubmit: (v) => API.put(`/api/audit-risk-assessments/${a.id}/notes/${r.entity_id}`, { note: v.note }),
    onDone: reload });
}

async function configureAssessment(a) {
  const [uni, fac] = await Promise.all([safeGet("/api/audit-universe", { entities: [] }), safeGet("/api/assessment-factors", { items: [] })]);
  openForm({
    title: "Configure audit risk assessment", draftable: false, width: 760,
    intro: "Changing entities or factors keeps earlier scores. Renaming keeps the assessment and its Created on date.",
    fields: [
      { name: "name", label: "Name", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "entity_ids", label: "Auditable entities", type: "checklist", full: true, options: uni.entities.filter((e) => e.status === "Active").map((e) => ({ value: e.id, label: e.name })) },
      { name: "factor_ids", label: "Assessment factors", type: "checklist", full: true, options: fac.items.map((f) => ({ value: f.id, label: `${f.ref} ${f.name}` })) },
    ],
    initial: { name: a.name, entity_ids: a.rows.map((r) => r.entity_id), factor_ids: a.factor_list.map((f) => f.id) },
    validate: (v) => (!(v.entity_ids || []).length ? { entity_ids: "Include at least one entity" } : !(v.factor_ids || []).length ? { factor_ids: "Include at least one factor" } : {}),
    submitLabel: "Save",
    onSubmit: (v) => API.patch(`/api/audit-risk-assessments/${a.id}`, { name: v.name, entity_ids: v.entity_ids.map(Number), factor_ids: v.factor_ids.map(Number) }),
    onDone: () => { toast("Assessment configured"); openAssessment(a.id); },
  });
}

async function startPlanningDialog(a) {
  const plans = (await safeGet("/api/assurance-plans", [])).filter((p) => p.status === "Draft");
  const year = new Date().getFullYear() + 1;
  openForm({
    title: "Start planning", draftable: false, width: 600,
    intro: "Each prioritised auditable entity not yet in the plan becomes a planned engagement, named after the entity, with the default budget hours and its port as the responsible site.",
    fields: [
      { name: "mode", label: "Audit plan", type: "select", required: true, options: [{ value: "new", label: "Add audit plan" }, ...(plans.length ? [{ value: "link", label: "Link to existing audit plan" }] : [])] },
      { name: "fiscal_year", label: "Plan year (new plan)", type: "number", min: 2000, max: 2100 },
      ...(plans.length ? [{ name: "plan_id", label: "Existing draft plan", type: "select", emptyLabel: "- choose -", options: plans.map((p) => ({ value: p.id, label: `${p.plan_ref} · ${p.title}` })) }] : []),
    ],
    initial: { mode: a.plan_id ? "link" : "new", fiscal_year: year, plan_id: a.plan_id || null },
    validate: (v) => (v.mode === "link" && !v.plan_id ? { plan_id: "Choose the plan" } : v.mode === "new" && !v.fiscal_year ? { fiscal_year: "Enter the plan year" } : {}),
    submitLabel: "Generate and include",
    onSubmit: (v) => API.post(`/api/audit-risk-assessments/${a.id}/start-planning`, v.mode === "link" ? { plan_id: Number(v.plan_id) } : { fiscal_year: Number(v.fiscal_year) }),
    onDone: (r) => { toast(`${r.added} engagement(s) added to ${r.plan_ref}`); openPlan(r.plan_id); },
  });
}
