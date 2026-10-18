// GPHA Audit Workspace - integrated audit universe (Diligent One / HighBond Audit model).
//
//   Org Structure            the internal org tree (ports, offices, departments, units), bulk add
//   Process library          business processes and the org units that perform them, bulk add
//   Audit universe           Overview | Units | Processes | Entities (see the section below)
//   Auditable entity page    Overview | Risk assessment | Audits | Findings | History
//   Audit risk assessment    assessments list, Add (Name > Auditable entities > Assessment factors > Rating scale),
//                            scoring matrix, Conclude (prioritise, notes, conclusion), Mark as completed,
//                            Start planning; Settings (assessment factors, scale)
// Loaded after fieldwork.js and before app.js.

const UNIVERSE_EDIT = () => hasPerm("method.library", "system.reference");
const PLANNING_EDIT = () => hasPerm("plan.prepare", "plan.amend", "method.library");

function ratingBadge(r) {
  if (!r) return el("span", { class: "muted" }, "Not assessed");
  const tone = { "Very high": "risk-high", High: "risk-high", Medium: "risk-medium", Low: "risk-low", "Very low": "risk-low" }[r] || "";
  return el("span", { class: `badge badge-${tone}` }, r);
}

// ==================================================================== Org Structure
//
// The internal structure (ports, offices, departments, units) as a tree. Each unit opens a panel with its head,
// people, sub-units, audits, processes and change history. Units that are no longer used are deactivated rather
// than deleted, so the audits, plans and history that name them stay intact; the server enforces every rule.

async function renderOrgStructure() {
  clear(viewRoot);
  const can = UNIVERSE_EDIT();
  const showInactive = !!state.orgShowInactive;
  const exportBtn = hasPerm("data.export") ? btn("Export", () => exportOrgStructure(), "secondary") : null;
  viewRoot.append(viewHeader("Org Structure", el("div", { class: "actions" }, exportBtn,
    can ? btn("Bulk add", () => importDialog({ title: "Bulk add organizational units", templateKind: "orgunits", path: "/api/import/orgunits",
      intro: "Units are matched on name.", onDone: () => renderOrgStructure() }), "secondary") : null,
    can ? btn("New unit", () => orgUnitForm(null)) : null),
  ));
  const body = el("div");
  viewRoot.append(body);
  body.append(loadingState());
  let data;
  try { data = await API.get(`/api/org-structure${showInactive ? "?include_inactive=true" : ""}`); }
  catch (err) { clear(body); body.append(errorState(err, renderOrgStructure)); return; }
  state.orgStructure = data;
  clear(body);
  if (!data.items.length && !data.inactive_count) {
    body.append(emptyState({ icon: "diagram-3", title: "No organizational units yet",
      action: can ? btn("Create organizational unit", () => orgUnitForm(null)) : null }));
    return;
  }

  const active = data.items.filter((r) => r.is_active);
  const pending = active.filter((r) => r.status === "Pending").length;
  const noHead = active.filter((r) => !r.head_user_id).length;
  const toggle = el("input", { type: "checkbox", checked: showInactive ? "1" : null });
  toggle.addEventListener("change", () => { state.orgShowInactive = toggle.checked; renderOrgStructure(); });
  body.append(el("div", { class: "org-summary" },
    el("span", { class: "chip-mini" }, `${active.length} active unit${active.length === 1 ? "" : "s"}`),
    pending ? el("span", { class: "chip-mini warn" }, `${pending} awaiting approval`) : null,
    noHead ? el("span", { class: "chip-mini" }, `${noHead} without a head`) : null,
    data.inactive_count ? el("label", { class: "org-toggle" }, toggle, ` Show ${data.inactive_count} deactivated unit${data.inactive_count === 1 ? "" : "s"}`) : null));

  const collapsed = state.orgCollapsed || (state.orgCollapsed = new Set());
  const table = el("div");
  const fb = filterBar({ placeholder: "Search units, references or heads…",
    filters: [{ key: "category", label: "Type", options: data.types }, { key: "status", label: "Status", options: ["Approved", "Pending"] }],
    onChange: () => paint() });
  body.append(el("div", { class: "card" }, fb.root, table));
  const byId = Object.fromEntries(data.items.map((r) => [r.id, r]));
  const hiddenByCollapse = (r) => { let p = r.parent_id; while (p) { if (collapsed.has(p)) return true; p = byId[p] ? byId[p].parent_id : null; } return false; };
  function paint() {
    const v = fb.values();
    const filtering = !!(v.q || v.category || v.status);
    const q = (v.q || "").toLowerCase();
    const rows = data.items.filter((r) => (!v.category || r.category === v.category) && (!v.status || r.status === v.status)
      && (!q || `${r.name} ${r.org_ref} ${r.head_name || ""}`.toLowerCase().includes(q)) && (filtering || !hiddenByCollapse(r)));
    fb.setCount(`${rows.length} of ${data.items.length}`);
    clear(table);
    if (!rows.length) { table.append(el("div", { class: "empty" }, "No unit matches these filters.")); return; }
    const open = (r) => openOrgUnitPanel(r.id);
    table.append(el("div", { class: "table-wrap" }, el("table", { class: "dense tree-table org-table" },
      el("thead", null, el("tr", null, ...["Organizational unit", "Reference", "Type", "Head", "People", "Processes", "Auditable entities", "Status", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rows.map((r) => el("tr", { class: r.is_active ? "" : "row-inactive", tabindex: "0", onclick: () => open(r),
        onkeydown: (e) => { if (e.key === "Enter" && e.target === e.currentTarget) open(r); } },
        el("td", { class: "col-wide", "data-label": "Organizational unit" },
          el("span", { class: "tree-cell", style: `padding-left:${filtering ? 0 : r.depth * 20}px` },
            r.children && !filtering ? el("button", { class: "tree-toggle", type: "button", "aria-expanded": collapsed.has(r.id) ? "false" : "true",
              "aria-label": `${collapsed.has(r.id) ? "Expand" : "Collapse"} ${r.name}`, onclick: (e) => { e.stopPropagation(); if (collapsed.has(r.id)) collapsed.delete(r.id); else collapsed.add(r.id); paint(); } },
            el("i", { class: `bi bi-chevron-${collapsed.has(r.id) ? "right" : "down"}` })) : el("span", { class: "tree-spacer" }),
            el("span", { class: "cell-title" }, r.name), r.children ? el("span", { class: "muted small" }, ` (${r.children})`) : null)),
        el("td", { class: "ref", "data-label": "Reference" }, r.org_ref),
        el("td", { "data-label": "Type" }, r.category || "-"),
        el("td", { "data-label": "Head" }, r.head_name || el("span", { class: "muted" }, "Not set")),
        el("td", { class: "num", "data-label": "People" }, r.people ? String(r.people) : "-"),
        el("td", { class: "num", "data-label": "Processes", title: r.processes.map((p) => p.name).join(", ") }, r.processes.length ? String(r.processes.length) : "-"),
        el("td", { class: "num", "data-label": "Auditable entities" }, r.entities ? String(r.entities) : "-"),
        el("td", { "data-label": "Status" }, r.is_active ? badge(r.status) : badge("Deactivated")),
        el("td", null, can && r.is_active ? btn("Add unit", (e) => { if (e) e.stopPropagation(); orgUnitForm(null, r); }, "secondary") : null)))))));
  }
  paint();
}

async function exportOrgStructure() {
  const data = await safeGet("/api/org-structure?include_inactive=true", { items: [] });
  const byId = Object.fromEntries(data.items.map((r) => [r.id, r]));
  const path = (r) => { const out = []; let cur = r; const seen = new Set(); while (cur && !seen.has(cur.id)) { seen.add(cur.id); out.unshift(cur.name); cur = byId[cur.parent_id]; } return out.join(" / "); };
  downloadXlsx("Org structure", [
    { key: "path", label: "Path", csv: path }, { key: "org_ref", label: "Reference" }, { key: "name", label: "Unit" },
    { key: "category", label: "Type" }, { key: "status", label: "Status" }, { key: "is_active", label: "In use", csv: (r) => (r.is_active ? "Yes" : "Deactivated") },
    { key: "head_name", label: "Head" }, { key: "people", label: "People" },
    { key: "processes", label: "Processes", csv: (r) => r.processes.map((p) => p.name).join("; ") }, { key: "entities", label: "Auditable entities" },
  ], data.items);
}

// After a change in the panel: repaint the tree underneath (when it is open) and show the unit again.
function refreshOrgAfter(id) {
  if (state.view === "orgstructure") renderOrgStructure();
  if (id) openOrgUnitPanel(id);
}

async function openOrgUnitPanel(id) {
  const body = el("div", { class: "org-panel" }, loadingState("Loading the unit…"));
  const panel = detailPanel({ title: "Organizational unit", body, width: 640 });
  let d;
  try { d = await API.get(`/api/organizations/${id}/overview`); } catch (err) { clear(body); body.append(errorState(err)); return; }
  const u = d.unit;
  const act = async (fn, okText, reopen = true) => {
    try { await fn(); toast(okText); panel.close(); refreshOrgAfter(reopen ? id : null); } catch (err) { toast(err.message, "error"); }
  };
  clear(body);

  // Header: name, where it sits, status
  body.append(el("div", { class: "user-panel-head" },
    el("div", null, el("h3", null, u.name),
      el("div", { class: "muted small" }, `${u.org_ref}${u.category ? ` · ${u.category}` : ""}${u.port_name && u.port_id !== u.id ? ` · ${u.port_name}` : ""}`),
      d.path.length ? el("nav", { class: "org-path small", "aria-label": "Where this unit sits" }, ...d.path.flatMap((p, i) => [
        i ? el("span", { class: "muted", "aria-hidden": "true" }, " › ") : null,
        el("button", { class: "link-btn", type: "button", onclick: () => { panel.close(); openOrgUnitPanel(p.id); } }, p.name)]).filter(Boolean),
      el("span", { class: "muted", "aria-hidden": "true" }, " › "), el("span", null, u.name)) : el("div", { class: "muted small" }, "Top level")),
    el("div", { class: "user-badges" }, u.is_active ? badge(u.status) : badge("Deactivated"))));
  if (!u.is_active) body.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-archive" }),
    el("div", null, el("strong", null, "Deactivated"), ` ${fmtDate(u.deactivated_at).split(",")[0]}${d.deactivated_by ? ` by ${d.deactivated_by}` : ""}. `,
      u.deactivation_reason ? el("span", null, `Reason: ${u.deactivation_reason}`) : null)));

  // Head of unit
  body.append(el("h4", { class: "user-sec" }, "Head of unit"));
  if (d.can.administer && u.is_active) {
    const sel = el("select", { class: "compact", "aria-label": "Head of unit" }, el("option", { value: "" }, "- not set -"));
    const save = el("button", { class: "btn small", type: "button", disabled: "1" }, "Save");
    sel.addEventListener("change", () => { save.disabled = String(u.head_user_id || "") === sel.value; });
    save.addEventListener("click", () => act(() => API.patch(`/api/organizations/${u.id}`, { head_user_id: sel.value ? Number(sel.value) : null }), "Head of unit saved"));
    body.append(el("div", { class: "org-head-row" }, sel, save));
    safeGet("/api/organizations/people", []).then((people) => {
      people.forEach((p) => sel.append(el("option", { value: String(p.id), selected: p.id === u.head_user_id ? "1" : null }, `${p.name} (${p.username})`)));
      if (u.head_user_id && !people.some((p) => p.id === u.head_user_id)) sel.append(el("option", { value: String(u.head_user_id), selected: "1" }, `${u.head_name || "Unknown"} (account not active)`));
    });
  } else body.append(el("p", null, u.head_name || el("span", { class: "muted" }, "Not set")));

  // Actions
  const actions = [];
  if (d.can.edit && u.is_active) {
    actions.push(el("button", { class: "btn small", type: "button", onclick: () => { panel.close(); orgUnitForm(null, { id: u.id, name: u.name }); } }, el("i", { class: "bi bi-plus-lg" }), " Add sub-unit"));
    actions.push(el("button", { class: "btn small secondary", type: "button", onclick: () => { panel.close(); orgUnitForm(u); } }, el("i", { class: "bi bi-pencil" }), " Edit or move"));
  }
  if (d.can.approve) actions.push(el("button", { class: "btn small secondary", type: "button", onclick: () => { panel.close();
    eSignModal({ title: `Approve ${u.name}`, recordType: "organization", recordId: u.id, pathOverride: `/api/organizations/${u.id}/approve`, onDone: () => refreshOrgAfter(u.id) }); } },
  el("i", { class: "bi bi-pen" }), " Approve"));
  if (d.can.administer && u.is_active) actions.push(el("button", { class: "btn small danger-ghost", type: "button", onclick: async () => {
    const activeKids = d.children.filter((c) => c.is_active).length;
    if (activeKids) { toast(`Deactivate or move the ${activeKids} active unit${activeKids === 1 ? "" : "s"} under ${u.name} first.`, "error"); return; }
    const notes = [];
    if (d.people_total) notes.push(`${d.people_total} person${d.people_total === 1 ? " has" : "s have"} it as their workplace; move them afterwards.`);
    if (d.audit_open) notes.push(`${d.audit_open} open audit${d.audit_open === 1 ? " names" : "s name"} it; they keep it.`);
    const ok = await confirmDialog({ title: `Deactivate ${u.name}?`, danger: true, confirmLabel: "Deactivate", reason: true, reasonLabel: "Reason", maxLength: 500,
      text: `Existing records keep it; it is no longer offered for new work. ${notes.join(" ")}` });
    if (ok.ok) act(() => API.post(`/api/organizations/${u.id}/deactivate`, { reason: ok.reason }), "Unit deactivated");
  } }, el("i", { class: "bi bi-archive" }), " Deactivate"));
  if (d.can.administer && !u.is_active) actions.push(el("button", { class: "btn small", type: "button", onclick: () => act(() => API.post(`/api/organizations/${u.id}/reactivate`), "Unit reactivated") },
    el("i", { class: "bi bi-arrow-counterclockwise" }), " Reactivate"));
  if (actions.length) body.append(el("div", { class: "actions user-actions org-actions" }, ...actions));

  // Sub-units
  body.append(el("h4", { class: "user-sec" }, `Units under it (${d.children.length})`));
  body.append(d.children.length ? el("ul", { class: "org-list" }, ...d.children.map((c) => el("li", null,
    el("button", { class: "link-btn", type: "button", onclick: () => { panel.close(); openOrgUnitPanel(c.id); } }, c.name),
    el("span", { class: "muted small" }, ` ${c.org_ref}${c.category ? ` · ${c.category}` : ""}`),
    c.is_active ? (c.status === "Pending" ? el("span", { class: "chip-mini warn" }, "Pending") : null) : el("span", { class: "chip-mini" }, "Deactivated"))))
    : el("p", { class: "muted small" }, "No units under this one."));

  // People
  body.append(el("h4", { class: "user-sec" }, `People who work here (${d.people_total})`));
  if (d.people_below) body.append(el("p", { class: "muted small" }, `${d.people_below} more in the units under it.`));
  body.append(d.people.length ? el("ul", { class: "org-list" }, ...d.people.map((p) => el("li", null,
    hasPerm("system.users") ? el("button", { class: "link-btn", type: "button", onclick: () => { panel.close(); openUserPanel(p.id); } }, p.name) : el("span", null, p.name),
    el("span", { class: "muted small" }, ` ${p.role}`), p.is_active ? null : el("span", { class: "chip-mini" }, "Deactivated account"))))
    : el("p", { class: "muted small" }, "Nobody has this unit as their workplace."));

  // Audits and processes
  body.append(el("h4", { class: "user-sec" }, `Audits (${d.audit_total}${d.audit_open ? `, ${d.audit_open} open` : ""})`));
  body.append(d.audits.length ? el("ul", { class: "org-list" }, ...d.audits.map((a) => el("li", null,
    el("button", { class: "link-btn", type: "button", onclick: () => { panel.close(); openAudit(a.id); } }, a.title), " ", badge(a.status))))
    : el("p", { class: "muted small" }, "No audit names this unit."));
  if (d.audit_total > d.audits.length) body.append(el("p", { class: "muted small" }, `Showing the latest ${d.audits.length}.`));
  body.append(el("h4", { class: "user-sec" }, `Processes performed here (${d.processes.length})`));
  body.append(d.processes.length ? el("p", { class: "small" }, d.processes.map((p) => p.name).join(" · ")) : el("p", { class: "muted small" }, "No process is linked to this unit."));

  // History
  body.append(el("h4", { class: "user-sec" }, "Change history"));
  body.append(d.history.length ? el("ul", { class: "admin-changes" }, ...d.history.map((h) => el("li", null,
    el("div", { class: "admin-change-line" }, el("strong", null, h.by)), el("div", { class: "admin-change-action" }, h.action), el("div", { class: "muted small" }, fmtDate(h.at)))))
    : el("p", { class: "muted small" }, "No changes recorded."));

  if (d.can.delete) body.append(el("div", { class: "user-danger" },
    el("button", { class: "btn small danger-ghost", type: "button", title: "Only for pending units that nothing uses", onclick: async () => {
      const ok = await confirmDialog({ title: `Delete ${u.name}?`, danger: true, confirmLabel: "Delete", text: "This removes the unit completely." });
      if (ok.ok) act(() => API.del(`/api/organizations/${u.id}`), "Unit deleted", false);
    } }, el("i", { class: "bi bi-trash" }), " Delete unit")));
}

