# Monetra — as-built architecture

**Date:** 2026-10-29  
**Audience:** Someone who has not read the review. This file describes the process that is running.  
**Module diagrams:** `docs/architecture_modules/README.md`  
**Historical notes:** `docs/planning/` and `docs/execution/testing_reports/` explain why older code looks the way it does. They are not the current system. The product name in those files is often FinPilot.

A browser confirms a new address once, then signs in with a one-time code. The API stores that sign-in as an access cookie and a refresh cookie. Report and chat calls to Groq run in a separate worker process. Application data is PostgreSQL database `finpilot`. Rate-limit counters are PostgreSQL database `finpilot_ratelimit`. PDFs are files on disk. Mail is sent through Resend.

Capacity, copied from `docs/execution/testing_reports/REMEDIATION_6_LOAD_TEST_REPORT.md`: This host does not meet the written pass lines for 100 concurrent health checks or 100 concurrent profile lists. Report enqueue does. Eighty lists while 10 report jobs were running, and the chat gate after chat was queued, are both still over 300 ms. It is not fair to say that about 100 people can load the app and list their profiles at once, or that a report no longer freezes those reads.

---

## 1. Start the app

PostgreSQL comes up with Docker. The API and the worker are two processes. The React app is a third.

```bash
docker compose up -d
python app.py
python -m services.jobs.worker
```

Frontend, from `frontend/`:

```bash
npm install
npm run dev
```

The Vite server is `http://localhost:5173` and proxies `/api` to `http://127.0.0.1:5000`, so the session cookie stays on one origin. Sign in from the landing page.

Required environment names (values live in `.env`, never in this file): `GROQ_API_KEY`, `API_SECRET_KEY`, `SESSION_SECRET`. `SESSION_SECRET` signs `finpilot_access`. It must be at least 32 characters and different from `API_SECRET_KEY`. Changing it signs every browser out. Mail also needs `EMAIL_API_KEY`, `EMAIL_FROM` on a verified domain, and `APP_PUBLIC_URL` with no path. Local `FLASK_ENV` of `development`, `dev`, or `local` sets the cookies to `SameSite=Lax` without `Secure`. Any other value sets `SameSite=None` and `Secure`, which is what the public site needs.

`APP_DATABASE_URL` points at database `finpilot`. `RATELIMIT_DATABASE_URL` points at `finpilot_ratelimit`. `RATELIMIT_STORAGE_BACKEND=sql` turns on the gateway. `FLASK_ENV` of `development`, `dev`, or `local` turns Swagger on at `http://127.0.0.1:5000/apidocs/`.

`API_SECRET_KEY` is the local Swagger password (HTTP Basic, any username). It does not open profiles, reports, chat, or goals. A script that must call those routes uses a scoped key from `python scripts/issue_api_credential.py`. The script prints the raw key once. The database stores a Werkzeug hash and, for a key issued now, a SHA-256 digest in `api_credentials.key_sha256`.

When `FLASK_ENV` is outside `development`, `dev`, and `local`, startup refuses `APP_DATABASE_URL` if that URL is the Compose database named `finpilot` and it still contains the local dev password. The test database name `finpilot_test` stays allowed, so the suite can keep using the local server. The refusal message is `APP_DATABASE_URL is still the local default. Set a production database URL.`

`SQLITE_IMPORT` defaults off. A normal start does not open a SQLite file. Set it only to copy an old `finance.db` into an empty `public` schema.

`BOOTSTRAP_ACCOUNT_EMAIL` and `BOOTSTRAP_ACCOUNT_PASSWORD` are required only when existing profiles have no `account_id`. Startup then attaches those profiles to one account. The password is stored as a hash.

`python app.py` is the local debugger. It listens when `FLASK_ENV` is `development`, `dev`, or `local`. Outside those values it exits before it listens. A host that serves traffic uses Waitress or Gunicorn. Thread and timeout numbers are in `docs/architecture/CAPACITY_RUNBOOK.md`. The Groq worker is still `python -m services.jobs.worker` beside that process. Waitress is a host tool. It is not in `requirements.txt`.

---

## 2. Request path

`app.py` `require_api_key` then `enforce_rate_limit`, then the blueprint. `services/actor.py` `resolve_actor` is the only place a request becomes an actor.

```mermaid
sequenceDiagram
    participant C as Browser or script
    participant A as require_api_key
    participant G as Rate-limit gateway
    participant R as Blueprint

    C->>A: Cookie, or X-API-Key, or neither
    alt OPTIONS, /, health, or an anonymous auth post
        A->>G: anonymous, health is exempt
    else finpilot_access present
        A->>A: Verify signature, live session row, and session_version
        alt cookie valid
            A->>G: Actor user
        else cookie bad
            A-->>C: 401 session_expired
        end
    else scoped X-API-Key
        A->>A: Match digest, else a legacy hash
        alt scope missing
            A-->>C: 403 forbidden
        else scope ok
            A->>G: Actor api_key for that account
        end
    else local Swagger and API_SECRET_KEY
        A->>R: Actor docs, no data route
    else no match
        A-->>C: 401 unauthorized
    end
    G->>R: blueprint
```

