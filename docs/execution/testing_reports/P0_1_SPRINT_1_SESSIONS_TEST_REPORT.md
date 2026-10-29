# P0.1 Sprint 1 — device sessions

**Date:** 2026-10-29
**Plan:** `docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md` sprint 1
**Verdict:** Sign-in stores one session row per device. Logout revokes that row and leaves every other device signed in. The 12-hour `finpilot_session` cookie is replaced by a 15-minute `finpilot_access` cookie and a 7-day `finpilot_refresh` cookie.

`API_SECRET_KEY` was not rotated.

---

## 1. What shipped

`database/sql/sessions.sql` creates `sessions`. Startup applies that script from `database/models.py`. The same script is safe to run again.

`finpilot_access` is signed with `SESSION_SECRET` (salt `finpilot-access`) and holds `account_id`, `session_id`, and `session_version`. It expires in 15 minutes. `finpilot_refresh` is an opaque secret. The database stores SHA-256 only. Its path is `/api/auth/refresh`. `expires_at` is seven days from the insert and refresh does not move it.

Refresh stores a new hash and keeps the previous hash. Presenting that previous secret revokes that session row only. Logout sets `revoked_at` on the session in the access cookie and does not call `bump_session_version`. When the access cookie has already expired, logout uses the refresh secret to find the same row.

`resolve_actor` accepts the access cookie only when the signature is valid, the session row is live, and `session_version` still matches. A bad cookie does not fall through to an API key.

The React client, on `401` `session_expired`, calls `POST /api/auth/refresh` once and retries the original request once. A second failure dispatches the existing `finpilot:session-expired` event. The signup form shows “Password must be at least 12 characters.” before submit.

Cookie flags are unchanged: Lax without Secure on local, None and Secure otherwise. Deploying this signs current browsers out once, because the cookie name changed.

`POST /api/auth/refresh` is exempt from the rate limiter until sprint 2 adds the auth refresh bucket. Login and signup stay on the existing fixed window.

## 2. Tests

`python -m pytest -q` — **141 passed**.

`npm test` in `frontend/` — **17 passed**.

| Case | Result |
| --- | --- |
| Access token signed with a different `SESSION_SECRET` | `read_token` returns `None` |
| Signup | Sets `finpilot_access` and `finpilot_refresh` |
| Production cookies | Both cookies are `Secure` and `SameSite=None`. Refresh path is `/api/auth/refresh` |
| Logout | `session_version` stays 1. That session’s `revoked_at` is set. The old access cookie gets 401 `session_expired` |
| Two devices | Logout on one leaves the other able to call `/api/auth/me` |
| Refresh | Secret hash changes, `expires_at` stays the same, and the new access cookie calls `/api/auth/me` |
| Reuse of the previous refresh secret | Revokes that session only. The other device still calls `/api/auth/me` |
| Bad access cookie plus a valid API key | 401 `session_expired` |
| Signup password hint | The create-account form shows the 12-character rule before submit |

## 3. Left for later

Sprint 2 adds the auth token buckets. Refresh is exempt until that sprint. Email verification, password reset, email change, and account deletion are not in this sprint.