async function orgUnitForm(unit, parent = null) {
  const data = await safeGet("/api/org-structure", { items: [], types: [] });
  // A unit cannot move under itself or one of its own sub-units (the server checks this too).
  const below = new Set();
  if (unit) {
    let grew = true; below.add(unit.id);
    while (grew) { grew = false; data.items.forEach((r) => { if (r.parent_id && below.has(r.parent_id) && !below.has(r.id)) { below.add(r.id); grew = true; } }); }
  }
  const options = data.items.filter((r) => !below.has(r.id)).map((r) => ({ value: r.id, label: `${"  ".repeat(r.depth)}${r.name}` }));
  openForm({
    title: unit ? `Edit ${unit.name}` : parent ? `Add a unit under ${parent.name}` : "Create organizational unit", draftable: false, width: 640,
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
    onDone: (saved) => { toast(unit ? "Unit saved" : "Unit created (pending approval)"); refreshOrgAfter(unit ? unit.id : saved && saved.id); },
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
      el("thead", null, el("tr", null, ...["Reference", "Process", "Parent process", "Org units", "Risks · Controls", "Owner", "Auditable entities", "Status", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...list.map((p) => el("tr", { class: "no-click" },
        el("td", { class: "ref", "data-label": "Reference" }, p.ref),
        el("td", { class: "col-wide", "data-label": "Process" }, el("div", { class: "cell-title" }, p.name), p.description ? el("div", { class: "muted small" }, clip(p.description, 90)) : null),
        el("td", { "data-label": "Parent process" }, p.parent || "-"),
        el("td", { class: "small", "data-label": "Org units" }, p.org_units.length ? p.org_units.map((o) => o.name).join(", ") : el("span", { class: "muted" }, "Not linked")),
        el("td", { class: "small", "data-label": "Risks · Controls" }, (p.risk_count || p.control_count) ? `${p.risk_count} · ${p.control_count}` : el("span", { class: "muted" }, "Not linked")),
        el("td", { class: "small", "data-label": "Owner" }, p.owner_email || "-"),
        el("td", { class: "num", "data-label": "Auditable entities" }, p.entities ? String(p.entities) : "-"),
        el("td", { "data-label": "Status" }, statusBadge(p.status)),
        el("td", null, can ? el("div", { class: "actions" }, btn("Risks & controls", () => objectLinksForm("process", p, renderProcessLibrary), "secondary"),
          btn("Edit", () => processForm(p, rows), "secondary")) : null)))))));
  }
  paint();
}

