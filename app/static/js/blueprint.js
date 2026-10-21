// PROJECTBLUEPRINT additions: user groups, objective import / clone, strategy treatment and assurance,
// issue remediation and retest, next-cycle planning signals.
// Loaded after planning.js, grc.js and fieldwork.js; uses their helpers (btn, panel, modal, toast, openForm).

// ------------------------------------------------------------------ user groups (Users & access)

async function groupsDialog() {
  const body = el("div");
  const dlg = modal({ title: "Groups", body, width: 720,
    footer: el("div", { class: "actions" },
      el("button", { class: "btn secondary", type: "button", onclick: () => dlg.close() }, "Close"),
      el("button", { class: "btn", type: "button", onclick: () => groupForm(null, load) }, el("i", { class: "bi bi-plus" }), " New group")) });
  async function load() {
    clear(body);
    body.append(loadingState());
    let rows;
    try { rows = await API.get("/api/groups?include_inactive=true"); } catch (err) { clear(body); body.append(errorState(err, load)); return; }
    clear(body);
    if (!rows.length) { body.append(emptyState({ icon: "people", title: "No groups yet" })); return; }
    body.append(el("div", { class: "table-wrap" }, el("table", { class: "dense" },
      el("thead", null, el("tr", null, el("th", null, "Group"), el("th", null, "Owner"), el("th", { class: "num" }, "Members"), el("th", null, "Status"))),
      el("tbody", null, ...rows.map((g) => el("tr", { tabindex: "0", onclick: () => groupMembers(g.id, load), onkeydown: (e) => { if (e.key === "Enter") groupMembers(g.id, load); } },
        el("td", null, el("strong", null, g.name), g.description ? el("div", { class: "muted small" }, clip(g.description, 90)) : null),
        el("td", null, g.owner || "-"), el("td", { class: "num" }, String(g.members)),
        el("td", null, badge(g.is_active ? "Active" : "Inactive"))))))));
  }
  load();
}

function groupForm(g, after) {
  openForm({
    title: g ? `Edit ${g.name}` : "New group",
    key: g ? `group:edit:${g.id}` : "group:new",
    fields: [
      { name: "name", label: "Name", required: true, minLength: 2, maxLength: 120 },
      { name: "description", label: "Description", type: "textarea", maxLength: 2000, full: true },
    ],
    initial: g || {},
    submitLabel: g ? "Save" : "Create",
    onSubmit: (v) => (g ? API.patch(`/api/groups/${g.id}`, v) : API.post("/api/groups", v)),
    onDone: () => { toast(g ? "Group saved" : "Group created"); closeFormPanel(); if (after) after(); },
  });
}

async function groupMembers(id, after) {
  let g;
  let people;
  try { [g, people] = await Promise.all([API.get(`/api/groups/${id}`), API.get("/api/users/search?page_size=200&sort=name")]); }
  catch (err) { toast(err.message, "error"); return; }
  const chosen = new Set(g.member_list.map((m) => m.id));
  const search = el("input", { type: "search", class: "compact", placeholder: "Filter people", "aria-label": "Filter people" });
  const list = el("div", { class: "checklist" });
  const paint = () => {
    const q = search.value.trim().toLowerCase();
    list.replaceChildren(...people.items.filter((u) => !q || `${u.full_name || ""} ${u.username} ${u.email || ""}`.toLowerCase().includes(q))
      .map((u) => {
        const box = el("input", { type: "checkbox", value: String(u.id), checked: chosen.has(u.id) ? "1" : null });
        box.addEventListener("change", () => { if (box.checked) chosen.add(u.id); else chosen.delete(u.id); });
        return el("label", { class: "check" }, box, ` ${u.full_name || u.username}`, el("span", { class: "muted small" }, ` ${u.email || ""}`));
      }));
  };
  search.addEventListener("input", paint);
  paint();
  const dlg = modal({ title: g.name, width: 640,
    body: el("div", null, g.description ? el("p", { class: "muted" }, g.description) : null,
      el("p", { class: "muted small" }, "Groups are an audience for sharing. Each member's permissions still come from their role."),
      search, list),
    footer: el("div", { class: "actions" },
      g.is_active ? el("button", { class: "btn secondary danger", type: "button", onclick: async () => {
        const ok = await confirmDialog({ title: "Deactivate group", text: `${g.name} will no longer be offered for sharing. Its history is kept.`, confirmLabel: "Deactivate", danger: true });
        if (!ok.ok) return;
        try { await API.del(`/api/groups/${g.id}`); toast("Group deactivated"); dlg.close(); if (after) after(); } catch (err) { toast(err.message, "error"); }
      } }, "Deactivate") : el("button", { class: "btn secondary", type: "button", onclick: async () => {
        try { await API.patch(`/api/groups/${g.id}`, { is_active: true }); toast("Group reactivated"); dlg.close(); if (after) after(); } catch (err) { toast(err.message, "error"); }
      } }, "Reactivate"),
      el("button", { class: "btn secondary", type: "button", onclick: () => { dlg.close(); groupForm(g, after); } }, "Edit"),
      el("button", { class: "btn", type: "button", onclick: async () => {
        try { await API.put(`/api/groups/${g.id}/members`, { user_ids: [...chosen] }); toast("Members saved"); dlg.close(); if (after) after(); }
        catch (err) { toast(err.message, "error"); }
      } }, "Save members")) });
}

