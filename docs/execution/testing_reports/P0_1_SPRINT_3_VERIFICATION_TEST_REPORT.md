# P0.1 Sprint 3 — email verification

**Date:** 2026-10-29
**Plan:** `docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md` sprint 3
**Verdict:** Signup sends a 30-minute confirm-button link and still signs the browser in. Until `email_verified_at` is set, profile create, report, chat, goal, and PDF download return 403 `email_unverified`. Password reset, email change, and account deletion are not in this sprint.

A missing `EMAIL_API_KEY` or `EMAIL_FROM` logs and skips the network call, including on Railway. Tests replace `send_email`. The key stays in the gitignored `.env`.

---

## 1. What shipped

`services/emailer.py` POSTs to Resend when both settings are present. `database/sql/auth_challenges.sql` adds `accounts.email_verified_at` and the `auth_challenges` table. The backfill `email_verified_at = created_at` runs only when that column is first added. A later startup leaves a new signup null. Purpose is `verify_email` only.

The link is `{APP_PUBLIC_URL}/verify-email?id={id}&token={secret}`. Opening the page does not consume the secret. `POST /api/auth/verify-email` does. Five wrong secrets consume the row. Expired, used, and wrong secrets share: "That link is invalid or expired."

Signup still sets both cookies. If Resend rejects the message, the account stays and the 201 body includes "Account created, but the verification email could not be sent. Use resend." Resend consumes the previous unconsumed `verify_email` row. `GET /api/auth/me`, verify, resend, refresh, and logout stay available.

The React app shows a confirm page on `/verify-email` and a waiting panel, with resend and sign out, while `email_verified` is false.

| Bucket | Routes | Key | Capacity | Refill |
| --- | --- | --- | --- | --- |
| `auth_ip` | Signup, login, and verify submit | `ip:<address>:auth_ip` | 8 | 1 token every 15 seconds |
| `auth_challenge` | Wrong verification secret | `challenge:<id>:auth_challenge` | 5 | none |
| `auth_resend` | `POST /api/auth/resend-verification` | `email:<sha256>:auth_resend` | 3 | 1 token every 10 minutes |

## 2. Tests

`python -m pytest -q` — **154 passed**.

`npm test` in `frontend/` — **18 passed**.

| Case | Result |
| --- | --- |
| Signup | HTTP 201, `email_verified` false, mail captured, profile create 403 `email_unverified`, `/api/auth/me` still 200 |
| Confirm POST | HTTP 200, row consumed, profile create then 201. A second POST returns the invalid-link sentence |
| Failed send | HTTP 201, account kept, body tells the client to use resend |
| Five wrong secrets | Row consumed. The real token then returns the same sentence and does not verify |
| Expired row | Same sentence. `email_verified_at` stays null |
| Resend | Three sends replace the open challenge. The old token fails. The fourth is HTTP 429 `auth_resend`, `retry_after` 600. The latest token still confirms |
| Nine verify posts from one address | The ninth is HTTP 429 `auth_ip`, `retry_after` 15 |
| Column added to an existing account | `email_verified_at` becomes `created_at`. A signup inserted after that stays null across another startup |
| `/verify-email` while signed out | Stays on that screen. The address bar is not sent back to `/` |

## 3. Live send

Signup for `shantanugarg94@gmail.com` against the local API returned 201 with `email_verified` false and the resend sentence. Resend answered 403: the shared test sender only delivers to the Resend account inbox, `shantanugarg.04@gmail.com`.

One delivery check to that inbox was accepted (`sent`). The requested Gmail address cannot receive mail until a domain is verified and `EMAIL_FROM` moves onto that domain.

## 4. Left for later

Password reset, email change, and account deletion. The browser confirm button was not clicked in this pass: the IDE kept the foreground while the confirm page was open. The route test covers that the page is not redirected away.
