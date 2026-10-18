// GPHA Audit Workspace - roles & responsibilities: permission-aware navigation, the Roles & permissions
// matrix (Platform Administrator), audit programmes (Audit Administrator), evidence requests (auditors and
// auditees), the governance portal (Audit Committee) and the port portfolio (PIA / GM Audit).
// Loaded after entities.js and before app.js.

function hasPerm(...perms) {
  const have = state.perms || [];
  return perms.some((p) => have.includes(p));
}
function isCommittee() { return state.user && state.user.role === "Committee"; }

// Views a Committee (read-only governance) account may open.
const COMMITTEE_VIEWS = ["portal", "dashboard", "governance", "portfolio", "committee", "analytics", "qaip", "profile"];
const CONFIG_PERMS = ["system.config", "system.workflow", "system.reference", "method.reporting", "method.audit_types", "method.plan_config", "grc.manage", "governance.charter"];

const GRC_VIEW_PERMS = ["grc.view", "grc.manage", "grc.risk", "grc.compliance", "grc.policy", "grc.policy_approve", "grc.assets"];

function viewAllowed(view) {
  if (typeof appEnabledForView === "function" && !appEnabledForView(view)) return false;
  if (isCommittee()) return COMMITTEE_VIEWS.includes(view);
  const rules = {
    roles: ["system.roles", "system.users"],
    configuration: CONFIG_PERMS,
    governance: ["governance.view", "oversight.reporting", "oversight.portfolio"],
    portfolio: ["oversight.port", "oversight.portfolio", "governance.view"],
    programs: null,
    platform: ["system.technical", "system.config"],
    automations: ["system.automation"],
    apps: ["system.superadmin"],
    risk: GRC_VIEW_PERMS, compliance: GRC_VIEW_PERMS, policies: GRC_VIEW_PERMS, assets: GRC_VIEW_PERMS,
  };
  if (["programs", "practice", "library", "scheduler", "issues", "orgstructure", "processes", "riskassess", "statustracker", "results", "robots", "audittypes", "universe", "universe_units", "universe_processes", "universe_entities"].includes(view)) return state.user.role !== "Auditee";
  if (view === "logs" || view === "backups") return hasPerm("system.technical");
  if (view === "imports") return hasPerm("system.users", "system.reference", "method.library", "followup.manage", "grc.risk");
  if (view === "users") return hasPerm("system.users");
  if (view === "admin") return typeof adminAreasAllowed === "function" && adminAreasAllowed().length > 0;
  return rules[view] ? hasPerm(...rules[view]) : true;
}

function applyNavPermissions() {
  document.querySelectorAll("#sidebarNav button[data-view]").forEach((b) => {
    const g = typeof hostGroup === "function" ? hostGroup(b.dataset.view) : null;
    const allowed = g && g.host === b.dataset.view ? hostTabsAllowed(g).length > 0 : viewAllowed(b.dataset.view);
    if (!allowed) b.classList.add("hidden");
    else if (b.dataset.perm !== undefined || isCommittee()) b.classList.remove("hidden");
  });
  // Section headings with nothing visible under them are hidden too.
  // A module group with no visible pages disappears.
  document.querySelectorAll("#sidebarNav .nav-group").forEach((g) => {
    g.classList.toggle("hidden", ![...g.querySelectorAll("button[data-view]")].some((b) => !b.classList.contains("hidden")));
  });
}

// ==================================================================== Roles & permissions

