// Frameworks & standard controls library, and the Scheduler (engagement timeline with double-booking warnings).

// ------------------------------------------------------------------ Frameworks & controls
async function renderLibrary(filters = state.libFilters || {}) {
  state.libFilters = filters;
  clear(viewRoot);
  const canEdit = hasPerm("method.library");
  const msg = el("div");
  let fws; let lib;
  try {
    const qs = new URLSearchParams();
    if (filters.framework_id) qs.set("framework_id", filters.framework_id);
    if (filters.process_area) qs.set("process_area", filters.process_area);
    if (filters.q) qs.set("q", filters.q);
    [fws, lib] = await Promise.all([API.get(`/api/library/frameworks${canEdit ? "?include_inactive=true" : ""}`),
      API.get(`/api/library/controls?${qs}${canEdit ? "&include_inactive=true" : ""}`)]);
  } catch (err) { viewRoot.append(viewHeader("Frameworks"), msg); notify(msg, err.message, "error"); return; }

  viewRoot.append(viewHeader("Frameworks", canEdit ? [
    el("button", { class: "btn small secondary", onclick: () => frameworkForm(null, fws.types) }, el("i", { class: "bi bi-plus-lg" }), " Framework"),
    fws.items.length ? el("button", { class: "btn small secondary", onclick: () => controlsImportDialog(fws.items) }, el("i", { class: "bi bi-upload" }), " Import CSV") : null,
    fws.items.length ? el("button", { class: "btn small", onclick: () => libraryControlForm(null, fws.items, lib) }, el("i", { class: "bi bi-plus-lg" }), " Standard control") : null,
  ] : null, { sub: "Frameworks GPHA audits against and their standard controls with suggested tests. Auditors add them to an engagement's risk and control matrix." }), msg);

  if (!fws.items.length) {
    viewRoot.append(el("div", { class: "card empty-state" }, el("i", { class: "bi bi-diagram-3 big-icon" }),
      el("h3", null, "No frameworks yet"),
      el("p", { class: "muted" }, canEdit
        ? "Add the frameworks you audit against - for example COSO Internal Control, ISO 31000, COBIT, the PFM Regulations or a GPHA procedure - then add or import their standard controls."
        : "The Audit Administrator has not set up any frameworks yet.")));
    return;
  }
  // Framework cards act as filters.
  const cards = el("div", { class: "fw-grid" }, ...fws.items.map((f) => el("button", {
    type: "button", class: `fw-card ${String(filters.framework_id) === String(f.id) ? "active" : ""} ${f.active ? "" : "retired"}`,
    onclick: () => renderLibrary({ ...filters, framework_id: String(filters.framework_id) === String(f.id) ? "" : f.id }),
  }, el("span", { class: "ref" }, f.code), el("strong", null, f.name),
  el("span", { class: "muted small" }, [f.framework_type, f.version].filter(Boolean).join(" · ") || "-"),
  el("span", { class: "small" }, `${f.controls} control${f.controls === 1 ? "" : "s"}${f.active ? "" : " · retired"}`),
  canEdit ? el("span", { class: "linkish small", onclick: (e) => { e.stopPropagation(); frameworkForm(f, fws.types); } }, "Edit") : null)));
  viewRoot.append(cards);

  const search = el("input", { type: "search", class: "compact", placeholder: "Search controls", value: filters.q || "", "aria-label": "Search controls" });
  search.addEventListener("keydown", (e) => { if (e.key === "Enter") renderLibrary({ ...filters, q: search.value.trim() }); });
  const area = el("select", { class: "compact", "aria-label": "Process area" }, el("option", { value: "" }, "All process areas"),
    ...lib.process_areas.map((a) => el("option", { value: a, selected: a === filters.process_area ? "1" : null }, a)));
  area.addEventListener("change", () => renderLibrary({ ...filters, process_area: area.value }));
  viewRoot.append(el("div", { class: "card" }, el("div", { class: "card-head" },
    el("h3", null, `Standard controls (${lib.items.length})`), el("div", { class: "actions" }, area, search)),
  dataTable(lib.items, [
    { key: "framework_code", label: "Framework" }, { key: "ref", label: "Ref" }, { key: "title", label: "Control" },
    { key: "process_area", label: "Process area" }, { key: "control_type", label: "Type" }, { key: "frequency", label: "Frequency" },
    { key: "is_key", label: "Key", render: (c) => (c.is_key ? "Key" : "-") },
    { key: "used_in", label: "Used in", render: (c) => (c.used_in ? `${c.used_in} engagement control(s)` : "-") },
    { key: "active", label: "Status", render: (c) => badge(c.active ? "Active" : "Retired") },
  ], { onRow: (c) => (canEdit ? libraryControlForm(c, fws.items, lib) : libraryControlView(c)), pageSize: 25, exportName: "standard-controls" })));
}

