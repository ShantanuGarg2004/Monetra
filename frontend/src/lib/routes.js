/** Path guard for the signed-in app. No router package. */

export const PAGE_TO_PATH = {
  profile: "/profile",
  dashboard: "/dashboard",
  advisory: "/advisory",
  chat: "/chat",
  goals: "/goals",
  settings: "/settings",
};

const SCREENS = {
  "/profile": "profile",
  "/dashboard": "dashboard",
  "/advisory": "advisory",
  "/chat": "chat",
  "/goals": "goals",
  "/settings": "settings",
};

const NEEDS_PROFILE = new Set(["/dashboard", "/advisory", "/chat", "/goals"]);
const MAIL_LINKS = new Set(["/verify-email", "/reset-password", "/confirm-email"]);

export function isMailLink(path) {
  return MAIL_LINKS.has(normalizePath(path));
}

/** Keep ?id=&token= when a refresh rewrites the same mail page. A different page drops it. */
export function locationForSamePath(nextPath, currentPath, search = "", hash = "") {
  const next = normalizePath(nextPath);
  const current = normalizePath(currentPath);
  if (next !== current) return next;
  const query = typeof search === "string" ? search : "";
  const fragment = typeof hash === "string" ? hash : "";
  return `${next}${query}${fragment}`;
}

export function normalizePath(pathname) {
  const raw = typeof pathname === "string" ? pathname : "/";
  const path = raw.split("?")[0].split("#")[0];
  if (!path || path === "/") return "/";
  const trimmed = path.replace(/\/+$/, "");
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

export function pathForPage(page) {
  if (typeof page === "string" && page.startsWith("/")) return normalizePath(page);
  return PAGE_TO_PATH[page] || "/profile";
}

/**
 * Decide which screen to draw, and which path the address bar should show.
 * `redirect` is null when the current path may stay.
 * A signed-out visit to a known app path keeps that path so sign-in can return to it.
 */
export function resolveRoute({ signedIn, path, profileId }) {
  const current = normalizePath(path);
  const hasProfile = profileId != null && Number.isFinite(Number(profileId));
  const knownApp = Object.prototype.hasOwnProperty.call(SCREENS, current);

  if (current === "/verify-email") {
    return { screen: "verify-email", redirect: null, remember: null };
  }

  if (current === "/reset-password") {
    return { screen: "reset-password", redirect: null, remember: null };
  }

  if (current === "/confirm-email") {
    return { screen: "confirm-email", redirect: null, remember: null };
  }

  if (!signedIn) {
    if (current !== "/" && !knownApp) {
      return { screen: "landing", redirect: "/", remember: null };
    }
    return { screen: "landing", redirect: null, remember: knownApp ? current : null };
  }

  if (current === "/") {
    const next = hasProfile ? "/dashboard" : "/profile";
    return { screen: SCREENS[next], redirect: next, remember: null };
  }

  if (current === "/profile" || current === "/settings") {
    return { screen: SCREENS[current], redirect: null, remember: null };
  }

  if (NEEDS_PROFILE.has(current)) {
    if (!hasProfile) return { screen: "profile", redirect: "/profile", remember: null };
    return { screen: SCREENS[current], redirect: null, remember: null };
  }

  return { screen: "profile", redirect: "/profile", remember: null };
}
