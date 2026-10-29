# P0.1 — Account lifecycle execution plan

**Date:** 2026-10-29  
**Design:** `docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md`  
**Rule:** One sprint is one prompt. Paste the prompt for the current sprint only. Do not start the next sprint in the same session.

Each prompt assumes the solutions document is binding. Do not add Alembic. Do not rotate `API_SECRET_KEY`. Do not add a superuser scope. Do not send live email from tests. Schema changes are idempotent SQL in `database/sql/`.

Order: 1, then 2, then 3, then 4, then 5, then 6. Sprint 2 can share a branch with sprint 1 only after sprint 1 is merged. Later sprints depend on the session table and the email function.

---

## Sprint 1 — Device sessions, access cookie, refresh cookie

Depends on: nothing in this plan. Replaces the 12-hour `finpilot_session` cookie.

```text
Implement sprint 1 of docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md only. Do not build email verification, password reset, email change, or account deletion.

Sessions are one database row per sign-in. Logout sets revoked_at on that session id and clears cookies on this browser. Do not call bump_session_version from logout. Other sessions for the same account stay valid.

Replace finpilot_session with finpilot_access (15 minutes, signed, account_id + session_id + session_version) and finpilot_refresh (opaque secret, SHA-256 stored, path /api/auth/refresh, absolute expiry 7 days from session creation). Refresh rotates the secret. Reuse of the previous secret revokes that session only and does not revoke other devices. Refresh does not extend the 7-day expiry.

resolve_actor accepts the access cookie only when the signature is valid, the session row is live, and session_version still matches. A bad cookie does not fall through to an API key.

On 401 session_expired, the React client calls POST /api/auth/refresh once and retries the original request once. A second failure uses the existing sign-out path.

Signup still creates the account and signs in, using the new cookies. Show the 12-character password rule on the form before submit. Keep Werkzeug hashes. Keep the 409 for a duplicate email.

Update tests that expect logout to bump session_version. Add a test with two sessions: logout on one leaves the other able to call /api/auth/me. Add a test that refresh rotates and that reuse of the old refresh secret revokes only that session.

Do not add Alembic. Put table changes in an idempotent SQL file under database/sql/. Do not rotate API_SECRET_KEY.
```

---

## Sprint 2 — Auth token buckets

Depends on: sprint 1 routes existing (`login`, `signup`, `refresh`, `logout`).

```text
Implement sprint 2 of docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md only. Do not change report, chat, goal, or read quotas. Do not change the credential_failure fixed window for rejected API keys.

Auth route classes use a token bucket in the existing rate-limit database. First time a key is seen, the bucket starts full (capacity = initial tokens).

tokens_now = min(capacity, stored + refill_per_second * elapsed)
If tokens_now < 1, return 429 with retry_after = ceil((1 - tokens_now) / refill_per_second).
Otherwise store tokens_now - 1.

Buckets, exactly:
- auth_ip: signup, login. Capacity 8. Refill 1 token every 15 seconds. Key ip:<address>.
- auth_account: failed password checks on login only. Capacity 5. Refill 1 token every 10 minutes. Key email:<sha256 of normalized email>. A successful password does not spend this bucket.
- auth_refresh: POST /api/auth/refresh. Capacity 4. Refill 1 token every 60 seconds. Key session:<id>.
Logout is not bucketed.

Wire the classes through the existing gateway so a store error on these classes fails closed. Add tests for a full bucket, a refill, and a 429 retry_after. Do not add email, reset, or deletion in this sprint.
```

---

## Sprint 3 — Verification email and the unverified gate

Depends on: sprint 1 sessions. Sprint 2 buckets should be in place so resend and verify use them.