function frameworkForm(f, types) {
  openForm({
    title: f ? `Edit framework ${f.code}` : "New framework", key: f ? `fw:${f.id}` : "fw:new", width: 720, draftable: false,
    fields: [
      { name: "code", label: "Code", required: true, maxLength: 30, singleLine: true, help: "Short, e.g. COSO2013, ISO31000, PFMR2019" },
      { name: "name", label: "Name", required: true, maxLength: 200, singleLine: true },
      { name: "framework_type", label: "Kind", type: "select", options: types, emptyLabel: "-" },
      { name: "issuer", label: "Issued by", maxLength: 160, singleLine: true },
      { name: "version", label: "Version / year", maxLength: 40, singleLine: true },
      { name: "active", label: "Active (retire it to hide it from auditors)", type: "checkbox" },
      { name: "description", label: "Description and scope", type: "textarea", rows: 4, full: true },
    ],
    initial: f || { active: true },
    submitLabel: f ? "Save" : "Create",
    onSubmit: (v) => { const b = { ...v, framework_type: v.framework_type || "", issuer: v.issuer || "", version: v.version || "", description: v.description || "" };
      return f ? API.put(`/api/library/frameworks/${f.id}`, b) : API.post("/api/library/frameworks", b); },
    onDone: () => { toast("Framework saved"); renderLibrary(); },
  });
}

async function libraryControlForm(c, frameworks, lib) {
  const criteria = (await safeGet("/api/criteria?status=Active", { items: [] })).items;
  openForm({
    title: c ? `Edit ${c.framework_code} ${c.ref}` : "New standard control", key: c ? `libctl:${c.id}` : "libctl:new", width: 860, draftable: false,
    fields: [
      { name: "framework_id", label: "Framework", type: "select", required: true, options: frameworks.map((f) => ({ value: f.id, label: `${f.code} · ${f.name}` })) },
      { name: "ref", label: "Reference", required: true, maxLength: 40, singleLine: true, help: "The framework's own numbering" },
      { name: "title", label: "Control", required: true, maxLength: 255, singleLine: true, full: true },
      { name: "process_area", label: "Process area", maxLength: 100, singleLine: true, help: lib.process_areas.length ? `In use: ${lib.process_areas.join(", ")}` : "e.g. Procurement, Treasury, Marine operations" },
      { name: "control_type", label: "Type", type: "select", required: true, options: lib.control_types },
      { name: "nature", label: "Nature", type: "select", required: true, options: lib.natures },
      { name: "frequency", label: "Frequency", type: "select", required: true, options: lib.frequencies },
      { name: "is_key", label: "Key control", type: "checkbox" },
      { name: "active", label: "Active", type: "checkbox" },
      { name: "criterion_id", label: "Criterion (law, policy or standard)", type: "select", emptyLabel: "-",
        options: criteria.map((x) => ({ value: x.id, label: `${x.crit_ref} · ${x.title}` })), full: true },
      { name: "description", label: "What the control does (who, when, evidence)", type: "textarea", rows: 3, full: true },
      { name: "risk_statement", label: "Risk it addresses", type: "textarea", rows: 2, full: true },
      { name: "test_procedure", label: "Suggested test procedure", type: "textarea", rows: 4, full: true },
    ],
    initial: c ? { ...c, criterion_id: c.criterion_id || "" } : { framework_id: (state.libFilters || {}).framework_id || frameworks[0].id, control_type: "Preventive", nature: "Manual", frequency: "Monthly", is_key: true, active: true },
    submitLabel: c ? "Save" : "Add control",
    onSubmit: (v) => {
      const b = { ...v, framework_id: Number(v.framework_id), criterion_id: v.criterion_id ? Number(v.criterion_id) : null,
        description: v.description || "", process_area: v.process_area || "", risk_statement: v.risk_statement || "", test_procedure: v.test_procedure || "" };
      return c ? API.put(`/api/library/controls/${c.id}`, b) : API.post("/api/library/controls", b);
    },
    onDone: () => { toast("Standard control saved"); renderLibrary(); },
  });
}

