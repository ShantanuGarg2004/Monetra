# Step-by-step: deploy FinPilot (Vercel + Railway + Docker Hub)

**Locked path:** Vercel (frontend) · Railway trial (API, worker, Postgres, PDF volume) · Docker Hub (image).  
**Strategy overview:** [`DEPLOYMENT_STRATEGY.md`](DEPLOYMENT_STRATEGY.md).  
**GCP alternate (not this guide):** [`GCP_FREE_CREDITS_DEPLOYMENT.md`](GCP_FREE_CREDITS_DEPLOYMENT.md).

Follow the phases **in order**. Later steps need values produced by earlier steps (especially the Railway API URL and the Vercel URL). Do not jump ahead to Vercel env vars before the API has a public domain.

---

## How the steps depend on each other

```mermaid
flowchart TD
  A[Phase_A_Code_and_image] --> B[Phase_B_Railway_backend]
  B --> C[Phase_C_Vercel_frontend]
  C --> D[Phase_D_Wire_CORS]
  D --> E[Phase_E_Smoke_test]
```

| Phase | What you do | What you get for later |
|---|---|---|
| **A** | Cookie code fix → Dockerfile → build → push to Docker Hub | Image `USER/finpilot:latest` |
| **B** | Railway Postgres → volume → API → worker | **API host** (write it down) |
| **C** | Vercel project with `VITE_API_URL` pointing at that API host | **Vercel origin** (write it down) |
| **D** | Set Railway `CORS_ORIGINS` to the Vercel origin; redeploy API | Cross-origin browser calls work |
| **E** | Signup, report, PDF, chat from the Vercel site | Deploy verified |

`VITE_API_URL` and the final `CORS_ORIGINS` value **cannot** be set correctly in Phase A. They belong in Phases C and D after Railway and Vercel exist.

---

## Values to write down as you go

Keep a notepad (or a local scratch file that is **not** committed):

```text
DOCKERHUB_USER=
IMAGE=              # e.g. myuser/finpilot:latest
API_HOST=           # e.g. finpilot-api-production-xxxx.up.railway.app  (no https://)
API_BASE=           # https://API_HOST/api
VERCEL_ORIGIN=      # e.g. https://finpilot-xxx.vercel.app  (no trailing slash)
APP_DATABASE_URL=
RATELIMIT_DATABASE_URL=
```

---

## Phase A — Prepare the repo and the Docker image

You are still on your laptop. No Railway or Vercel URLs are required yet.

### Step A1 — Accounts and tools

Create or confirm:

1. **GitHub** — this repo available to push
2. **Docker Hub** — username → write `DOCKERHUB_USER`
3. **Railway** — trial credits ([railway.app](https://railway.app))
4. **Vercel** — ([vercel.com](https://vercel.com))
5. **Groq** — API key ([console.groq.com](https://console.groq.com))

| Tool | Check |
|---|---|
| Docker Desktop (or Engine) | `docker version` |
| Git | `git --version` |
| Node.js 18+ | `node -v` (needed when Vercel builds; optional locally) |
| Python 3.10+ | `python --version` (for generating secrets) |

---

### Step A2 — Code fix: production session cookie (required)

Vercel (`*.vercel.app`) and Railway (`*.up.railway.app`) are **different sites**. With today’s code, production sets `Secure` but keeps `SameSite=Lax`, so the browser will not send `finpilot_session` on cross-site API calls after login. Fix this **before** you build the image that Railway will run.

Open [`services/sessions.py`](../../services/sessions.py) and replace the cookie helpers so production uses `SameSite=None` and `Secure=True`. Logout must clear the cookie with the **same** flags.

**Replace** the current `attach_cookie` / `clear_cookie` (and add `_cookie_flags`) with:

```python
def _cookie_flags():
    local = Config.FLASK_ENV in ("development", "dev", "local")
    if local:
        return {"secure": False, "samesite": "Lax"}
    return {"secure": True, "samesite": "None"}


def attach_cookie(response, account_id: int, session_version: int):
    flags = _cookie_flags()
    response.set_cookie(
        COOKIE_NAME,
        issue_token(account_id, session_version),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        secure=flags["secure"],
        samesite=flags["samesite"],
        path="/",
    )
    return response


def clear_cookie(response):
    flags = _cookie_flags()
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=flags["secure"],
        samesite=flags["samesite"],
    )
    return response
```

Leave `issue_token`, `read_token`, and the imports as they are.

Then commit (example):

```powershell
git add services/sessions.py
git commit -m "fix: allow cross-origin session cookies for Vercel and Railway"
```

Local Vite (proxied `/api`) still uses `Lax` when `FLASK_ENV` is `development` / `dev` / `local`.

CORS already has `supports_credentials=True` in [`app.py`](../../app.py). You will set the **allowed origin list** only after Vercel exists (Phase D). Do not invent a Vercel URL here.

---

### Step A3 — Add `.dockerignore` and `Dockerfile`

These files live at the **repo root** ([`Dockerfile`](../../Dockerfile), [`.dockerignore`](../../.dockerignore)). They are already in the repository for this locked path.

**Waitress (your laptop) vs Gunicorn (Railway):**

| Where | Server | Why |
|---|---|---|
| Local Windows | **Waitress** | Works on Windows; what you already run |
| Docker / Railway | **Gunicorn** | Containers are Linux; Gunicorn is the usual production WSGI server there |

You do **not** need Waitress inside the image. Railway never runs Windows. Keep using Waitress only for local `python -m waitress …`. The image installs Gunicorn and uses it as the default `CMD`. The worker process is unchanged: `python -m services.jobs.worker` (no Waitress, no Gunicorn).

Never bake `.env` into the image. Secrets go only into Railway (and `VITE_API_URL` into Vercel later).

---

### Step A4 — Build the image locally

Docker Desktop must be running. From the repo root:

```powershell
docker build -t YOUR_DOCKERHUB_USER/finpilot:local .
```

Replace `YOUR_DOCKERHUB_USER` with your Hub username.

Quick import check (does not need Postgres). Pass a dummy `GROQ_API_KEY` because the Groq client is created at import time:

```powershell
docker run --rm -e GROQ_API_KEY=dummy-for-import-check YOUR_DOCKERHUB_USER/finpilot:local python -c "import app; print('ok')"
```

Optional fuller local run (only if Compose Postgres is up and `.env` is filled) is not required for Railway deploy. Skip it if you prefer to test on Railway.

---

### Step A5 — Push the image to Docker Hub

1. [hub.docker.com](https://hub.docker.com) → **Create Repository** → name `finpilot` (private recommended).
2. Log in and push:

```powershell
docker login
$sha = git rev-parse --short HEAD
docker tag YOUR_DOCKERHUB_USER/finpilot:local YOUR_DOCKERHUB_USER/finpilot:latest
docker tag YOUR_DOCKERHUB_USER/finpilot:local YOUR_DOCKERHUB_USER/finpilot:$sha
docker push YOUR_DOCKERHUB_USER/finpilot:latest
docker push YOUR_DOCKERHUB_USER/finpilot:$sha
```

Write down:

```text
IMAGE=YOUR_DOCKERHUB_USER/finpilot:latest
```

Create a Hub **Access Token** (Account → Security) if you will use CI later.

**Phase A done.** Next: Railway backend. You still do not need a Vercel URL.

---

## Phase B — Deploy the backend on Railway

You will produce `API_HOST` and `API_BASE` here. Those are what Vercel needs in Phase C.

### Step B1 — Project and PostgreSQL

1. [railway.app](https://railway.app) → **New Project** → name e.g. `finpilot`
2. **Add PostgreSQL**

Railway’s default DB name is often `railway`. FinPilot needs **two** databases on that instance:

- `finpilot` — accounts, profiles, reports, chat, jobs
- `finpilot_ratelimit` — rate-limit counters

Connect (Railway Postgres → Connect → URL or Query). Example with `psql`:

```bash
psql "postgresql://USER:PASSWORD@HOST:PORT/railway"
```

```sql
CREATE DATABASE finpilot;
CREATE DATABASE finpilot_ratelimit;
```

### Step B2 — Rate-limit schema

Apply [`database/sql/rate_limit_schema.sql`](../../database/sql/rate_limit_schema.sql) to database **`finpilot_ratelimit`** only (Railway SQL UI paste, or):

```powershell
$env:PGURL = "postgresql://USER:PASSWORD@HOST:PORT/finpilot_ratelimit"
psql $env:PGURL -f database/sql/rate_limit_schema.sql
```

App tables in `finpilot` are created when the API or worker starts.

### Step B3 — Database URLs

From Railway Postgres credentials, write:

```text
APP_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/finpilot
RATELIMIT_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/finpilot_ratelimit
```

Use the `postgresql+psycopg://` scheme. Do **not** use the local Compose password `finpilot_dev_password` — production startup rejects that default.

### Step B4 — PDF volume

1. Create a Volume (e.g. `finpilot-pdfs`, 1 GB is enough to start).
2. You will mount it at `/data/pdfs` on **both** API and worker in the next steps.
3. Env on both services: `PDF_STORAGE_DIR=/data/pdfs`.

### Step B5 — API service from Docker Hub

1. **New Service** → **Docker Image** → `YOUR_DOCKERHUB_USER/finpilot:latest`
2. If the Hub repo is private, connect Docker Hub credentials in Railway.
3. Name: `finpilot-api`
4. Start command (or image default):

```bash
gunicorn --workers 2 --timeout 120 --bind 0.0.0.0:$PORT "app:create_app()"
```

5. Mount volume `finpilot-pdfs` at `/data/pdfs`.

### Step B6 — API environment variables

Set on `finpilot-api`:

| Variable | Value |
|---|---|
| `FLASK_ENV` | `production` |
| `GROQ_API_KEY` | your Groq key |
| `API_SECRET_KEY` | long random string |
| `SESSION_SECRET` | different random string, ≥32 chars |
| `APP_DATABASE_URL` | from Step B3 |
| `RATELIMIT_DATABASE_URL` | from Step B3 |
| `RATELIMIT_STORAGE_BACKEND` | `sql` |
| `PDF_STORAGE_DIR` | `/data/pdfs` |
| `CORS_ORIGINS` | `https://example.com` (temporary placeholder — **you will replace this in Phase D** after Vercel exists) |
| `WORKER_TIMEOUT_SECONDS` | `120` |
| `GROQ_TIMEOUT_SECONDS` | `90` |
| `WORKER_CLAIM_THREADS` | `1` |

Why a placeholder? Production config requires a non-empty `CORS_ORIGINS` list. The real Vercel origin does not exist until Phase C. Browser login from Vercel will **not** work until Phase D updates this value.

Generate secrets:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32)); print(secrets.token_urlsafe(32))"
```

### Step B7 — Public API domain (write this down)

1. `finpilot-api` → **Settings** → **Networking** → **Generate Domain**
2. Copy the host only, e.g. `finpilot-api-production-xxxx.up.railway.app`
3. Write:

```text
API_HOST=finpilot-api-production-xxxx.up.railway.app
API_BASE=https://finpilot-api-production-xxxx.up.railway.app/api
```

4. Health check:

```powershell
curl https://API_HOST/api/health
```

Expect `"status":"ok"`, `"database_ok":true`, `"ratelimit_store_ok":true`. If `503`, fix DB URLs or re-run Step B2.

You now have everything required to configure Vercel’s `VITE_API_URL`.

### Step B8 — Worker service

1. **New Service** → same image `YOUR_DOCKERHUB_USER/finpilot:latest`
2. Name: `finpilot-worker`
3. Custom start command:

```bash
python -m services.jobs.worker
```

4. Mount the **same** volume at `/data/pdfs`
5. Copy the same env vars as the API (Groq key, both DB URLs, `PDF_STORAGE_DIR`, timeouts). No public domain.
6. Disable HTTP healthcheck on the worker if Railway marks it unhealthy (it does not listen on HTTP).
7. Logs should show: `Report worker watching the jobs table`

Without the worker, reports stay `queued` forever.

**Phase B done.** You have `API_BASE`. Next: Vercel.

---

## Phase C — Deploy the frontend on Vercel

You need `API_BASE` from Step B7. Do not guess a Railway URL.

### Step C1 — How the frontend builds API URLs (read once)

[`frontend/src/config/api.js`](../../frontend/src/config/api.js) does:

- `API_BASE = import.meta.env.VITE_API_URL || "/api"`
- Requests use `` `${API_BASE}${path}` `` with paths like `/users`, `/auth/login` (no second `/api` prefix)

Locally, Vite proxies `/api` → Flask. On Vercel there is **no** proxy, so you must set an absolute `VITE_API_URL` at **build** time.

Correct:

```text
VITE_API_URL=https://API_HOST/api
```

Wrong examples:

```text
VITE_API_URL=https://API_HOST          → calls https://API_HOST/users (missing /api)
VITE_API_URL=https://API_HOST/api/     → usually OK, but prefer no trailing slash
VITE_API_URL=/api                      → breaks on Vercel (relative to vercel.app)
```

Do **not** set `VITE_API_KEY`.

### Step C2 — Import the repo on Vercel

1. [vercel.com](https://vercel.com) → **Add New** → **Project** → import this GitHub repo
2. Configure:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Vite
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`

### Step C3 — Set `VITE_API_URL` (Production), then deploy

In the Vercel project → **Settings** → **Environment Variables** → Production:

| Name | Value |
|---|---|
| `VITE_API_URL` | exactly your `API_BASE` from Step B7, e.g. `https://finpilot-api-production-xxxx.up.railway.app/api` |

Deploy Production. When the deploy finishes, copy the site URL and write:

```text
VERCEL_ORIGIN=https://finpilot-xxx.vercel.app
```

No path, no trailing slash.

**Phase C done.** Browser calls will still fail CORS until Phase D.

---

## Phase D — Point Railway CORS at Vercel

You need `VERCEL_ORIGIN` from Step C3.

1. Open Railway service `finpilot-api` → Variables
2. Set:

| Variable | Value |
|---|---|
| `CORS_ORIGINS` | your `VERCEL_ORIGIN` exactly, e.g. `https://finpilot-xxx.vercel.app` |

3. Redeploy `finpilot-api` so the process reloads env (required).
4. Optional: set the same `CORS_ORIGINS` on the worker for consistency (worker does not serve browser CORS).

Preview deployments need extra origins, comma-separated:

```text
https://finpilot-xxx.vercel.app,https://finpilot-git-main-xxx.vercel.app
```

**Phase D done.** Login from Vercel can work (cookie fix from A2 + CORS from D).

---

## Phase E — End-to-end smoke test

Use the **Vercel** URL, not localhost.

| # | Action | Pass |
|---|---|---|
| 1 | Open `VERCEL_ORIGIN` | Landing / login loads |
| 2 | Sign up | Stays signed in (cookie on API host) |
| 3 | Create a profile | Profile listed |
| 4 | Generate report | Completes; worker log shows success (not `upstream_error`) |
| 5 | Read advisory | Text visible |
| 6 | Download PDF | File downloads |
| 7 | Chat | Reply appears |
| 8 | `curl https://API_HOST/api/health` | Still `ok` |
| 9 | Open `https://API_HOST/apidocs/` | Not available in production |

| Failure | Usually means | Fix |
|---|---|---|
| Login immediately lost | Cookie fix missing from image, or CORS wrong | Rebuild/push image with A2; recheck Phase D |
| Browser CORS error | `CORS_ORIGINS` ≠ `VERCEL_ORIGIN` | Phase D; redeploy API |
| Reports stuck queued | Worker down | Step B8 |
| `upstream_error` / 401 in worker | Bad `GROQ_API_KEY` | Update Railway env; redeploy worker (and API if shared) |
| PDF missing after redeploy | Volume not on both services | Steps B4–B5, B8 |
| Calls to wrong host / 404 HTML | `VITE_API_URL` wrong or built before it was set | Fix C3; **redeploy Vercel** (Vite bakes env at build time) |

---

## After the first deploy — updating

```powershell
$sha = git rev-parse --short HEAD
docker build -t YOUR_DOCKERHUB_USER/finpilot:$sha -t YOUR_DOCKERHUB_USER/finpilot:latest .
docker push YOUR_DOCKERHUB_USER/finpilot:$sha
docker push YOUR_DOCKERHUB_USER/finpilot:latest
```

Redeploy Railway `finpilot-api` and `finpilot-worker` to pull the new image.

Frontend-only changes: push to GitHub; Vercel rebuilds. Change `VITE_API_URL` only if the API host changes, then redeploy Vercel.

---

## Optional later — GitHub Actions

Not required for the first deploy. Secrets when you automate: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `RAILWAY_TOKEN`, Vercel token/org/project. Pipeline shape: pytest → build/push image → redeploy Railway → Vercel. See [`DEPLOYMENT_STRATEGY.md`](DEPLOYMENT_STRATEGY.md) §8.

---

## Railway credit hygiene (~$5 trial)

| Do | Why |
|---|---|
| Gunicorn `--workers 2` | Less CPU |
| `WORKER_CLAIM_THREADS=1` | Default |
| Stop API + worker when not demoing | Credits drain while running |
| One Postgres, two databases | Cheaper than two plugins |
| Load-test only on local Compose | Do not burn the trial |

---

## Master checklist

```text
Phase A
[ ] A2 Cookie SameSite=None + Secure in production (sessions.py) committed
[ ] A3 Dockerfile + .dockerignore committed
[ ] A4 docker build succeeds
[ ] A5 Image pushed (latest + sha); IMAGE= written down

Phase B
[ ] B1–B3 Postgres + two DBs + rate_limit schema; DB URLs written down
[ ] B4 Volume created
[ ] B5–B6 finpilot-api running with env (CORS placeholder OK)
[ ] B7 API_HOST / API_BASE written down; /api/health ok
[ ] B8 finpilot-worker running; logs show watching jobs

Phase C
[ ] C3 VITE_API_URL = API_BASE; Vercel Production deploy
[ ] VERCEL_ORIGIN written down

Phase D
[ ] CORS_ORIGINS = VERCEL_ORIGIN on API; API redeployed

Phase E
[ ] Signup, profile, report, PDF, chat from Vercel
```

---

## Account deletion and backups

Deleting an account removes that account’s rows and PDF files from the running application. Operator backups are outside this deletion. A Postgres dump or a disk snapshot can still contain those rows and files until that backup ages out on the operator’s own schedule. No statutory retention period is coded.

## Related docs

| Doc | Role |
|---|---|
| [`DEPLOYMENT_STRATEGY.md`](DEPLOYMENT_STRATEGY.md) | Topology, CI, env matrix |
| [`GCP_FREE_CREDITS_DEPLOYMENT.md`](GCP_FREE_CREDITS_DEPLOYMENT.md) | Alternate GCP backend |
| [`../architecture/NEW_DEVICE_SETUP.md`](../architecture/NEW_DEVICE_SETUP.md) | Local machine only |
| [`../architecture/CAPACITY_RUNBOOK.md`](../architecture/CAPACITY_RUNBOOK.md) | Workers and timeouts |
| [`../architecture/ARCHITECTURE.md`](../architecture/ARCHITECTURE.md) | As-built request path |