// ------------------------------------------------------------------ Issues: Remediation and Retest

let REMEDIATION_OPTIONS = null;
async function remediationOptions() {
  if (!REMEDIATION_OPTIONS) REMEDIATION_OPTIONS = await safeGet("/api/findings/remediation-options", { statuses: [], retest_results: ["Effective", "Not effective"], retest_required_severities: [] });
  return REMEDIATION_OPTIONS;
}

function issueRemediationActions(f) {
  if (!f) return [];
  return [
    el("button", { class: "btn secondary", type: "button", onclick: () => { closeFormPanels(); openIssue(f.id, "remediation"); } },
      el("i", { class: "bi bi-tools" }), " Follow-up & Remediation"),
    isStaff() ? el("button", { class: "btn secondary", type: "button", onclick: () => { closeFormPanels(); openIssue(f.id, "retest"); } },
      el("i", { class: "bi bi-arrow-repeat" }), " Retest") : null,
  ].filter(Boolean);
}

// ------------------------------------------------------------------ Next-cycle planning signals

async function planSignalsDialog() {
  const year = el("input", { type: "number", class: "compact", min: "2000", max: "2100", value: String(currentFiscalYear() + 1), "aria-label": "Next fiscal year" });
  const body = el("div");
  const load = async () => {
    clear(body);
    body.append(loadingState());
    let s;
    try { s = await API.get(`/api/assurance-plans/next-cycle-signals?fiscal_year=${encodeURIComponent(year.value)}`); }
    catch (err) { clear(body); body.append(errorState(err, load)); return; }
    clear(body);
    const cf = s.carry_forward;
    body.append(el("p", { class: "muted small" }, s.basis_plan ? `Based on ${s.basis_plan.ref} (FY ${s.basis_plan.fiscal_year}, ${s.basis_plan.status}). ${s.note}` : s.note));
    body.append(el("div", { class: "kpi-row" },
      ...[["Open actions", cf.open_actions], ["Overdue actions", cf.overdue_actions], ["Open High issues", cf.open_high_findings], ["Open audits", cf.open_audits]]
        .map(([l, n]) => el("div", { class: "kpi" }, el("div", { class: "kpi-value" }, String(n)), el("div", { class: "kpi-label" }, l)))));
    body.append(panel("Strategic risks", s.risks.length ? dataTable(s.risks, [
      { key: "ref", label: "Risk", render: (r) => `${r.ref} ${r.title}` },
      { key: "residual_level", label: "Residual", render: (r) => `${r.residual_level} (${r.residual_score})${r.above_target ? " · above target" : ""}` },
      { key: "overall_assurance", label: "Assurance", render: (r) => (r.overall_assurance === null ? "-" : `${r.overall_assurance}%`) },
      { key: "signal", label: "Signal" },
    ], { pageSize: 10 }) : el("p", { class: "muted" }, "No high or above-target strategic risks.")));
    body.append(panel("High-risk entities not covered", s.uncovered_entities.length ? dataTable(s.uncovered_entities, [
      { key: "name", label: "Entity" }, { key: "location_name", label: "Location" }, { key: "risk_rating", label: "Risk", render: (u) => `${u.risk_rating} (${u.risk_score})` }], { pageSize: 10 }) : el("p", { class: "muted" }, "None.")));
    body.append(panel("Deferred or cancelled projects", s.deferred_engagements.length ? dataTable(s.deferred_engagements, [
      { key: "title", label: "Project" }, { key: "quarter", label: "Quarter" }, { key: "status", label: "Status" }, { key: "hours", label: "Hours", num: true }], { pageSize: 10 })
      : el("p", { class: "muted" }, "None.")));
  };
  year.addEventListener("change", load);
  const dlg = modal({ title: "Next-cycle planning signals", width: 900, body: el("div", null, field("Next fiscal year", year), body),
    footer: el("button", { class: "btn secondary", type: "button", onclick: () => dlg.close() }, "Close") });
  load();
}
