# FinPilot — deployment strategy (free-tier path)

**Status:** locked primary path. Strategy only — hands-on steps are in [`VERCEL_RAILWAY_DEPLOY_GUIDE.md`](VERCEL_RAILWAY_DEPLOY_GUIDE.md).  
**Audience:** someone who will host FinPilot without a paid production bill.  
**As-built runtime:** `docs/architecture/ARCHITECTURE.md` and `docs/architecture/CAPACITY_RUNBOOK.md`.  
**GCP alternate:** `docs/deployment/GCP_FREE_CREDITS_DEPLOYMENT.md`.

This document is the primary hosting plan: **Vercel** (frontend), **Railway trial (~$5 credits)** (API, worker, Postgres, PDF volume), **Docker Hub** (image), **GitHub Actions** (test → build → push → deploy), and **Groq** (LLM, free tier subject to Groq’s own limits). For the ordered checklist (Dockerfile contents, Hub push, Railway, Vercel, smoke tests), use the deploy guide.

---

## 1. Goals and constraints

| Goal | Constraint |
|---|---|
| Public demo of the signed-in app | Free or trial accounts only |
| Keep the as-built process split | HTTP process never calls Groq; `python -m services.jobs.worker` does |
| One image for API and worker | Different start commands on Railway |
| Browser auth stays cookie-based | Vercel and Railway are different sites — cookie flags must change before go-live |
| PDFs remain downloadable across redeploys | Railway volume (or later object storage) |

Out of scope for this path: Redis, Alembic, OAuth, billing, custom domain automation, multi-region HA.

---

## 2. Target architecture

```mermaid
flowchart LR
  Browser --> Vercel["Vercel_React_static"]
  Vercel -->|"HTTPS_CORS_cookie"| API["Railway_Gunicorn_API"]
  API --> Worker["Railway_job_worker"]
  API --> PG["Railway_Postgres"]
  Worker --> PG
  Worker --> Groq["Groq_API"]
  Worker --> Vol["Railway_volume_PDFs"]
  GHA["GitHub_Actions"] -->|build_push| Hub["Docker_Hub"]
  Hub --> API
  Hub --> Worker
  GHA --> Vercel
```

| Piece | Platform | Role |
|---|---|---|
| React SPA | Vercel | Static build of `frontend/` |
| Flask API | Railway service `finpilot-api` | Gunicorn, `app:create_app()` |
| Job worker | Railway service `finpilot-worker` | Same image; `python -m services.jobs.worker` |
| App + limiter DBs | One Railway PostgreSQL | Databases `finpilot` and `finpilot_ratelimit` |
| PDF files | Railway volume | Mounted at `PDF_STORAGE_DIR` (e.g. `/data/pdfs`) |
| Container image | Docker Hub | `DOCKERHUB_USER/finpilot:<sha>` and `:latest` |
| CI/CD | GitHub Actions | Test, build, push, redeploy |
| LLM | Groq | Key only in Railway secrets |

Three processes are still required for a full product: API, worker, and Postgres. The browser is the fourth.

---

## 3. Prerequisites (must fix before production auth works)

These are **repo gaps**. Documented here so deploy work does not start against a broken cross-origin login.

### 3.1 Cross-origin session cookie

Today [`services/sessions.py`](../../services/sessions.py) sets `samesite="Lax"`. That is correct for same-site local Vite → Flask (proxy). It is **wrong** when the UI is `https://*.vercel.app` and the API is `https://*.up.railway.app`.

Before go-live:

1. In production (`FLASK_ENV` outside `development` / `dev` / `local`), set the session cookie to `SameSite=None` and `Secure=True`.
2. Apply the same attributes when clearing the cookie on logout.
3. Keep Flask-CORS configured for the Vercel origin with credentials allowed (already the production expectation via `CORS_ORIGINS`).

Until that lands, signup/login from Vercel will look like “session never sticks.”

### 3.2 CORS and frontend API base

| Setting | Production value |
|---|---|
| `CORS_ORIGINS` | Exact Vercel URL(s), comma-separated (e.g. `https://finpilot.vercel.app`) |
| `VITE_API_URL` | Absolute API prefix, e.g. `https://finpilot-api.up.railway.app/api` |

