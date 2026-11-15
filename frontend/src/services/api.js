// All HTTP calls to the FastAPI backend live here. Components never call fetch directly.
//
// Authentication: the browser keeps the HttpOnly session cookie and sends it automatically; JavaScript never sees it.
// For every change (POST/PUT/PATCH/DELETE) we add the per-session CSRF token from /api/auth/me in a header.
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(message, { status = 0, errors = {}, code = null } = {}) {
    super(message);
    this.status = status;
    this.errors = errors; // field -> message, for showing validation errors next to inputs
    this.code = code; // e.g. "session_expired", "forbidden", "rate_limited"
  }
}

const UNREACHABLE = "Cannot reach the WorkforceOS API. Is the backend running on port 8000?";

// Set by AuthProvider: where to get the CSRF token, and what to do when the server says "you're not signed in".
let csrfToken = null;
let onUnauthorized = () => {};
let onReauthRequired = null; // () => Promise<boolean>: asks the user for their password ("sudo mode")
export function configureAuth({ token, unauthorized, reauth } = {}) {
  if (token !== undefined) csrfToken = token;
  if (unauthorized) onUnauthorized = unauthorized;
  if (reauth) onReauthRequired = reauth;
}

// Requests whose 401 is an expected answer, not "your session ended".
const AUTH_PROBES = ["/auth/me", "/auth/login", "/auth/register", "/auth/reset-password", "/auth/config", "/auth/logout",
  "/auth/reauthenticate"];

async function request(path, { method = "GET", body, params, signal, retried = false } = {}) {
  const query = params
    ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString()
    : "";
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let res;
  try {
    res = await fetch(`${BASE}${path}${query ? `?${query}` : ""}`, {
      method,
      signal,
      headers,
      credentials: "include", // send the session cookie (also if the API ever lives on another origin)
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(UNREACHABLE);
  }
  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    // The Vite proxy answers 500/502 with an empty body when the backend is down.
    if (!data && res.status >= 500) throw new ApiError(UNREACHABLE, { status: res.status });
    const error = new ApiError(data?.detail || `Request failed (${res.status})`, { status: res.status, errors: data?.errors, code: data?.code });
    if (res.status === 401 && !AUTH_PROBES.includes(path)) onUnauthorized(error);
    // High-impact admin action, password not confirmed recently: ask for it once, then repeat the same request.
    if (data?.code === "reauth_required" && onReauthRequired && !retried) {
      if (await onReauthRequired()) return request(path, { method, body, params, signal, retried: true });
      throw new ApiError("Cancelled: your password wasn't confirmed.", { status: 403, code: "reauth_cancelled" });
    }
    throw error;
  }
  return data;
}

const crud = (base) => ({
  list: (params, signal) => request(base, { params, signal }),
  get: (id, signal) => request(`${base}/${id}`, { signal }),
  create: (body) => request(base, { method: "POST", body }),
  update: (id, body) => request(`${base}/${id}`, { method: "PUT", body }),
  remove: (id) => request(`${base}/${id}`, { method: "DELETE" }),
});

export const api = {
  health: (signal) => request("/health", { signal }),
  meta: (signal) => request("/meta", { signal }),
  dashboard: (signal) => request("/dashboard", { signal }),
  resetDemo: () => request("/demo/reset", { method: "POST" }),
  auth: {
    config: (signal) => request("/auth/config", { signal }),
    me: (signal) => request("/auth/me", { signal }),
    login: (body) => request("/auth/login", { method: "POST", body }),
    register: (body) => request("/auth/register", { method: "POST", body }),
    logout: () => request("/auth/logout", { method: "POST" }),
    updateProfile: (body) => request("/auth/me", { method: "PATCH", body }),
    changePassword: (body) => request("/auth/change-password", { method: "POST", body }),
    logoutOthers: () => request("/auth/logout-others", { method: "POST" }),
    resetPassword: (body) => request("/auth/reset-password", { method: "POST", body }),
    reauthenticate: (body) => request("/auth/reauthenticate", { method: "POST", body }),
    signIns: (signal) => request("/auth/me/sign-ins", { signal }),
  },
  me: {
    employee: (signal) => request("/me/employee", { signal }),
    updateEmployee: (body) => request("/me/employee", { method: "PATCH", body }),
  },
  users: {
    list: (params, signal) => request("/users", { params, signal }),
    get: (id, signal) => request(`/users/${id}`, { signal }),
    invite: (body) => request("/users", { method: "POST", body }),
    update: (id, body) => request(`/users/${id}`, { method: "PATCH", body }),
    setStatus: (id, status) => request(`/users/${id}/status`, { method: "PATCH", body: { status } }),
    setRoles: (id, role_ids) => request(`/users/${id}/roles`, { method: "PUT", body: { role_ids } }),
    resetLink: (id) => request(`/users/${id}/reset-link`, { method: "POST" }),
    revokeSessions: (id) => request(`/users/${id}/revoke-sessions`, { method: "POST" }),
  },
  roles: {
    list: (signal) => request("/roles", { signal }),
    permissions: (signal) => request("/permissions", { signal }),
    create: (body) => request("/roles", { method: "POST", body }),
    update: (id, body) => request(`/roles/${id}`, { method: "PUT", body }),
    remove: (id) => request(`/roles/${id}`, { method: "DELETE" }),
  },
  audit: {
    events: (params, signal) => request("/audit/events", { params, signal }),
    summary: (signal) => request("/audit/summary", { signal }),
    verify: () => request("/audit/verify"),
  },
  departments: crud("/departments"),
  employees: { ...crud("/employees"), nextCode: (signal) => request("/employees/next-code", { signal }) },
  jobs: crud("/jobs"),
  candidates: crud("/candidates"),
  applications: {
    list: (params, signal) => request("/applications", { params, signal }),
    create: (body) => request("/applications", { method: "POST", body }),
    updateStatus: (id, status) => request(`/applications/${id}/status`, { method: "PATCH", body: { status } }),
    remove: (id) => request(`/applications/${id}`, { method: "DELETE" }),
  },
};
