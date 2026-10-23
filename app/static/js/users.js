// Users & access: internal accounts with search, filters, sorting and paging (server side), and a detail panel
// with the account's role, status actions, open sessions and access history. Every action is checked again by
// the server (Manage user accounts permission; only a Super Administrator manages administrators; the last
// active administrator can never be removed).

const USER_STATUS_TABS = [
  { key: "", label: "All" }, { key: "active", label: "Active" }, { key: "pending", label: "Awaiting approval" },
  { key: "locked", label: "Locked" }, { key: "deactivated", label: "Deactivated" },
  { key: "inactive", label: "No sign-in for 90+ days" },
];
const USER_STATUS_LABEL = { active: "Active", pending: "Awaiting approval", locked: "Locked", deactivated: "Deactivated" };

// After a change made from a form or dialog, refresh whichever users screen is open.
function refreshUsers() {
  if (state.view === "users" && typeof state.usersReload === "function") state.usersReload();
  else if (state.view === "profile") renderProfile();
}

async function ensureRoleCatalogue() {
  if (!ROLE_CATALOGUE) {
    try { ROLE_CATALOGUE = await API.get("/api/roles"); } catch { ROLE_CATALOGUE = { roles: [], can_assign: false, can_appoint_admins: false }; }
    JOB_ROLE_OPTIONS = ROLE_CATALOGUE.roles.map((r) => ({ code: r.code, name: r.name, tier: r.tier, assignable: ROLE_CATALOGUE.can_appoint_admins || !["super_admin", "admin"].includes(r.code) }));
  }
  return ROLE_CATALOGUE;
}

