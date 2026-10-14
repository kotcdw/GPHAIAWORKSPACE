// GPHA Audit Workspace - configurable entities (Organizations): entity types, ports and hierarchy,
// admin-defined custom fields, and "where I work". Loaded after insight.js and before app.js.

const EntityCache = { at: 0, types: null, entities: [], defs: [] };

async function loadEntityConfig(force = false) {
  if (!force && EntityCache.types && Date.now() - EntityCache.at < 15000) return EntityCache;
  const [types, entities, defs] = await Promise.all([
    API.get("/api/organizations/types"),
    API.get("/api/organizations/entities"),
    API.get("/api/custom-fields?module=organizations"),
  ]);
  Object.assign(EntityCache, { at: Date.now(), types, entities, defs });
  return EntityCache;
}
function invalidateEntityConfig() { EntityCache.at = 0; }

// Admin-defined field definitions -> form field definitions (keys cf_<key>).
function customFieldDefs(defs) {
  return defs.map((d) => {
    const base = { key: `cf_${d.key}`, label: d.label, required: d.required, help: d.help || undefined };
    if (d.field_type === "longtext") return { ...base, type: "textarea", maxLength: 5000 };
    if (d.field_type === "number") return { ...base, type: "number", step: "any" };
    if (d.field_type === "date") return { ...base, type: "date" };
    if (d.field_type === "select") return { ...base, type: "select", options: d.options };
    if (d.field_type === "yesno") return { ...base, type: "select", options: [{ value: true, label: "Yes" }, { value: false, label: "No" }] };
    return { ...base, maxLength: 255 };
  });
}

function entityLabel(e) {
  return `${e.name}${e.category ? ` · ${e.category}` : ""}${e.port_name && !e.is_port ? ` (${e.port_name})` : ""}`;
}

async function prepareOrganizations(m, fresh = false) {
  const { types, entities, defs } = await loadEntityConfig(fresh);
  const ports = entities.filter((e) => e.is_port);
  m.filters = [
    { param: "category", label: "Type", options: types.categories },
    { param: "port_id", label: "Port / site", options: [
      ...(state.user.work_entity_id ? [{ value: "mine", label: "My port" }] : []),
      ...ports.map((p) => ({ value: p.id, label: p.name }))],
    apply: (params, v) => { if (v === "mine") params.set("mine", "true"); else params.set("port_id", v); } },
    { param: "status", label: "Status", options: ["Pending", "Approved"] },
  ];
  m.fields = [
    { key: "name", label: "Name", required: true },
    { key: "category", label: "Type", type: "select", options: types.categories,
      help: `${types.port_categories.join(" and ")} count as ports / sites` },
    { key: "parent_id", label: "Part of", type: "select", options: entities.map((e) => ({ value: e.id, label: entityLabel(e) })),
      help: "The port, office or department this entity sits under", display: (r) => (r.parent_name ? entityLink(r.parent_id, r.parent_name) : el("span", { class: "muted" }, "-")) },
    { key: "contact_name", label: "Contact name" },
    { key: "contact_email", label: "Contact email", type: "email" },
    { key: "contact_phone", label: "Contact phone" },
    ...customFieldDefs(defs),
    { key: "address", label: "Address / location", type: "textarea", maxLength: 2000 },
    ...(hasPerm("system.reference") ? [
      { key: "plan_destination", label: "Receives the approved Assurance Plan (distribution destination)", type: "checkbox",
        help: "Set up by administrators. Engagements can name this entity as their responsible site, and the GM Audit distributes its copy here.",
        display: (r) => (r.plan_destination ? `Yes - as "${r.destination_label || r.name}"` : "No") },
      { key: "destination_label", label: "Destination label", maxLength: 60,
        help: "How the destination appears in distribution, e.g. HQ, PIA Tema, PIA Takoradi. Leave blank to use the name." },
    ] : []),
    { key: "notes", label: "Notes", type: "textarea" },
  ];
}

// Plan destinations (HQ, PIA Tema ...): entities administrators marked as receiving the approved plan;
// until any are marked, the configured port / site types.
async function planSites() {
  const { entities } = await loadEntityConfig();
  const flagged = entities.filter((e) => e.plan_destination);
  return (flagged.length ? flagged : entities.filter((e) => e.is_port))
    .map((e) => ({ value: e.id, label: e.destination_label ? `${e.destination_label} (${e.name})` : e.name }));
}

