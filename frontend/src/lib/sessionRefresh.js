/** One refresh attempt after a dead access cookie, then the existing sign-out path. */

export function shouldAttemptRefresh({ code, path, alreadyRetried }) {
  const clean = String(path || "").split("?")[0];
  return code === "session_expired" && !alreadyRetried && clean !== "/auth/refresh";
}
