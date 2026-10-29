# Identity seam

**Status:** Current as of 2026-10-29.  
**Design:** `docs/architecture/AUTH_ARCHITECTURE.md`

`services/actor.py` resolves one `Actor` before the rate-limit gateway runs.

| Kind | Meaning |
|---|---|
| `anonymous` | Health, `/`, CORS preflight, and the anonymous auth posts listed in `app.py`. |
| `user` | `finpilot_access` matches a live session and the account's `session_version`. `credential` is the account id. |
| `api_key` | `X-API-Key` matches a live `api_credentials` row. `credential` is that account id. `scopes` is `data`, `llm`, or both. |
| `docs` | Local Swagger only, when the presented secret equals `API_SECRET_KEY`. Not a data actor. |

`Actor.rate_limit_subject()` for `user` and `api_key` is `acct:<account_id>`. A bad access cookie is `session_expired` and does not fall through to a key. An unmatched key is `unauthorized` and is counted on the `credential_failure` bucket before the 401.

A scoped key sees the same profiles as that account's browser. There is no superuser scope. `GET /api/users` is the caller's profiles only.

`CORS_ORIGINS` is the list of browser origins allowed to call `/api` with credentials. The public site is `https://monetra.site`. Swagger is registered only when `FLASK_ENV` is `development`, `dev`, or `local`.
