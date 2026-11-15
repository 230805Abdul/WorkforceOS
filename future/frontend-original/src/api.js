const API_BASE = "/api/v1";

function getTokens() {
  return {
    access: localStorage.getItem("access_token"),
    refresh: localStorage.getItem("refresh_token"),
  };
}

function setTokens(access, refresh) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const { access } = getTokens();
    if (access) headers["Authorization"] = `Bearer ${access}`;
  }

  let res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  // Transparent refresh-on-401, once, before giving up.
  if (res.status === 401 && auth) {
    const { refresh } = getTokens();
    if (refresh) {
      const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (refreshRes.ok) {
        const { access_token, refresh_token } = await refreshRes.json();
        setTokens(access_token, refresh_token);
        headers["Authorization"] = `Bearer ${access_token}`;
        res = await fetch(`${API_BASE}${path}`, {
          method,
          headers,
          body: body ? JSON.stringify(body) : undefined,
        });
      } else {
        clearTokens();
      }
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password }, auth: false }),
  register: (payload) => request("/auth/register", { method: "POST", body: payload, auth: false }),
  me: () => request("/auth/me"),
  listJobs: () => request("/jobs", { auth: false }),
  createJob: (payload) => request("/jobs", { method: "POST", body: payload }),
  listCandidates: () => request("/candidates"),
  createCandidate: (payload) => request("/candidates", { method: "POST", body: payload }),
  setTokens,
  clearTokens,
  getTokens,
};