async function processForm(p, all = null) {
  const [tree, procs] = await Promise.all([safeGet("/api/org-structure?include_inactive=true", { items: [] }), all ? Promise.resolve(all) : safeGet("/api/processes", [])]);
  // Only active units are offered, plus any deactivated unit the process is already linked to (so saving keeps it).
  const linked = new Set(p ? p.org_units.map((o) => o.id) : []);
  tree.items = tree.items.filter((o) => o.is_active || linked.has(o.id)).map((o) => (o.is_active ? o : { ...o, name: `${o.name} (deactivated)` }));
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
//
//   Overview    setup flow (units > processes > entities > risk assessment), real counts and coverage
//   Units       Org Structure units: include in the universe or mark Not included (with a reason)
//   Processes   Process library: map each process to the units that perform it
//   Entities    auditable entity register; New / Edit entity; entity page with the risk assessment hand-off
// Source records stay in the Org Structure and the Process library; nothing is copied. No risk score is shown here
// until an audit risk assessment has produced one.

const U_STATUS_TONE = { Included: "ok", "Not included": "muted", "Needs review": "warn", Mapped: "ok", Unmapped: "warn",
  Draft: "muted", Ready: "ok", Retired: "muted" };

function uChip(text, tone) {
  return el("span", { class: `u-chip ${tone || U_STATUS_TONE[text] || ""}` }, text);
}

function uStat(n, label, tone = "", onClick = null) {
  const box = el(onClick ? "button" : "div", { class: `u-stat ${tone}`, type: onClick ? "button" : null, onclick: onClick },
    el("span", { class: "l" }, label), el("strong", null, String(n)));
  return box;
}

function uBar(done, total, tone = "") {
  const pct = total ? Math.round((100 * done) / total) : 0;
  return el("span", { class: `u-bar ${tone}`, role: "progressbar", "aria-valuenow": String(pct), "aria-valuemin": "0", "aria-valuemax": "100", "aria-label": `${pct}%` },
    el("span", { style: `width:${pct}%` }));
}

// Audit management / Audit universe / Entities / <record>
function uCrumbs(last) {
  const base = recordCrumbs("universe", "Entities");
  base[base.length - 1] = { label: "Entities", onClick: () => navigate("universe_entities") };
  return [...base, { label: last }];
}

function uHead(title, sub, actions = null) {
  return viewHeader(title, actions, { sub });
}

// A client-side table: sort, page, optional row selection. columns: [{ key, label, render?, sort?: fn|key, num? }]
function uTable({ columns, rows, selectable = false, selected = new Set(), onSelect = null, onRow = null, pageSize = 25, sortKey = null, empty = null }) {
  const st = { page: 1, sort: sortKey, desc: false, size: pageSize };
  const root = el("div", { class: "u-table" });
  const valueOf = (c, r) => (typeof c.sort === "function" ? c.sort(r) : r[c.sort || c.key]);
  function paint() {
    clear(root);
    if (!rows.length) { root.append(empty || emptyState({ icon: "funnel", title: "Nothing matches", text: "Change or clear the filters." })); return; }
    let list = rows.slice();
    const sc = columns.find((c) => c.key === st.sort);
    if (sc) {
      list.sort((a, b) => {
        const x = valueOf(sc, a); const y = valueOf(sc, b);
        const r = typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""), undefined, { numeric: true, sensitivity: "base" });
        return st.desc ? -r : r;
      });
    }
    const pages = Math.max(1, Math.ceil(list.length / st.size));
    st.page = Math.min(st.page, pages);
    const pageRows = list.slice((st.page - 1) * st.size, st.page * st.size);
    const allOn = selectable && pageRows.length && pageRows.every((r) => selected.has(r.id));
    const all = selectable ? el("input", { type: "checkbox", "aria-label": "Select all on this page", checked: allOn ? "1" : null }) : null;
    if (all) all.addEventListener("change", () => { pageRows.forEach((r) => (all.checked ? selected.add(r.id) : selected.delete(r.id))); if (onSelect) onSelect(); paint(); });
    const head = el("tr", null, selectable ? el("th", { class: "u-check", scope: "col" }, all) : null, ...columns.map((c) => {
      const sortable = c.sort !== false;
      const active = st.sort === c.key;
      return el("th", { scope: "col", class: c.num ? "num" : null, "aria-sort": active ? (st.desc ? "descending" : "ascending") : (sortable ? "none" : null) },
        sortable ? el("button", { class: "th-sort", type: "button", onclick: () => { st.desc = active ? !st.desc : false; st.sort = c.key; paint(); } },
          c.label, el("i", { class: `bi ${active ? (st.desc ? "bi-caret-down-fill" : "bi-caret-up-fill") : "bi-chevron-expand"} sort-ico`, "aria-hidden": "true" })) : c.label);
    }));
    const body = el("tbody", null, ...pageRows.map((r) => {
      const cb = selectable ? el("input", { type: "checkbox", "aria-label": `Select ${r.name}`, checked: selected.has(r.id) ? "1" : null }) : null;
      if (cb) {
        cb.addEventListener("click", (e) => e.stopPropagation());
        cb.addEventListener("change", () => { if (cb.checked) selected.add(r.id); else selected.delete(r.id); if (onSelect) onSelect(); paint(); });
      }
      return el("tr", onRow ? { tabindex: "0", class: selected.has(r.id) ? "is-selected" : null, onclick: () => onRow(r), onkeydown: (e) => { if (e.key === "Enter") onRow(r); } } : { class: "no-click" },
        selectable ? el("td", { class: "u-check" }, cb) : null,
        ...columns.map((c) => el("td", { class: c.num ? "num" : (c.cls || null), "data-label": c.label }, c.render ? c.render(r) : (r[c.key] ?? "-"))));
    }));
    root.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" }, el("thead", null, head), body)));
    const sizeSel = el("select", { class: "compact", "aria-label": "Rows per page" }, ...[10, 25, 50, 100].map((n) => el("option", { value: n, selected: n === st.size ? "1" : null }, `${n} / page`)));
    sizeSel.addEventListener("change", () => { st.size = Number(sizeSel.value); st.page = 1; paint(); });
    root.append(el("div", { class: "table-foot" },
      el("span", { class: "muted small" }, `Showing ${(st.page - 1) * st.size + 1}–${Math.min(st.page * st.size, list.length)} of ${list.length}`),
      el("div", { class: "actions" }, sizeSel,
        el("button", { class: "btn small secondary icon-only", type: "button", "aria-label": "Previous page", disabled: st.page <= 1 ? "1" : null, onclick: () => { st.page -= 1; paint(); } }, el("i", { class: "bi bi-chevron-left" })),
        el("span", { class: "small" }, `${st.page} / ${pages}`),
        el("button", { class: "btn small secondary icon-only", type: "button", "aria-label": "Next page", disabled: st.page >= pages ? "1" : null, onclick: () => { st.page += 1; paint(); } }, el("i", { class: "bi bi-chevron-right" })))));
  }
  paint();
  return { root, set: (r) => { rows = r; st.page = 1; paint(); }, repaint: paint };
}

// A searchable multi-select list with chips for the chosen items. items: [{ id, label, sub? }]
function uPicker({ items, selected, label, placeholder = "Search…", onChange = null, empty = "Nothing to choose." }) {
  const chosen = new Set(selected || []);
  const chips = el("div", { class: "u-chips" });
  const search = el("input", { type: "search", class: "u-pick-search", placeholder, "aria-label": `Search ${label}` });
  const list = el("div", { class: "u-pick-list", role: "listbox", "aria-label": label, "aria-multiselectable": "true" });
  const byId = Object.fromEntries(items.map((i) => [i.id, i]));
  function paint() {
    clear(chips);
    [...chosen].filter((id) => byId[id]).forEach((id) => chips.append(el("span", { class: "u-chip-x" }, byId[id].label,
      el("button", { type: "button", "aria-label": `Remove ${byId[id].label}`, onclick: () => { chosen.delete(id); changed(); } }, el("i", { class: "bi bi-x" })))));
    if (!chosen.size) chips.append(el("span", { class: "muted small" }, "None selected"));
    clear(list);
    const q = search.value.trim().toLowerCase();
    const shown = items.filter((i) => !q || `${i.label} ${i.sub || ""}`.toLowerCase().includes(q)).slice(0, 200);
    if (!items.length) list.append(el("div", { class: "muted small u-pick-empty" }, empty));
    shown.forEach((i) => {
      const cb = el("input", { type: "checkbox", checked: chosen.has(i.id) ? "1" : null });
      cb.addEventListener("change", () => { if (cb.checked) chosen.add(i.id); else chosen.delete(i.id); changed(); });
      list.append(el("label", { class: "u-pick-item", style: i.depth ? `padding-left:${8 + i.depth * 14}px` : null }, cb,
        el("span", null, i.label), i.sub ? el("span", { class: "muted small" }, ` ${i.sub}`) : null));
    });
  }
  function changed() { paint(); if (onChange) onChange([...chosen]); }
  search.addEventListener("input", paint);
  paint();
  return { root: el("div", { class: "u-picker" }, chips, search, list), values: () => [...chosen], set: (ids) => { chosen.clear(); ids.forEach((i) => chosen.add(i)); paint(); } };
}

function uExport(name, cols, rows) {
  if (!hasPerm("data.export") || typeof downloadXlsx !== "function") return null;
  return el("button", { class: "btn secondary", type: "button", onclick: () => downloadXlsx(name, cols, rows) }, el("i", { class: "bi bi-download" }), " Export");
}

// ---------------------------------------------------------------- 1. Overview