async function renderRolesPage(tab = state.rolesTab || "matrix") {
  state.rolesTab = tab;
  clear(viewRoot);
  const msg = el("div");
  let cat;
  try { cat = await API.get("/api/roles"); } catch (err) { viewRoot.append(viewHeader("Roles & permissions"), msg); notify(msg, err.message, "error"); return; }
  const canEdit = cat.can_edit;
  viewRoot.append(viewHeader("Roles & permissions"), msg);

  // Compact role tiles: name, people and permissions; the full description is on hover.
  viewRoot.append(el("div", { class: "role-tiles" }, ...cat.roles.map((r) => el("div", { class: `role-tile role-${r.code}`, title: r.description },
    el("span", { class: "role-icon" }, el("i", { class: `bi bi-${r.icon}` })),
    el("div", { class: "role-tile-text" },
      el("strong", null, r.name, r.locked ? el("i", { class: "bi bi-lock-fill role-lock", title: "Fixed: always every permission" }) : null),
      el("span", { class: "muted small role-counts" },
        el("span", { title: `${r.users} active user${r.users === 1 ? "" : "s"}` }, el("i", { class: "bi bi-person", "aria-hidden": "true" }), ` ${r.users}`),
        el("span", { title: `${r.permissions.length} permissions` }, el("i", { class: "bi bi-key", "aria-hidden": "true" }), ` ${r.permissions.length}`))),
    r.customised ? el("span", { class: "cfg-dot", title: "Changed from the standard permissions" }) : null))));

  viewRoot.append(tabBar([{ key: "matrix", label: "Permission matrix" }, { key: "modules", label: "Access by module" }, { key: "people", label: "People by role" }], tab, (k) => renderRolesPage(k)));
  if (tab === "people") return rolesPeople(cat);
  if (tab === "modules") return renderAccessMatrix();

  const work = Object.fromEntries(cat.roles.map((r) => [r.code, new Set(r.permissions)]));
  const saveRow = el("tr", { class: "no-click" }, el("td", null, ""),
    ...cat.roles.map((r) => el("td", { class: "center" }, canEdit && !r.locked ? el("div", { class: "actions center" },
      el("button", { class: "btn small", "data-save": r.code, disabled: "1", title: `Save ${r.name}`, onclick: async () => {
        try { await API.put(`/api/roles/${r.code}/permissions`, { permissions: [...work[r.code]] }); toast(`${r.name} saved`); renderRolesPage("matrix"); }
        catch (err) { toast(err.message, "error"); }
      } }, "Save"),
      r.customised ? el("button", { class: "btn small secondary", title: "Back to the standard permissions", onclick: async () => {
        if (!window.confirm(`Reset ${r.name} to the standard permissions?`)) return;
        try { await API.post(`/api/roles/${r.code}/reset`); toast(`${r.name} reset`); renderRolesPage("matrix"); } catch (err) { toast(err.message, "error"); }
      } }, "Reset") : null) : (r.locked ? el("span", { class: "muted small" }, el("i", { class: "bi bi-lock-fill" }), " Fixed") : null))));
  const q = el("input", { type: "search", class: "compact", placeholder: "Filter permissions", "aria-label": "Filter permissions" });
  const body = el("tbody");
  const groups = [...new Set(cat.permissions.map((p) => p.group))];
  groups.forEach((g) => {
    body.append(el("tr", { class: "no-click group-row", "data-group": g }, el("th", { colspan: String(cat.roles.length + 1) }, g)));
    cat.permissions.filter((p) => p.group === g).forEach((p) => {
      body.append(el("tr", { class: "no-click perm-row", "data-text": `${p.label} ${p.code}`.toLowerCase(), "data-group": g },
        el("td", null, p.label,
          p.super_only ? el("i", { class: "bi bi-lock-fill perm-flag", title: "Super Administrator only" }) : null,
          p.cae_only ? el("i", { class: "bi bi-star-fill perm-flag", title: "Managers only with the GM Audit (CAE) approval level" }) : null),
        ...cat.roles.map((r) => {
          const fixed = r.locked || p.super_only || !canEdit;
          const box = el("input", { type: "checkbox", "aria-label": `${r.name}: ${p.label}`, checked: work[r.code].has(p.code) ? "1" : null, disabled: fixed ? "1" : null });
          box.addEventListener("change", () => {
            if (box.checked) work[r.code].add(p.code); else work[r.code].delete(p.code);
            const btn = saveRow.querySelector(`[data-save="${r.code}"]`);
            if (btn) btn.disabled = false;
          });
          return el("td", { class: "center" }, box);
        })));
    });
  });
  q.addEventListener("input", () => {
    const t = q.value.trim().toLowerCase();
    body.querySelectorAll(".perm-row").forEach((tr) => tr.classList.toggle("hidden", !!t && !tr.dataset.text.includes(t)));
    body.querySelectorAll(".group-row").forEach((tr) => tr.classList.toggle("hidden", !!t && ![...body.querySelectorAll(`.perm-row[data-group="${CSS.escape(tr.dataset.group)}"]`)].some((x) => !x.classList.contains("hidden"))));
  });
  viewRoot.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Permission matrix"), el("div", { class: "actions" }, q)),
    el("div", { class: "table-wrap matrix-wrap" }, el("table", { class: "perm-matrix" },
      el("thead", null, el("tr", null, el("th", null, "Permission"), ...cat.roles.map((r) => el("th", { class: "center", title: r.description }, el("i", { class: `bi bi-${r.icon}` }), el("div", null, r.name))))),
      body, el("tfoot", null, saveRow)))));
}

