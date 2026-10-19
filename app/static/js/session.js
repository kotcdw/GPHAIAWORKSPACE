// Session helpers: stay on the same page after a refresh, and sign out automatically when idle.
// Loaded after app.js; boot() is asynchronous, so everything here exists before showApp() runs.

// ------------------------------------------------------------------ page address (#/...) and UI state

// Write the current page into the address bar without adding history entries, so a refresh reopens it.
function setRoute(hash) {
  if (window.location.hash !== hash) history.replaceState(null, "", hash);
}

// Pages that open a single record: remember them as #/<kind>/<id>.
[["openRecord", (key, id) => `#/record/${key}/${id}`], ["openPlan", (id) => `#/plan/${id}`],
  ["openRisk", (id) => `#/risk/${id}`], ["openRegulation", (id) => `#/regulation/${id}`],
  ["openPolicy", (id) => `#/policy/${id}`], ["openAsset", (id) => `#/asset/${id}`],
  ["openEntity", (id) => `#/entity/${id}`], ["openAssessment", (id) => `#/assessment/${id}`]].forEach(([name, route]) => {
  const original = window[name];
  if (typeof original !== "function") return;
  window[name] = async function routed(...args) {
    const result = await original.apply(this, args);
    setRoute(route(...args));
    return result;
  };
});

// Reopen the page in the address bar. Returns a truthy value (the page's promise) when it handled the route.
function restoreRoute() {
  const h = window.location.hash;
  let m = /^#\/audit\/(\d+)(?:\/([a-z_]+))?$/.exec(h);
  if (m) return openAudit(Number(m[1]), m[2] || null) || true;
  m = /^#\/record\/([a-z_]+)\/(\d+)$/.exec(h);
  if (m && typeof MODULES !== "undefined" && MODULES[m[1]] && viewAllowed(m[1])) return openRecord(m[1], Number(m[2])) || true;
  m = /^#\/(plan|risk|regulation|policy|asset|entity|assessment)\/(\d+)$/.exec(h);
  if (m) {
    if (["entity", "assessment"].includes(m[1]) && !viewAllowed("universe")) return false;
    const fn = { plan: openPlan, risk: openRisk, regulation: openRegulation, policy: openPolicy, asset: openAsset, entity: openEntity, assessment: openAssessment }[m[1]];
    if (typeof fn === "function") return fn(Number(m[2])) || true;
  }
  m = /^#\/([a-z_]+)$/.exec(h);
  if (m && viewAllowed(m[1])) return navigate(m[1]) || true;
  return false;
}

// Small bits of screen state (selected section, tab, filters) survive a refresh in this browser tab.
const UI_STATE_KEYS = ["configSection", "myWork", "remTab", "committeeTab", "lastAuditTab"];
function loadUiState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem("gpha_ui") || "{}");
    UI_STATE_KEYS.forEach((k) => { if (saved[k] !== undefined && state[k] === undefined) state[k] = saved[k]; });
  } catch { /* storage unavailable: start fresh */ }
}
function saveUiState() {
  try {
    const out = {};
    UI_STATE_KEYS.forEach((k) => { if (state[k] !== undefined) out[k] = state[k]; });
    sessionStorage.setItem("gpha_ui", JSON.stringify(out));
  } catch { /* storage unavailable */ }
}
loadUiState();
window.addEventListener("beforeunload", saveUiState);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") saveUiState(); });

// ------------------------------------------------------------------ automatic sign-out when idle

const IDLE_EVENTS = ["pointerdown", "pointermove", "keydown", "wheel", "touchstart", "scroll"];
const LAST_KEY = "gpha_last_activity";
const SIGNOUT_KEY = "gpha_signed_out";
const SENT_KEY = "gpha_last_request";
// The server records activity at most every 20 s, so its clock can trail the last request by that much (+ slack).
const SERVER_LAG_MS = 25000;
// Activity without requests (reading, typing a long form) is reported to the server at least this often.
const PING_EVERY_MS = 30000;

