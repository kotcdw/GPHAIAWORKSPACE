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

const fmtBytes = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
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

  // ---------------------------------------------------------------- headline figures
  const tiles = [];
  if (d.users) {
    tiles.push(stat(d.users.active, "Active accounts", `${d.users.total} in total`));
    tiles.push(stat(d.users.pending_count, "Awaiting approval", d.users.pending_count ? "sign-ups to review" : "none waiting", d.users.pending_count ? "warn" : "ok"));
    tiles.push(stat(d.users.inactive_count, `No sign-in for ${d.users.inactive_days}+ days`, "active accounts to review", d.users.inactive_count ? "warn" : "ok"));
  }
  if (d.security) tiles.push(stat(d.security.failed_sign_ins, "Failed sign-ins", `last ${d.security.days} days · ${d.security.lockouts} lockouts`, d.security.lockouts ? "danger" : ""));
  if (d.backups) {
    const b = d.backups;
    tiles.push(b.latest
      ? stat(fmtAge(b.latest.age_hours), "Last backup", `${b.verified ? (b.verified.outcome === "passed" ? "check passed" : "check failed") : "not checked"} · ${b.count} kept`, b.overdue || (b.verified && b.verified.outcome === "failed") ? "danger" : "ok")
      : stat("None", "Last backup", "no backup found on the server", "danger"));
  }
  if (tiles.length) viewRoot.append(el("div", { class: "stats admin-stats" }, ...tiles));

  // ---------------------------------------------------------------- needs attention
  const attention = [];
  if (d.users) {
    if (d.users.pending_count) attention.push({ tone: "warn", icon: "person-plus", text: `${d.users.pending_count} account${d.users.pending_count === 1 ? "" : "s"} awaiting approval`, go: () => navigate("users") });
    if (d.users.locked.length) attention.push({ tone: "danger", icon: "lock", text: `${d.users.locked.length} account${d.users.locked.length === 1 ? " is" : "s are"} locked after failed sign-ins`, go: () => navigate("users") });
    if (d.users.admins_without_mfa) attention.push({ tone: "warn", icon: "shield-exclamation", text: `${d.users.admins_without_mfa} administrator${d.users.admins_without_mfa === 1 ? " has" : "s have"} no two-step verification`, go: () => navigate("users") });
    if (d.org && d.org.people_without_workplace) attention.push({ tone: "warn", icon: "geo-alt", text: `${d.org.people_without_workplace} active account${d.org.people_without_workplace === 1 ? " has" : "s have"} no workplace, so their port scope is unknown`, go: () => openUsersFiltered({ workplace: "none" }) });
    if (d.org && d.org.people_at_inactive_unit) attention.push({ tone: "warn", icon: "geo-alt", text: `${d.org.people_at_inactive_unit} active account${d.org.people_at_inactive_unit === 1 ? " is" : "s are"} placed in a deactivated unit`, go: () => openUsersFiltered({ workplace: "inactive" }) });
    if (d.users.admins_active === 1) attention.push({ tone: "warn", icon: "person-badge", text: "Only one active administrator: appoint a second so access is never lost", go: () => navigate("users") });
  }
  if (d.backups) {
    const b = d.backups;
    if (!b.latest) attention.push({ tone: "danger", icon: "hdd-stack", text: "No backup file exists on the server", go: () => navigate("backups") });
    else if (b.overdue) attention.push({ tone: "danger", icon: "hdd-stack", text: `The newest backup is ${fmtAge(b.latest.age_hours)}; backups are scheduled every ${b.interval_hours} hours`, go: () => navigate("backups") });
    if (b.last_failure && (!b.latest || new Date(b.last_failure.at) > new Date(b.latest.created_at))) {
      attention.push({ tone: "danger", icon: "x-octagon", text: `The last backup attempt failed (${dayOf(b.last_failure.at)})`, go: () => navigate("backups") });
    }
    if (b.server_schedule === false) attention.push({ tone: "warn", icon: "calendar-x", text: "Scheduled backups are switched off on the server", go: () => navigate("backups") });
    else if (!b.interval_hours) attention.push({ tone: "warn", icon: "calendar-x", text: "Automatic backups are paused", go: () => navigate("backups") });
    if (b.verified && b.verified.outcome === "failed") attention.push({ tone: "danger", icon: "shield-exclamation", text: "The newest backup failed its check", go: () => navigate("backups") });
    const rt = b.restore_test;
    if (b.latest && (!rt || rt.outcome === "failed" || Date.now() - parseWhen(rt.at).date.getTime() > 92 * 86400000)) {
      attention.push({ tone: "warn", icon: "arrow-counterclockwise", text: !rt ? "No restore test has been run" : rt.outcome === "failed" ? "The last restore test failed" : "The last restore test is over three months old", go: () => navigate("backups") });
    }
  }
  const attentionCard = el("section", { class: "card admin-attention", "aria-label": "Needs attention" },
    el("div", { class: "card-head" }, el("h3", null, "Needs attention")));
  if (attention.length) {
    attentionCard.append(el("ul", { class: "admin-attn-list" }, ...attention.map((a) => el("li", null,
      el("button", { class: `admin-attn ${a.tone}`, type: "button", onclick: a.go },
        el("i", { class: `bi bi-${a.icon}`, "aria-hidden": "true" }), el("span", null, a.text), el("i", { class: "bi bi-chevron-right", "aria-hidden": "true" }))))));
  } else {
    attentionCard.append(el("p", { class: "muted admin-all-clear" }, el("i", { class: "bi bi-check-circle", "aria-hidden": "true" }), " Nothing needs attention in the areas you manage."));
  }

  // ---------------------------------------------------------------- areas
  const area = (key, icon, title, desc, summary, actions) => (can.has(key)
    ? el("section", { class: "card admin-area", "aria-labelledby": `adm-${key}` },
      el("div", { class: "admin-area-head" }, el("span", { class: "admin-area-ico" }, el("i", { class: `bi bi-${icon}`, "aria-hidden": "true" })),
        el("div", { title: desc }, el("h3", { id: `adm-${key}` }, title))),
      summary ? el("div", { class: "admin-area-summary" }, summary) : null,
      el("div", { class: "admin-area-actions" }, ...actions))
    : null);
  const link = (label, fn, primary = false) => el("button", { class: `btn small ${primary ? "" : "secondary"}`, type: "button", onclick: fn }, label);
  const u = d.users;
  const imp = d.imports;
  const b = d.backups;
  const pol = d.policies;
  const areas = [
    area("users", "people", "Users, roles and access", "Internal accounts, sign-up approvals, roles and what each role may do.",
      u ? `${u.active} active · ${u.pending_count} awaiting approval · ${u.deactivated} deactivated` : null,
      [hasPerm("system.users") ? link("Users & access", () => navigate("users"), true) : null,
        viewAllowed("roles") ? link("Roles & permissions", () => navigate("roles")) : null].filter(Boolean)),
    area("org", "diagram-3", "Organisational structure", "Ports, departments, units and outside organisations used for scoping and reporting.",
      d.org ? `${d.org.active} active unit${d.org.active === 1 ? "" : "s"} · ${d.org.pending} awaiting approval · ${d.org.without_head} without a head${d.org.inactive ? ` · ${d.org.inactive} deactivated` : ""}` : null,
      [link("Open org structure", () => navigate("orgstructure"), true)]),
    area("settings", "sliders", "Application settings", "Regional settings, business rules, workflow, reference lists, report text and SLA time limits.",
      d.settings ? `${d.settings.changed_from_default} of ${d.settings.total} changed from default · ${d.settings.regional.time_zone} · ${d.settings.regional.date_format}${d.settings.last_change ? ` · last change ${dayOf(d.settings.last_change.at)} by ${d.settings.last_change.by}` : ""}` : null, [link("Open configuration", () => navigate("configuration"), true),
        viewAllowed("audittypes") ? link("Audit types", () => navigate("audittypes")) : null,
        viewAllowed("apps") ? link("Apps & branding", () => navigate("apps")) : null].filter(Boolean)),
    area("activity", "journal-text", "Audit and activity log", "Read-only record of sign-ins, user and role changes, settings, exports and record changes.",
      d.recent_changes ? `${d.recent_changes.length ? `Last change ${dayOf(d.recent_changes[0].at)}` : "No administrative changes recorded"}` : null,
      [link("Open audit trail", () => navigate("logs"), true)]),
    area("imports", "upload", "Bulk data import", "Excel templates with validation and a preview before anything is written.",
      imp ? `${imp.completed} imported · ${imp.failed} rejected · last ${imp.days} days` : null,
      [link("Open data import", () => navigate("imports"), true)]),
    area("policies", "file-earmark-lock", "Data and attachment policies", "File types, sizes, import limits and session rules in force.",
      pol ? `Files up to ${pol.attachments.max_upload_mb} MB · ${pol.attachments.allowed_extensions.length} types${pol.attachments.content_checked ? " · content checked" : ""} · imports up to ${pol.imports.max_rows} rows · ${pol.sessions.max_failed_sign_ins} failed sign-ins lock an account` : null,
      [link("Open policies", () => { state.configSection = "Data & attachments"; navigate("configuration"); }, true),
        link("Storage", () => { state.configSection = "@storage"; navigate("configuration"); })]),
    area("backups", "hdd-stack", "Backup and recovery", "Encrypted backups of the database and attachments.",
      b ? (b.latest ? `Newest ${fmtAge(b.latest.age_hours)} · ${b.verified ? (b.verified.outcome === "passed" ? "check passed" : "check failed") : "not checked"} · ${b.count} kept · ${b.interval_hours ? `every ${b.interval_hours} h` : "schedule off"}` : "No backup found") : null,
      [link("Open backups", () => navigate("backups"), true)]),
  ].filter(Boolean);

  const grid = el("div", { class: "admin-grid" }, ...areas);
  const side = el("div", { class: "admin-side" });
  if (d.recent_changes) side.append(recentChangesCard(d.recent_changes));
  if (b) side.append(backupFactsCard(b));
  // Desktop: cards on the left, attention and facts on the right. Phone: attention first, then the cards.
  viewRoot.append(el("div", { class: "admin-layout" }, el("div", { class: "admin-attn-wrap" }, attentionCard), grid, side));
}