function rolesPeople(cat) {
  const wrap = el("div", { class: "two-cols" });
  cat.roles.forEach((r) => {
    const list = el("div", { class: "member-list" });
    if (!r.members.length) list.append(el("p", { class: "muted small" }, "Nobody has this role."));
    r.members.forEach((m) => list.append(el("div", { class: `member-row ${m.active ? "" : "inactive"}` },
      el("div", { class: "pi-main" }, el("strong", null, m.name), el("div", { class: "muted small" }, [m.username, m.approval_level ? approvalLabel(m.approval_level) : null, m.active ? null : "inactive"].filter(Boolean).join(" · "))),
      cat.can_assign && m.id !== state.user.id ? el("div", { class: "member-actions" }, roleAssignControls({ id: m.id, username: m.username, job_role: r.code, review_level: m.approval_level }, cat, () => renderRolesPage("people"))) : null)));
    wrap.append(panel(`${r.name} (${r.members.length})`, list));
  });
  viewRoot.append(wrap);
}

const APPROVAL_LEVELS = [["Unit Head", "Unit Head"], ["Manager", "Audit Manager"], ["PIA", "PIA"], ["CAE", "GM Audit (CAE)"]];
function approvalLabel(v) { const f = APPROVAL_LEVELS.find(([k]) => k === v); return f ? f[1] : v; }

// Role and approval-level controls for one user (used on Roles & permissions and in user management).
function roleAssignControls(u, cat, onChanged) {
  const options = cat.roles.map((r) => ({ code: r.code, name: r.name, assignable: cat.can_appoint_admins || !["super_admin", "admin"].includes(r.code) }));
  const blocked = !cat.can_appoint_admins && ["super_admin", "admin"].includes(u.job_role);
  const sel = el("select", { class: "compact", "aria-label": `Role of ${u.username}`, disabled: blocked ? "1" : null },
    ...options.map((r) => el("option", { value: r.code, selected: r.code === u.job_role ? "1" : null, disabled: r.assignable ? null : "1" }, r.name)));
  const lvl = el("select", { class: "compact", "aria-label": `Approval level of ${u.username}`, title: "Review chain: Unit Head, then Audit Manager, then PIA; the GM Audit (CAE) approves and distributes" },
    ...APPROVAL_LEVELS.map(([v, t]) => el("option", { value: v, selected: (u.review_level || "Manager") === v ? "1" : null }, t)));
  lvl.classList.toggle("hidden", u.job_role !== "manager");
  const send = async () => {
    try {
      const body = { job_role: sel.value };
      if (sel.value === "manager") body.approval_level = lvl.value;
      const res = await API.patch(`/api/users/${u.id}/job-role`, body);
      toast(`${u.username} is now ${res.job_role_name}${res.review_level ? ` (${approvalLabel(res.review_level)})` : ""}${res.sessions_ended ? "; signed out" : ""}`);
      if (onChanged) onChanged();
    } catch (err) { toast(err.message, "error"); sel.value = u.job_role; }
  };
  sel.addEventListener("change", () => { lvl.classList.toggle("hidden", sel.value !== "manager"); send(); });
  lvl.addEventListener("change", send);
  return el("span", { class: "inline-row" }, sel, lvl);
}

// Job-role select used in user management.
let JOB_ROLE_OPTIONS = null;
let ROLE_CATALOGUE = null;
async function jobRoleSelect(u, onChanged) {
  if (!ROLE_CATALOGUE) {
    try { ROLE_CATALOGUE = await API.get("/api/roles"); } catch { ROLE_CATALOGUE = { roles: [], can_assign: false, can_appoint_admins: false }; }
    JOB_ROLE_OPTIONS = ROLE_CATALOGUE.roles.map((r) => ({ code: r.code, name: r.name, tier: r.tier, assignable: ROLE_CATALOGUE.can_appoint_admins || !["super_admin", "admin"].includes(r.code) }));
  }
  if (u.id === state.user.id) return el("span", null, (JOB_ROLE_OPTIONS.find((r) => r.code === u.job_role) || {}).name || u.job_role_name || "-");
  return roleAssignControls(u, ROLE_CATALOGUE, onChanged);
}

// ==================================================================== Audit programmes


async function renderProgramsPage() {
  clear(viewRoot);
  const msg = el("div");
  const canEdit = hasPerm("method.programs");
  viewRoot.append(viewHeader("Project Library", canEdit ? el("button", { class: "btn", onclick: () => programEditor(null) },
    el("i", { class: "bi bi-plus-lg" }), " New programme") : null,
  { sub: "Reusable work programmes: objectives, risks, controls and test steps that can be applied to an audit's risk & control matrix" }), msg);
  let rows;
  try { rows = await API.get(`/api/audit-programs?include_retired=${canEdit}`); } catch (err) { notify(msg, err.message, "error"); return; }
  viewRoot.append(el("div", { class: "card" }, dataTable(rows, [
    { key: "prog_ref", label: "Ref", render: (p) => el("span", { class: "ref" }, p.prog_ref) },
    { key: "name", label: "Programme" },
    { key: "audit_type", label: "Audit type", render: (p) => p.audit_type || "-" },
    { key: "step_count", label: "Steps", num: true },
    { key: "times_used", label: "Used", num: true },
    { key: "status", label: "Status", render: (p) => badge(p.status) },
  ], { onRow: (p) => programEditor(p), exportName: "audit-programmes.csv", emptyText: "No programmes yet." })));
}