async function renderUsersAdmin() {
  clear(viewRoot);
  const f = state.usersFilter || (state.usersFilter = { q: "", status: "", job_role: "", mfa: "", workplace: "", sort: "name", desc: false, page: 1 });
  const cat = await ensureRoleCatalogue();
  const add = hasPerm("system.users") ? el("button", { class: "btn", type: "button", onclick: newUserForm }, el("i", { class: "bi bi-person-plus" }), " Add user") : null;
  const lic = hasPerm("system.users") ? el("button", { class: "btn secondary", type: "button", onclick: () => navigate("licenses") }, el("i", { class: "bi bi-card-checklist" }), " Licenses") : null;
  viewRoot.append(viewHeader("Users & access", [lic, add].filter(Boolean)));

  const tabs = el("div", { class: "tabs users-tabs", role: "tablist" });
  const search = el("input", { type: "search", class: "compact", placeholder: "Search name, username, e-mail or unit", "aria-label": "Search users", value: f.q });
  const roleSel = el("select", { class: "compact", "aria-label": "Role" }, el("option", { value: "" }, "All roles"),
    ...cat.roles.map((r) => el("option", { value: r.code, selected: f.job_role === r.code ? "1" : null }, r.name)));
  const mfaSel = el("select", { class: "compact", "aria-label": "Two-step verification" },
    ...[["", "Two-step: any"], ["true", "Two-step on"], ["false", "Two-step off"]].map(([v, l]) => el("option", { value: v, selected: f.mfa === v ? "1" : null }, l)));
  const placeSel = el("select", { class: "compact", "aria-label": "Workplace" },
    ...[["", "Workplace: any"], ["none", "No workplace"], ["inactive", "In a deactivated unit"]].map(([v, l]) => el("option", { value: v, selected: (f.workplace || "") === v ? "1" : null }, l)));
  const host = el("div", { class: "card users-card" });
  const invites = el("div");
  viewRoot.append(tabs, el("div", { class: "toolbar users-toolbar" }, search, roleSel, mfaSel, placeSel), host, invites);
  if (hasPerm("system.users")) paintInvitations(invites);

  let timer = null;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { f.q = search.value.trim(); f.page = 1; load(); }, 300); });
  roleSel.addEventListener("change", () => { f.job_role = roleSel.value; f.page = 1; load(); });
  mfaSel.addEventListener("change", () => { f.mfa = mfaSel.value; f.page = 1; load(); });
  placeSel.addEventListener("change", () => { f.workplace = placeSel.value; f.page = 1; load(); });

  async function load() {
    clear(host);
    host.append(loadingState("Loading accounts…"));
    const qs_ = new URLSearchParams({ sort: f.sort, desc: String(f.desc), page: String(f.page), page_size: "25" });
    if (f.q) qs_.set("q", f.q);
    if (f.status) qs_.set("status", f.status);
    if (f.job_role) qs_.set("job_role", f.job_role);
    if (f.mfa) qs_.set("mfa", f.mfa);
    if (f.workplace) qs_.set("workplace", f.workplace);
    let data;
    try { data = await API.get(`/api/users/search?${qs_}`); }
    catch (err) { clear(host); host.append(errorState(err, load)); return; }
    paintTabs(data.counts);
    clear(host);
    if (!data.items.length) {
      host.append(el("div", { class: "empty" }, f.q || f.status || f.job_role || f.mfa || f.workplace ? "No account matches these filters." : "No accounts yet."));
      return;
    }
    const sortBtn = (key, label) => {
      const active = f.sort === key;
      return el("th", { "aria-sort": active ? (f.desc ? "descending" : "ascending") : "none" },
        el("button", { class: "th-sort", type: "button", onclick: () => { if (f.sort === key) f.desc = !f.desc; else { f.sort = key; f.desc = key === "last_sign_in"; } load(); } },
          label, el("i", { class: `bi ${active ? (f.desc ? "bi-caret-down-fill" : "bi-caret-up-fill") : "bi-chevron-expand"} sort-ico` })));
    };
    const roleName = (code) => (cat.roles.find((r) => r.code === code) || {}).name || code;
    host.append(el("div", { class: "table-wrap" }, el("table", { class: "users-table" },
      el("thead", null, el("tr", null, sortBtn("name", "Name"), sortBtn("role", "Role"), el("th", null, "Status"),
        el("th", null, "Two-step"), sortBtn("last_sign_in", "Last sign-in"), sortBtn("created", "Created"))),
      el("tbody", null, ...data.items.map((u) => el("tr", { tabindex: "0", onclick: () => openUserPanel(u.id),
        onkeydown: (e) => { if (e.key === "Enter") openUserPanel(u.id); } },
      el("td", null, el("div", { class: "cell-title" }, u.full_name || u.username), el("div", { class: "muted small" }, `${u.username} · ${u.email}`),
        el("div", { class: `small user-place ${u.workplace ? (u.workplace_active ? "" : "warn") : "muted"}` }, el("i", { class: "bi bi-geo-alt", "aria-hidden": "true" }), " ",
          u.workplace ? `${u.workplace}${u.workplace_active ? "" : " (deactivated)"}` : "No workplace")),
      el("td", null, roleName(u.job_role), u.review_level && u.job_role === "manager" ? el("div", { class: "muted small" }, approvalLabel(u.review_level)) : null),
      el("td", null, badge(USER_STATUS_LABEL[u.status] || u.status)),
      el("td", null, u.mfa_enabled ? el("span", { class: "chip-mini", title: "Two-step verification on" }, el("i", { class: "bi bi-shield-check" }), " On") : el("span", { class: "muted" }, "Off")),
      el("td", null, u.last_sign_in ? fmtDate(u.last_sign_in).split(",")[0] : el("span", { class: "muted" }, "Never")),
      el("td", null, fmtDate(u.created_at).split(",")[0])))))));
    const pages = Math.max(1, Math.ceil(data.total / data.page_size));
    host.append(el("div", { class: "table-foot" },
      el("span", { class: "muted small" }, `${data.total} account${data.total === 1 ? "" : "s"}${pages > 1 ? ` · page ${data.page} of ${pages}` : ""}`),
      el("div", { class: "actions" },
        pages > 1 ? el("button", { class: "btn small secondary", type: "button", disabled: f.page <= 1 ? "1" : null, onclick: () => { f.page -= 1; load(); } }, el("i", { class: "bi bi-chevron-left" }), " Previous") : null,
        pages > 1 ? el("button", { class: "btn small secondary", type: "button", disabled: f.page >= pages ? "1" : null, onclick: () => { f.page += 1; load(); } }, "Next ", el("i", { class: "bi bi-chevron-right" })) : null)));
  }

  function paintTabs(counts) {
    clear(tabs);
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    USER_STATUS_TABS.forEach((t) => {
      const n = t.key === "" ? total : t.key === "inactive" ? null : (counts[t.key] || 0);
      tabs.append(el("button", { class: `tab ${f.status === t.key ? "active" : ""}`, type: "button", role: "tab",
        "aria-selected": f.status === t.key ? "true" : "false", onclick: () => { f.status = t.key; f.page = 1; load(); } },
      t.label, n === null ? null : el("span", { class: "tab-count" }, String(n))));
    });
  }

  state.usersReload = load;
  load();
}

