# P0.1 Sprint 6 — settings, deletion, and cross-account reads

**Date:** 2026-10-29
**Plan:** `docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md` sprint 6
**Verdict:** The settings control opens change password, change email, and delete account. Password change and deletion sign every device out. Deletion removes that account’s rows and PDF files from the running application. Another account’s profile, report, chat, and PDF reads return 404. Operator backups are outside this deletion. No statutory retention period is coded.

---

## 1. What shipped

The top-bar settings control opens `/settings`. The page holds change password, change email, and delete account. Change email uses the sprint 5 route.

`POST /api/auth/change-password` requires the current password. The new password must be at least 12 characters and the confirmation must match. A wrong current password is HTTP 401, “Email or password is incorrect.”, code `invalid_credentials`, and spends `auth_account`. Success replaces the password hash, revokes every session, bumps `session_version`, clears both cookies, and does not sign the browser in. Scoped API keys stay valid.

`POST /api/auth/delete-account` requires the current password and the account email typed again. A wrong password uses the same `invalid_credentials` path. A different email is HTTP 400, code `email_mismatch`, and the account stays. Success runs one transaction: revoke every session, bump `session_version`, revoke `api_credentials`, delete job rows for that account (their account foreign key has no cascade), delete users (reports, chat, and any remaining jobs cascade), delete challenges and sessions, delete the credential rows, then delete the account. PDF files for those profiles are removed after the commit. Both cookies are cleared. The body is only `{"message": "Account deleted."}`. The handler does not log the password, secrets, or profile amounts.

`GET /api/profile/<id>` returns that profile for the owning account and HTTP 404, code `not_found`, for every other account. Report, chat history, and PDF download already returned that 404 through the same owner check.

| Bucket | When | Key | Capacity | Refill |
| --- | --- | --- | --- | --- |
| `auth_account_action` | Change email, change password, and delete | `acct:<id>:auth_account_action` | 5 | 1 token every 60 seconds |
| `auth_account` | Wrong current password | `email:<sha256>:auth_account` | 5 | 1 token every 10 minutes |

Logout is still exempt and still revokes only the session that called it.

## 2. Tests

`python -m pytest -q` — **166 passed**.

`npm test` in `frontend/` — **22 passed**.

| Case | Result |
| --- | --- |
| Delete account | HTTP 200. Body is only `{"message": "Account deleted."}` |
| After deletion | Both devices’ `/api/auth/me` and refresh calls return 401. The scoped key returns 401. Profile, report, chat, and PDF reads return 404. The PDF file is gone. The account, profile, report, chat, and job rows are gone |
| Account A reading account B | Profile, report, chat, and PDF return 404. A’s profile list does not include B’s id. B can still read B’s own profile, report, chat, and PDF |
| Logout | The device that called it gets 401. The other device stays signed in |
| Short new password | HTTP 400. The other session stays signed in |
| Wrong current password | HTTP 401, `invalid_credentials`, the login sentence |
| Password change | HTTP 200. Both sessions and both refresh cookies fail. The caller is not signed in. The scoped key still works. The old password fails. The new password signs in |
| Typed email does not match | HTTP 400, `email_mismatch`. Both sessions stay signed in |
| Typed email with different case | Deletion succeeds |
| `/settings` signed in, no profile | Stays on settings |
| `/settings` signed out | Landing screen, path remembered |

Backup retention is not implemented in code. `docs/deployment/DEPLOYMENT_STRATEGY.md`, `docs/deployment/VERCEL_RAILWAY_DEPLOY_GUIDE.md`, and `docs/deployment/GCP_FREE_CREDITS_DEPLOYMENT.md` state that operator backups are outside this deletion and that no statutory hold is coded.

## 3. Browser

The local app was open and signed out on the landing page. The address bar stayed on `http://localhost:5173` when `/settings` was typed, so the signed-in settings form was not clicked. The route tests cover that screen. The running API, with no cookie, returns 401 `session_expired` for change password and delete account. No signup was sent, so no verification mail went out.