function entityLink(id, name) {
  return el("a", { href: "#", onclick: (e) => { e.preventDefault(); openRecord("organizations", id); } }, name);
}

// Detail page extras: where the entity sits, what sits under it, and "this is where I work".
async function renderEntityExtras(panelEl, record, canWrite) {
  const mine = state.user.work_entity_id === record.id;
  const card = el("div", { class: "card" });
  panelEl.append(card);
  const head = el("div", { class: "card-head" }, el("h3", null, "Structure"), el("div", { class: "actions" },
    canWrite ? el("button", { class: "btn small secondary", onclick: () => createModal("organizations", { parent_id: record.id }) },
      el("i", { class: "bi bi-diagram-3" }), " Add entity under this") : null,
    el("button", { class: `btn small ${mine ? "secondary" : ""}`.trim(), disabled: mine ? "1" : null, onclick: async () => {
      try {
        const res = await API.patch("/api/auth/me", { work_entity_id: record.id });
        state.user = res.user; invalidateEntityConfig();
        toast(`Saved: you work at ${record.name}`); openRecord("organizations", record.id);
      } catch (err) { toast(err.message, "error"); }
    } }, el("i", { class: `bi bi-${mine ? "geo-alt-fill" : "geo-alt"}` }), mine ? " Where I work" : " Set as where I work")));
  card.append(head, el("dl", { class: "kv two-col" },
    el("dt", null, "Port / site"), el("dd", null, record.port_name
      ? (record.port_id === record.id ? el("span", null, badge("Port / site"), " this entity") : entityLink(record.port_id, record.port_name))
      : el("span", { class: "muted" }, "Not under a port")),
    el("dt", null, "Part of"), el("dd", null, record.parent_name ? entityLink(record.parent_id, record.parent_name) : el("span", { class: "muted" }, "Top level"))));
  if (!record.children) return;
  try {
    const kids = await API.get(`/api/organizations?parent_id=${record.id}`);
    card.append(el("h4", null, `Entities under ${record.name}`), dataTable(kids.items, [
      { key: "name", label: "Name" },
      { key: "category", label: "Type", render: (o) => o.category || "-" },
      { key: "children", label: "Under it", num: true },
      { key: "status", label: "Status", render: (o) => badge(o.status) },
    ], { onRow: (o) => openRecord("organizations", o.id), pageSize: 10, emptyText: "None." }));
  } catch (err) { card.append(el("div", { class: "muted" }, err.message)); }
}

// Profile card: where I work.
async function renderWorkplaceCard(container) {
  const card = el("div", { class: "card" }, el("h3", null, "Where I work"));
  container.append(card);
  let cfgData;
  try { cfgData = await loadEntityConfig(true); } catch (err) { card.append(el("div", { class: "muted" }, err.message)); return; }
  const ents = cfgData.entities;
  if (!ents.length) {
    card.append(el("p", { class: "muted" }, "No ports or offices are set up yet."),
      canWriteModule("organizations") ? el("button", { class: "btn small", onclick: () => createModal("organizations", { category: cfgData.types.port_categories[0] }) }, "Create a port") : null);
    return;
  }
  const ports = ents.filter((e) => e.is_port);
  const others = ents.filter((e) => !e.is_port);
  const sel = el("select", { id: "workplace", "aria-describedby": "workplace-help" },
    el("option", { value: "" }, "- not set -"),
    ports.length ? el("optgroup", { label: "Ports and sites" }, ...ports.map((e) => el("option", { value: e.id }, e.name))) : null,
    others.length ? el("optgroup", { label: "Departments, units and other entities" }, ...others.map((e) => el("option", { value: e.id }, entityLabel(e)))) : null);
  sel.value = state.user.work_entity_id ? String(state.user.work_entity_id) : "";
  const current = ents.find((e) => e.id === state.user.work_entity_id);
  const note = el("div", { class: "help muted", id: "workplace-help" }, current
    ? `Port / site: ${current.is_port ? current.name : current.port_name || "not under a port"}. Lists can then be filtered to "My port".`
    : "Choose your port or office (or your department). Lists can then be filtered to \"My port\".");
  const save = el("button", { class: "btn", onclick: async () => {
    try {
      const res = await API.patch("/api/auth/me", { work_entity_id: sel.value ? Number(sel.value) : null });
      state.user = res.user; invalidateEntityConfig(); toast("Workplace saved");
      card.remove(); renderWorkplaceCard(container);
    } catch (err) { toast(err.message, "error"); }
  } }, "Save");
  card.append(el("div", { class: "form-field" }, el("label", { for: "workplace" }, "Port, office or department"), sel, note),
    el("div", { class: "actions end" }, save));
}