// ------------------------------------------------------------------ one account

async function openUserPanel(id) {
  const body = el("div", { class: "user-panel" }, loadingState("Loading the account…"));
  const panel = detailPanel({ title: "User account", body, width: 640 });
  let u; let access;
  try {
    [u, access] = await Promise.all([API.get(`/api/users/${id}`), API.get(`/api/users/${id}/access`)]);
  } catch (err) { clear(body); body.append(errorState(err)); return; }
  const cat = await ensureRoleCatalogue();
  const self = u.id === state.user.id;
  const isAdminAccount = ["super_admin", "admin"].includes(u.job_role);
  const canManage = hasPerm("system.users") && (self || !isAdminAccount || cat.can_appoint_admins);
  const locked = u.locked_until && new Date(`${u.locked_until}Z`) > new Date();
  const status = u.is_active ? (locked ? "Locked" : "Active") : (access.last_sign_in ? "Deactivated" : "Awaiting approval");
  const reopen = () => { panel.close(); refreshUsers(); openUserPanel(id); };
  const act = async (fn, okText) => { try { await fn(); toast(okText); reopen(); } catch (err) { toast(err.message, "error"); } };

  clear(body);
  body.append(el("div", { class: "user-panel-head" },
    el("div", null, el("h3", null, u.full_name || u.username), el("div", { class: "muted small" }, `${u.username} · ${u.email}${u.company ? ` · ${u.company}` : ""}`),
      el("div", { class: `small user-place ${access.workplace ? (access.workplace.is_active ? "" : "warn") : "muted"}` }, el("i", { class: "bi bi-geo-alt", "aria-hidden": "true" }), " ",
        access.workplace ? (viewAllowed("orgstructure")
          ? el("button", { class: "link-btn", type: "button", onclick: () => { panel.close(); openOrgUnitPanel(access.workplace.id); } }, access.workplace.name)
          : access.workplace.name) : "No workplace set",
        access.workplace && !access.workplace.is_active ? " (deactivated unit)" : "")),
    el("div", { class: "user-badges" }, badge(status), u.mfa_enabled ? el("span", { class: "chip-mini" }, el("i", { class: "bi bi-shield-check" }), " Two-step on") : el("span", { class: "chip-mini" }, "Two-step off"))));
  if (!canManage && !self) body.append(el("div", { class: "callout warn" }, el("i", { class: "bi bi-shield-lock" }), el("div", null, "Only a Super Administrator can change an administrator account.")));

  // Role and approval level
  body.append(el("h4", { class: "user-sec" }, "Role"));
  body.append(self || !cat.can_assign || !canManage
    ? el("p", null, u.job_role_name, u.job_role === "manager" && u.review_level ? ` · ${approvalLabel(u.review_level)}` : "")
    : el("div", null, roleAssignControls(u, cat, reopen)));

  // Status and account actions
  const actions = [];
  if (canManage && !self) {
    if (!u.is_active) actions.push(el("button", { class: "btn small", type: "button", onclick: () => act(() => API.patch(`/api/users/${u.id}`, { is_active: true }), access.last_sign_in ? "Account reactivated" : "Account approved") }, access.last_sign_in ? "Reactivate" : "Approve"));
    else actions.push(el("button", { class: "btn small danger-ghost", type: "button", onclick: async () => {
      const ok = await confirmDialog({ title: "Deactivate this account?", text: `${u.full_name || u.username} will be signed out and can no longer sign in. Their work and history stay in the workspace; you can reactivate the account later.`, confirmLabel: "Deactivate", danger: true });
      if (ok.ok) act(() => API.patch(`/api/users/${u.id}`, { is_active: false }), "Account deactivated");
    } }, "Deactivate"));
    if (locked) actions.push(el("button", { class: "btn small secondary", type: "button", onclick: () => act(() => API.post(`/api/users/${u.id}/unlock`), "Account unlocked") }, "Unlock"));
    actions.push(el("button", { class: "btn small secondary", type: "button", onclick: () => { panel.close(); resetPasswordForm(u); } }, el("i", { class: "bi bi-key" }), " Reset password"));
    if (u.mfa_enabled) actions.push(el("button", { class: "btn small secondary", type: "button", onclick: async () => {
      const ok = await confirmDialog({ title: "Reset two-step verification?", text: "Use this when the person lost their phone. They set it up again at their next sign-in.", confirmLabel: "Reset" });
      if (ok.ok) act(() => API.patch(`/api/users/${u.id}`, { reset_mfa: true }), "Two-step verification reset");
    } }, "Reset two-step"));
  }
  if (canManage) {
    actions.push(el("button", { class: "btn small secondary", type: "button", onclick: () => { panel.close(); editUserForm(u); } }, el("i", { class: "bi bi-pencil" }), " Edit details"));
  }
  if (actions.length) body.append(el("h4", { class: "user-sec" }, "Account"), el("div", { class: "actions user-actions" }, ...actions));

  // Sessions
  body.append(el("h4", { class: "user-sec" }, `Open sessions (${access.sessions.length})`));
  if (access.sessions.length) {
    body.append(el("div", { class: "table-wrap" }, el("table", { class: "compact-table" },
      el("thead", null, el("tr", null, el("th", null, "Signed in"), el("th", null, "Last activity"), el("th", null, "From"))),
      el("tbody", null, ...access.sessions.map((s) => el("tr", { class: "no-click" },
        el("td", null, fmtDate(s.started)), el("td", null, fmtDate(s.last_activity)),
        el("td", null, el("div", null, s.ip || "-"), el("div", { class: "muted small user-agent" }, (s.browser || "").slice(0, 80)))))))));
    if (canManage) body.append(el("button", { class: "btn small secondary", type: "button", onclick: async () => {
      const ok = await confirmDialog({ title: self ? "Sign out your other sessions?" : "Sign this person out everywhere?", text: self ? "Every other device signed in to your account is signed out. This window stays signed in." : "Every open session ends at once; they can sign in again.", confirmLabel: "Sign out" });
      if (ok.ok) act(() => API.post(`/api/users/${u.id}/sessions/revoke`), self ? "Other sessions ended" : "Signed out everywhere");
    } }, el("i", { class: "bi bi-box-arrow-right" }), self ? " Sign out other sessions" : " Sign out everywhere"));
  } else body.append(el("p", { class: "muted small" }, "No open sessions."));

  // Access history
  body.append(el("h4", { class: "user-sec" }, "Sign-in history"),
    el("p", { class: "muted small" }, `Last successful sign-in: ${access.last_sign_in ? fmtDate(access.last_sign_in) : "never"}`));
  body.append(access.sign_ins.length ? el("div", { class: "table-wrap user-history" }, el("table", { class: "compact-table" },
    el("thead", null, el("tr", null, el("th", null, "When"), el("th", null, "Event"), el("th", null, "From"))),
    el("tbody", null, ...access.sign_ins.map((r) => el("tr", { class: `no-click ${r.outcome === "failure" ? "row-failure" : ""}` },
      el("td", null, fmtDate(r.at)), el("td", null, r.event || r.action), el("td", null, r.ip || "-"))))))
    : el("p", { class: "muted small" }, "No sign-in events recorded."));
  body.append(el("h4", { class: "user-sec" }, "Changes made by administrators"));
  body.append(access.changes.length ? el("ul", { class: "admin-changes" }, ...access.changes.map((c) => el("li", null,
    el("div", { class: "admin-change-line" }, el("strong", null, c.by), c.outcome === "failure" ? el("span", { class: "rating rating-needs-improvement" }, "failed") : null),
    el("div", { class: "admin-change-action", title: c.action }, c.event || c.action, c.details ? el("span", { class: "muted small" }, ` · ${clip(c.details, 70)}`) : null), el("div", { class: "muted small" }, fmtDate(c.at)))))
    : el("p", { class: "muted small" }, "No changes recorded."));

  if (canManage && !self) body.append(el("div", { class: "user-danger" },
    el("button", { class: "btn small danger-ghost", type: "button", title: "Only for accounts with no recorded work; otherwise deactivate", onclick: () => { panel.close(); deleteUser(u); } }, el("i", { class: "bi bi-trash" }), " Delete account")));
}