[`frontend/src/config/api.js`](../../frontend/src/config/api.js) already uses `credentials: "include"` and `import.meta.env.VITE_API_URL || "/api"`. The local Vite proxy in [`frontend/vite.config.js`](../../frontend/vite.config.js) does **not** apply on Vercel; `VITE_API_URL` must be set at **build** time on Vercel.

Confirm path joining: if `VITE_API_URL` ends with `/api` and hooks call `/users`, the final URL must be `/api/users` (no double `/api/api`). Match whatever the frontend paths already assume today (`API_BASE` + path).

### 3.3 Production config

| Variable | Production |
|---|---|
| `FLASK_ENV` | `production` |
| `APP_DATABASE_URL` | Railway Postgres URL for database `finpilot` (not the Compose default password) |
| `RATELIMIT_DATABASE_URL` | Same host, database `finpilot_ratelimit` |
| `RATELIMIT_STORAGE_BACKEND` | `sql` |
| Swagger | Off (local envs only) |

`Config.validate()` refuses the Compose default URL when `FLASK_ENV` is not local. That is intentional.

### 3.4 Image and Gunicorn

There is no `Dockerfile` in the repo yet. Gunicorn is not in [`requirements.txt`](../../requirements.txt); the image (or Railway start command install) must provide it. Prefer installing Gunicorn in the image runtime stage.

---

## 4. Multi-stage Docker image

### 4.1 Contract

| Item | Value |
|---|---|
| Registry | Docker Hub (personal account) |
| Repository | `DOCKERHUB_USER/finpilot` |
| Tags | `<git-sha>` on every main build; `latest` on main |
| Secrets | Never in layers; only Railway / Vercel / Actions secrets |

Same image for API and worker. Railway (or the process manager) chooses the command.

### 4.2 Intended stages

**Stage `builder`**

- Base: `python:3.12-slim`
- Install build deps if wheels need them
- `pip install --prefix=/install -r requirements.txt gunicorn`

**Stage `runtime`**

- Base: `python:3.12-slim`
- Copy `/install` from builder
- Copy application code (`app.py`, `config.py`, `database/`, `routes/`, `services/`, `schemas.py`, `extensions.py`, etc.)
- Create non-root user
- `ENV PYTHONUNBUFFERED=1`
- `ENV PDF_STORAGE_DIR=/data/pdfs`
- Expose `PORT` (Railway injects `PORT`; default document `5000` for local runs)
- `HEALTHCHECK` against `GET /api/health` when the API command is used (worker service may disable healthcheck or use a process check)
- Default `CMD` can be the API; Railway overrides for the worker

Example start commands (not committed yet):

```bash
# API (Railway)
gunicorn --workers 2 --timeout 120 --bind 0.0.0.0:${PORT:-5000} "app:create_app()"

# Worker (Railway)
python -m services.jobs.worker
```

Start with **2** Gunicorn workers on the trial. The local capacity formula defaults to 6 (`PEAK_CONCURRENT_LLM` + `WORKER_HEADROOM`); that burns Railway credits faster. Raise only if credits and load justify it. Keep `WORKER_CLAIM_THREADS=1`.

---

## 5. Railway layout

### 5.1 Project services

| Railway service | Image | Start command | Notes |
|---|---|---|---|
| `finpilot-postgres` | Postgres 16 plugin/template | managed | One instance |
| `finpilot-api` | `DOCKERHUB_USER/finpilot` | Gunicorn as above | Public HTTPS domain |
| `finpilot-worker` | same image digest | `python -m services.jobs.worker` | No public HTTP required |

### 5.2 PostgreSQL: two databases on one instance

Match the local model in [`docker-compose.yml`](../../docker-compose.yml):

1. Provision Railway PostgreSQL.
2. Connect as the admin user and create:
   - `finpilot` — accounts, profiles, reports, chat, jobs, api_credentials
   - `finpilot_ratelimit` — rate-limit buckets
3. Apply [`database/sql/rate_limit_schema.sql`](../../database/sql/rate_limit_schema.sql) once to `finpilot_ratelimit`.
4. Point:
   - `APP_DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:PORT/finpilot`
   - `RATELIMIT_DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:PORT/finpilot_ratelimit`

App tables are created on API/worker startup via `CREATE TABLE IF NOT EXISTS` in `database/models.py`. For existing column-type upgrades on an old DB, run `database/sql/issue8_column_types.sql` once if needed.

### 5.3 PDF volume