function recentChangesCard(rows) {
  const card = el("section", { class: "card", "aria-label": "Recent administrative changes" },
    el("div", { class: "card-head" }, el("h3", null, "Recent administrative changes"),
      el("button", { class: "linkish small", type: "button", onclick: () => navigate("logs") }, "Full audit trail")));
  if (!rows.length) { card.append(el("p", { class: "muted" }, "No administrative changes recorded yet.")); return card; }
  card.append(el("ul", { class: "admin-changes" }, ...rows.map((r) => el("li", null,
    el("div", { class: "admin-change-line" }, el("strong", null, r.user),
      r.outcome === "failure" ? el("span", { class: "rating rating-needs-improvement" }, "failed") : null),
    el("div", { class: "admin-change-action", title: r.action }, r.event || r.action, r.details ? el("span", { class: "muted small" }, ` · ${clip(r.details, 70)}`) : null),
    el("div", { class: "muted small" }, fmtDate(r.at))))));
  return card;
}

function backupFactsCard(b) {
  const outcome = (c) => (c ? `${c.outcome === "passed" ? "passed" : "failed"} · ${dayOf(c.at)}` : null);
  const facts = [
    ["Newest backup", b.latest ? `${dayOf(b.latest.created_at)} (${fmtAge(b.latest.age_hours)})` : "none on the server"],
    ["Schedule", !b.server_schedule ? "switched off on the server" : b.interval_hours ? `every ${b.interval_hours} hours` : "paused"],
    ["Kept", `${b.count} of up to ${b.retention}`],
    ["Last check", outcome(b.verified) || "not checked"],
    ["Restore test", outcome(b.restore_test) || "never run"],
    ["Attachments", b.includes_attachments ? "included" : "database only"],
    ["Last failed attempt", b.last_failure ? dayOf(b.last_failure.at) : "none"],
  ];
  return el("section", { class: "card", "aria-label": "Backup facts" },
    el("div", { class: "card-head" }, el("h3", null, "Backup facts"), el("button", { class: "btn small secondary", type: "button", onclick: () => navigate("backups") }, "Open")),
    el("dl", { class: "kv admin-kv" }, ...facts.flatMap(([k, v]) => [el("dt", null, k), el("dd", null, v)])));
}