function libraryControlView(c) {
  const m = modal({ title: `${c.framework_code} ${c.ref}`, width: 720,
    body: el("div", null, el("h3", null, c.title),
      el("p", { class: "muted small" }, [c.process_area, c.control_type, c.nature, c.frequency, c.is_key ? "Key" : ""].filter(Boolean).join(" · ")),
      longBlock("What the control does", c.description, "-"), longBlock("Risk it addresses", c.risk_statement, "-"),
      longBlock("Suggested test procedure", c.test_procedure, "-")),
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", onclick: () => m.close() }, "Close")) });
}

function controlsImportDialog(frameworks) {
  const sel = el("select", { id: "imp-fw" }, ...frameworks.map((f) => el("option", { value: f.id }, `${f.code} · ${f.name}`)));
  const file = el("input", { type: "file", id: "imp-file", accept: ".csv,text/csv" });
  const out = el("div");
  const m = modal({ drawer: true, title: "Import standard controls (CSV)", width: 640,
    body: el("div", null,
      el("p", { class: "muted small" }, "Columns: ref, title, description, process_area, risk_statement, control_type, nature, frequency, is_key, test_procedure. A ref that already exists in the framework is updated. Save from Excel as CSV UTF-8."),
      el("a", { href: "/api/library/controls/template.csv" }, el("i", { class: "bi bi-download" }), " Download the template"),
      el("div", { class: "form-field" }, el("label", { for: "imp-fw" }, "Framework"), sel),
      el("div", { class: "form-field" }, el("label", { for: "imp-file" }, "CSV file"), file), out),
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", onclick: () => m.close() }, "Close"),
      el("button", { class: "btn", onclick: async () => {
        if (!file.files.length) { toast("Choose a CSV file", "error"); return; }
        const fd = new FormData(); fd.append("file", file.files[0]);
        try {
          const r = await API.upload(`/api/library/frameworks/${sel.value}/import`, fd);
          clear(out);
          out.append(el("div", { class: `callout ${r.errors.length ? "warn" : "ok"}` }, el("i", { class: "bi bi-check2-circle" }),
            el("div", null, `${r.created} added, ${r.updated} updated.`, r.errors.length ? el("ul", null, ...r.errors.map((x) => el("li", null, x))) : null)));
          renderLibrary();
        } catch (err) { toast(err.message, "error"); }
      } }, "Import")) });
}

// Picker on an objective of the risk & control matrix.
async function fromLibraryDialog(o, reload) {
  let lib;
  try { lib = await API.get("/api/library/controls"); } catch (err) { toast(err.message, "error"); return; }
  if (!lib.items.length) { toast("The controls library is empty. Ask the Audit Administrator to set up frameworks.", "error"); return; }
  const chosen = new Set();
  const listBox = el("div", { class: "lib-pick" });
  const q = el("input", { type: "search", placeholder: "Search", class: "compact", "aria-label": "Search library" });
  const area = el("select", { class: "compact", "aria-label": "Process area" }, el("option", { value: "" }, "All process areas"), ...lib.process_areas.map((a) => el("option", { value: a }, a)));
  const paint = () => {
    clear(listBox);
    const term = q.value.trim().toLowerCase();
    lib.items.filter((c) => (!area.value || c.process_area === area.value)
      && (!term || `${c.ref} ${c.title} ${c.framework_code} ${c.risk_statement}`.toLowerCase().includes(term)))
      .forEach((c) => {
        const box = el("input", { type: "checkbox", id: `lp-${c.id}` });
        box.checked = chosen.has(c.id);
        box.addEventListener("change", () => { if (box.checked) chosen.add(c.id); else chosen.delete(c.id); });
        listBox.append(el("label", { class: "lib-item", for: `lp-${c.id}` }, box,
          el("div", null, el("div", null, el("span", { class: "ref" }, `${c.framework_code} ${c.ref}`), " ", el("strong", null, c.title)),
            el("div", { class: "muted small" }, [c.process_area, c.control_type, c.frequency, c.test_procedure ? "has test" : ""].filter(Boolean).join(" · ")))));
      });
  };
  q.addEventListener("input", paint); area.addEventListener("change", paint);
  const risks = o.risks.map((r) => { const b = el("input", { type: "checkbox", id: `lr-${r.id}`, value: r.id }); return [b, el("label", { class: "check", for: `lr-${r.id}` }, b, ` ${r.ref} ${r.title}`)]; });
  const tests = el("input", { type: "checkbox", id: "lp-tests", checked: "1" });
  paint();
  const m = modal({ drawer: true, title: `Add controls from the library to ${o.ref}`, width: 820,
    body: el("div", null, el("div", { class: "actions", style: "margin-bottom:8px" }, area, q), listBox,
      o.risks.length ? el("div", null, el("h4", null, "Map them to these risks"), ...risks.map((x) => x[1])) : el("p", { class: "muted small" }, "This objective has no risks yet; you can map the controls later."),
      el("label", { class: "check", for: "lp-tests" }, tests, " Create a test from each suggested procedure")),
    footer: el("div", { class: "form-foot-wrap" }, el("button", { class: "btn secondary", onclick: () => m.close() }, "Cancel"),
      el("button", { class: "btn", onclick: async () => {
        if (!chosen.size) { toast("Tick at least one control", "error"); return; }
        try {
          const r = await API.post(`/api/objectives/${o.id}/controls/from-library`, { library_control_ids: [...chosen],
            risk_ids: risks.filter((x) => x[0].checked).map((x) => Number(x[0].value)), create_tests: tests.checked });
          m.close(); toast(`${r.added.length} control(s) added`); reload();
        } catch (err) { toast(err.message, "error"); }
      } }, "Add to matrix")) });
}

// ------------------------------------------------------------------ Scheduler
const iso = (d) => d.toISOString().slice(0, 10);
const parseDay = (s) => new Date(`${String(s).slice(0, 10)}T00:00:00Z`);
const dayDiff = (a, b) => Math.round((parseDay(b) - parseDay(a)) / 86400000);

async function renderScheduler(range = state.schedRange) {
  const now = new Date();
  if (!range) {
    const q = Math.floor(now.getUTCMonth() / 3);
    range = { year: now.getUTCFullYear(), q: q + 1 };
  }
  state.schedRange = range;
  const start = range.q ? new Date(Date.UTC(range.year, (range.q - 1) * 3, 1)) : new Date(Date.UTC(range.year, 0, 1));
  const end = range.q ? new Date(Date.UTC(range.year, range.q * 3, 0)) : new Date(Date.UTC(range.year, 11, 31));
  clear(viewRoot);
  const canManage = hasPerm("oversight.resources", "plan.prepare");
  const msg = el("div");
  let t;
  try { t = await API.get(`/api/schedule?start=${iso(start)}&end=${iso(end)}`); }
  catch (err) { viewRoot.append(viewHeader("Scheduler"), msg); notify(msg, err.message, "error"); return; }

  const yearSel = el("select", { class: "compact", "aria-label": "Year" }, ...[-1, 0, 1, 2].map((d) => {
    const y = now.getUTCFullYear() + d; return el("option", { value: y, selected: y === range.year ? "1" : null }, String(y)); }));
  const qSel = el("select", { class: "compact", "aria-label": "Period" }, el("option", { value: 0, selected: range.q ? null : "1" }, "Whole year"),
    ...[1, 2, 3, 4].map((q) => el("option", { value: q, selected: range.q === q ? "1" : null }, `Q${q}`)));
  const go = () => renderScheduler({ year: Number(yearSel.value), q: Number(qSel.value) });
  yearSel.addEventListener("change", go); qSel.addEventListener("change", go);
  viewRoot.append(viewHeader("Scheduler", [yearSel, qSel,
    canManage ? el("button", { class: "btn small", onclick: () => bookingForm(null, t) }, el("i", { class: "bi bi-plus-lg" }), " Booking") : null],
  { sub: `${t.working_days} working days · engagements, auditors, leave and training on one timeline` }), msg);

  const people = t.people.filter((p) => p.bookings.length || !["super_admin", "admin"].includes(p.job_role));
  if (t.conflicts.length) {
    viewRoot.append(el("div", { class: "callout danger" }, el("i", { class: "bi bi-exclamation-octagon" }),
      el("div", null, el("strong", null, `${t.conflicts.length} double-booking${t.conflicts.length === 1 ? "" : "s"}: `),
        el("ul", null, ...t.conflicts.map((c) => el("li", null,
          `${(people.find((p) => p.user_id === c.user_id) || {}).name || "Auditor"}: ${c.what} overlap ${dayOnly(c.from)} to ${dayOnly(c.to)} (${c.days} working day${c.days === 1 ? "" : "s"})`))))));
  }

  const total = dayDiff(iso(start), iso(end)) + 1;
  const pos = (s, e) => {
    const a = Math.max(0, dayDiff(iso(start), s)); const b = Math.min(total - 1, dayDiff(iso(start), e));
    return { left: (100 * a) / total, width: Math.max((100 * (b - a + 1)) / total, 0.6) };
  };
  // Month (or week) scale.
  const scale = el("div", { class: "tl-scale" });
  for (let d = new Date(start); d <= end; d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))) {
    const monthEnd = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
    const p = pos(iso(d), iso(monthEnd > end ? end : monthEnd));
    scale.append(el("span", { style: `left:${p.left}%;width:${p.width}%` }, d.toLocaleString([], { month: "short", timeZone: "UTC" })));
  }
  const todayPos = dayDiff(iso(start), iso(now));
  const todayLine = todayPos >= 0 && todayPos < total ? el("div", { class: "tl-today", style: `left:${(100 * todayPos) / total}%`, title: "Today" }) : null;

  const rows = el("div", { class: "tl" });
  rows.append(el("div", { class: "tl-row tl-head" }, el("div", { class: "tl-label" }, ""), el("div", { class: "tl-track" }, scale)));
  // Engagements lane.
  t.engagements.forEach((e) => {
    const p = pos(e.planned_start, e.planned_end);
    const bar = el("button", { type: "button", class: "tl-bar eng", style: `left:${p.left}%;width:${p.width}%`,
      title: `${e.title} · ${dayOnly(e.planned_start)} - ${dayOnly(e.planned_end)}`, onclick: () => canManage && datesForm(e, t) }, e.title);
    rows.append(el("div", { class: "tl-row" }, el("div", { class: "tl-label" }, el("i", { class: "bi bi-briefcase" }), ` ${e.title}`,
      el("div", { class: "muted small" }, `${e.plan_ref} · ${e.planned_quarter} · ${e.booked_user_ids.length} booked`)),
    el("div", { class: "tl-track" }, todayLine ? todayLine.cloneNode() : null, bar)));
  });
  // People lanes.
  people.forEach((p) => {
    const clashIds = new Set(p.conflicts.flatMap((c) => [c.a, c.b]));
    const load = p.available_days ? Math.round((100 * p.engagement_days) / p.available_days) : 0;
    const track = el("div", { class: "tl-track" }, todayLine ? todayLine.cloneNode() : null);
    p.bookings.forEach((b) => {
      const q = pos(b.start_date, b.end_date);
      track.append(el("button", { type: "button", class: `tl-bar ${b.kind === "Engagement" ? "work" : "away"} ${clashIds.has(b.id) ? "clash" : ""}`,
        style: `left:${q.left}%;width:${q.width}%`, title: `${b.title} (${b.kind}${b.role ? `, ${b.role}` : ""}) · ${dayOnly(b.start_date)} - ${dayOnly(b.end_date)} · ${b.working_days} working days`,
        onclick: () => canManage && bookingForm(b, t) }, b.title));
    });
    rows.append(el("div", { class: `tl-row ${p.conflicts.length ? "has-clash" : ""}` },
      el("div", { class: "tl-label" }, el("strong", null, p.name),
        el("div", { class: "muted small" }, `${p.engagement_days} of ${p.available_days} days on engagements (${load}%)`,
          p.conflicts.length ? el("span", { class: "clash-chip" }, ` double-booked`) : null)),
      track));
  });
  viewRoot.append(el("div", { class: "card tl-card" }, el("div", { class: "tl-legend small muted" },
    el("span", { class: "lg eng" }), " Engagement window ", el("span", { class: "lg work" }), " On an engagement ",
    el("span", { class: "lg away" }), " Leave / training / other ", el("span", { class: "lg clash" }), " Double-booked"), rows));

  if (t.unscheduled.length) {
    viewRoot.append(el("div", { class: "card" }, el("h3", null, `Engagements without dates (${t.unscheduled.length})`),
      dataTable(t.unscheduled, [
        { key: "title", label: "Engagement" }, { key: "plan_ref", label: "Plan" }, { key: "planned_quarter", label: "Quarter" },
        { key: "budget_hours", label: "Budget hours" }, { key: "status", label: "Status", render: (e) => badge(e.status) },
      ], { onRow: (e) => canManage && datesForm(e, t), pageSize: 10, emptyText: "-" })));
  }
}

