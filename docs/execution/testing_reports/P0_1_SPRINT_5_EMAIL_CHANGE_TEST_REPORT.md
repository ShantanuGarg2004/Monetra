# P0.1 Sprint 5 — change email

**Date:** 2026-10-29
**Plan:** `docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md` sprint 5
**Verdict:** A verified session can ask to change the email. The current password is required. A wrong password returns the same `invalid_credentials` sentence as login and spends `auth_account`. The request spends `auth_account_action`. `accounts.email` changes only when the new address posts the confirm link. Account deletion is not in this sprint.

---

## 1. What shipped

`POST /api/auth/change-email` requires a signed-in user whose email is already verified. The body is the new address and the current password. A missing password is a validation error. A wrong password is HTTP 401, “Email or password is incorrect.”, code `invalid_credentials`. A correct password does not spend `auth_account`.

The new address is stored on a `change_email` challenge (`target_email`). It is not written onto `accounts.email`. The confirm link goes to the new address. A notice goes to the current address with no secret and no confirm link. If that notice fails, the challenge stays unconfirmed and the address does not change. The link still works.

`POST /api/auth/confirm-email` uses the same pattern as the other links: the page shows a button, and only the POST consumes the secret. Lifetime is 30 minutes. Five wrong secrets consume the row. Success updates `email`, sets `email_verified_at`, revokes every session, bumps `session_version`, and does not sign the browser in. The screen says to sign in again with the new address.

If another account already has the new address, the confirm consumes the challenge and returns “That link is invalid or expired.” The address does not change.

| Bucket | When | Key | Capacity | Refill |
| --- | --- | --- | --- | --- |
| `auth_account_action` | Every change-email request | `acct:<id>:auth_account_action` | 5 | 1 token every 60 seconds |
| `auth_account` | Wrong current password | `email:<sha256>:auth_account` | 5 | 1 token every 10 minutes |
| `auth_challenge` | Wrong confirm secret | `challenge:<id>:auth_challenge` | 5 | none |

The purpose check now allows `change_email` as well as `verify_email` and `reset_password`. Databases created earlier get that check replaced on startup.

## 2. Tests

`python -m pytest -q` — **163 passed**.

`npm test` in `frontend/` — **20 passed**.

| Case | Result |
| --- | --- |
| Body without a password | HTTP 400. The address is unchanged. No confirm mail |
| Five wrong passwords | Each is HTTP 401 with the login sentence. The address is unchanged |
| Sixth change-email request | HTTP 429, `route_class` `auth_account_action`, `retry_after` 60 |
| Wrong login after those five | HTTP 429, `route_class` `auth_account`, `retry_after` 600 |
| Correct password | HTTP 200. A following wrong login is still HTTP 401, so the correct password did not spend `auth_account` |
| Before confirm | The account email is still the old address. The notice to that address has no confirm link |
| Confirm | HTTP 200. The account email is the new address and `email_verified_at` is set. The caller is not signed in |
| Two sessions | Both `/api/auth/me` calls and both refresh calls return 401 |
| Second use of the secret | HTTP 400, “That link is invalid or expired.” |
| Address already on another account | HTTP 400 with that same sentence. Both accounts keep their addresses. The challenge is consumed |
| Notice send fails | HTTP 200. The challenge is unconfirmed and the old address remains. Confirming afterward still moves the email |
| `/confirm-email` while signed out | Stays on that screen |

## 3. Left for later

Account deletion, and the settings screen that will host this form.