async function programEditor(p) {
  const canEdit = hasPerm("method.programs");
  let types = [];
  try { types = (await loadEntityConfig()).types.audit_types || []; } catch { /* optional */ }
  const steps = (p ? p.steps : []).map((s) => ({ ...s }));
  if (!steps.length) steps.push({ objective: "", risk: "", likelihood: 3, impact: 3, control: "", control_type: "Preventive", test_type: "Operating Effectiveness", procedure: "" });
  const name = el("input", { value: p ? p.name : "", maxlength: "255", disabled: canEdit ? null : "1", "aria-label": "Programme name" });
  const type = el("select", { disabled: canEdit ? null : "1", "aria-label": "Audit type" }, el("option", { value: "" }, "Any type"),
    ...types.map((t) => el("option", { value: t, selected: p && p.audit_type === t ? "1" : null }, t)));
  const desc = el("textarea", { rows: "2", maxlength: "8000", disabled: canEdit ? null : "1", "aria-label": "Description" }, p ? p.description : "");
  const list = el("div", { class: "step-list" });
  const sel = (opts, v, onc) => { const s = el("select", { disabled: canEdit ? null : "1" }, ...opts.map((o) => el("option", { value: o, selected: o === v ? "1" : null }, o))); s.addEventListener("change", () => onc(s.value)); return s; };
  const inp = (v, onc, attrs = {}) => { const i = el("input", { value: v ?? "", disabled: canEdit ? null : "1", ...attrs }); i.addEventListener("input", () => onc(i.value)); return i; };
  function paint() {
    clear(list);
    steps.forEach((s, i) => list.append(el("div", { class: "step card" },
      el("div", { class: "card-head" }, el("strong", null, `Step ${i + 1}`),
        canEdit && steps.length > 1 ? el("button", { class: "btn small danger-ghost", type: "button", onclick: () => { steps.splice(i, 1); paint(); } }, "Remove") : null),
      el("div", { class: "grid-2" },
        field("Objective", inp(s.objective, (v) => { s.objective = v; }, { maxlength: "255" })),
        field("Risk", inp(s.risk, (v) => { s.risk = v; }, { maxlength: "255" })),
        field("Likelihood (1-5)", inp(s.likelihood, (v) => { s.likelihood = Number(v); }, { type: "number", min: "1", max: "5" })),
        field("Impact (1-5)", inp(s.impact, (v) => { s.impact = Number(v); }, { type: "number", min: "1", max: "5" })),
        field("Control", inp(s.control, (v) => { s.control = v; }, { maxlength: "255" })),
        field("Control type", sel(CONTROL_TYPES, s.control_type, (v) => { s.control_type = v; })),
        field("Test type", sel(TEST_TYPES, s.test_type, (v) => { s.test_type = v; }))),
      field("Test procedure", (() => { const t = el("textarea", { rows: "2", maxlength: "4000", disabled: canEdit ? null : "1" }, s.procedure || ""); t.addEventListener("input", () => { s.procedure = t.value; }); return t; })()))));
  }
  paint();
  const body = el("div", null, field("Name", name), field("Audit type", type), field("Description", desc),
    el("h4", null, "Steps"), list,
    canEdit ? el("button", { class: "btn small secondary", type: "button", onclick: () => {
      const last = steps[steps.length - 1] || {};
      steps.push({ objective: last.objective || "", risk: "", likelihood: 3, impact: 3, control: "", control_type: "Preventive", test_type: "Operating Effectiveness", procedure: "" });
      paint();
    } }, el("i", { class: "bi bi-plus" }), " Add step") : null);
  const m = modal({
    title: p ? `${p.prog_ref} · ${p.name}` : "New audit programme", width: 900, body,
    footer: canEdit ? el("div", { class: "actions" },
      p ? el("button", { class: "btn secondary", onclick: async () => {
        try { await API.patch(`/api/audit-programs/${p.id}`, { status: p.status === "Active" ? "Retired" : "Active" }); m.close(); renderProgramsPage(); }
        catch (err) { toast(err.message, "error"); }
      } }, p.status === "Active" ? "Retire" : "Reactivate") : null,
      el("button", { class: "btn", onclick: async () => {
        const payload = { name: name.value.trim(), audit_type: type.value || null, description: desc.value,
          steps: steps.filter((s) => s.objective || s.risk || s.control || s.procedure) };
        try {
          if (p) await API.patch(`/api/audit-programs/${p.id}`, payload); else await API.post("/api/audit-programs", payload);
          toast("Programme saved"); m.close(); renderProgramsPage();
        } catch (err) { toast(err.message, "error"); }
      } }, "Save programme")) : null,
  });
}

