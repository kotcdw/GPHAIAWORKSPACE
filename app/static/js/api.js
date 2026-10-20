// Tiny fetch wrapper for the GPHA Audit Workspace JSON API.
// Handles cookie credentials and the double-submit CSRF token.

function readCookie(name) {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}

class ApiError extends Error {
  constructor(status, payload) {
    let detail = "Request failed";
    if (payload && payload.detail) {
      detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    }
    if (status === 0) detail = "The server is not reachable (network or server down)";
    else if (status >= 500 && !(payload && payload.detail)) detail = `Server error (${status})`;
    super(detail);
    this.status = status;
    this.code = (payload && payload.code) || null;
    this.payload = payload;
    // Field-level validation problems: [{field, message}, ...]
    this.errors = (payload && Array.isArray(payload.errors)) ? payload.errors : [];
  }
}

const API = {
  csrf: null,

  async request(method, path, opts = {}) {
    const headers = {};
    const token = this.csrf || readCookie("gpha_csrf");
    if (token) headers["X-CSRF-Token"] = token;
    // Timed refreshes (notification counts) must not keep an idle session alive.
    if (opts.background) headers["X-Background"] = "1";

    let body;
    if (opts.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.json);
    } else if (opts.form !== undefined) {
      body = opts.form; // FormData: let the browser set the boundary
    }

    // The server counts foreground requests as activity: tell the idle clock when one is sent.
    if (!opts.background && typeof Idle !== "undefined" && !path.startsWith("/api/auth/login")) Idle.noteRequest();
    let res;
    try {
      res = await fetch(path, { method, headers, body, credentials: "include" });
    } catch (err) {
      throw new ApiError(0, null);
    }
    const text = await res.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch { data = text; }
    }
    if (!res.ok) {
      // The server ended the session (idle limit, revoked, expired): leave the app for the sign-in page.
      if (res.status === 401 && !path.startsWith("/api/auth/login") && typeof handleSessionEnded === "function"
          && typeof state !== "undefined" && state.user) {
        handleSessionEnded(data && data.detail);
      }
      throw new ApiError(res.status, data);
    }
    return data;
  },

  get(path) { return this.request("GET", path); },
  getBackground(path) { return this.request("GET", path, { background: true }); },
  post(path, json) { return this.request("POST", path, { json }); },
  patch(path, json) { return this.request("PATCH", path, { json }); },
  put(path, json) { return this.request("PUT", path, { json }); },
  del(path) { return this.request("DELETE", path); },
  upload(path, form) { return this.request("POST", path, { form }); },
};

// Simple DOM helpers.
function qs(selector) { return document.querySelector(selector); }
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}
function badge(value) {
  const cls = String(value).toLowerCase().replace(/\s+/g, "-");
  return el("span", { class: `badge badge-${cls}` }, value);
}
function clear(node) { node.replaceChildren(); }

// ------------------------------------------------------------------ regional settings (time zone, date format)
// Set by an administrator (Configuration > Regional) and sent with the signed-in user. Every date on screen goes
// through these helpers, so changing the setting changes the whole workspace.
const REGIONAL = { time_zone: "Africa/Accra", date_format: "DD/MM/YYYY", time_format: "24-hour", fiscal_year_start_month: 1 };
const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function setRegional(r) { if (r && typeof r === "object") Object.assign(REGIONAL, r); }

// Plain dates ("2026-10-15") are calendar days, never shifted. Server datetimes are UTC; those written without a
// zone ("2026-10-15T08:30:00") are read as UTC too.
function parseWhen(value) {
  if (value instanceof Date) return { date: value };
  const s = String(value);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (m) return { day: { y: Number(m[1]), m: Number(m[2]), d: Number(m[3]) } };
  const iso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s) ? `${s}Z` : s;
  return { date: new Date(iso) };
}

function zonedParts(date) {
  let tz = REGIONAL.time_zone || "UTC";
  try { new Intl.DateTimeFormat("en-GB", { timeZone: tz }); } catch { tz = "UTC"; }
  const parts = {};
  new Intl.DateTimeFormat("en-GB", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(date).forEach((p) => { parts[p.type] = p.value; });
  return { y: Number(parts.year), m: Number(parts.month), d: Number(parts.day), hh: Number(parts.hour), mm: Number(parts.minute) };
}

function formatDay({ y, m, d }) {
  const dd = String(d).padStart(2, "0"); const mo = String(m).padStart(2, "0");
  switch (REGIONAL.date_format) {
    case "DD MMM YYYY": return `${dd} ${MONTHS_SHORT[m - 1]} ${y}`;
    case "DD-MM-YYYY": return `${dd}-${mo}-${y}`;
    case "YYYY-MM-DD": return `${y}-${mo}-${dd}`;
    case "MM/DD/YYYY": return `${mo}/${dd}/${y}`;
    default: return `${dd}/${mo}/${y}`;
  }
}

function formatClock({ hh, mm }) {
  const min = String(mm).padStart(2, "0");
  if (REGIONAL.time_format === "12-hour") return `${hh % 12 || 12}:${min} ${hh < 12 ? "AM" : "PM"}`;
  return `${String(hh).padStart(2, "0")}:${min}`;
}

// The fiscal year a day falls in (named after the calendar year in which it starts).
function fiscalYearOf(date = new Date()) {
  const p = zonedParts(date);
  const start = Number(REGIONAL.fiscal_year_start_month) || 1;
  return p.m >= start ? p.y : p.y - 1;
}
function currentFiscalYear() { return fiscalYearOf(new Date()); }
