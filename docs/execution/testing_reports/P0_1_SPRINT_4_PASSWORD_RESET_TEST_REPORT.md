# P0.1 Sprint 4 — forgot password and reset

**Date:** 2026-10-29
**Plan:** `docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md` sprint 4
**Verdict:** `POST /api/auth/forgot-password` returns the same 200 body for an unknown address, an unverified account, and a verified account. A reset link is sent only when the account exists and `email_verified_at` is set. Confirming the link replaces the password, revokes every session, bumps `session_version`, and does not sign the browser in. Scoped API keys stay valid. Email change and account deletion are not in this sprint.

---

## 1. What shipped

`auth_challenges.purpose` now allows `reset_password` as well as `verify_email`. The check is replaced on databases created in sprint 3. Link lifetime is 30 minutes. The page is `/reset-password?id=&token=`. Opening it does not consume the secret. The confirm POST does. Five wrong secrets consume the row. Expired, used, and wrong secrets share: "That link is invalid or expired."

The new password uses the 12-character rule and a matching confirm password. A password that fails those rules does not consume the link.

Success, in one transaction, writes the new Werkzeug hash, sets `revoked_at` on every session row for the account, increments `session_version`, and consumes the challenge. The response clears cookies and does not issue a new session. The screen says "You will need to sign in again on each device."

`auth_ip` now includes forgot-password and the reset submit, with the same capacity of 8. The reset send spends `auth_resend` (capacity 3, one token every 10 minutes, key `email:<sha256>`). When that bucket is empty the send is skipped and the 200 body stays the same. An unknown or unverified address does not spend `auth_resend` and does not send mail.

A body that is not an email is a validation error. That response is the same whether or not an account exists.

## 2. Tests

`python -m pytest -q` — **158 passed**.

`npm test` in `frontend/` — **19 passed**.

| Case | Result |
| --- | --- |
| Unknown, verified, and unverified addresses | HTTP 200 and the same body. Mail is sent only for the verified address |
| Fourth reset send for one verified address | HTTP 200, same body, no further mail |
| Two live sessions, then reset | Both `/api/auth/me` and both refresh calls return 401. The reset response does not sign the caller in |
| Old password | HTTP 401 `invalid_credentials` |
| New password | HTTP 200 |
| Second POST of the same secret | HTTP 400, "That link is invalid or expired." |
| Five wrong reset secrets | The real token then fails and the stored password is unchanged |
| Scoped API key issued before reset | `GET /api/users` with that key still returns 200 |
| Account email | Unchanged |
| `/reset-password` while signed out | Stays on that screen |

## 3. Left for later

Change email and account deletion.