// "Apply programme" on an audit's risk & control matrix.
async function applyProgramDialog(audit, onDone) {
  let rows;
  try { rows = await API.get("/api/audit-programs"); } catch (err) { toast(err.message, "error"); return; }
  if (!rows.length) { toast("No audit programmes yet - an Audit Administrator creates them under Audit programmes", "error"); return; }
  const preferred = rows.filter((r) => !audit.audit_type || !r.audit_type || r.audit_type === audit.audit_type);
  const pick = el("select", { "aria-label": "Programme" }, ...(preferred.length ? preferred : rows).map((r) =>
    el("option", { value: r.id }, `${r.prog_ref} · ${r.name} (${r.step_count} steps${r.audit_type ? ` · ${r.audit_type}` : ""})`)));
  const m = modal({ title: "Apply an audit programme", body: el("div", null,
    el("p", { class: "muted small" }, audit.workflow === "Workplan"
      ? "The programme's objectives and risks are added to this audit's Workplan, and each step becomes a procedure addressing its risk. Objectives with the same name are reused."
      : "The programme's objectives, risks, controls and test steps are added to this audit's risk & control matrix. Objectives with the same name are reused."),
    field("Programme", pick)),
  footer: el("button", { class: "btn", onclick: async () => {
    try {
      const res = await API.post(`/api/audits/${audit.id}/apply-program/${pick.value}`);
      toast(res.procedures !== undefined ? `Added ${res.objectives} objective(s), ${res.risks} risk(s), ${res.procedures} procedure(s)`
        : `Added ${res.objectives} objective(s), ${res.risks} risk(s), ${res.controls} control(s), ${res.tests} test step(s)`);
      m.close(); if (onDone) onDone();
    } catch (err) { toast(err.message, "error"); }
  } }, "Apply") });
}

// ==================================================================== Evidence requests

function evidenceColumns(withAudit) {
  return [
    { key: "request_ref", label: "Ref", render: (r) => el("span", { class: "ref" }, r.request_ref) },
    ...(withAudit ? [{ key: "audit_title", label: "Audit" }] : []),
    { key: "requested_by_name", label: "Requester", render: (r) => r.requested_by_name || "-" },
    { key: "title", label: "Description" },
    { key: "target_label", label: "Linked to", render: (r) => (r.target_label ? el("span", { class: "small" }, el("i", { class: "bi bi-link-45deg", "aria-hidden": "true" }), ` ${r.target_label}`) : el("span", { class: "muted" }, "Audit")) },
    { key: "assignee_name", label: "Owner", render: (r) => r.assignee_name || "-" },
    { key: "due_date", label: "Due", render: (r) => (r.due_date ? el("span", { class: r.overdue ? "text-danger" : null }, fmtDay(r.due_date.slice(0, 10)), r.overdue ? " · overdue" : "") : "-") },
    { key: "status", label: "Status", render: (r) => badge(r.status) },
    { key: "files", label: "Files", num: true, render: (r) => String(r.files.length), sortValue: (r) => r.files.length },
  ];
}

async function renderEvidencePage(scope = "mine") {
  clear(viewRoot);
  const msg = el("div");
  const staff = isStaff();
  const tabs = staff ? [{ key: "mine", label: "Raised by me" }, { key: "open", label: "All open" }, { key: "overdue", label: "Overdue" }] : null;
  viewRoot.append(viewHeader("Requests", null,
    { sub: staff ? "Documents requested from auditees - review what was submitted and accept or return it"
      : "Documents the audit team has asked you for - upload the files and submit" }), msg);
  if (tabs) viewRoot.append(tabBar(tabs, scope, (k) => renderEvidencePage(k)));
  let rows;
  try { rows = await API.get(`/api/evidence-requests?scope=${scope}`); } catch (err) { notify(msg, err.message, "error"); return; }
  viewRoot.append(el("div", { class: "card" }, dataTable(rows, evidenceColumns(true),
    { onRow: (r) => evidenceDetail(r, () => renderEvidencePage(scope)), exportName: "evidence-requests.csv",
      emptyText: staff ? "No evidence requests." : "Nothing has been requested from you." })));
}

async function renderEvidenceTab(panelEl, audit, canWrite) {
  const reload = () => { clear(panelEl); renderEvidenceTab(panelEl, audit, canWrite); };
  let rows;
  try { rows = await API.get(`/api/audits/${audit.id}/evidence-requests`); }
  catch (err) { panelEl.append(el("div", { class: "empty" }, err.message)); return; }
  const add = canWrite && hasPerm("audit.evidence") && audit.status !== "Closed"
    ? el("button", { class: "btn small", onclick: () => requestEvidenceDialog(audit.id, null, reload) }, el("i", { class: "bi bi-plus-lg" }), " Request evidence") : null;
  panelEl.append(el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", null, "Evidence requests"), add),
    dataTable(rows, evidenceColumns(false), { onRow: (r) => evidenceDetail(r, reload), emptyText: "No evidence has been requested for this audit." })));
}

