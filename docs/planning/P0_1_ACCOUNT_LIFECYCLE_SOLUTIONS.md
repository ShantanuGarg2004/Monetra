# P0.1 — Account lifecycle solutions

**Date:** 2026-10-29  
**Status:** Plan only. No application code in this change.  
**Execution prompts:** `P0_1_ACCOUNT_LIFECYCLE_EXECUTION.md`

This note reviews the current auth path and records the design for the gaps in the P0.1 brief. It is not a legal opinion. Where a retention period would depend on a statute, the plan says so and does not invent one.

## What the code does today

| Behavior | Where | Consequence |
| --- | --- | --- |
| Signup requires email, password, confirm password. Password minimum is 12 characters. The dialog shows that rule only after the server rejects the submit | `schemas.py`, `LoginPage.jsx` | Duplicate email returns `409` and `account_exists` |
| Passwords are Werkzeug hashes | `database/repository.py` `insert_account` | Keep this. Do not add a second hasher |
| One cookie, `finpilot_session`, signed with `SESSION_SECRET`, salt `finpilot-session`, max age 12 hours | `services/sessions.py` | Every browser holds the same kind of token |
| The cookie stores `account_id` and `session_version`. A request is accepted only when the version matches `accounts.session_version` | `services/actor.py` | Logout calls `bump_session_version`, so every device for that account stops working |
| Login failure uses one sentence: “Email or password is incorrect.” | `routes/auth_routes.py` | Signup still reveals that the email is registered |
| Login and signup are a fixed window: `RATELIMIT_AUTH`, default 20 per minute, route class `auth_attempt`, keyed by client address | `services/rate_limit/policies.py` | Logout is exempt. Verify, reset, and resend routes do not exist. A fixed window can allow two bursts at the minute boundary |
| Rejected API keys use a separate class, `credential_failure`, same 20-per-minute expression | `gateway.py` `note_rejected_credential` | Leave this class alone. It is not the password form |
| No email sender, no verification, no reset, no email change, no account-delete route, no settings screen | — | The settings icon in the top bar has no handler |

`API_SECRET_KEY` stays the local Swagger password. This plan does not rotate it and does not add a superuser scope. Schema changes stay idempotent SQL under `database/sql/`. Do not add Alembic.

Existing accounts, when verification ships, get `email_verified_at` set to `accounts.created_at` in that same SQL script. New signups stay unverified until they finish the check. That keeps current users able to open their profiles on the day of deploy.

## Third-party dependency

Verification, reset, and the notice to the old address need a transactional email API. The repository has no mailer.

**Chosen dependency:** Resend’s HTTPS API (`https://api.resend.com/emails`).

| Item | Choice |
| --- | --- |
| Why this and not a second auth product | The app already owns the password hash and the cookie. Firebase Auth and similar would replace that path. Deployment notes already keep email and password in this app |
| Configuration | `EMAIL_API_KEY` and `EMAIL_FROM` live in the environment. The key is never committed, never copied into these docs, and never set on Railway |
| Code shape | One function, `send_email(to, subject, text)`. Tests replace it. No provider SDK is required if the call is a single HTTP POST |
| What must never be sent to logs | The raw password, the raw verification secret, the raw refresh token, the Resend API key |

**Where it runs.** Localhost calls Resend as soon as the mailer exists. The gitignored `.env` holds the key. `EMAIL_FROM` is `FinPilot <onboarding@resend.dev>` until a domain is verified. Resend delivers that shared address only to the inbox on the Resend account, and returns 403 for every other recipient. The account row is still created, and the client gets the resend hint.

The current Railway deployment does not receive the key. A missing key logs and skips the network call in every environment, so that process keeps starting. After a domain is verified in Resend, the API moves to GCP and `EMAIL_FROM` becomes an address on that domain. The Vercel frontend can stay on its current hostname. The link in the mail uses the public app origin, which is separate from the From domain.