```text
Implement sprint 3 of docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md only.

Add a small send_email(to, subject, text) that POSTs to Resend when EMAIL_API_KEY and EMAIL_FROM are set. Tests replace send_email. A missing key logs and skips the network call in every environment, so the current Railway process keeps starting. Localhost reads both values from the gitignored .env. EMAIL_FROM there is FinPilot <onboarding@resend.dev>, which Resend delivers only to the inbox on the Resend account. Do not commit the key and do not put it on Railway. After a domain is verified, GCP sets EMAIL_FROM to an address on that domain.

Add auth_challenges as in the solutions note. Purpose for this sprint is verify_email only. Link lifetime 30 minutes. The link opens a page with a confirm button. Only the POST consumes the secret. Five wrong presents burn the row. Expired, used, and wrong secrets return one sentence: "That link is invalid or expired."

Signup sends the link and still signs the browser in. If the send fails, return the account-created response with a resend hint, and keep the account. Resend consumes the previous unconsumed verify_email challenge.

Until email_verified_at is set, profile create, report, chat, goal, and PDF download return 403 code email_unverified. me, verify, resend, refresh, and logout stay allowed. The React app shows a verify panel instead of the profile form.

Grandfather existing accounts: the SQL script sets email_verified_at = created_at where it is null on rows already present. New signups leave it null.

Buckets from the solutions note:
- verify submit joins auth_ip
- wrong secret uses auth_challenge, capacity 5, no refill
- resend uses auth_resend, capacity 3, refill 1 token every 10 minutes, key email:<sha256>

Do not implement password reset, email change, or account deletion.
```

---

## Sprint 4 — Forgot password and reset

Depends on: sprints 1 and 3 (sessions, challenges, send_email).

```text
Implement sprint 4 of docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md only.

POST /api/auth/forgot-password always returns 200 with the same body: "If an account exists for that email, a reset link is on its way." Send a reset link only when the account exists and email_verified_at is set. Unverified or unknown addresses send no mail and still return 200. The send spends auth_resend.

The reset confirm POST uses the same link pattern as verification: confirm button, not GET consumption, 30-minute lifetime, five wrong presents burn the challenge. New password uses the 12-character rule and confirm password.

Success replaces the password hash, revokes every session row for the account, bumps session_version, consumes the challenge, and does not set a new cookie. Scoped API keys stay valid. The screen tells the person to sign in again on each device.

Add tests: unknown email and known email return the same status and the same body; reset kills both of two sessions; the old password fails; a second use of the secret fails. Do not change email or delete the account in this sprint.
```

---

## Sprint 5 — Change email

Depends on: sprints 1, 3, and 4.

```text
Implement sprint 5 of docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md only.

Change email requires a verified session and the current password. A wrong password returns the same invalid_credentials sentence as login and spends auth_account. The request spends auth_account_action (capacity 5, refill 1 token per 60 seconds, key acct:<id>).

Do not write the new address onto accounts.email until the new address confirms a change_email challenge. Send the confirm link to the new address. Send a notice to the old address with no secret in it. If that notice fails, leave the challenge unconfirmed.

Confirming consumes the challenge, updates email, sets email_verified_at, revokes every session, and bumps session_version. If the new address is already another account, consume the challenge and return the invalid-link sentence. The address does not change.

Add tests for: password required, old address unchanged until confirm, both sessions dead after confirm, and a taken address rejected. Do not implement account deletion.
```

---

## Sprint 6 — Settings, deletion, and isolation

Depends on: sprints 1 through 5.

```text
Implement sprint 6 of docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md. This sprint adds the settings screen, account deletion, and the cross-account checks. Do not add a new auth vendor.

The settings icon opens a page with change password, change email (sprint 5), and delete account. Change password requires the current password, applies the 12-character rule, revokes every session, bumps session_version, and does not keep the current cookie.

Delete account requires the current password and the account email typed again. Then, in one transaction: revoke every session, bump session_version, revoke api_credentials, delete PDF files for that account's profiles, delete users (cascades reports, chat, jobs), delete challenges and sessions, delete the account, clear both cookies. The body is only "Account deleted." Do not log the password, secrets, or profile amounts.

Spend auth_account_action on the delete request.

Add tests:
- After deletion, the old access cookie, refresh cookie, and scoped key fail, and profile, report, chat, and PDF reads return 404.
- Account A cannot read account B's profile, report, chat, or PDF.
- Logout still revokes only the session that called it. Password change and deletion revoke all sessions.
- Backup retention is not implemented in code. State in the deployment notes that operator backups are outside this deletion and that no statutory hold is coded.

Do not add Alembic. Do not rotate API_SECRET_KEY.
```