// ------------------------------------------------------------------ invitations and licences

// + Add user: the person receives a link and chooses their own password (no password is typed for them).
async function newUserForm() {
  let groups = [];
  try { [groups] = await Promise.all([API.get("/api/groups"), ensureRoleCatalogue()]); } catch { /* groups optional */ }
  openForm({
    title: "Add user",
    key: "user:new",
    meta: { title: "Add user" },
    width: 560,
    fields: [
      { name: "email", label: "Email address", type: "email", required: true, placeholder: "Unique work email" },
      { name: "job_role", label: "Platform user type", type: "select", required: true,
        options: (JOB_ROLE_OPTIONS || []).filter((r) => r.assignable).map((r) => ({ value: r.code, label: r.name })) },
      { name: "group_ids", label: "Groups", type: "checklist", options: groups.map((g) => ({ value: g.id, label: g.name })), emptyLabel: "No groups yet." },
      { name: "full_name", label: "Name (optional)", maxLength: 255, singleLine: true },
    ],
    initial: { job_role: "auditor" },
    submitLabel: "Send invitation",
    onSubmit: (v) => API.post("/api/users/invite", { ...v, group_ids: v.group_ids || [], full_name: v.full_name || "" }),
    onDone: (r) => { refreshUsers(); invitationSent(r.user.email, r); },
  });
}

