import { ApiError, toApiError } from "../lib/apiErrors";
import { shouldAttemptRefresh } from "../lib/sessionRefresh";

/* Central API configuration shared by every data hook and page. */
export const API_BASE = import.meta.env.VITE_API_URL || "/api";
export const headers = {
  "Content-Type": "application/json",
};

function fetchOnce(path, options) {
  return fetch(`${API_BASE}${path}`, {
    ...options,
    cache: options.cache || "no-store",
    credentials: "include",
    headers: { ...headers, ...(options.headers || {}) },
  });
}

async function readBody(res) {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }
  if (!res.ok) {
    try {
      return { error: await res.text() };
    } catch {
      return null;
    }
  }
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function noteSessionEnded(error) {
  if (error.code === "session_expired" && typeof window !== "undefined") {
    window.dispatchEvent(new Event("finpilot:session-expired"));
  }
}

async function refreshSession() {
  try {
    const res = await fetchOnce("/auth/refresh", { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

async function failOrRefresh(path, options, res, data, alreadyRetried) {
  const error = toApiError(new Error("request failed"), res, data);
  if (shouldAttemptRefresh({ code: error.code, path, alreadyRetried })) {
    if (await refreshSession()) return "retry";
  }
  noteSessionEnded(error);
  throw error;
}

/* Small fetch helper that normalises the backend's error shape into ApiError. */
export async function apiFetch(path, options = {}, alreadyRetried = false) {
  let res;
  try {
    res = await fetchOnce(path, options);
  } catch (err) {
    throw toApiError(err);
  }
  const data = await readBody(res);
  if (!res.ok) {
    const next = await failOrRefresh(path, options, res, data, alreadyRetried);
    if (next === "retry") return apiFetch(path, options, true);
  }
  return data;
}

export async function apiFetchRaw(path, options = {}, alreadyRetried = false) {
  let res;
  try {
    res = await fetchOnce(path, options);
  } catch (err) {
    throw toApiError(err);
  }
  if (!res.ok) {
    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    const next = await failOrRefresh(path, options, res, data, alreadyRetried);
    if (next === "retry") return apiFetchRaw(path, options, true);
  }
  return res;
}

export { ApiError, toApiError };