function datesForm(e, t) {
  openForm({
    title: `Fieldwork dates · ${e.title}`, key: `sched:eng:${e.id}`, width: 600, draftable: false,
    intro: `Planned for ${e.planned_quarter} ${e.fiscal_year} (${dayOnly(e.quarter_start)} to ${dayOnly(e.quarter_end)}). Moving it to another quarter is a plan change request.`,
    fields: [
      { name: "planned_start", label: "Start", type: "date", required: true },
      { name: "planned_end", label: "End", type: "date", required: true },
      { name: "book_lead", label: "Book the lead auditor for these dates", type: "checkbox" },
    ],
    initial: { planned_start: e.planned_start || String(e.quarter_start).slice(0, 10), planned_end: e.planned_end || "", book_lead: true },
    validate: (v) => (v.planned_end && v.planned_start && v.planned_end < v.planned_start ? { planned_end: "The end is before the start" } : null),
    submitLabel: "Save dates",
    onSubmit: (v) => API.put(`/api/schedule/engagements/${e.id}/dates`, v),
    onDone: (r) => { toast(r.conflicts && r.conflicts.length ? "Saved - the lead auditor is double-booked" : "Dates saved", r.conflicts && r.conflicts.length ? "error" : undefined); renderScheduler(); },
  });
  void t;
}