// E-mail sent, or (e-mail not set up) the one-time link to pass on.
function invitationSent(email, r) {
  if (r.emailed) { toast(`Invitation sent to ${email}`); return; }
  const input = el("input", { type: "text", readonly: "1", value: r.link, "aria-label": "Activation link" });
  const dlg = modal({ title: "Invitation ready", width: 560,
    body: el("div", null, el("p", null, `E-mail is not set up, so give this link to ${email}. It works once.`),
      el("div", { class: "inv-link" }, input, el("button", { class: "btn small secondary", type: "button", onclick: async () => {
        try { await navigator.clipboard.writeText(r.link); toast("Link copied"); } catch { input.select(); }
      } }, el("i", { class: "bi bi-clipboard" }), " Copy"))),
    footer: el("div", { class: "actions" }, el("button", { class: "btn", type: "button", onclick: () => dlg.close() }, "Done")) });
}

async function paintInvitations(card) {
  let rows;
  try { rows = await API.get("/api/users/invitations"); } catch { return; }
  clear(card);
  if (!rows.length) return;
  const cat = await ensureRoleCatalogue();
  const roleName = (code) => (cat.roles.find((r) => r.code === code) || {}).name || code;
  const act = async (fn, okText) => { try { const r = await fn(); if (r && r.link !== undefined) invitationSent("the person", r); else toast(okText); paintInvitations(card); } catch (err) { toast(err.message, "error"); } };
  card.append(el("section", { class: "card", "aria-label": "Invitations" },
    el("div", { class: "card-head" }, el("h3", null, `Invitations (${rows.length})`)),
    el("div", { class: "table-wrap" }, el("table", { class: "compact-table" },
      el("thead", null, el("tr", null, ...["Email", "Platform user type", "Sent", "Expires", ""].map((h) => el("th", null, h)))),
      el("tbody", null, ...rows.map((i) => el("tr", { class: "no-click" },
        el("td", null, i.email, el("div", { class: "muted small" }, i.username)), el("td", null, roleName(i.job_role)),
        el("td", null, fmtDay(i.sent_at), i.invited_by ? el("div", { class: "muted small" }, i.invited_by) : null), el("td", null, fmtDay(i.expires_at)),
        el("td", { class: "actions" },
          el("button", { class: "btn small secondary", type: "button", onclick: () => act(() => API.post(`/api/users/invitations/${i.id}/resend`), "Invitation sent again") }, "Resend"),
          el("button", { class: "btn small danger-ghost", type: "button", onclick: () => act(() => API.del(`/api/users/invitations/${i.id}`), "Invitation withdrawn") }, "Withdraw")))))))));
}

