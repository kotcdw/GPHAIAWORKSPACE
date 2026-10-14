// Apps & customization: the Super Administrator switches apps on and off, renames them and sets the branding.
// applyAppCustomization() runs at sign-in for everyone: hidden apps leave the sidebar, renamed apps show their
// new name and the workspace name follows the branding. The server also refuses requests to switched-off apps.

const APPS = { list: [], byView: {}, branding: null };

async function loadAppCustomization() {
  const data = await safeGet("/api/apps", { apps: [], branding: null });
  APPS.list = data.apps;
  APPS.branding = data.branding;
  APPS.byView = {};
  data.apps.forEach((a) => a.views.forEach((v) => { APPS.byView[v] = a; }));
  return data;
}

function appEnabledForView(view) {
  const a = APPS.byView[view];
  return !a || a.enabled;
}

function appLabel(view, fallback) {
  const a = APPS.byView[view];
  return a ? a.label : fallback;
}

async function applyAppCustomization() {
  await loadAppCustomization();
  document.querySelectorAll("#sidebarNav button[data-view]").forEach((b) => {
    const a = APPS.byView[b.dataset.view];
    if (!a) return;
    const span = b.querySelector("span:not(.count)");
    if (span) span.textContent = a.label;
    if (!a.enabled) b.classList.add("hidden");
  });
  const br = APPS.branding;
  if (br) {
    const name = document.querySelector(".brand-name"); const sub = document.querySelector(".brand-sub");
    const title = document.querySelector(".topbar-title");
    if (name) name.textContent = br.name;
    if (sub) sub.textContent = br.sub;
    if (title) title.textContent = br.title;
    document.title = br.title;
  }
}

async function renderAppsPage() {
  clear(viewRoot);
  const msg = el("div");
  let data;
  try { data = await loadAppCustomization(); } catch (err) { viewRoot.append(viewHeader("Apps & customization"), msg); notify(msg, err.message, "error"); return; }
  const work = Object.fromEntries(data.apps.map((a) => [a.key, { enabled: a.enabled, label: a.label === a.name ? "" : a.label }]));
  const brand = { ...data.branding };
  const save = async () => {
    try {
      await API.put("/api/apps", { apps: work, branding: brand });
      toast("Customization saved");
      await applyAppCustomization();
      applyNavPermissions();
      renderAppsPage();
    } catch (err) { notify(msg, err.message, "error"); }
  };
  viewRoot.append(viewHeader("Apps & customization", [
    el("button", { class: "btn small secondary", onclick: () => renderAppsPage() }, "Discard changes"),
    el("button", { class: "btn small", onclick: save }, el("i", { class: "bi bi-check2" }), " Save"),
  ], { sub: "Full control for Super Administrators: switch apps on or off for everyone, rename them and set the workspace branding. Core apps stay on because the rest of the workspace depends on them." }), msg);

  const input = (key, label, help) => {
    const i = el("input", { type: "text", value: brand[key] || "", maxlength: "80", "aria-label": label });
    i.addEventListener("input", () => { brand[key] = i.value; });
    return el("div", { class: "form-field" }, el("label", null, label), i, help ? el("div", { class: "help muted" }, help) : null);
  };
  viewRoot.append(panel("Branding", el("div", { class: "grid cols-3 form-fields" },
    input("name", "Workspace name (sidebar)", "e.g. GPHA INTERNAL AUDIT"), input("sub", "Second word (highlighted)", "e.g. WORKSPACE"),
    input("title", "Browser and top bar title"))));

  const sections = [...new Set(data.apps.map((a) => a.section))];
  const on = data.apps.filter((a) => a.enabled).length;
  viewRoot.append(el("p", { class: "muted small" }, `${on} of ${data.apps.length} apps switched on.`));
  sections.forEach((sec) => {
    const rows = data.apps.filter((a) => a.section === sec).map((a) => {
      const toggle = el("input", { type: "checkbox", role: "switch", checked: work[a.key].enabled ? "1" : null, disabled: a.core ? "1" : null, "aria-label": `${a.name} on or off` });
      const label = el("input", { type: "text", class: "compact", value: work[a.key].label, placeholder: a.name, maxlength: "60", "aria-label": `Name shown for ${a.name}` });
      const row = el("div", { class: `app-row ${work[a.key].enabled ? "" : "off"}` },
        el("span", { class: "app-icon" }, el("i", { class: `bi bi-${a.icon}` })),
        el("div", { class: "pi-main" }, el("strong", null, a.name), el("div", { class: "muted small" }, a.description)),
        label,
        el("label", { class: "switch", title: a.core ? "Core app: always on" : "Switch on or off" }, toggle, el("span", { class: "slider" })),
        a.core ? el("span", { class: "chip-mini" }, el("i", { class: "bi bi-lock-fill" }), " Core") : el("span", { class: "chip-mini" }, work[a.key].enabled ? "On" : "Off"));
      toggle.addEventListener("change", () => { work[a.key].enabled = toggle.checked; row.classList.toggle("off", !toggle.checked); row.lastChild.textContent = toggle.checked ? "On" : "Off"; });
      label.addEventListener("input", () => { work[a.key].label = label.value; });
      return row;
    });
    viewRoot.append(panel(sec, el("div", { class: "app-list" }, ...rows)));
  });
}
