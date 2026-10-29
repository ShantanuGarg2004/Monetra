# Auth architecture

**Status:** Current as of 2026-10-29.  
**Product name:** Monetra.  
**Companions:** `docs/architecture/ARCHITECTURE.md`, `docs/architecture_modules/02-identity-and-sessions.md`, `docs/architecture_modules/03-account-lifecycle.md`

This is the contract for who a request is. There is still one `Actor`. There is no second auth vendor.

## 1. Decisions

| Decision | Choice |
|---|---|
| How a person proves who they are | Email and a password hashed in this app. |
| New account | One confirmation link to that address. The link is confirmed by a button. Opening the page does not use it. |
| Later sign-in | Password, then a 6-digit code emailed to the same address. The code lasts 10 minutes. |
| Browser credential | `finpilot_access` for 15 minutes and `finpilot_refresh` for 7 days from the session row. |
| `API_SECRET_KEY` | Local Swagger password only. It does not open profiles. |
| External login | Not built. `auth_provider` stays `local`. |

## 2. Credentials, one actor

| Caller | What they send | `Actor.kind` |
|---|---|---|
| Signed-in browser | `finpilot_access` | `user` |
| Script with a scoped key | `X-API-Key` matched to `api_credentials` | `api_key` |
| Local Swagger | Basic password equal to `API_SECRET_KEY` | `docs` |
| Health, `/`, and the anonymous auth posts | Nothing | `anonymous` |

`resolve_actor()` in `services/actor.py` is the only place a request becomes an actor.

1. Anonymous posts are login, login-code, signup, logout, refresh, verify-email, forgot-password, reset-password, and confirm-email, plus health, `/`, and CORS preflight.
2. If `finpilot_access` is present, the signature, the live `sessions` row, and `accounts.session_version` must match. A bad cookie is `401` `session_expired` and does not fall through to a key.
3. Else a scoped key is `api_key` for that account. Scopes are `data`, `llm`, or both.
4. Else local Swagger plus `API_SECRET_KEY` is `docs`.
5. Else the request is rejected.

A missing scope on a data or model route is `403` `forbidden`. `GET /api/auth/me` requires `kind=user`.

Until `accounts.email_verified_at` is set, profile create and read-by-id, report, chat, goal, and PDF download return `403` `email_unverified`. Change-password and delete-account stay available to a signed-in unconfirmed account. The settings screen itself is behind the confirmed-email gate in the React app.

## 3. Cookies

| Cookie | Lifetime | Storage | Path |
|---|---|---|---|
| `finpilot_access` | 15 minutes | Signed payload: `account_id`, `session_id`, `session_version`. Salt `finpilot-access`. | `/` |
| `finpilot_refresh` | 7 days from the session row, not sliding | SHA-256 of an opaque secret. Rotation keeps the previous hash. Reuse of that previous hash revokes that session only. | `/api/auth/refresh` |
| `finpilot_session` | Not issued | Cleared on sign-in and sign-out so an old browser drops it. | `/` |

Local `FLASK_ENV` (`development`, `dev`, `local`) uses `SameSite=Lax` and `Secure` false. Every other environment uses `SameSite=None` and `Secure`. Logout clears both live cookies with those flags.

Logout revokes only the session that called it. It does not bump `session_version`. Password reset, password change, confirmed email change, and account deletion revoke every session and bump `session_version`. Scoped keys stay valid across a password change. Account deletion revokes them and then deletes the rows.

## 4. Account rows

```text
accounts
  id, email, password_hash, auth_provider, session_version, email_verified_at, created_at

sessions
  id, account_id, secret_hash, previous_secret_hash, expires_at, revoked_at

auth_challenges
  purpose in verify_email, reset_password, change_email, login_code
  secret_hash, target_email, expires_at, consumed_at, attempt_count
```

The signup link, the password-reset link, and the email-change link last 30 minutes. The sign-in code lasts 10 minutes. Five wrong secrets consume that challenge. The raw secret is only placed in the email.
