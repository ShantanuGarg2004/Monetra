# Identity and sessions

## Explanation

Every application request becomes one `Actor` before a quota is counted. A browser proves itself with `finpilot_access`. A script proves itself with a scoped key. Those two callers see the same account. Neither is a superuser.

The access cookie lasts 15 minutes. The refresh cookie lasts 7 days from the session row and does not slide. Logout revokes only that session.

## High-level design

```mermaid
flowchart TD
  req[Request] --> anon{Anonymous route?}
  anon -->|yes| guest[Actor anonymous]
  anon -->|no| access{finpilot_access valid?}
  access -->|yes| user[Actor user]
  access -->|bad cookie| expired[401 session_expired]
  access -->|absent| key{Scoped key?}
  key -->|yes| apikey[Actor api_key]
  key -->|swagger secret| docs[Actor docs]
  key -->|no| deny[401 unauthorized]
```

## Low-level design

| Rule | Detail |
|---|---|
| Access cookie | Signed with `SESSION_SECRET`, salt `finpilot-access`. Payload is `account_id`, `session_id`, `session_version`. Path `/`. |
| Refresh cookie | Opaque secret. SHA-256 stored on `sessions`. Path `/api/auth/refresh`. |
| Live session | `revoked_at` is null, `expires_at` is in the future, and `session_version` matches the account. |
| Bad access cookie | Does not fall through to `X-API-Key`. |
| Refresh | Rotates the secret, keeps `previous_secret_hash`, does not extend `expires_at`. Reuse of the previous secret revokes that session only. |
| Cookie flags | Local Flask: `SameSite=Lax`, `Secure` false. Otherwise `SameSite=None` and `Secure`. |
| Legacy name | `finpilot_session` is cleared and is not issued. |
| Scoped key | `api_credentials.key_sha256`. Scopes `data` and `llm`. `API_SECRET_KEY` is Swagger only. |

Files: `services/actor.py`, `services/sessions.py`, `database/repository.py`.

## Sequence

```mermaid
sequenceDiagram
  participant B as Browser
  participant A as API
  participant D as sessions table

  B->>A: API call with expired finpilot_access
  A-->>B: 401 session_expired
  B->>A: POST /api/auth/refresh with finpilot_refresh
  A->>D: Match hash, store new hash, keep previous hash
  A-->>B: New finpilot_access and finpilot_refresh
  B->>A: Retry the original call once
```