function evidenceDetail(r, onDone) {
  const files = el("ul", { class: "file-list" }, ...r.files.map((f) => el("li", null,
    el("a", { href: `/api/evidence-files/${f.id}/download` }, el("i", { class: "bi bi-paperclip" }), ` ${f.filename}`),
    el("span", { class: "muted small" }, ` · ${(f.size_bytes / 1024).toFixed(1)} KB · ${fmtDate(f.uploaded_at)}`))));
  if (!r.files.length) files.append(el("li", { class: "muted" }, "No files yet."));
  const body = el("div", null,
    el("dl", { class: "kv two-col" },
      el("dt", null, "Audit"), el("dd", null, r.audit_title || `#${r.audit_id}`),
      el("dt", null, "Requested by"), el("dd", null, `${r.requested_by_name || "-"} · ${fmtDate(r.requested_at)}`),
      el("dt", null, "Owner"), el("dd", null, r.assignee_name || "-"),
      el("dt", null, "Linked to"), el("dd", null, r.target_label || "The audit"),
      r.cc && r.cc.length ? el("dt", null, "CC") : null, r.cc && r.cc.length ? el("dd", null, r.cc.map((c) => c.name).join(", ")) : null,
      el("dt", null, "Due"), el("dd", null, r.due_date ? fmtDate(r.due_date) : "-", r.overdue ? " (overdue)" : ""),
      el("dt", null, "Status"), el("dd", null, badge(r.status))),
    r.description ? el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Details"), el("div", { class: "lf-value" }, r.description)) : null,
    r.review_comment ? el("div", { class: "callout warn" }, el("i", { class: "bi bi-chat-left-text" }), el("div", null, el("strong", null, "Reviewer: "), r.review_comment)) : null,
    r.response ? el("div", { class: "long-field" }, el("div", { class: "lf-label" }, "Response"), el("div", { class: "lf-value" }, r.response)) : null,
    el("h4", null, "Files"), files);
  let footer = null;
  let m;
  const done = () => { m.close(); onDone(); };
  if (r.can_respond) {
    const file = el("input", { type: "file", "aria-label": "Evidence file" });
    const resp = el("textarea", { rows: "3", maxlength: "8000", "aria-label": "Response", placeholder: "Notes for the auditor (or why something is not available)" }, r.response || "");
    body.append(field("Add a file", file), field("Response", resp));
    footer = el("div", { class: "actions" },
      el("button", { class: "btn secondary", onclick: async () => {
        if (!file.files.length) { toast("Choose a file first", "error"); return; }
        const fd = new FormData(); fd.append("file", file.files[0]);
        try { const res = await API.upload(`/api/evidence-requests/${r.id}/files`, fd); toast("File uploaded"); m.close(); evidenceDetail(res, onDone); }
        catch (err) { toast(err.message, "error"); }
      } }, el("i", { class: "bi bi-upload" }), " Upload"),
      el("button", { class: "btn", onclick: async () => {
        try { await API.post(`/api/evidence-requests/${r.id}/submit`, { response: resp.value }); toast("Submitted to the audit team"); done(); }
        catch (err) { toast(err.message, "error"); }
      } }, "Submit"));
  } else if (r.can_review) {
    const comment = el("textarea", { rows: "2", maxlength: "4000", "aria-label": "Review comment", placeholder: "Required when returning" });
    const asWp = el("input", { type: "checkbox", checked: "1", id: "erWp" });
    body.append(field("Comment", comment), el("label", { class: "check", for: "erWp" }, asWp, " File accepted documents as working papers"));
    const decide = (decision) => async () => {
      try { await API.post(`/api/evidence-requests/${r.id}/review`, { decision, comment: comment.value, file_as_working_paper: asWp.checked }); toast(`Evidence ${decision.toLowerCase()}`); done(); }
      catch (err) { toast(err.message, "error"); }
    };
    footer = el("div", { class: "actions" }, el("button", { class: "btn secondary", onclick: decide("Returned") }, "Return for more"),
      el("button", { class: "btn", onclick: decide("Accepted") }, "Accept"));
  } else if (isStaff() && hasPerm("audit.evidence") && ["Requested", "Returned"].includes(r.status)) {
    const rem = el("select", { class: "compact", "aria-label": "Reminder" },
      ...[["", "No reminder"], ["Daily", "Daily reminder"], ["Weekly", "Weekly reminder"]].map(([v, l]) => el("option", { value: v, selected: (r.reminder || "") === v ? "1" : null }, l)));
    rem.addEventListener("change", async () => {
      try { await API.patch(`/api/evidence-requests/${r.id}/reminder`, { reminder: rem.value || null }); toast("Reminder updated"); } catch (err) { toast(err.message, "error"); }
    });
    body.append(el("h4", null, "Notification"), el("div", { class: "actions" }, rem,
      el("button", { class: "btn small secondary", type: "button", onclick: async () => {
        try { await API.post(`/api/evidence-requests/${r.id}/remind`); toast("Reminder sent"); } catch (err) { toast(err.message, "error"); }
      } }, el("i", { class: "bi bi-bell" }), " Send reminder now"),
      r.last_reminded_at ? el("span", { class: "muted small" }, `Last reminded ${fmtDate(r.last_reminded_at)}`) : null));
    footer = el("button", { class: "btn danger-ghost", onclick: async () => {
      const ok = await confirmDialog({ title: "Cancel evidence request", text: `${r.request_ref} will be cancelled and the owner will no longer be asked for it.`, confirmLabel: "Cancel request", danger: true });
      if (!ok.ok) return;
      try { await API.post(`/api/evidence-requests/${r.id}/cancel`); toast("Request cancelled"); done(); } catch (err) { toast(err.message, "error"); }
    } }, "Cancel request");
  }
  m = modal({ title: `${r.request_ref} · ${r.title}`, body, footer, width: 720 });
}