async function renderUniverse() {
  clear(viewRoot);
  viewRoot.append(uHead("Audit universe", "Org units and processes, defined as auditable entities, then assessed for risk.",
    el("div", { class: "actions" },
      viewAllowed("orgstructure") ? btn("View org structure", () => navigate("orgstructure"), "secondary") : null,
      viewAllowed("processes") ? btn("Visit Process library", () => navigate("processes"), "secondary") : null)));
  const body = el("div", null, loadingState());
  viewRoot.append(body);
  let d;
  try { d = await API.get("/api/audit-universe/overview"); } catch (err) { clear(body); body.append(errorState(err, renderUniverse)); return; }
  clear(body);
  if (!d.units.total) {
    body.append(emptyState({ icon: "diagram-3", title: "No org units yet", text: "The audit universe starts from the Org Structure.",
      action: viewAllowed("orgstructure") ? btn("Open Org Structure", () => navigate("orgstructure")) : null }));
    return;
  }
  const step = (n, done, title, metric, label, go) => el("div", { class: `u-step ${done ? "done" : ""}` },
    el("span", { class: "u-step-n", "aria-hidden": "true" }, done ? el("i", { class: "bi bi-check-lg" }) : String(n)),
    el("div", { class: "u-step-t" }, title), el("div", { class: "muted small" }, metric),
    el("button", { class: "link-btn", type: "button", onclick: go }, label, " ", el("i", { class: "bi bi-arrow-right", "aria-hidden": "true" })));
  const s = d.entities.by_status;
  body.append(el("section", { class: "u-flow", "aria-label": "Setup flow" },
    step(1, d.steps.units, "Review units", d.units.needs_review ? `${d.units.needs_review} to review` : `${d.units.included} included`, "Review units", () => navigate("universe_units")),
    step(2, d.steps.processes, "Review processes", d.processes.unmapped ? `${d.processes.unmapped} unmapped` : `${d.processes.mapped} mapped`, "Review processes", () => navigate("universe_processes")),
    step(3, d.steps.entities, "Define entities", `${s.Ready} ready${s.Draft + s["Needs review"] ? ` · ${s.Draft + s["Needs review"]} in progress` : ""}`, "Define entities", () => navigate("universe_entities")),
    step(4, d.steps.assessment, "Assess risk", d.assessments.latest ? `${d.assessments.latest.ref} · ${d.assessments.latest.status}` : "Not started", "Audit risk assessment", () => navigate("riskassess"))));
  body.append(el("div", { class: "u-stats" },
    uStat(d.units.total, "Org units", "", () => navigate("universe_units")),
    uStat(d.processes.total, "Processes", "", () => navigate("universe_processes")),
    uStat(d.entities.active, "Defined entities", "", () => navigate("universe_entities")),
    uStat(d.needs_review, "Needs review", d.needs_review ? "warn" : "ok")));
  const row = (label, done, total, chip, tone, go) => el("tr", { tabindex: "0", onclick: go, onkeydown: (e) => { if (e.key === "Enter") go(); } },
    el("td", { "data-label": "Source" }, label), el("td", { class: "num", "data-label": "Linked" }, `${done} of ${total}`),
    el("td", { "data-label": "Coverage" }, uBar(done, total, tone)), el("td", { "data-label": "Status" }, chip));
  body.append(el("section", { class: "card" }, el("h3", null, "Universe coverage"),
    el("div", { class: "table-wrap" }, el("table", { class: "dense u-coverage" },
      el("thead", null, el("tr", null, ...["Source", "Linked", "Coverage", "Status"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null,
        row("Organizational units", d.units.included, d.units.total, d.units.needs_review ? uChip(`${d.units.needs_review} to review`, "warn") : uChip("Reviewed", "ok"), "", () => navigate("universe_units")),
        row("Processes", d.processes.mapped, d.processes.total, d.processes.unmapped ? uChip(`${d.processes.unmapped} unmapped`, "warn") : uChip("All mapped", "ok"), "ok", () => navigate("universe_processes")),
        row("Auditable entities", s.Ready, d.entities.active, s.Draft + s["Needs review"] ? uChip(`${s.Draft + s["Needs review"]} not ready`, "warn") : uChip(d.entities.active ? "All ready" : "None yet", d.entities.active ? "ok" : "muted"), "", () => navigate("universe_entities"))))),
    el("div", { class: "actions end" },
      btn("Open risk assessment", () => navigate("riskassess"), "secondary"),
      btn("Define entities", () => navigate("universe_entities")))));
}

// ---------------------------------------------------------------- 2. Units

async function renderUniverseUnits() {
  clear(viewRoot);
  const can = UNIVERSE_EDIT();
  const head = el("div");
  const body = el("div", null, loadingState());
  viewRoot.append(head, body);
  let d;
  try { d = await API.get("/api/audit-universe/units"); } catch (err) { clear(body); body.append(errorState(err, renderUniverseUnits)); return; }
  clear(body);
  const rows = d.items;
  const cols = [{ key: "code", label: "Code" }, { key: "name", label: "Unit" }, { key: "type", label: "Type" }, { key: "parent", label: "Parent unit", csv: (r) => (r.parent ? r.parent.name : "") },
    { key: "location", label: "Location" }, { key: "owner", label: "Business owner" }, { key: "processes", label: "Processes" }, { key: "status", label: "Status" }, { key: "reason", label: "Reason" }];
  head.append(uHead("Organizational units", "Include the units that belong in the audit universe.", el("div", { class: "actions" }, uExport("audit-universe-units", cols, rows))));
  if (!rows.length) {
    body.append(emptyState({ icon: "diagram-3", title: "No org units yet", text: "Add ports, offices, departments and units in the Org Structure.",
      action: viewAllowed("orgstructure") ? btn("Open Org Structure", () => navigate("orgstructure")) : null }));
    return;
  }
  const uniq = (f) => [...new Set(rows.map(f).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const selected = new Set();
  const fb = filterBar({ placeholder: "Search units", values: state.unitFilters || {}, onChange: () => paint(),
    filters: [{ key: "type", label: "Type", options: uniq((r) => r.type) }, { key: "parent", label: "Parent", options: uniq((r) => r.parent && r.parent.name) },
      { key: "location", label: "Location", options: uniq((r) => r.location) }, { key: "owner", label: "Owner", options: uniq((r) => r.owner) },
      { key: "status", label: "Status", options: ["Included", "Needs review", "Not included"] },
      { key: "linked", label: "Processes", options: [{ value: "yes", label: "Linked" }, { value: "no", label: "None" }] }] });
  const setFilter = (k, v) => { const sel = fb.root.querySelector(`select[aria-label="${k}"]`); if (sel) { sel.value = v; sel.dispatchEvent(new Event("change")); } };
  body.append(el("div", { class: "u-stats" },
    uStat(d.summary.total, "Total units", "", () => setFilter("Status", "")),
    uStat(d.summary.included, "Included", "ok", () => setFilter("Status", "Included")),
    uStat(d.summary.with_processes, "With processes", "", () => setFilter("Processes", "yes")),
    uStat(d.summary.needs_review, "Needs review", d.summary.needs_review ? "warn" : "ok", () => setFilter("Status", "Needs review"))));
  const selInfo = el("span", { class: "u-selinfo" });
  const includeBtn = el("button", { class: "btn", type: "button", disabled: "1" }, "Include selected");
  const excludeBtn = el("button", { class: "btn secondary", type: "button", disabled: "1" }, "Not included…");
  const decide = async (decision) => {
    let reason = "";
    if (decision === "Not included") {
      const r = await confirmDialog({ title: `Mark ${selected.size} unit${selected.size === 1 ? "" : "s"} Not included`, confirmLabel: "Save", reason: true, reasonLabel: "Reason", maxLength: 2000 });
      if (!r.ok) return;
      reason = r.reason;
    }
    try {
      await API.post("/api/audit-universe/units/review", { ids: [...selected], decision, reason });
      toast(decision === "Included" ? "Units included" : "Units marked Not included");
      state.unitFilters = fb.values(); renderUniverseUnits();
    } catch (err) { toast(err.message, "error"); }
  };
  includeBtn.addEventListener("click", () => decide("Included"));
  excludeBtn.addEventListener("click", () => decide("Not included"));
  const onSelect = () => {
    selInfo.textContent = selected.size ? `${selected.size} selected` : "";
    includeBtn.disabled = !selected.size; excludeBtn.disabled = !selected.size;
  };
  const table = uTable({ rows, selectable: can, selected, onSelect, onRow: (r) => openUnitPanel(r.id), sortKey: null,
    columns: [
      { key: "name", label: "Unit / code", render: (r) => el("div", null, el("div", { class: "cell-title" }, r.name), el("div", { class: "muted small" }, r.code || "-")) },
      { key: "type", label: "Type" },
      { key: "parent", label: "Parent unit", sort: (r) => (r.parent ? r.parent.name : ""), render: (r) => (r.parent ? r.parent.name : "-") },
      { key: "location", label: "Location" },
      { key: "owner", label: "Business owner", render: (r) => r.owner || el("span", { class: "muted" }, "-") },
      { key: "processes", label: "Processes", num: true, render: (r) => (r.processes ? String(r.processes) : el("span", { class: "muted" }, "0")) },
      { key: "status", label: "Status", render: (r) => uChip(r.status) },
    ] });
  body.append(el("section", { class: "card u-card" }, fb.root,
    can ? el("div", { class: "u-selbar" }, selInfo, el("div", { class: "actions" }, excludeBtn, includeBtn)) : null, table.root));
  function paint() {
    const v = fb.values();
    const q = (v.q || "").toLowerCase();
    const list = rows.filter((r) => (!q || `${r.name} ${r.code || ""}`.toLowerCase().includes(q))
      && (!v.type || r.type === v.type) && (!v.parent || (r.parent && r.parent.name === v.parent)) && (!v.location || r.location === v.location)
      && (!v.owner || r.owner === v.owner) && (!v.status || r.status === v.status) && (!v.linked || (v.linked === "yes" ? r.processes > 0 : r.processes === 0)));
    fb.setCount(`${list.length} of ${rows.length}`);
    table.set(list);
  }
  paint();
}

async function openUnitPanel(id) {
  const body = el("div", null, loadingState());
  const panel = detailPanel({ title: "Org unit", body, width: 600 });
  let u;
  try { u = await API.get(`/api/audit-universe/units/${id}`); } catch (err) { clear(body); body.append(errorState(err)); return; }
  clear(body);
  const can = UNIVERSE_EDIT();
  const fact = (k, v) => el("div", { class: "log-fact" }, el("dt", null, k), el("dd", null, v || "-"));
  const decide = async (decision) => {
    let reason = "";
    if (decision === "Not included") {
      const r = await confirmDialog({ title: `Mark ${u.name} Not included`, confirmLabel: "Save", reason: true, reasonLabel: "Reason" });
      if (!r.ok) return;
      reason = r.reason;
    }
    try { await API.post("/api/audit-universe/units/review", { ids: [u.id], decision, reason }); toast("Saved"); if (panel && panel.close) panel.close(); renderUniverseUnits(); }
    catch (err) { toast(err.message, "error"); }
  };
  body.append(...[el("div", { class: "u-panel-head" }, el("h3", null, u.name), uChip(u.status)),
    el("dl", { class: "log-facts" }, fact("Code", u.code), fact("Type", u.type), fact("Path", u.path), fact("Location", u.location),
      fact("Business owner", u.owner), fact("Source", "Org Structure"), fact("Last updated", u.updated_at ? fmtDate(u.updated_at) : null)),
    u.review ? el("p", { class: "muted small" }, `${u.review.decision} by ${u.review.by || "-"}, ${fmtDate(u.review.at)}${u.review.reason ? ` · ${u.review.reason}` : ""}`) : null,
    can ? el("div", { class: "actions" },
      u.status !== "Included" ? btn("Include", () => decide("Included")) : null,
      u.status !== "Not included" && !u.entity_list.length ? btn("Not included…", () => decide("Not included"), "secondary") : null,
      u.review ? btn("Reset to review", () => decide("Needs review"), "secondary") : null) : null,
    el("h4", null, `Processes (${u.process_list.length})`),
    u.process_list.length ? el("ul", { class: "u-list" }, ...u.process_list.map((p) => el("li", null, el("span", null, el("span", { class: "ref" }, p.ref), ` ${p.name}`),
      el("span", { class: "muted small" }, `${p.risks} risks · ${p.controls} controls`)))) : el("p", { class: "muted small" }, "No processes linked."),
    el("h4", null, `Auditable entities (${u.entity_list.length})`),
    u.entity_list.length ? el("ul", { class: "u-list" }, ...u.entity_list.map((e) => el("li", null,
      el("button", { class: "link-btn", type: "button", onclick: () => { if (panel && panel.close) panel.close(); openEntity(e.id); } }, `${e.code} ${e.name}`), uChip(e.status)))) : el("p", { class: "muted small" }, "None yet."),
    el("h4", null, "Audits and findings"),
    el("p", { class: "small" }, `${u.audit_count} audit${u.audit_count === 1 ? "" : "s"} · ${u.open_findings} open finding${u.open_findings === 1 ? "" : "s"} · ${u.risks} risks and ${u.controls} controls through its processes`),
    u.audits.length ? el("ul", { class: "u-list" }, ...u.audits.map((a) => el("li", null, el("button", { class: "link-btn", type: "button", onclick: () => { if (panel && panel.close) panel.close(); openAudit(a.id); } }, `${a.ref} ${a.title}`), statusBadge(a.status)))) : null,
    viewAllowed("orgstructure") ? el("div", { class: "actions" }, btn("Open in Org Structure", () => { if (panel && panel.close) panel.close(); navigate("orgstructure"); setTimeout(() => openOrgUnitPanel(u.id), 300); }, "secondary")) : null].filter(Boolean));
}

// ---------------------------------------------------------------- 3. Processes

async function renderUniverseProcesses() {
  clear(viewRoot);
  const can = UNIVERSE_EDIT();
  const head = el("div");
  const body = el("div", null, loadingState());
  viewRoot.append(head, body);
  let d; let units;
  try { [d, units] = await Promise.all([API.get("/api/audit-universe/processes"), API.get("/api/org-structure")]); }
  catch (err) { clear(body); body.append(errorState(err, renderUniverseProcesses)); return; }
  clear(body);
  const rows = d.items;
  const cols = [{ key: "ref", label: "Code" }, { key: "name", label: "Process" }, { key: "group", label: "Process group" },
    { key: "units", label: "Performed by units", csv: (r) => r.units.map((u) => u.name).join("; ") }, { key: "owner", label: "Owner" },
    { key: "risks", label: "Linked risks" }, { key: "controls", label: "Linked controls" }, { key: "mapping", label: "Mapping" }];
  head.append(uHead("Process library review", "Map each process to the units that perform it.", el("div", { class: "actions" },
    uExport("audit-universe-processes", cols, rows), viewAllowed("processes") ? btn("Visit Process library", () => navigate("processes"), "secondary") : null)));
  if (!rows.length) {
    body.append(emptyState({ icon: "diagram-2", title: "No processes yet", text: "Add the processes GPHA performs in the Process library.",
      action: viewAllowed("processes") ? btn("Visit Process library", () => navigate("processes")) : null }));
    return;
  }
  const selected = new Set();
  const selStat = uStat(0, "Selected");
  const uniq = (f) => [...new Set(rows.flatMap(f).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const fb = filterBar({ placeholder: "Search processes", onChange: () => paint(),
    filters: [{ key: "group", label: "Process group", options: uniq((r) => [r.group || r.name]) },
      { key: "unit", label: "Unit", options: uniq((r) => r.units.map((u) => u.name)) },
      { key: "mapping", label: "Mapping", options: ["Mapped", "Unmapped"] }] });
  const setFilter = (k, v) => { const sel = fb.root.querySelector(`select[aria-label="${k}"]`); if (sel) { sel.value = v; sel.dispatchEvent(new Event("change")); } };
  body.append(el("div", { class: "u-stats" },
    uStat(d.summary.total, "Total processes", "", () => setFilter("Mapping", "")),
    uStat(d.summary.mapped, "Mapped", "ok", () => setFilter("Mapping", "Mapped")),
    uStat(d.summary.unmapped, "Unmapped", d.summary.unmapped ? "warn" : "ok", () => setFilter("Mapping", "Unmapped")), selStat));
  const selInfo = el("span", { class: "u-selinfo" });
  const mapBtn = el("button", { class: "btn secondary", type: "button", disabled: "1" }, el("i", { class: "bi bi-diagram-3" }), " Map to units");
  const entBtn = el("button", { class: "btn secondary", type: "button", disabled: "1" }, el("i", { class: "bi bi-plus-lg" }), " New entity");
  mapBtn.addEventListener("click", () => mapUnitsDialog([...selected], units.items, "add"));
  entBtn.addEventListener("click", () => openEntityForm(null, { process_ids: [...selected] }));
  const onSelect = () => {
    selInfo.textContent = selected.size ? `${selected.size} selected` : "";
    selStat.querySelector("strong").textContent = String(selected.size);
    mapBtn.disabled = !selected.size; entBtn.disabled = !selected.size;
  };
  const table = uTable({ rows, selectable: can, selected, onSelect, onRow: can ? (r) => mapUnitsDialog([r.id], units.items, "replace", r) : null,
    columns: [
      { key: "name", label: "Process / code", render: (r) => el("div", null, el("div", { class: "cell-title" }, r.name), el("div", { class: "muted small" }, r.ref)) },
      { key: "group", label: "Process group", render: (r) => r.group || el("span", { class: "muted" }, "-") },
      { key: "units", label: "Performed by units", sort: (r) => r.units.length, render: (r) => (r.units.length ? (r.units.length > 3 ? `${r.units.slice(0, 3).map((u) => u.name).join(", ")} +${r.units.length - 3}` : r.units.map((u) => u.name).join(", ")) : el("span", { class: "muted" }, "None")) },
      { key: "owner", label: "Owner", render: (r) => r.owner || el("span", { class: "muted" }, "-") },
      { key: "risks", label: "Linked risks", num: true, render: (r) => (r.risks ? String(r.risks) : el("span", { class: "muted" }, "-")) },
      { key: "mapping", label: "Mapping", render: (r) => uChip(r.mapping) },
    ] });
  body.append(el("section", { class: "card u-card" }, fb.root,
    can ? el("div", { class: "u-selbar" }, selInfo, el("div", { class: "actions" }, mapBtn, entBtn)) : null, table.root));
  if (d.summary.units_without_processes.length) {
    body.append(el("details", { class: "card u-details" }, el("summary", null, `Units with no processes (${d.summary.units_without_processes.length})`),
      el("div", { class: "u-chips" }, ...d.summary.units_without_processes.map((u) => el("button", { class: "u-chip warn as-btn", type: "button", onclick: () => openUnitPanel(u.id) }, u.name)))));
  }
  body.append(el("div", { class: "actions end u-foot" }, btn("Continue to entities", () => navigate("universe_entities"))));
  function paint() {
    const v = fb.values();
    const q = (v.q || "").toLowerCase();
    const list = rows.filter((r) => (!q || `${r.name} ${r.ref} ${r.owner || ""}`.toLowerCase().includes(q))
      && (!v.group || (r.group || r.name) === v.group) && (!v.unit || r.units.some((u) => u.name === v.unit)) && (!v.mapping || r.mapping === v.mapping));
    fb.setCount(`${list.length} of ${rows.length}`);
    table.set(list);
  }
  paint();
}

function mapUnitsDialog(processIds, units, mode, proc = null) {
  const picker = uPicker({ label: "Org units", items: units.map((o) => ({ id: o.id, label: o.name, sub: o.category, depth: o.depth })),
    selected: proc ? proc.units.map((u) => u.id) : [], placeholder: "Search units" });
  const err = el("div", { class: "field-error", role: "alert" });
  const save = el("button", { class: "btn", type: "button" }, "Save");
  const m = modal({ title: proc ? `Units performing ${proc.name}` : `Map ${processIds.length} process${processIds.length === 1 ? "" : "es"} to units`, width: 560,
    body: el("div", null, mode === "add" ? el("p", { class: "muted small" }, "The units are added to each selected process.") : null, picker.root, err),
    footer: el("div", { class: "actions end" }, el("button", { class: "btn secondary", type: "button", onclick: () => m.close() }, "Cancel"), save) });
  save.addEventListener("click", async () => {
    const ids = picker.values();
    if (mode === "add" && !ids.length) { err.textContent = "Choose at least one unit"; return; }
    save.disabled = true;
    try { await API.post("/api/audit-universe/processes/map", { process_ids: processIds, org_ids: ids, mode }); m.close(true); toast("Mapping saved"); renderUniverseProcesses(); }
    catch (e) { err.textContent = e.message; save.disabled = false; }
  });
}

// ---------------------------------------------------------------- 4. Entities

async function renderUniverseEntities() {
  clear(viewRoot);
  const can = UNIVERSE_EDIT();
  const head = el("div");
  const body = el("div", null, loadingState());
  viewRoot.append(head, body);
  let d;
  try { d = await API.get("/api/audit-universe/entities"); } catch (err) { clear(body); body.append(errorState(err, renderUniverseEntities)); return; }
  clear(body);
  const rows = d.items;
  const cols = [{ key: "code", label: "Code" }, { key: "name", label: "Entity" }, { key: "entity_type", label: "Type" },
    { key: "org_units", label: "Org units", csv: (r) => r.org_units.map((o) => o.name).join("; ") }, { key: "processes", label: "Processes", csv: (r) => r.processes.map((p) => p.name).join("; ") },
    { key: "owner", label: "Business owner" }, { key: "risks", label: "Linked risks" }, { key: "last_audited_at", label: "Last audit", csv: (r) => (r.last_audited_at ? r.last_audited_at.slice(0, 10) : "") },
    { key: "definition_status", label: "Status" }];
  head.append(uHead("Auditable entities", "Meaningful audit scopes, ready for the audit risk assessment.", el("div", { class: "actions" },
    uExport("auditable-entities", cols, rows), can ? btn("New entity", () => openEntityForm(null)) : null)));
  if (!rows.length) {
    body.append(emptyState({ icon: "bullseye", title: "No auditable entities yet", text: "Define entities from the units and processes you reviewed.",
      action: can ? btn("New entity", () => openEntityForm(null)) : null }));
    return;
  }
  const s = d.summary;
  const fb = filterBar({ placeholder: "Search entities", values: { status: "current" }, onChange: () => paint(),
    filters: [{ key: "type", label: "Type", options: [...new Set(rows.map((r) => r.entity_type))].sort() },
      { key: "status", label: "Status", options: [{ value: "current", label: "Current" }, "Draft", "Needs review", "Ready", "Retired"] },
      { key: "unit", label: "Unit", options: [...new Set(rows.flatMap((r) => r.org_units.map((o) => o.name)))].sort() }] });
  const setFilter = (v) => { const sel = fb.root.querySelector('select[aria-label="Status"]'); sel.value = v; sel.dispatchEvent(new Event("change")); };
  body.append(el("div", { class: "u-stats" },
    uStat(s.Ready, "Ready", "ok", () => setFilter("Ready")), uStat(s.Draft, "Draft", "", () => setFilter("Draft")),
    uStat(s["Needs review"], "Needs review", s["Needs review"] ? "warn" : "", () => setFilter("Needs review")), uStat(s.Retired, "Retired", "", () => setFilter("Retired"))));
  const names = (items) => (items.length ? (items.length > 2 ? `${items.slice(0, 2).map((i) => i.name).join(", ")} +${items.length - 2}` : items.map((i) => i.name).join(", ")) : el("span", { class: "muted" }, "-"));
  const table = uTable({ rows, onRow: (r) => openEntity(r.id),
    columns: [
      { key: "name", label: "Entity name", render: (r) => el("div", null, el("div", { class: "cell-title" }, r.name), el("div", { class: "muted small" }, r.code)) },
      { key: "entity_type", label: "Type" },
      { key: "org_units", label: "Org units", sort: (r) => r.org_units.map((o) => o.name).join(), render: (r) => names(r.org_units) },
      { key: "processes", label: "Processes", sort: (r) => r.processes.map((p) => p.name).join(), render: (r) => names(r.processes) },
      { key: "owner", label: "Business owner", render: (r) => r.owner || el("span", { class: "muted" }, "-") },
      { key: "risks", label: "Linked risks", num: true, render: (r) => (r.risks ? String(r.risks) : el("span", { class: "muted" }, "-")) },
      { key: "last_audited_at", label: "Last audit", render: (r) => (r.last_audited_at ? fmtDay(r.last_audited_at.slice(0, 10)) : el("span", { class: "muted" }, "Never")) },
      { key: "definition_status", label: "Status", render: (r) => uChip(r.definition_status) },
    ] });
  body.append(el("section", { class: "card u-card" }, fb.root, table.root));
  if (viewAllowed("riskassess")) {
    body.append(el("section", { class: "u-next" }, el("div", null, el("strong", null, "Next: Audit risk assessment"),
      el("div", { class: "muted small" }, `${s.Ready} ready entit${s.Ready === 1 ? "y" : "ies"}`)), btn("Open risk assessment", () => navigate("riskassess"))));
  }
  function paint() {
    const v = fb.values();
    const q = (v.q || "").toLowerCase();
    const list = rows.filter((r) => (!q || [r.name, r.code, ...r.org_units.map((o) => o.name), ...r.processes.map((p) => p.name)].join(" ").toLowerCase().includes(q))
      && (!v.type || r.entity_type === v.type) && (!v.unit || r.org_units.some((o) => o.name === v.unit))
      && (!v.status || (v.status === "current" ? r.definition_status !== "Retired" : r.definition_status === v.status)));
    fb.setCount(`${list.length} of ${rows.length}`);
    table.set(list);
  }
  paint();
}

// ---------------------------------------------------------------- 5. New / edit entity (a page, so nothing is lost by accident)

async function openEntityForm(entity = null, preset = {}) {
  if (!UNIVERSE_EDIT()) { toast("You cannot define auditable entities", "error"); return; }
  setActiveNav("universe_entities");
  clear(viewRoot);
  viewRoot.append(loadingState());
  let opt; let lib;
  try { [opt, lib] = await Promise.all([API.get("/api/audit-universe/entity-options"), safeGet("/api/object-library/options", { risks: [], controls: [] })]); }
  catch (err) { clear(viewRoot); viewRoot.append(errorState(err, () => openEntityForm(entity, preset))); return; }
  let own = { risks: [], controls: [] };
  if (entity && entity.links) own = entity.links.own;
  clear(viewRoot);
  setCrumbs(uCrumbs(entity ? entity.code : "New entity"));
  const unitName = Object.fromEntries(opt.units.map((u) => [u.id, u.name]));
  const procById = Object.fromEntries(opt.processes.map((p) => [p.id, p]));
  const v = {
    name: entity ? entity.name : "", entity_type: entity ? entity.entity_type : (preset.process_ids && preset.process_ids.length ? "Process + unit" : opt.types[0]),
    owner_email: entity ? entity.owner_email || "" : "", definition_status: entity ? entity.definition_status : "Draft",
    effective_from: entity ? entity.effective_from || "" : "", effective_to: entity ? entity.effective_to || "" : "",
    scope: entity ? entity.scope : "", objectives: entity ? entity.objectives : "", rationale: entity ? entity.rationale : "",
  };
  let dirty = false;
  let typeTouched = !!entity;
  const markDirty = () => { dirty = true; state.dirtyGuard = guard; paintPreview(); };
  const field = (label, control, { req = false, help = null, full = false } = {}) => el("div", { class: `form-field ${full ? "full" : ""}` },
    el("label", null, label, req ? el("span", { class: "req" }, " *") : null), control, help ? el("div", { class: "help" }, help) : null,
    el("div", { class: "field-error", "data-err": "" }));
  const input = (key, attrs = {}) => {
    const i = el(attrs.tag || "input", { type: attrs.type || "text", value: attrs.tag ? null : v[key], maxlength: attrs.max || null, rows: attrs.rows || null, "aria-label": attrs.label || key, name: key });
    if (attrs.tag === "textarea") i.value = v[key] || "";
    i.addEventListener("input", () => { v[key] = i.value; markDirty(); });
    return i;
  };
  const select = (key, options, label) => {
    const s = el("select", { "aria-label": label, name: key }, ...options.map((o) => { const val = typeof o === "object" ? o.value : o; const lab = typeof o === "object" ? o.label : o; return el("option", { value: val, selected: String(val) === String(v[key]) ? "1" : null }, lab); }));
    s.addEventListener("change", () => { v[key] = s.value; if (key === "entity_type") typeTouched = true; markDirty(); });
    return s;
  };
  const initialUnits = entity ? entity.org_units.map((o) => o.id) : (preset.org_ids || []);
  const initialProcs = entity ? entity.processes.map((p) => p.id) : (preset.process_ids || []);
  // Links the entity already has to a deactivated unit or an archived process stay listed, so they can be removed.
  const oldUnits = entity ? entity.org_units.filter((o) => !unitName[o.id]).map((o) => ({ id: o.id, label: `${o.name} (deactivated)` })) : [];
  const oldProcs = entity ? entity.processes.filter((p) => !procById[p.id]).map((p) => ({ id: p.id, label: `${p.name} (archived)` })) : [];
  oldUnits.forEach((o) => { unitName[o.id] = o.label; });
  oldProcs.forEach((p) => { procById[p.id] = { id: p.id, name: p.label, units: [] }; });
  const unitPick = uPicker({ label: "Org units", placeholder: "Search units", items: [...oldUnits, ...opt.units.map((u) => ({ id: u.id, label: u.name, sub: u.type, depth: u.depth }))], selected: initialUnits, onChange: () => markDirty() });
  const procPick = uPicker({ label: "Processes", placeholder: "Search processes", items: [...oldProcs, ...opt.processes.map((p) => ({ id: p.id, label: p.name, sub: p.units.length ? p.units.map((u) => unitName[u]).filter(Boolean).slice(0, 3).join(", ") : "not mapped" }))], selected: initialProcs, onChange: () => markDirty() });
  const riskPick = uPicker({ label: "Risks", placeholder: "Search risks", items: lib.risks.map((r) => ({ id: r.id, label: r.label, sub: r.category })), selected: own.risks.map((r) => r.id), onChange: () => markDirty(), empty: "No enterprise risks in the Risk Manager." });
  const ctrlPick = uPicker({ label: "Controls", placeholder: "Search controls", items: lib.controls.map((c) => ({ id: c.id, label: c.label })), selected: own.controls.map((c) => c.id), onChange: () => markDirty(), empty: "No standard controls yet." });
  const nameInput = input("name", { max: 255, label: "Entity name" });
  const preview = el("div", { class: "u-preview" });
  const formErr = el("div", { class: "field-error", role: "alert" });
  function suggestName() {
    if (v.name.trim()) return;
    const us = unitPick.values().map((i) => unitName[i]).filter(Boolean);
    const ps = procPick.values().map((i) => (procById[i] || {}).name).filter(Boolean);
    const s = [us.length === 1 ? us[0] : (us.length > 1 ? "Multiple units" : ""), ps.length === 1 ? ps[0] : (ps.length > 1 ? `${ps.length} processes` : "")].filter(Boolean).join(" — ");
    nameInput.placeholder = s || "e.g. Tema Port — Cargo clearance";
  }
  function paintPreview() {
    suggestName();
    const us = unitPick.values(); const ps = procPick.values();
    const derived = !us.length ? [...new Set(ps.flatMap((p) => (procById[p] || { units: [] }).units))] : [];
    if (!typeTouched) {
      const auto = us.length && ps.length ? "Process + unit" : (ps.length ? "Process" : (us.length ? "Org unit" : null));
      if (auto && opt.types.includes(auto) && v.entity_type !== auto) { v.entity_type = auto; const ts = viewRoot.querySelector("select[name=entity_type]"); if (ts) ts.value = auto; }
    }
    clear(preview);
    preview.append(...[el("h3", null, "Relationships"),
      el("dl", { class: "log-facts" },
        el("div", { class: "log-fact" }, el("dt", null, "Type"), el("dd", null, v.entity_type || "-")),
        el("div", { class: "log-fact" }, el("dt", null, "Org units"), el("dd", null, us.length ? us.map((i) => unitName[i]).join(", ") : (derived.length ? `${derived.map((i) => unitName[i]).join(", ")} (units performing the processes)` : el("span", { class: "text-danger" }, "Choose a unit or a mapped process")))),
        el("div", { class: "log-fact" }, el("dt", null, "Processes"), el("dd", null, ps.length ? ps.map((i) => (procById[i] || {}).name).join(", ") : "Whole unit")),
        el("div", { class: "log-fact" }, el("dt", null, "Business owner"), el("dd", null, (opt.people.find((p) => p.email === v.owner_email) || {}).name || "-")),
        el("div", { class: "log-fact" }, el("dt", null, "Risks · controls"), el("dd", null, `${riskPick.values().length} · ${ctrlPick.values().length}`))),
      v.definition_status === "Ready" && (!v.owner_email || v.scope.trim().length < 10) ? el("p", { class: "u-warn small" }, el("i", { class: "bi bi-info-circle" }), " Ready needs a business owner and a scope statement.") : null].filter(Boolean));
  }
  const people = [{ value: "", label: "- choose -" }, ...opt.people.map((p) => ({ value: p.email, label: p.name }))];
  if (v.owner_email && !opt.people.some((p) => p.email === v.owner_email)) people.push({ value: v.owner_email, label: v.owner_email });
  const statusOpts = entity && entity.definition_status === "Retired" ? ["Retired", ...opt.statuses] : opt.statuses;
  const save = el("button", { class: "btn", type: "button" }, entity ? "Save" : "Save entity");
  const cancel = el("button", { class: "btn secondary", type: "button" }, "Cancel");
  function guard(proceed) {
    if (!dirty || !document.body.contains(save)) { state.dirtyGuard = null; proceed(); return; }
    confirmDialog({ title: "Discard changes?", text: "Your changes to this entity are not saved.", confirmLabel: "Discard", danger: true }).then((r) => { if (r.ok) { dirty = false; state.dirtyGuard = null; proceed(); } });
  }
  const leave = () => (entity ? openEntity(entity.id) : navigate("universe_entities"));
  cancel.addEventListener("click", () => guard(() => { state.dirtyGuard = null; leave(); }));
  async function submit(allowDuplicate = false) {
    formErr.textContent = "";
    viewRoot.querySelectorAll("[data-err]").forEach((n) => { n.textContent = ""; });
    const body = {
      name: v.name.trim() || nameInput.placeholder.replace(/^e\.g\. .*/, "").trim(), entity_type: v.entity_type, org_ids: unitPick.values().map(Number), process_ids: procPick.values().map(Number),
      owner_email: v.owner_email || null, definition_status: v.definition_status, scope: v.scope, objectives: v.objectives, rationale: v.rationale,
      effective_from: v.effective_from || null, effective_to: v.effective_to || null, allow_duplicate: allowDuplicate,
    };
    if (body.name.length < 2) { showErr("name", "Enter the entity name"); return; }
    if (!body.org_ids.length && !body.process_ids.length) { showErr("org_ids", "Choose at least one org unit or process"); return; }
    save.disabled = true;
    try {
      const saved = entity ? await API.patch(`/api/auditable-entities/${entity.id}`, body) : await API.post("/api/auditable-entities", { ...body, risk_ids: riskPick.values().map(Number), control_ids: ctrlPick.values().map(Number) });
      if (entity) await API.put(`/api/auditable-entities/${entity.id}/links`, { risk_ids: riskPick.values().map(Number), control_ids: ctrlPick.values().map(Number) });
      dirty = false; state.dirtyGuard = null;
      toast(entity ? "Entity saved" : "Entity created");
      openEntity(saved.id);
    } catch (err) {
      save.disabled = false;
      if (err.status === 409 && /duplicate/i.test(err.message)) {
        const r = await confirmDialog({ title: "Possible duplicate", text: err.message, confirmLabel: "Save anyway" });
        if (r.ok) submit(true);
        return;
      }
      const fe = err.errors && err.errors[0];
      if (fe && fe.field) showErr(fe.field, fe.message || err.message); else formErr.textContent = err.message;
    }
  }
  function showErr(fieldName, msg) {
    const box = viewRoot.querySelector(`[data-field="${fieldName}"] [data-err]`);
    if (box) { box.textContent = msg; box.closest("[data-field]").scrollIntoView({ block: "center", behavior: "smooth" }); } else formErr.textContent = msg;
  }
  save.addEventListener("click", () => submit(false));
  const wrapField = (key, node) => { node.setAttribute("data-field", key); return node; };
  viewRoot.append(viewHeader(entity ? `Edit ${entity.name}` : "New auditable entity", el("div", { class: "actions" }, cancel, save), { back: () => cancel.click() }),
    el("div", { class: "u-form-grid" },
      el("section", { class: "card u-form" },
        el("div", { class: "grid cols-2 form-fields" },
          wrapField("name", field("Entity name", nameInput, { req: true, full: true })),
          wrapField("entity_type", field("Entity type", select("entity_type", opt.types.includes(v.entity_type) ? opt.types : [v.entity_type, ...opt.types], "Entity type"), { req: true })),
          wrapField("definition_status", field("Status", select("definition_status", statusOpts, "Status"))),
          wrapField("org_ids", field("Organizational units", unitPick.root, { full: true })),
          wrapField("process_ids", field("Processes", procPick.root, { full: true })),
          wrapField("owner_email", field("Business owner", select("owner_email", people, "Business owner"))),
          el("div", { class: "form-field u-dates" }, el("label", null, "Effective"), el("div", { class: "u-date-pair" }, wrapField("effective_from", el("div", null, input("effective_from", { type: "date", label: "Effective from" }), el("div", { class: "field-error", "data-err": "" }))),
            el("span", { class: "muted" }, "to"), wrapField("effective_to", el("div", null, input("effective_to", { type: "date", label: "Effective to" }), el("div", { class: "field-error", "data-err": "" }))))),
          wrapField("scope", field("Scope statement", input("scope", { tag: "textarea", rows: 3, max: 20000, label: "Scope statement" }), { full: true })),
          wrapField("objectives", field("Objectives", input("objectives", { tag: "textarea", rows: 3, max: 20000, label: "Objectives" }), { full: true })),
          wrapField("rationale", field("Rationale / notes", input("rationale", { tag: "textarea", rows: 2, max: 20000, label: "Rationale" }), { full: true }))),
        el("details", { class: "u-details", open: own.risks.length || own.controls.length ? "1" : null }, el("summary", null, "Risks and controls"),
          el("div", { class: "grid cols-2 form-fields" }, field("Risks", riskPick.root, { full: true }), field("Controls", ctrlPick.root, { full: true }))),
        formErr),
      el("aside", { class: "card u-side" }, preview)));
  paintPreview();
  setTimeout(() => nameInput.focus(), 30);
}

// ---------------------------------------------------------------- 6. Entity page and the risk assessment hand-off

async function openEntity(id, tab = "overview") {
  setActiveNav("universe_entities");
  clear(viewRoot);
  viewRoot.append(loadingState());
  let e;
  try { e = await API.get(`/api/auditable-entities/${id}`); } catch (err) { clear(viewRoot); viewRoot.append(errorState(err, () => openEntity(id))); return; }
  clear(viewRoot);
  const can = UNIVERSE_EDIT();
  const retired = e.definition_status === "Retired";
  const used = e.usage.audits + e.usage.assessments + e.usage.plans;
  const handoff = !viewAllowed("riskassess") ? null : e.open_assessment
    ? btn(`Open risk assessment`, () => openAssessment(e.open_assessment.id))
    : (e.definition_status === "Ready" && PLANNING_EDIT() ? btn("Start audit risk assessment", () => addAssessmentWizard({ entityIds: [e.id] })) : null);
  const more = can ? el("details", { class: "u-more" }, el("summary", { class: "btn secondary icon-only", "aria-label": "More actions" }, el("i", { class: "bi bi-three-dots" })),
    el("div", { class: "u-more-menu" },
      el("button", { type: "button", onclick: async () => {
        const goingOut = !retired;
        const r = await confirmDialog({ title: goingOut ? "Retire entity" : "Reactivate entity", confirmLabel: goingOut ? "Retire" : "Reactivate", danger: goingOut,
          text: goingOut ? (used ? `Used by ${e.usage.audits} audit(s), ${e.usage.assessments} assessment(s) and ${e.usage.plans} plan engagement(s). Its history stays; it is no longer offered for new work.` : "It is no longer offered for new work.") : "It returns as Draft." });
        if (!r.ok) return;
        try { await API.patch(`/api/auditable-entities/${e.id}`, { definition_status: goingOut ? "Retired" : "Draft" }); openEntity(e.id); } catch (err) { toast(err.message, "error"); }
      } }, retired ? "Reactivate" : "Retire"),
      !used ? el("button", { type: "button", class: "danger", onclick: async () => {
        const r = await confirmDialog({ title: "Delete entity", text: `${e.code} ${e.name} has never been used and will be removed.`, confirmLabel: "Delete", danger: true });
        if (!r.ok) return;
        try { await API.del(`/api/auditable-entities/${e.id}`); toast("Entity deleted"); navigate("universe_entities"); } catch (err) { toast(err.message, "error"); }
      } }, "Delete") : null)) : null;
  const layout = recordLayout({
    crumbs: uCrumbs(e.code), back: () => navigate("universe_entities"),
    title: e.name, ref: e.code, meta: [uChip(e.definition_status), el("span", { class: "u-chip muted" }, e.entity_type)],
    actions: [can && !retired ? btn("Edit", () => openEntityForm(e), "secondary") : null, handoff, more].filter(Boolean),
    tabs: [{ key: "overview", label: "Overview" }, { key: "assess", label: "Risk assessment" }, { key: "audits", label: "Audits" },
      { key: "findings", label: "Findings", count: e.open_findings || null }, { key: "history", label: "History" }],
    side: null,
    onTab: (key, pane) => paintEntityTab(key, pane, e, can),
  });
  setCrumbs(uCrumbs(e.code));
  viewRoot.append(layout.root);
  layout.select(tab);
}

async function paintEntityTab(key, pane, e, can) {
  const fact = (k, v) => el("div", { class: "log-fact" }, el("dt", null, k), el("dd", null, v || "-"));
  const text = (t) => (t ? el("p", { class: "u-text" }, t) : el("p", { class: "muted small" }, "Not recorded."));
  if (key === "overview") {
    const freq = el("select", { class: "compact", "aria-label": "Audit frequency", disabled: can && e.definition_status !== "Retired" ? null : "1" },
      el("option", { value: "0" }, `Default (${e.frequency_is_default ? e.frequency : "by rating"})`),
      ...e.frequencies.map((f) => el("option", { value: f.value, selected: !e.frequency_is_default && f.value === e.frequency_months ? "1" : null }, f.label)));
    freq.addEventListener("change", async () => {
      try { await API.patch(`/api/auditable-entities/${e.id}`, { audit_frequency_months: Number(freq.value) }); toast("Audit frequency saved"); openEntity(e.id); } catch (err) { toast(err.message, "error"); }
    });
    const via = e.links.processes;
    pane.append(el("div", { class: "u-detail-grid" },
      el("section", { class: "card" }, el("h3", null, "Definition"),
        el("dl", { class: "log-facts" }, fact("Type", e.entity_type), fact("Status", uChip(e.definition_status)), fact("Business owner", e.owner),
          fact("Effective", e.effective_from || e.effective_to ? `${e.effective_from ? fmtDay(e.effective_from) : "…"} – ${e.effective_to ? fmtDay(e.effective_to) : "open"}` : null),
          fact("Audit frequency", freq), fact("Last audit", e.last_audited_at ? fmtDay(e.last_audited_at.slice(0, 10)) : "Never"),
          fact("Next due", e.next_due ? fmtDay(e.next_due) : null), fact("Defined", e.defined_at ? fmtDay(e.defined_at.slice(0, 10)) : null))),
      el("section", { class: "card" }, el("h3", null, "Relationships"),
        el("h4", null, "Organizational units"), e.org_units.length ? el("ul", { class: "u-list" }, ...e.org_units.map((o) => el("li", null, o.path || o.name))) : el("p", { class: "muted small" }, "None."),
        el("h4", null, "Processes"), e.processes.length ? el("ul", { class: "u-list" }, ...e.processes.map((p) => el("li", null, p.name))) : el("p", { class: "muted small" }, "Whole unit.")),
      el("section", { class: "card u-span" }, el("h3", null, "Scope and objectives"),
        el("h4", null, "Scope"), text(e.scope), el("h4", null, "Objectives"), text(e.objectives), e.rationale ? el("h4", null, "Rationale") : null, e.rationale ? text(e.rationale) : null),
      el("section", { class: "card u-span" }, el("div", { class: "card-head" }, el("h3", null, `Risks and controls (${e.risk_counts.risks} · ${e.risk_counts.controls})`),
        can && e.definition_status !== "Retired" ? btn("Edit links", () => objectLinksForm("unit", e, () => openEntity(e.id)), "secondary") : null),
      el("h4", null, "On the entity"), linkList([...e.links.own.risks, ...e.links.own.controls], "None."),
      ...via.flatMap((pr) => [el("h4", null, `Through ${pr.process}`), linkList([...pr.risks, ...pr.controls], "None.")]))));
  }
  if (key === "assess") {
    const rows = await safeGet(`/api/auditable-entities/${e.id}/assessments`, []);
    const card = el("section", { class: "card u-handoff" });
    if (e.open_assessment) card.append(el("div", null, el("strong", null, `${e.open_assessment.ref} ${e.open_assessment.name}`), el("div", { class: "muted small" }, e.open_assessment.status)),
      btn("Open risk assessment", () => openAssessment(e.open_assessment.id)));
    else if (e.definition_status === "Ready") card.append(...[el("div", null, el("strong", null, "Ready for assessment"), el("div", { class: "muted small" }, "Scored in the audit risk assessment.")),
      PLANNING_EDIT() ? btn("Start audit risk assessment", () => addAssessmentWizard({ entityIds: [e.id] })) : null].filter(Boolean));
    else card.append(el("div", null, el("strong", null, "Not ready for assessment"), el("div", { class: "muted small" }, e.definition_status === "Retired" ? "Retired entities are not assessed." : "Set the status to Ready (business owner and scope required).")));
    pane.append(card);
    if (e.rating) pane.append(el("section", { class: "card" }, el("h3", null, "Latest completed assessment"), el("dl", { class: "log-facts" },
      fact("Risk rating", ratingBadge(e.rating)), fact("Overall score", e.score != null ? String(e.score) : null), fact("Assessed", e.assessed_at ? fmtDay(e.assessed_at.slice(0, 10)) : null))));
    pane.append(el("section", { class: "card" }, el("h3", null, "Assessments"), rows.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Assessment", "Status", "Overall score", "Risk rating", "Priority", "Completed"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rows.map((r) => el("tr", { tabindex: "0", onclick: () => openAssessment(r.id), onkeydown: (ev) => { if (ev.key === "Enter") openAssessment(r.id); } },
        el("td", { class: "col-wide" }, el("span", { class: "ref" }, r.ref), ` ${r.name}`), el("td", null, statusBadge(r.status)),
        el("td", { class: "num" }, r.status === "Completed" && r.overall != null ? String(r.overall) : "-"), el("td", null, r.status === "Completed" ? ratingBadge(r.rating) : el("span", { class: "muted" }, "-")),
        el("td", { class: "num" }, r.priority ? `#${r.priority}` : "-"), el("td", null, r.completed_at ? fmtDay(r.completed_at.slice(0, 10)) : "-"))))))
      : el("p", { class: "muted small" }, "Not assessed yet.")));
  }
  if (key === "audits") {
    const rows = await safeGet(`/api/auditable-entities/${e.id}/audits`, []);
    pane.append(el("section", { class: "card" }, el("h3", null, "Audits"), rows.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Audit", "Status", "Type", "Quarter"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...rows.map((r) => el("tr", r.id ? { tabindex: "0", onclick: () => openAudit(r.id) } : { class: "no-click" },
        el("td", { class: "col-wide" }, r.ref ? el("span", { class: "ref" }, r.ref) : null, ` ${r.title}`), el("td", null, statusBadge(r.status)),
        el("td", null, r.audit_type || "-"), el("td", null, r.quarter || "-"))))))
      : el("p", { class: "muted small" }, "No audits yet.")));
  }
  if (key === "findings") {
    const d = await safeGet(`/api/auditable-entities/${e.id}/findings`, { summary: {}, items: [] });
    pane.append(el("div", { class: "u-stats" }, uStat(d.summary.findings || 0, "Findings"), uStat(d.summary.open || 0, "Open", d.summary.open ? "warn" : ""),
      uStat(d.summary.high || 0, "Open high", d.summary.high ? "danger" : ""), uStat(d.summary.open_actions || 0, "Open actions")),
    el("section", { class: "card" }, d.items.length ? el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, ...["Finding", "Severity", "Status", "Remediation", "Audit"].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...d.items.map((f) => el("tr", { tabindex: "0", onclick: async () => { const full = await API.get(`/api/findings/${f.id}`); issueForm(full, f.audit_id, canWriteModule("audits"), () => openEntity(e.id, "findings")); } },
        el("td", { class: "col-wide" }, el("span", { class: "ref" }, `#${f.id}`), ` ${f.title}`), el("td", null, statusBadge(f.severity)), el("td", null, statusBadge(f.status)),
        el("td", { class: "small" }, f.remediation), el("td", { class: "small" }, f.audit))))))
      : el("p", { class: "muted small" }, "No findings.")));
  }
  if (key === "history") {
    const rows = await safeGet(`/api/auditable-entities/${e.id}/history`, []);
    pane.append(el("section", { class: "card" }, el("h3", null, "History"), rows.length ? el("ol", { class: "u-history" }, ...rows.map((h) => el("li", null,
      el("div", null, h.action), el("div", { class: "muted small" }, `${h.by} · ${fmtDate(h.at)}`)))) : el("p", { class: "muted small" }, "No changes recorded yet.")));
  }
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
      el("thead", null, el("tr", null, ...["ID", "Assessment factor", "Scoring", "Used in", ""].map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", null, ...list.map((f) => el("tr", { class: "no-click" },
        el("td", { class: "ref" }, f.ref), el("td", { class: "col-wide" }, el("div", { class: "cell-title" }, f.name), f.description ? el("div", { class: "muted small" }, f.description) : null),
        el("td", { class: "small" }, f.auto_source ? el("span", { class: "outcome ok" }, el("i", { class: "bi bi-magic" }), " Automatic") : "By the auditor"),
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

async function factorForm(f, reload) {
  const d = await safeGet("/api/assessment-factors", { auto_sources: [] });
  openForm({
    title: f ? `Edit ${f.ref}` : "Add assessment factor", draftable: false, width: 560,
    intro: f ? "Changes apply everywhere this factor is used." : null,
    fields: [
      { name: "name", label: "Name", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "description", label: "Description (what a high score means)", type: "textarea", maxLength: 5000, full: true },
      { name: "auto_source", label: "Scoring", type: "select", emptyLabel: "Scored by the auditor", full: true,
        options: d.auto_sources.map((a) => ({ value: a.value, label: `Automatic: ${a.label}` })),
        help: "Automatic factors are filled from GIAW records when an assessment is added, and can be refreshed or changed by hand." },
    ],
    initial: f || {}, submitLabel: f ? "Save" : "Add assessment factor",
    onSubmit: (v) => {
      const b = { name: v.name, description: v.description || "", auto_source: v.auto_source || null };
      return f ? API.patch(`/api/assessment-factors/${f.id}`, b) : API.post("/api/assessment-factors", b);
    },
    onDone: () => { toast("Assessment factor saved"); reload(); },
  });
}

// Add audit risk assessment: Name > Auditable entities > Assessment factors > Rating scale.
async function addAssessmentWizard(preset = {}) {
  const [uni, fac] = await Promise.all([safeGet("/api/audit-universe", { entities: [] }), safeGet("/api/assessment-factors", { items: [], scales: [], scale: "" })]);
  // Only entities defined as Ready go to the audit risk assessment (Audit universe > Entities).
  const active = uni.entities.filter((e) => e.definition_status === "Ready");
  if (!active.length) { toast("No auditable entity is Ready yet", "error"); navigate("universe_entities"); return; }
  const st = { step: 0, name: "", entities: new Set((preset.entityIds || []).filter((id) => active.some((e) => e.id === id))), factors: new Set(), scale: fac.scale };
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
    open ? btn("Refresh automatic scores", async () => {
      try { const r = await API.post(`/api/audit-risk-assessments/${a.id}/auto-score`, { overwrite: true }); toast(`${r.filled} automatic score(s) refreshed`); openAssessment(a.id, "score"); }
      catch (err) { toast(err.message, "error"); }
    }, "secondary") : null,
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
    el("thead", null, el("tr", null, el("th", { scope: "col" }, "Auditable entity"), ...a.factor_list.map((f) => el("th", { scope: "col", title: f.auto ? `${f.name} (scored automatically)` : f.name },
      f.name, f.auto ? el("i", { class: "bi bi-magic auto-ico", "aria-label": "scored automatically" }) : null)),
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
      { name: "entity_ids", label: "Auditable entities", type: "checklist", full: true, options: uni.entities.filter((e) => e.definition_status === "Ready" || a.rows.some((r) => r.entity_id === e.id)).map((e) => ({ value: e.id, label: e.name })) },
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


// Object library links: the enterprise risks (Risk Manager) of a process or entity and the standard controls
// (Frameworks & controls) that address them. Detailed scoping brings these into an audit.
async function objectLinksForm(kind, rec, onDone) {
  const [opts, current] = await Promise.all([safeGet("/api/object-library/options", { risks: [], controls: [] }),
    kind === "process" ? safeGet(`/api/processes/${rec.id}/links`, { risks: [], controls: [] }) : Promise.resolve(rec.links.own)]);
  openForm({
    title: `Risks and controls: ${rec.name}`, draftable: false, width: 760,
    intro: "Risks come from the Risk Manager register and controls from Frameworks & controls. Controls linked to a chosen risk there are brought in with it when an audit is scoped.",
    fields: [
      { name: "risk_ids", label: "Enterprise risks", type: "checklist", full: true, emptyLabel: "No risks in the Risk Manager register yet.",
        options: opts.risks.map((r) => ({ value: r.id, label: r.label })) },
      { name: "control_ids", label: "Standard controls", type: "checklist", full: true, emptyLabel: "No controls in Frameworks & controls yet.",
        options: opts.controls.map((c) => ({ value: c.id, label: c.label })) },
    ],
    initial: { risk_ids: current.risks.map((r) => r.id), control_ids: current.controls.map((c) => c.id) },
    submitLabel: "Save links",
    onSubmit: (v) => API.put(kind === "process" ? `/api/processes/${rec.id}/links` : `/api/auditable-entities/${rec.id}/links`,
      { risk_ids: (v.risk_ids || []).map(Number), control_ids: (v.control_ids || []).map(Number) }),
    onDone: () => { toast("Links saved"); onDone(); },
  });
}

function linkList(items, empty) {
  return items.length ? el("ul", { class: "plain-list" }, ...items.map((i) => el("li", null, el("span", { class: "ref" }, i.ref), ` ${i.title}`)))
    : el("p", { class: "muted small" }, empty);
}