Order inside `resolve_actor`:

1. A presented `finpilot_access` cookie is resolved first. The signature, the live `sessions` row, and `accounts.session_version` must all match. A bad cookie does not fall through to a key. The browser refreshes it once from `finpilot_refresh` on `POST /api/auth/refresh`.
2. Else `X-API-Key` (or the Swagger Basic password) is matched to a non-revoked row in `api_credentials`. A new key is one indexed read on `key_sha256`, then `hmac.compare_digest`. A live row whose digest is still null is checked with its password hash, and startup logs how many of those rows remain so they can be reissued. The actor is `api_key`. `credential` is that account id. `scopes` is `data`, `llm`, or both.
3. Else, on local `/apidocs/` and `/apispec.json` only, a value equal to `API_SECRET_KEY` is `docs`.
4. Else the request is rejected.

`GET /api/auth/me` still requires `kind=user`. A scoped key is not a browser session.

Data routes need scope `data`. `POST /api/generate-report` and `POST /api/chat` need scope `llm`. A browser session is not checked for scopes. A scoped key without the scope is `403` `forbidden`. An unmatched key is `401` `unauthorized`.

A presented key that matches nothing is counted for that client address before the `401`. The limit is the same expression as `RATELIMIT_AUTH` (default 20 per minute), in its own bucket, so it does not share the login counter. A missing cookie stays `401` `session_expired` and is left out of that bucket. A store error on this count fails closed.

`GET /api/health` is public. The body is `status`, `database_ok`, and `ratelimit_store_ok`. The response is HTTP 200 with `status` `ok` when the app database answers and the rate-limit store ping is not a failure. `database_ok` false, or `ratelimit_store_ok` false, is `status` `degraded` and HTTP 503. With the gateway off, `ratelimit_store_ok` is null and the database result decides the status.

The gateway in `services/rate_limit` is the live limiter when `RATELIMIT_STORAGE_BACKEND` is `sql` or `memory`. Flask-Limiter stays imported and its decorators stay on routes, and `limiter.enabled` is false on that path so the two do not both count. Unknown `/api` paths return `429` `rate_policy_missing`. Health is exempt.

Logout (`routes/auth_routes.py`) revokes only the `sessions` row for the cookie that called it and clears `finpilot_access` and `finpilot_refresh`. It does not change `accounts.session_version`. A password change, a confirmed email change, a password reset, and account deletion revoke every session and bump `session_version`. Until `email_verified_at` is set, profile, report, chat, goal, and PDF routes return `403` `email_unverified`.

---

## 3. Report job and chat job

Groq does not run inside the HTTP request. `routes/report_routes.py` and `routes/chat_routes.py` insert a row. `services/jobs/worker.py` claims it.

`WORKER_CLAIM_THREADS` is how many claim loops share this one process. The default is 1, which is the main thread calling `process_once` and sleeping half a second when the queue is empty. A higher number starts that many daemon threads, named `finpilot-claim-N`, on the same engine and the same pool. A second operating-system process opens its own pool. Leave the setting at 1 unless a cost decision says otherwise.

| Step | File | What happens |
| --- | --- | --- |
| Enqueue report | `database/repository.py` `enqueue_report_job` | Inserts `jobs.kind = 'report'`, status `queued`. A second click while that profile already has a queued or running report returns the same job. |
| Enqueue chat | `enqueue_chat_job` | Inserts `kind = 'chat'` and stores the query in `payload`. Many chats may be queued. |
| Claim | `claim_next_report_job` | `FOR UPDATE SKIP LOCKED` on the oldest queued report or chat. Status becomes `running`. |
| Report work | `_run_report` | Scores health, calls Groq, saves the advisory text, then writes the PDF. Text is saved before the PDF. A PDF failure still marks the job `succeeded`. A Groq failure marks it `failed`. |
| Chat work | `_run_chat` | Calls Groq, then `save_chat_turn`. A failed chat is not stored. |
| Stale claim | `fail_stale_report_jobs` | A `running` row older than `WORKER_TIMEOUT_SECONDS` (default 120) becomes `failed` with `error_code` `worker_lost`. |

`POST /api/generate-report` returns `202` `{"job_id", "status"}`. `POST /api/chat` returns `202` `{"query", "job_id", "status"}`. Rate limits stay on that enqueue request.

`GET /api/report/<id>` (`get_stored_report`) returns the stored report when one exists. It adds `job` when the newest report job is `queued`, `running`, or `failed`. A `succeeded` job is omitted, because the stored report is the result. The same rule is on `GET /api/chat/history/<id>` for the newest chat job.