function bookingForm(b, t) {
  const engagements = [...t.engagements, ...t.unscheduled];
  openForm({
    title: b ? "Edit booking" : "New booking", key: b ? `sched:b:${b.id}` : "sched:b:new", width: 680, draftable: false,
    fields: [
      { name: "user_id", label: "Auditor", type: "select", required: true, options: t.people.map((p) => ({ value: p.user_id, label: p.name })) },
      { name: "kind", label: "Kind", type: "select", required: true, options: t.kinds },
      { name: "plan_engagement_id", label: "Engagement (for an engagement booking)", type: "select", emptyLabel: "-",
        options: engagements.map((e) => ({ value: e.id, label: `${e.title} (${e.planned_quarter} ${e.fiscal_year})` })), full: true },
      { name: "role", label: "Role on the engagement", type: "select", options: t.roles },
      { name: "title", label: "Description (leave, course, other work)", maxLength: 200, singleLine: true },
      { name: "start_date", label: "From", type: "date", required: true },
      { name: "end_date", label: "To", type: "date", required: true },
      { name: "hours", label: "Hours (optional)", type: "number", min: 0, max: 5000 },
      { name: "notes", label: "Notes", type: "textarea", rows: 2, full: true },
    ],
    initial: b ? { ...b, plan_engagement_id: b.plan_engagement_id || "" } : { kind: "Engagement", role: "Team member" },
    validate: (v) => (v.kind === "Engagement" && !v.plan_engagement_id ? { plan_engagement_id: "Choose the engagement" }
      : (v.end_date && v.start_date && v.end_date < v.start_date ? { end_date: "The end is before the start" } : null)),
    actions: b ? [el("button", { class: "btn danger-ghost", type: "button", onclick: async () => {
      try { await API.del(`/api/schedule/bookings/${b.id}`); closeFormPanel(); toast("Booking removed"); renderScheduler(); }
      catch (err) { toast(err.message, "error"); }
    } }, "Remove")] : [],
    submitLabel: b ? "Save" : "Book",
    onSubmit: (v) => {
      const body = { ...v, user_id: Number(v.user_id), plan_engagement_id: v.plan_engagement_id ? Number(v.plan_engagement_id) : null,
        role: v.role || "Team member", title: v.title || "", hours: v.hours === "" || v.hours == null ? null : Number(v.hours), notes: v.notes || "" };
      return b ? API.put(`/api/schedule/bookings/${b.id}`, body) : API.post("/api/schedule/bookings", body);
    },
    onDone: (r) => {
      if (r.conflicts && r.conflicts.length) toast(`Saved, but ${r.conflicts[0].what} overlap (${r.conflicts[0].days} working days)`, "error");
      else toast("Booking saved");
      renderScheduler();
    },
  });
}
