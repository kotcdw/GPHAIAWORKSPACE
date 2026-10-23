// Administration: one landing page for the people who configure and operate GIAW.
// Every figure comes from /api/admin/overview, which only returns what the system can verify; where something
// is not recorded yet the page says so instead of showing a number.

const ADMIN_AREA_PERMS = {
  users: ["system.users", "system.roles"],
  org: ["system.reference", "system.config"],
  settings: CONFIG_PERMS,
  activity: ["system.technical"],
  imports: ["system.reference", "method.library", "system.technical"],
  policies: ["system.technical", "system.config"],
  backups: ["system.technical"],
};

function adminAreasAllowed() {
  return Object.entries(ADMIN_AREA_PERMS)
    .filter(([, perms]) => hasPerm(...perms))
    .map(([k]) => k);
}

const fmtAge = (h) => (h < 1 ? "less than an hour ago" : h < 48 ? `${Math.round(h)} hours ago` : `${Math.round(h / 24)} days ago`);
const dayOf = (iso) => (iso ? fmtDay(iso) : "never");

// Open Users & access with a filter already applied (e.g. people without a workplace).
function openUsersFiltered(preset) {
  state.usersFilter = { q: "", status: "", job_role: "", mfa: "", workplace: "", sort: "name", desc: false, page: 1, ...preset };
  navigate("users");
}

async function renderAdministration() {
  clear(viewRoot);
  const msg = el("div");
  const refresh = el("button", { class: "btn small secondary", type: "button", onclick: () => renderAdministration() },
    el("i", { class: "bi bi-arrow-clockwise" }), " Refresh");
  viewRoot.append(viewHeader("Administration", refresh), msg);
  const loading = loadingState("Loading the administration summary…");
  viewRoot.append(loading);
  let d;
  try { d = await API.get("/api/admin/overview"); }
  catch (err) { loading.remove(); viewRoot.append(errorState(err, renderAdministration)); return; }
  loading.remove();
  const can = new Set(d.areas);

  // ---------------------------------------------------------------- areas
  // One card per area: its state in one line, "Open" for its main page and a drop-down with its other pages and
  // actions. Only what the person may open is listed; an area with nothing to open is left out.
  const area = (key, icon, title, desc, summary, items, tone = "") => {
    const list = items.filter(Boolean);
    if (!can.has(key) || !list.length) return null;
    const [, openFn] = list[0];
    return el("section", { class: `card admin-area ${tone}`, "aria-labelledby": `adm-${key}` },
      el("div", { class: "admin-area-head" }, el("span", { class: "admin-area-ico" }, el("i", { class: `bi bi-${icon}`, "aria-hidden": "true" })),
        el("div", null, el("h3", { id: `adm-${key}` }, title), el("div", { class: "muted small admin-area-desc" }, desc))),
      summary ? el("div", { class: "admin-area-summary" }, summary) : null,
      el("div", { class: "admin-area-actions" },
        el("button", { class: "btn small", type: "button", onclick: openFn }, "Open"),
        list.length > 1 ? dropMenu("More", list, { align: "left" }) : null));
  };
  const page = (label, view, before = null) => (viewAllowed(view) ? [label, () => { if (before) before(); navigate(view); }] : null);
  const cfgSection = (label, section) => (viewAllowed("configuration") ? [label, () => { state.configSection = section; navigate("configuration"); }] : null);
  const u = d.users;
  const imp = d.imports;
  const b = d.backups;
  const pol = d.policies;
  const areas = [
    area("users", "people", "Users, roles and access", "Accounts, sign-up approvals, roles and what each role may do.",
      u ? `${u.active} active · ${u.pending_count} awaiting approval · ${u.deactivated} deactivated` : null,
      [hasPerm("system.users") ? page("Users & access", "users") : null,
        u && u.pending_count && hasPerm("system.users") ? [`Approve sign-ups (${u.pending_count})`, () => openUsersFiltered({ status: "pending" })] : null,
        hasPerm("system.users") ? ["Accounts without a workplace", () => openUsersFiltered({ workplace: "none" })] : null,
        page("Roles & permissions", "roles")]),
    area("org", "diagram-3", "Organisational structure", "Ports, departments, units and outside organisations used for scoping and reporting.",
      d.org ? `${d.org.active} active unit${d.org.active === 1 ? "" : "s"} · ${d.org.pending} awaiting approval · ${d.org.without_head} without a head${d.org.inactive ? ` · ${d.org.inactive} deactivated` : ""}` : null,
      [page("Org structure", "orgstructure"),
        viewAllowed("orgstructure") && UNIVERSE_EDIT() ? ["New unit", () => { navigate("orgstructure"); setTimeout(() => orgUnitForm(null), 300); }] : null,
        page("Show deactivated units", "orgstructure", () => { state.orgShowInactive = true; })]),
    area("settings", "sliders", "Application settings", "Regional settings, business rules, workflow, reference lists, report text and SLA time limits.",
      d.settings ? `${d.settings.changed_from_default} of ${d.settings.total} changed from default · ${d.settings.regional.time_zone} · ${d.settings.regional.date_format}` : null,
      [page("Configuration", "configuration"), page("Audit types", "audittypes"), page("Apps & branding", "apps")]),
    area("activity", "journal-text", "Audit and activity log", "Read-only record of sign-ins, user and role changes, settings, exports and record changes.",
      d.recent_changes ? (d.recent_changes.length ? `Last change ${dayOf(d.recent_changes[0].at)}` : "No administrative changes recorded") : null,
      [page("Audit trail", "logs")]),
    area("imports", "upload", "Bulk data import", "Excel templates with validation and a preview before anything is written.",
      imp ? `${imp.completed} imported · ${imp.failed} rejected · last ${imp.days} days` : null,
      [page("Data import", "imports")]),
    area("policies", "file-earmark-lock", "Data and attachment policies", "File types, sizes, import limits and session rules in force.",
      pol ? `Files up to ${pol.attachments.max_upload_mb} MB · ${pol.attachments.allowed_extensions.length} types · imports up to ${pol.imports.max_rows} rows · ${pol.sessions.max_failed_sign_ins} failed sign-ins lock an account` : null,
      [cfgSection("Policies", "Data & attachments"), cfgSection("Storage", "@storage")]),
    area("backups", "hdd-stack", "Backup and recovery", "Encrypted backups of the database and attachments.",
      b ? (b.latest ? `Newest ${fmtAge(b.latest.age_hours)} · ${b.verified ? (b.verified.outcome === "passed" ? "check passed" : "check failed") : "not checked"} · ${b.count} kept` : "No backup found") : null,
      [page("Backups", "backups")], b && (!b.latest || b.overdue) ? "danger" : ""),
  ].filter(Boolean);

  viewRoot.append(el("div", { class: "admin-grid" }, ...areas));
}
