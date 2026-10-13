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

    let body;
    if (opts.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.json);
    } else if (opts.form !== undefined) {
      body = opts.form; // FormData: let the browser set the boundary
    }

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
    if (!res.ok) throw new ApiError(res.status, data);
    return data;
  },

  get(path) { return this.request("GET", path); },
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
    else if (key === "html") node.innerHTML = value;
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