const Idle = {
  minutes: 0,
  timer: null,
  last: Date.now(),
  lastSent: Date.now(),
  warning: null,

  start(minutes) {
    this.stop();
    this.minutes = Number(minutes) || 0;
    if (!this.minutes) return;
    this.last = Date.now();
    this.noteRequest();
    this.write();
    IDLE_EVENTS.forEach((e) => window.addEventListener(e, this.onActivity, { passive: true, capture: true }));
    this.timer = setInterval(() => this.check(), 5000);
  },

  stop() {
    clearInterval(this.timer);
    this.timer = null;
    IDLE_EVENTS.forEach((e) => window.removeEventListener(e, this.onActivity, { capture: true }));
    this.closeWarning();
  },

  write() {
    try { localStorage.setItem(LAST_KEY, String(this.last)); } catch { /* private window: this tab only */ }
  },

  // Any tab's activity counts: the newest time is shared through localStorage.
  latest() {
    let shared = 0;
    try { shared = Number(localStorage.getItem(LAST_KEY)) || 0; } catch { /* ignore */ }
    return Math.max(this.last, shared);
  },

  // A foreground request reached the server (any tab: they share one session).
  noteRequest() {
    this.lastSent = Date.now();
    try { localStorage.setItem(SENT_KEY, String(this.lastSent)); } catch { /* this tab only */ }
  },
  latestSent() {
    let shared = 0;
    try { shared = Number(localStorage.getItem(SENT_KEY)) || 0; } catch { /* ignore */ }
    return Math.max(this.lastSent, shared);
  },

  // When the session ends: the earlier of "idle in the browser" and "idle as the server last saw it", so the
  // warning always comes before the server refuses requests.
  deadline() {
    const limit = this.minutes * 60000;
    return Math.min(this.latest() + limit, this.latestSent() - SERVER_LAG_MS + limit);
  },

  onActivity: () => {
    if (Idle.warning) return; // once warned, only "Stay signed in" keeps the session
    const now = Date.now();
    if (now - Idle.last < 2000) return;
    Idle.last = now;
    Idle.write();
    // Reading or typing makes no requests; tell the server the person is still here.
    if (now - Idle.latestSent() > PING_EVERY_MS) API.get("/api/auth/me").catch(() => {});
  },

  check() {
    if (!state.user || !this.minutes) return;
    const left = this.deadline() - Date.now();
    if (left <= 0) { this.expire(); return; }
    if (left <= 60000) this.showWarning(Math.ceil(left / 1000));
    else this.closeWarning();
  },

  showWarning(seconds) {
    if (this.warning) { this.warning.count.textContent = String(Math.max(0, seconds)); return; }
    const count = el("strong", null, String(seconds));
    const stay = el("button", { class: "btn", type: "button" }, "Stay signed in");
    const leave = el("button", { class: "btn secondary", type: "button" }, "Sign out now");
    const body = el("div", { class: "idle-warning", role: "alert", "aria-live": "assertive" },
      el("p", null, "You have not used the workspace for a while. For security you will be signed out in ", count, " seconds."),
      el("p", { class: "muted small" }, "Choose Stay signed in to continue where you are."));
    // Keep any dialog the person had open (a half-filled form) underneath: the warning stacks on top of it.
    const root = qs("#modalRoot");
    const underneath = root ? [...root.children] : [];
    const m = modal({ title: "Still there?", body, width: 440, footer: el("div", { class: "actions end" }, leave, stay),
      onClose: () => { if (this.warning && this.warning.m === m) { this.warning = null; this.stay(); } } });
    if (root && underneath.length) root.prepend(...underneath);
    this.warning = { m, count };
    stay.addEventListener("click", () => m.close());
    leave.addEventListener("click", () => { this.warning = null; m.close(); signOut("You signed out."); });
    setTimeout(() => stay.focus(), 30);
  },

  closeWarning() {
    if (!this.warning) return;
    const { m } = this.warning;
    this.warning = null;
    m.close();
  },

  stay() {
    this.last = Date.now();
    this.write();
    API.get("/api/auth/me").catch(() => {}); // counts as activity on the server (and notes the request)
  },

  expire() {
    const mins = this.minutes;
    this.stop();
    signOut(`You were signed out after ${mins} minute${mins === 1 ? "" : "s"} without activity. Sign in again to continue where you left off.`);
  },
};

// Sign out of this tab (and tell the other open tabs). The page address is kept, so signing in again reopens it.
async function signOut(message = "", { callServer = true, broadcast = true } = {}) {
  if (!state.user) return;
  Idle.stop();
  if (callServer) { try { await API.post("/api/auth/logout"); } catch { /* already ended on the server */ } }
  saveUiState();
  state.user = null;
  state.csrf = null;
  API.csrf = null;
  document.querySelectorAll("#modalRoot .modal-backdrop").forEach((n) => n.remove());
  closeFormPanels(); // still listed for this tab: they reopen after signing in again
  appView.classList.add("hidden");
  authView.classList.remove("hidden");
  if (message) notify(authMsg, message, "ok");
  if (broadcast) { try { localStorage.setItem(SIGNOUT_KEY, `${Date.now()}|${message}`); } catch { /* ignore */ } }
}

// Another tab signed out (button or idle): follow it.
window.addEventListener("storage", (e) => {
  if (e.key !== SIGNOUT_KEY || !e.newValue || !state.user) return;
  const message = e.newValue.split("|").slice(1).join("|");
  signOut(message || "You were signed out in another tab.", { callServer: false, broadcast: false });
});

// The server ended the session (idle limit, revoked by an administrator, expired): go to the sign-in page.
function handleSessionEnded(detail) {
  if (!state.user) return;
  signOut(detail && detail !== "Not authenticated" ? detail : "Your session has ended. Sign in again to continue.",
    { callServer: false });
}

// Creator / editor panels reopen after a refresh: record the calls that open them.
trackFormOpeners();