// ==================================================================== Governance portal

async function renderGovernance() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Governance portal", null,
    { sub: "Approved plans, issued reports and headline indicators for the Audit Committee and executive reviewers (read-only)" }), msg);
  let g;
  try { g = await API.get("/api/governance/overview"); } catch (err) { notify(msg, err.message, "error"); return; }
  const k = g.kpis;
  viewRoot.append(el("div", { class: "stats" },
    stat(`${k.plan_completion_pct}%`, "Current plan completed"),
    stat(k.reports_issued, "Reports issued"),
    stat(k.open_findings, "Open findings", `${k.open_high_findings} high / critical`, k.open_high_findings ? "warn" : ""),
    stat(k.open_actions, "Open remediation actions"),
    stat(k.overdue_actions, "Overdue actions", null, k.overdue_actions ? "danger" : ""),
    stat(`${k.actions_closed_on_time_pct}%`, "Actions closed on time")));
  viewRoot.append(panel("Approved Assurance Plans", g.plans.length ? el("div", null, ...g.plans.map((p) => el("details", { class: "table-toggle", open: p === g.plans[0] ? "1" : null },
    el("summary", null, el("strong", null, `FY${p.fiscal_year} · ${p.title}`), " ", badge(p.status),
      el("span", { class: "muted small" }, ` · ${p.completed}/${p.total} completed${p.committee_reference ? ` · Committee approval ${p.committee_reference}` : ""}`)),
    dataTable(p.engagements, [
      { key: "title", label: "Engagement" }, { key: "planned_quarter", label: "Quarter" },
      { key: "budget_hours", label: "Budget (h)", num: true }, { key: "status", label: "Status", render: (e) => badge(e.status) }],
    { pageSize: 50 }))))
    : el("div", { class: "empty" }, "No approved plan yet.")));
  viewRoot.append(panel("Issued audit reports", dataTable(g.reports, [
    { key: "report_ref", label: "Ref", render: (r) => el("span", { class: "ref" }, r.report_ref) },
    { key: "title", label: "Report" },
    { key: "rating", label: "Opinion", render: (r) => (r.rating ? badge(r.rating) : "-") },
    { key: "issued_at", label: "Issued", render: (r) => fmtDate(r.issued_at) },
    { key: "findings", label: "Findings", render: (r) => Object.entries(r.findings).map(([x, n]) => `${n} ${x}`).join(" · ") || "-" },
    { key: "id", label: "", render: (r) => el("div", { class: "actions end" },
      el("a", { class: "btn small secondary", href: `/api/reports/${r.id}/export.docx` }, el("i", { class: "bi bi-file-earmark-word" }), " Word"),
      el("a", { class: "btn small secondary", href: `/api/reports/${r.id}/print`, target: "_blank", rel: "noopener" }, el("i", { class: "bi bi-printer" }), " Print")) },
  ], { exportName: "issued-reports.csv", emptyText: "No reports issued yet." })));
}

// ==================================================================== Port portfolio