// Configuration: custom fields for organizations (Admin).
async function renderCustomFieldsCard(container) {
  const card = el("div", { class: "card" });
  container.append(card);
  const types = { text: "Short text", longtext: "Long text", number: "Number", date: "Date", select: "Drop-down", yesno: "Yes / No" };
  const repaint = () => { card.remove(); invalidateEntityConfig(); renderCustomFieldsCard(container); };
  card.append(el("div", { class: "card-head" },
    el("h3", null, el("i", { class: "bi bi-input-cursor-text" }), " Organization fields"),
    el("button", { class: "btn small", onclick: () => customFieldForm(null, repaint) }, el("i", { class: "bi bi-plus-lg" }), " Add field")),
  el("p", { class: "muted small" }, "Extra inputs on every organization / entity form (for example TIN, region, staff count, contract end date). Retired fields stop appearing; values already entered are kept."));
  let defs = [];
  try { defs = await API.get("/api/custom-fields?module=organizations&include_inactive=true"); } catch (err) { card.append(el("div", { class: "muted" }, err.message)); return; }
  card.append(dataTable(defs, [
    { key: "label", label: "Field" },
    { key: "field_type", label: "Type", render: (d) => types[d.field_type] || d.field_type },
    { key: "options", label: "Choices", render: (d) => (d.options.length ? d.options.join(", ") : el("span", { class: "muted" }, "-")) },
    { key: "required", label: "Required", render: (d) => (d.required ? "Yes" : "No") },
    { key: "active", label: "Status", render: (d) => badge(d.active ? "Active" : "Inactive") },
  ], { onRow: (d) => customFieldForm(d, repaint), emptyText: "No custom fields yet.", pageSize: 10 }));
}

function customFieldForm(def, onDone) {
  const editing = !!def;
  openForm({
    key: editing ? `cfield:${def.id}` : "cfield:new", title: editing ? `Edit field · ${def.label}` : "Add organization field", width: 600, draftable: false,
    fields: [
      { name: "label", label: "Field name", required: true, maxLength: 100, singleLine: true },
      ...(editing ? [] : [{ name: "field_type", label: "Type", type: "select", required: true,
        options: [{ value: "text", label: "Short text" }, { value: "longtext", label: "Long text" }, { value: "number", label: "Number" },
          { value: "date", label: "Date" }, { value: "select", label: "Drop-down" }, { value: "yesno", label: "Yes / No" }] }]),
      { name: "options", label: "Choices (drop-down only)", type: "textarea", rows: 3, help: "One per line", full: true },
      { name: "help", label: "Help text", maxLength: 255, singleLine: true },
      { name: "sort_order", label: "Order", type: "number", min: 0, max: 999 },
      { name: "required", label: "Required", type: "checkbox" },
      ...(editing ? [{ name: "active", label: "Active", type: "checkbox" }] : []),
    ],
    initial: editing ? { ...def, options: def.options.join("\n") } : { field_type: "text", sort_order: 0, required: false },
    validate: (v) => {
      const type = editing ? def.field_type : v.field_type;
      const n = (v.options || "").split("\n").map((x) => x.trim()).filter(Boolean).length;
      return type === "select" && n < 2 ? { options: "Enter at least two choices" } : null;
    },
    submitLabel: editing ? "Save field" : "Add field",
    onSubmit: (v) => {
      const body = { ...v, options: (v.options || "").split("\n").map((x) => x.trim()).filter(Boolean), sort_order: v.sort_order || 0 };
      return editing ? API.patch(`/api/custom-fields/${def.id}`, body) : API.post("/api/custom-fields", { ...body, module: "organizations" });
    },
    onDone: () => { toast(editing ? "Field saved" : "Field added"); onDone(); },
  });
}