The React report hook polls that GET about every 2 seconds. The chat hook polls history about every 1 second. Both stop around 120 seconds.

---

## 4. Data

| Store | What it holds | Where it is set |
| --- | --- | --- |
| PostgreSQL database `finpilot` | Accounts, profiles, reports, chat, jobs, API credentials | `APP_DATABASE_URL`, pool in `database/db.py` |
| PostgreSQL database `finpilot_ratelimit` | Rate-limit buckets | `RATELIMIT_DATABASE_URL` |
| Directory `data/pdfs` | `profile_<user_id>.pdf` | `PDF_STORAGE_DIR` |

`database/models.py` `create_tables` creates the tables on startup (`CREATE TABLE IF NOT EXISTS`). `accounts.created_at`, `users.created_at`, `reports.generated_at`, and `chat_history.created_at` are `timestamptz`. `reports.health_json` is `jsonb`. `reports.ai_report` stays `text`. `load_report` accepts `health_json` as a dict or as a JSON string. Flask encodes `datetime` and `date` with `isoformat`, so a profile list stays JSON after those columns are timestamps. `CREATE TABLE IF NOT EXISTS` leaves an existing column's type as it is. The live type change is `database/sql/issue8_column_types.sql`. That script alters a column only while its type is still `text`, and running it again changes nothing. There is no Alembic. `reports` stores `pdf_path`. It does not store PDF bytes. `jobs.kind` is `report` or `chat`. A kind check that already allows both values is left in place on the next startup.

Back up the directory `data/pdfs` in the same breath as the `finpilot` database, and restore both. The PDF directory is a separate backup: a database restore does not bring the files back. `database/pdf_files.py` `resolve` trusts only the file name, so a stored path cannot leave that directory. Those files are on this machine's disk. Object storage is not part of this layout.

Production uses schema `public`. `database/db.py` `schema_name()` documents the exception: a test sets `DB_NAME` to a throwaway path and gets schema `t_<hash>` inside database `finpilot_test`. That is test isolation, not a multi-tenant feature.

SQL under `database/` uses named binds (`:user_id`). `AppConnection.execute` accepts a dict. A tuple raises `DatabaseError`.

Ownership is `users.account_id` in `database/repository.py`. Reports and chats stay on `users.id`. A browser or a scoped key sees that account’s profiles. A mismatch is hidden as not found. `GET /api/download-report/<user_id>` calls `get_user_by_id` before it opens the PDF. A profile this caller does not own, and a profile with no report, both return `404` with `code` `not_found` and the message `No report found. Generate one first.`

---

## 5. What is intentionally absent

- No Redis. The access cookie is signed. The refresh secret is a hash in PostgreSQL. Rate-limit state is PostgreSQL.
- No OAuth and no separate auth vendor. Login is email and a password hashed in this app, then a one-time code emailed by Resend. The access cookie is an itsdangerous token, not a third-party JWT service.
- No Alembic. A new database takes its column types from `CREATE TABLE IF NOT EXISTS` in `database/models.py`. A change to a column that already exists is a one-time SQL script, such as `database/sql/issue8_column_types.sql`, and the same types in that `CREATE TABLE` text.
- Chat is queued. The issue 6 measurement showed a synchronous chat call holding the web process, so `POST /api/chat` now returns `202` and the worker calls Groq.
- The production browser does not send `VITE_API_KEY`. That variable is for local scripts only, and the env key is not a data actor.

Profile checks on the request path live in Marshmallow schemas. Prompts are built in `services/ai_service.py`.

---

## 6. Files

| File | Role |
| --- | --- |
| `app.py` | Factory, auth, gateway, health, blueprints |
| `services/actor.py` | Cookie, then scoped credential, then docs password |
| `services/sessions.py` | `finpilot_access` (15 minutes) and `finpilot_refresh` (7 days) |
| `services/emailer.py` | One Resend HTTP call |
| `services/verification.py` | Signup confirmation link |
| `services/login_code.py` | Sign-in code |
| `services/rate_limit/` | Quotas |
| `routes/auth_routes.py` | Signup, confirmation, sign-in code, logout, refresh, password, email, deletion |
| `routes/report_routes.py` | Enqueue report, read report, download PDF |
| `routes/chat_routes.py` | Enqueue chat, read or clear history |
| `services/jobs/worker.py` | Claim and run Groq |
| `database/db.py` | Pool, named binds, test schema |
| `database/models.py` | Tables |
| `database/sql/issue8_column_types.sql` | One-time change of timestamps to `timestamptz` and `health_json` to `jsonb` |
| `database/repository.py` | SQL and ownership |
| `database/pdf_files.py` | PDF files on disk |
| `scripts/issue_api_credential.py` | Issue or revoke a scoped key |