async function renderPortfolio() {
  clear(viewRoot);
  const msg = el("div");
  viewRoot.append(viewHeader("Port portfolio", null,
    { sub: "Audits, open findings and remediation by port. A PIA sees their own port; the GM Audit and the Committee see all ports." }), msg);
  let rows;
  try { rows = await API.get("/api/portfolio/ports"); } catch (err) { notify(msg, err.message, "error"); return; }
  const detail = el("div");
  viewRoot.append(el("div", { class: "card" }, dataTable(rows, [
    { key: "port_name", label: "Port" },
    { key: "audits", label: "Audits", num: true },
    { key: "audits_by_status", label: "By status", render: (r) => Object.entries(r.audits_by_status).map(([s, n]) => `${n} ${s}`).join(" · ") || "-" },
    { key: "open_findings", label: "Open findings", num: true },
    { key: "open_high_findings", label: "High / critical", num: true },
    { key: "open_actions", label: "Open actions", num: true },
    { key: "overdue_actions", label: "Overdue", num: true, render: (r) => el("span", { class: r.overdue_actions ? "text-danger" : null }, String(r.overdue_actions)) },
    { key: "reports_issued", label: "Reports issued", num: true },
  ], { onRow: (r) => (r.port_id ? showPort(r.port_id, detail) : null), exportName: "port-portfolio.csv", emptyText: "No ports configured - mark an entity type as a port in Configuration." })), detail);
  if (rows.length === 1 && rows[0].port_id) showPort(rows[0].port_id, detail);
}

async function showPort(portId, holder) {
  clear(holder);
  let p;
  try { p = await API.get(`/api/portfolio/ports/${portId}`); } catch (err) { toast(err.message, "error"); return; }
  holder.append(panel(`${p.port_name}: audits`, dataTable(p.audits_list, [
    { key: "id", label: "Ref", render: (a) => el("span", { class: "ref" }, `AUD-${String(a.id).padStart(4, "0")}`) },
    { key: "title", label: "Audit" }, { key: "audit_type", label: "Type", render: (a) => a.audit_type || "-" },
    { key: "status", label: "Status", render: (a) => badge(a.status) }, { key: "open_findings", label: "Open findings", num: true },
  ], { onRow: isCommittee() ? null : (a) => openAudit(a.id), emptyText: "No audits for this port yet." })));
  holder.scrollIntoView({ behavior: "smooth", block: "start" });
}


// Access by module: who may view, create, edit, approve, export and configure each part of the workspace.
async function renderAccessMatrix() {
  const host = el("div", { class: "card" });
  viewRoot.append(host);
  host.append(loadingState("Building the access matrix…"));
  let m;
  try { m = await API.get("/api/roles/matrix"); } catch (err) { clear(host); host.append(errorState(err, () => renderRolesPage("modules"))); return; }
  clear(host);
  const ACT = { view: "View", create: "Create", edit: "Edit", approve: "Approve / sign", export: "Export", configure: "Configure" };
  let role = state.matrixRole && m.roles.some((r) => r.code === state.matrixRole) ? state.matrixRole : m.roles[0].code;
  const sel = el("select", { class: "compact", "aria-label": "Role" }, ...m.roles.map((r) => el("option", { value: r.code, selected: r.code === role ? "1" : null }, r.name)));
  const table = el("div");
  host.append(el("div", { class: "card-head" }, el("h3", null, "Access by module"), el("label", { class: "inline-row" }, el("span", { class: "muted small" }, "Role "), sel)),
    table);
  const paint = () => {
    clear(table);
    table.append(el("div", { class: "table-wrap" }, el("table", { class: "access-matrix" },
      el("thead", null, el("tr", null, el("th", null, "Module"), ...m.actions.map((a) => el("th", { class: "center" }, ACT[a])), el("th", null, "Delete"))),
      el("tbody", null, ...m.rows.map((r) => el("tr", { class: "no-click" },
        el("th", { scope: "row" }, r.module),
        ...m.actions.map((a) => {
          const c = r.cells[a];
          if (!c.permissions.length) return el("td", { class: "center muted", title: "Not applicable" }, "–");
          const yes = c.roles.includes(role);
          const why = c.permissions.map((p) => (p === "tier:staff" ? "every internal audit account" : p === "tier:all" ? "every account" : (m.labels[p] || p))).join("; ");
          return el("td", { class: `center ${yes ? "am-yes" : "am-no"}`, title: `Granted by: ${why}` },
            el("i", { class: `bi ${yes ? "bi-check-circle-fill" : "bi-x-circle"}`, "aria-hidden": "true" }),
            el("span", { class: "sr-only" }, yes ? "Allowed" : "Not allowed"));
        }),
        el("td", { class: "center" }, el("i", { class: "bi bi-info-circle am-info", title: r.delete, "aria-label": r.delete, tabindex: "0" }))))))));
  };
  sel.addEventListener("change", () => { role = sel.value; state.matrixRole = role; paint(); });
  paint();
}