| Setting | Value |
|---|---|
| Mount path | `/data/pdfs` |
| Env | `PDF_STORAGE_DIR=/data/pdfs` |
| Attached to | **Both** `finpilot-api` and `finpilot-worker` |

Without a shared volume:

- Worker writes a PDF that disappears on redeploy or is invisible to the API container’s filesystem.
- Downloads break after scale/restart.

Backup rule from architecture docs still applies: back up the volume in the same breath as the `finpilot` database.

### 5.4 Railway networking and health

- Generate a public domain for `finpilot-api` only.
- Health: `GET /api/health` → `200` with `status: ok` when app DB and rate-limit store answer.
- Worker has no inbound public URL; it only polls `jobs` in Postgres.

---

## 6. Vercel frontend

| Item | Value |
|---|---|
| Root directory | `frontend` |
| Build | `npm ci && npm run build` |
| Output | Vite `dist` |
| Framework preset | Vite |

Environment (Vercel project → Production):

| Name | Example |
|---|---|
| `VITE_API_URL` | `https://<api-domain>/api` |

Do **not** set `VITE_API_KEY`. The browser uses the session cookie only.

After the first Vercel URL is known, set Railway `CORS_ORIGINS` to that exact origin and redeploy the API.

---

## 7. Environment variable matrix

### 7.1 Railway (API + worker — share the same vars unless noted)

| Variable | Required | Notes |
|---|---|---|
| `GROQ_API_KEY` | yes | Real key; restart after change |
| `API_SECRET_KEY` | yes | Swagger password only in local; still required by validate |
| `SESSION_SECRET` | yes | ≥32 chars, ≠ `API_SECRET_KEY` |
| `FLASK_ENV` | yes | `production` |
| `APP_DATABASE_URL` | yes | DB `finpilot` |
| `RATELIMIT_DATABASE_URL` | yes | DB `finpilot_ratelimit` |
| `RATELIMIT_STORAGE_BACKEND` | yes | `sql` |
| `CORS_ORIGINS` | yes | Vercel origin(s) |
| `PDF_STORAGE_DIR` | yes | `/data/pdfs` |
| `GROQ_TIMEOUT_SECONDS` | no | default 90 |
| `WORKER_TIMEOUT_SECONDS` | no | default 120; must be > Groq timeout |
| `WORKER_CLAIM_THREADS` | no | keep `1` on trial |
| `PEAK_CONCURRENT_LLM` / `WORKER_HEADROOM` | no | informational for recommended workers |
| `GROQ_REPORT_MODEL` / `GROQ_CHAT_MODEL` | no | defaults in config |
| `BOOTSTRAP_ACCOUNT_*` | only if orphan profiles | usually unset on a fresh DB |

Worker needs the Groq key, DB URLs, and `PDF_STORAGE_DIR`. It does not serve HTTP.

### 7.2 Vercel

| Variable | Required |
|---|---|
| `VITE_API_URL` | yes (build-time) |

### 7.3 GitHub Actions secrets

| Secret | Purpose |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub login |
| `DOCKERHUB_TOKEN` | Access token (not password) |
| `RAILWAY_TOKEN` | Redeploy / CLI |
| `RAILWAY_SERVICE_API_ID` | API service |
| `RAILWAY_SERVICE_WORKER_ID` | Worker service |
| `VERCEL_TOKEN` | Deploy |
| `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID` | Project link |

Exact Railway/Vercel Action inputs can follow the official GitHub Actions when the workflows are added.

---

## 8. CI/CD pipelines (planned)

Existing: [`.github/workflows/pytest.yml`](../../.github/workflows/pytest.yml) — Postgres 16 + pytest on PR and `main`.

Planned additions (not in repo yet):

| Workflow | Trigger | Steps |
|---|---|---|
| `test` (keep) | `pull_request`, `push` to `main` | Checkout → Python 3.12 → pytest against service Postgres |
| `docker` | `push` to `main` after tests pass | Login Docker Hub → `docker build` multi-stage → push `:sha` and `:latest` |
| `deploy-railway` | after successful `docker` | Authenticate Railway → redeploy API + worker to pull new digest |
| `deploy-vercel` | after tests on `main` (or path filter `frontend/**`) | `vercel pull` / `vercel build` / `vercel deploy --prod` with `VITE_API_URL` |

Recommended DAG on `main`:

```mermaid
flowchart TD
  testJob[test] --> dockerJob[docker_build_push]
  testJob --> vercelJob[deploy_vercel]
  dockerJob --> railwayJob[deploy_railway_api_and_worker]
```

Rules:

- Never deploy Railway from an untested commit.
- Never bake `.env` into the image.
- Prefer digest pins on Railway after push (`image@sha256:…`) when the platform allows it.
- PR builds may build the image without pushing, or push a `pr-<n>` tag only if useful; production `:latest` is `main` only.

---

## 9. Cutover checklist

1. Create Docker Hub repository `finpilot` (private recommended).
2. Land pre-deploy code: `SameSite=None; Secure` for production cookies; confirm CORS credentials.
3. Add `Dockerfile` + `.dockerignore` per section 4.
4. Add GitHub Actions workflows and secrets (section 7.3 / 8).
5. Create Railway project: Postgres → create two databases → apply rate-limit SQL.
6. Create volume; attach to API and worker; set `PDF_STORAGE_DIR`.
7. Deploy API + worker from the Hub image; set env matrix; generate public API domain.
8. Create Vercel project on `frontend/`; set `VITE_API_URL`; deploy.
9. Set `CORS_ORIGINS` to the Vercel origin; redeploy API.
10. Smoke test:
    - `GET /api/health` → `200`, `database_ok` true, `ratelimit_store_ok` true
    - Sign up / log in from Vercel (cookie present on API host)
    - Create profile → generate report → worker log shows success → advisory text loads
    - Download PDF
    - Chat enqueue + history update
11. Confirm Swagger is **not** exposed in production.

---

## 10. Credit hygiene (Railway ~$5 trial)

Two always-on containers + Postgres will burn the trial quickly.

| Practice | Why |
|---|---|
| Gunicorn `--workers 2` | Fewer CPU hours than 6 |
| `WORKER_CLAIM_THREADS=1` | Default; avoid parallel Groq cost and CPU |
| Stop or remove services when not demoing | Trial credits are finite |
| One Postgres, two databases | Cheaper than two Postgres plugins |
| Do not run load tests against the trial | Use local Docker Compose |
| Watch Groq usage separately | LLM cost is outside Railway |

When credits are exhausted, the stack stops until you move to the GCP path, another free host, or a paid plan. This strategy does not claim multi-week always-on hosting on $5.

---

## 11. Risks and honest limits

| Risk | Mitigation |
|---|---|
| Cross-origin cookie forgotten | Block go-live until section 3.1 is implemented and smoke-tested |
| PDF volume not shared | Downloads 404 or empty after worker write |
| Image started without worker | Reports stay `queued` forever |
| Placeholder / stale `GROQ_API_KEY` | Worker logs `401 Invalid API Key` → `upstream_error` |
| Capacity “100 concurrent users” | Not met on measured Waitress setup; do not market that claim (see remediation 6 load report) |
| Trial exhaustion | Credit hygiene; GCP doc as longer free runway |

---

## 12. Later (not this path)

- Object storage for PDFs (S3-compatible / GCS) instead of a volume
- Redis limiter (Wave 4 optional)
- Custom domains + tighter cookie `Domain` if API and app share a parent domain
- Alembic migrations
- Autoscaling worker replicas (cost decision)

---

## 13. Account deletion and backups

Deleting an account removes that account, its sessions, challenges, API credentials, profiles, reports, chat, jobs, and the PDF files for those profiles from the running application. Operator backups are outside this deletion. A Postgres dump or a disk snapshot can still contain those rows and files until that backup ages out on the operator’s own schedule. No statutory retention period is coded.

## 14. Related docs

| Doc | Role |
|---|---|
| `docs/architecture/ARCHITECTURE.md` | As-built request path, worker, DBs |
| `docs/architecture/CAPACITY_RUNBOOK.md` | Threads, timeouts, Gunicorn formula |
| `docs/architecture/NEW_DEVICE_SETUP.md` | Local machine setup |
| `docs/architecture/AUTH_ARCHITECTURE.md` | Cookie and scoped keys |
| `docs/deployment/GCP_FREE_CREDITS_DEPLOYMENT.md` | GCP free-credits alternate |
| `docs/execution/testing_reports/REMEDIATION_6_LOAD_TEST_REPORT.md` | Capacity measurement |