function showPolicies(p) {
  if (!p) return;
  const body = el("div", { class: "admin-policies" },
    el("h4", null, "Attachments"),
    el("dl", { class: "kv" },
      el("dt", null, "Largest file"), el("dd", null, `${p.attachments.max_upload_mb} MB`),
      el("dt", null, "Stored"), el("dd", null, p.attachments.encrypted_at_rest ? "encrypted, with an integrity hash; every download is permission-checked and logged" : "as uploaded"),
      el("dt", null, "Set in"), el("dd", null, p.attachments.source)),
    el("div", { class: "admin-ext" }, ...p.attachments.allowed_extensions.map((x) => el("span", { class: "chip-mini" }, x))),
    el("h4", null, "Bulk import"),
    el("dl", { class: "kv" },
      el("dt", null, "File"), el("dd", null, `${p.imports.formats.join(", ").toUpperCase()}, up to ${p.imports.max_file_mb} MB and ${p.imports.max_rows} rows`),
      el("dt", null, "Behaviour"), el("dd", null, p.imports.all_or_nothing ? "all-or-nothing: nothing is written while any row has an error" : "row by row")),
    el("h4", null, "Sign-in and sessions"),
    el("dl", { class: "kv" },
      el("dt", null, "Session length"), el("dd", null, `${p.sessions.ttl_hours} hours`),
      el("dt", null, "Lockout"), el("dd", null, `after ${p.sessions.max_failed_sign_ins} failed attempts, for ${p.sessions.lockout_minutes} minutes`)),
    el("p", { class: "muted small" }, "These limits are read from the server settings. Making them editable here is part of a later phase."));
  const closeBtn = el("button", { class: "btn secondary", type: "button" }, "Close");
  const m = modal({ title: "Data and attachment policies", body, width: 620, footer: el("div", { class: "actions end" }, closeBtn) });
  closeBtn.addEventListener("click", () => m.close());
}