No SMS provider. One email mechanism covers verification, reset, and the new-address check.

## Mechanism for email proofs

Use a **signed, single-use link that does not complete on GET**. The mail contains a URL. Opening it shows a confirm button. The button POSTs the token. Mail scanners that only GET the URL do not burn it.

Do not also ship a 6-digit OTP in the first implementation.

The same table serves verification, password reset, and new-email confirmation.

`auth_challenges`

| Column | Role |
| --- | --- |
| `id` | Row id |
| `account_id` | Owner |
| `purpose` | `verify_email`, `reset_password`, `change_email` |
| `secret_hash` | SHA-256 of the random secret. The raw secret is only in the email |
| `target_email` | For `change_email`, the new address. Null for the other purposes |
| `expires_at` | 30 minutes |
| `consumed_at` | Set when the POST succeeds |
| `attempt_count` | Wrong presents. At 5, set `consumed_at` and reject further tries |
| `created_at` | Issued time |

A newer challenge for the same account and purpose marks the older unconsumed row consumed. One live challenge per purpose.

Expired, consumed, and wrong secrets all return the same client sentence: “That link is invalid or expired.” The server log can keep the reason code. The body does not say which of the three it was.

## 1. Sign-up

Keep the server rules: email shape, password at least 12 characters, confirm password must match. Show the 12-character rule on the form before submit. Do not add character-class rules. Those shrink the set of passwords people can pick and the hasher does not need them.

Hash with the existing `generate_password_hash`. Login keeps `check_password_hash`.

Duplicate email: keep `409` and `account_exists` on signup. The person is claiming that address, and the form can say it is already registered. Signup sits on the auth token bucket below so the status cannot be used as a high-speed directory. Forgot-password and resend do **not** use this 409. They always return the same 200 body.

Signup errors stay generic for anything that is not a field validation or a known duplicate: “Could not create the account.” Do not echo the database exception.

A new account is signed in and unverified. The next screen is the verification wait, not the profile form.

## 2. Email verification

After signup, send one link to that email. The account can call:

- `GET /api/auth/me`
- `POST /api/auth/verify-email`
- `POST /api/auth/resend-verification`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`

Profile create, report, chat, goal, and PDF download return `403` with code `email_unverified` until `accounts.email_verified_at` is set. The React shell shows a single verify panel instead of the profile form.

Link lifetime is 30 minutes. Confirming consumes the row. A second POST with the same secret fails. Resend mints a new secret and consumes the previous row. Resend uses its own bucket (below), which is the cooldown.

Delivery failure: the send returns an error to the client only on the signup response if the first mail fails (“Account created, but the verification email could not be sent. Use resend.”). The account row still exists. Resend is the recovery. Do not delete the account because mail failed.

Wrong, expired, and already-used links share the sentence in the mechanism section. Five wrong presents burn the challenge.

## 3. Sign-in and sessions

Replace the 12-hour cookie with two cookies.

| Cookie | Lifetime | Contents | Path |
| --- | --- | --- | --- |
| `finpilot_access` | 15 minutes | Signed payload: `account_id`, `session_id` | `/` |
| `finpilot_refresh` | 7 days, absolute from session creation | Opaque random secret. Database stores SHA-256 only | `/api/auth/refresh` |

Fifteen minutes is the access lifetime inside the 15-to-20-minute range. It is short enough that a stolen access cookie dies quickly, and long enough that a normal page is not refreshing on every click.

The refresh lifetime does not slide. `sessions.expires_at` is `created_at + 7 days`. Refreshing inside that window rotates the secret and does not extend the 7 days. When the window ends, both cookies are cleared and the person signs in again. That is the end of the session. Do not rotate `SESSION_SECRET` or `API_SECRET_KEY` to end it. Those secrets are process-wide and would sign every account out.

**Rotation.** Each successful refresh stores a new secret hash and keeps the previous hash on the row as `previous_secret_hash` until the next rotation. A request that presents `previous_secret_hash` means the old secret was reused. Revoke **that session row only**. Other devices keep their own rows.

**Device scope.** `sessions` is one row per sign-in:

- `id`, `account_id`
- `secret_hash`, `previous_secret_hash`
- `created_at`, `expires_at`, `revoked_at`, `last_seen_at`
- `user_agent` truncated to 200 characters, for a later settings list. The first UI does not need to list devices

Logout loads the access cookie, sets `revoked_at` on that `session_id`, and clears both cookies on this browser. It does **not** call `bump_session_version`.

`accounts.session_version` remains the “revoke every device” switch. Bump it only for password reset, password change, completed email change, and account deletion. `resolve_actor` keeps comparing the access payload’s version to the account so those events kill every device within one access lifetime, and the session rows are revoked in the same transaction so refresh cannot mint a new access cookie.

`resolve_actor` also loads the session row. A missing row, a `revoked_at`, or `expires_at` in the past is `session_expired`. A bad access cookie still does not fall through to an API key.

The React client, on `401` and `session_expired`, calls `POST /api/auth/refresh` once and retries the original request once. A second 401 runs the existing sign-out path. `/auth/me` on load uses the same single refresh.

Cookies stay HttpOnly. `Secure` and `SameSite` stay as `_cookie_flags` already defines them (Lax without Secure on local, None and Secure otherwise). Refresh uses the same flags so the cross-origin deployment still sends it.

Deploying this signs everyone out once. Old `finpilot_session` cookies do not match the new name. That is acceptable.

Scoped API keys are unchanged. They are not browser sessions and they do not use the refresh cookie.

## 4. Forgot password and reset

`POST /api/auth/forgot-password` with `{email}` always returns 200 and “If an account exists for that email, a reset link is on its way.” If the address exists and is verified, send the link. If it does not exist, send nothing and still return 200. Unverified accounts get the verification link path, not a reset, and the client still sees the same 200.

The reset POST takes the secret and a new password plus confirm. The same 12-character rule applies. Success consumes the challenge, replaces `password_hash`, revokes every session row, bumps `session_version`, and does not set a new cookie. The person signs in on the device they have. Existing API keys stay valid on reset. Deleting keys is reserved for account deletion. Say that in the reset screen: “You will need to sign in again on each device.”

## 5. Change email

This requires a verified session and the current password in the body. A wrong password is `invalid_credentials`, same sentence as login.

Store the new address on a `change_email` challenge. Do not write it onto `accounts.email` yet. Send the confirm link to the **new** address. Send a notice to the **old** address that a change was requested, with no secret in that notice. If the notice to the old address fails, still leave the challenge unconfirmed. The address does not change until the new one confirms.

Confirming consumes the challenge, updates `accounts.email`, sets `email_verified_at` to now, revokes every session, and bumps `session_version`. The person signs in again with the new address.

A challenge whose `target_email` is already another account’s email is consumed and the confirm returns the invalid-link sentence. Two accounts cannot end on one address.

## 6. Isolation, cookies, and limits

Access checks stay account-scoped through `resolve_actor` and the existing owner queries. Add tests that account A’s cookie receives 404 on account B’s profile, report, chat, job, and PDF. Those tests belong in the execution sprint that locks the suite. They do not need a new authorization model.

Cookie flags above. Secrets: `SESSION_SECRET` and `API_SECRET_KEY` stay environment-only. Challenge secrets and refresh secrets are stored as SHA-256. Rate-limit keys for emails are SHA-256 of the normalized address, not the raw address, in `finpilot_ratelimit`.

Logout, reset, and deletion each have a test that the revoked session’s refresh returns 401 and a second device’s session still works, except when the action is reset, email change, password change, or deletion. Those four revoke all devices on purpose.

## 7. Account deletion

Add a settings page. The top-bar settings control opens it. The page holds change password, change email, and delete account.

Delete is a typed confirmation of the account email plus the current password. The server checks both. Then, in one transaction:

1. Revoke every session row and bump `session_version`.
2. Revoke `api_credentials` for the account (`revoked_at`).
3. Delete PDF files for that account’s profiles (`data/pdfs` names the code already uses).
4. Delete `users` rows. Existing foreign keys cascade reports, chat, and jobs.
5. Delete `auth_challenges` and `sessions`.
6. Delete the `accounts` row.
7. Clear both cookies.

Goal results are browser memory only. Nothing to delete on the server. The response body is “Account deleted.” It does not include email, ids, or row counts.

**Backups and logs.** The application does not keep a copy after that transaction. Postgres dumps and disk snapshots, if an operator takes them, can still contain the rows until those backups age out. This plan does not set a statutory retention period. Record the operator’s backup window in the deployment notes when one exists. Until then the product behavior is immediate deletion. Do not log passwords, challenge secrets, refresh secrets, or profile amounts on this path.

Acceptance: after deletion, the old access cookie, the old refresh cookie, and any scoped key for that account fail. Profile, report, chat, and PDF reads for those ids return 404.

## Token buckets for auth

The gateway still chooses the route class. For the auth classes below, the limiter store uses a token bucket instead of the fixed window. Report, chat, read, and goal limits stay on the fixed window they have now. `credential_failure` stays a fixed window for bad API keys.

Bucket state in `finpilot_ratelimit`: key, `tokens` numeric, `updated_at`. First sight of a key starts at **capacity** (the bucket is full).

```text
tokens_now = min(capacity, tokens_stored + refill_per_second * seconds_since_updated)
if tokens_now < 1: reject, retry_after = ceil((1 - tokens_now) / refill_per_second)
else: store tokens_now - 1
```

| Bucket | Routes | Key | Initial tokens (capacity) | Refill | Why these numbers |
| --- | --- | --- | --- | --- | --- |
| `auth_ip` | Signup, login, forgot-password, reset submit, verify submit | `ip:<address>` | 8 | 1 token every 15 seconds (4 per minute) | A person needs a double-submit and a few typos. Eight covers that burst. The refill is 4 per minute, not the old 20, so a script cannot empty a second window of 20 at the minute boundary. A full bucket returns in 8 × 15 seconds = 2 minutes |
| `auth_account` | Failed password checks on login, change-password, change-email, and delete | `email:<sha256>` | 5 | 1 token every 10 minutes | Five wrong passwords, then one try each 10 minutes. Stops guessing one account from many addresses. A successful password check does not spend this bucket |
| `auth_resend` | Resend verification, and the send inside forgot-password | `email:<sha256>` | 3 | 1 token every 10 minutes | Three mails up front, then one each 10 minutes. That is the cooldown. Nine mails is the ceiling in an hour (3 + 6) |
| `auth_challenge` | Wrong secret on verify, reset, or change-email confirm | `challenge:<id>` | 5 | none | Five misses burn the row. No refill. This is the single-use attempt cap |
| `auth_refresh` | `POST /api/auth/refresh` | `session:<id>` | 4 | 1 token every 60 seconds | A live tab refreshes about once per 15 minutes. Four tokens cover a burst of retries. One per minute stops a loop |
| `auth_account_action` | Change email, change password, delete | `acct:<id>` | 5 | 1 token every 60 seconds | These need the password again. Five tries, then one per minute |

Logout is not on these buckets. It must succeed so a shared computer can be cleared.

`retry_after` from the formula is what the 429 body already exposes. The client can keep showing “Try again in N seconds.”

## What this plan leaves unchanged

- Werkzeug password hashes
- Scoped API keys and `API_SECRET_KEY` for Swagger
- Owner checks on profiles, reports, chat, and PDFs
- Fixed-window quotas for reports, chat, goals, and reads
- No Alembic