// Licenses: seats per role (limits are set under Configuration > Users & licenses).
async function renderLicenses() {
  clear(viewRoot);
  const set = viewAllowed("configuration") ? el("button", { class: "btn secondary", type: "button", onclick: () => { state.configSection = "Users & licenses"; navigate("configuration"); } }, "Set seat limits") : null;
  viewRoot.append(viewHeader("Licenses", set));
  const card = el("div", { class: "card" }, loadingState());
  viewRoot.append(card);
  let d;
  try { d = await API.get("/api/users/licenses"); } catch (err) { clear(card); card.append(errorState(err, renderLicenses)); return; }
  clear(card);
  if (!d.configured) card.append(el("p", { class: "muted small" }, "No seat limits are set: every role is unlimited."));
  card.append(el("div", { class: "table-wrap" }, el("table", { class: "compact-table" },
    el("thead", null, el("tr", null, el("th", null, "Role"), el("th", { class: "num" }, "Active"), el("th", { class: "num" }, "Invited"), el("th", { class: "num" }, "Seats"), el("th", { class: "num" }, "Available"))),
    el("tbody", null, ...d.roles.map((r) => el("tr", { class: `no-click ${r.available === 0 ? "row-failure" : ""}` },
      el("td", null, r.name), el("td", { class: "num" }, String(r.active)), el("td", { class: "num" }, String(r.invited)),
      el("td", { class: "num" }, r.seats === null ? "Unlimited" : String(r.seats)),
      el("td", { class: "num" }, r.available === null ? "-" : String(r.available))))))));
}

// ------------------------------------------------------------------ account activation (invitation link)
// Shown on the sign-in screen for #activate/<token>: the invited person chooses their name and password.
async function renderActivation(token) {
  const login = qs("#loginForm");
  history.replaceState(null, "", window.location.pathname);  // the link works once; keep it out of the address bar
  const box = el("div", { class: "card-body" });
  const card = el("form", { class: "login-div", autocomplete: "off" }, el("div", { class: "card blueBorder" },
    el("div", { class: "auth-head" }, el("div", { class: "auth-head-text" }, el("span", { class: "auth-head-title" }, "ACTIVATE YOUR ACCOUNT"))), el("hr"), box));
  login.classList.add("hidden");
  login.after(card);
  const back = (text, tone = "ok", username = "") => {
    card.remove(); login.classList.remove("hidden");
    if (username) qs("#loginUser").value = username;
    notify(authMsg, text, tone);
  };
  let d;
  try { d = await API.post("/api/auth/invitation", { token }); }
  catch (err) { back(err.message, "error"); return; }
  const name = el("input", { class: "ant-input ant-input-lg", required: "1", maxlength: "255", value: d.full_name || "", placeholder: "Your name", "aria-label": "Your name" });
  const pw = el("input", { class: "ant-input ant-input-lg", type: "password", required: "1", minlength: "8", maxlength: "128", placeholder: "Choose a password", "aria-label": "Choose a password", autocomplete: "new-password" });
  const pw2 = el("input", { class: "ant-input ant-input-lg", type: "password", required: "1", minlength: "8", maxlength: "128", placeholder: "Repeat the password", "aria-label": "Repeat the password", autocomplete: "new-password" });
  const msg = el("div");
  box.append(el("p", null, el("strong", null, d.username), el("span", { class: "muted" }, ` · ${d.email}`)), msg,
    ...[name, pw, pw2].map((n) => el("div", { class: "ant-form-item" }, n)),
    el("button", { type: "submit", class: "ant-btn ant-btn-primary ant-btn-lg ant-btn-block" }, el("span", null, "Activate account")));
  card.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (pw.value !== pw2.value) { notify(msg, "The two passwords do not match", "error"); return; }
    try {
      const r = await API.post("/api/auth/activate", { token, full_name: name.value.trim(), password: pw.value });
      back(r.message, "ok", d.username);
    } catch (err) { notify(msg, err.message, "error"); }
  });
}
