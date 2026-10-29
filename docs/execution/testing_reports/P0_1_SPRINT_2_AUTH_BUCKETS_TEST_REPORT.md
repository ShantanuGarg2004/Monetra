# P0.1 Sprint 2 — auth token buckets

**Date:** 2026-10-29
**Plan:** `docs/planning/P0_1_ACCOUNT_LIFECYCLE_SOLUTIONS.md` sprint 2
**Verdict:** Login, signup, failed passwords, and refresh use a token bucket. Logout is not limited. Report, chat, goal, and read quotas stay on their fixed windows. Rejected API keys stay on the `credential_failure` fixed window.

A new key starts full. A spend stores `tokens_now - 1`. A request with less than one token returns 429 and `retry_after = ceil((1 - tokens_now) / refill_per_second)`. A store error on these three classes fails closed.

---

## 1. What shipped

The bucket rows live in `rate_limit_token_buckets` in the existing rate-limit database (`database/sql/rate_limit_schema.sql`). The fixed-window table is unchanged. The SQL store creates the token table if this database was initialized before this sprint.

| Bucket | Routes | Key | Capacity | Refill |
| --- | --- | --- | --- | --- |
| `auth_ip` | Signup, login | `ip:<address>:auth_ip` | 8 | 1 token every 15 seconds |
| `auth_account` | Failed password on login | `email:<sha256>:auth_account` | 5 | 1 token every 10 minutes |
| `auth_refresh` | `POST /api/auth/refresh` | `session:<id>:auth_refresh` | 4 | 1 token every 60 seconds |

A correct password does not spend `auth_account`. Refresh looks up the session from the refresh cookie. A secret that matches no row shares `session:unknown`. Logout stays exempt.

## 2. Tests

`python -m pytest -q` — **147 passed**.

| Case | Result |
| --- | --- |
| Eight spends from a full bucket | Allowed. The first leaves 7 tokens. The ninth is denied |
| Ninth request with an empty bucket | `retry_after` is 15 seconds for a 1-token-per-15-seconds refill |
| Clock advanced 15 seconds | One token returns and the request is allowed |
| Clock advanced far past a full refill | The bucket stops at capacity |
| Ninth login from one address | HTTP 429, `route_class` `auth_ip`, `Retry-After: 15` |
| Sixth wrong password for one email | HTTP 429, `route_class` `auth_account`, `retry_after` 600 |
| Correct password after that bucket is empty | HTTP 200 |
| Fifth refresh for one session | HTTP 429, `retry_after` 60. `/api/auth/me` still succeeds |
| Twelve logouts | HTTP 200 |
| Token-store exception on login | Denied, `fail_open` is false, `retry_after` 30 |
| Report route and `credential_failure` | Still fixed-window. `credential_failure` limit stays 20 |

## 3. Left for later

Email verification, password reset, email change, and account deletion are later sprints. Those routes will add `auth_resend`, `auth_challenge`, and `auth_account_action` when they exist.
