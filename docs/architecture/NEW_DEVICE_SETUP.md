# Set up Monetra on a new device

Use this when the machine has never run the app. It covers the local stack: PostgreSQL in Docker, the Flask API, the job worker, the React app, and Waitress in place of the local debugger.

`python app.py` is only the local debugger. It listens when `FLASK_ENV` is `development`, `dev`, or `local`, and it exits before it listens otherwise. Waitress is the Windows process that serves HTTP. It is not listed in `requirements.txt`. Install it on the machine that serves the API.

The Groq worker stays a separate process in every case: `python -m services.jobs.worker`.

Thread counts and timeouts are in `CAPACITY_RUNBOOK.md` in this folder.

## What you need

- Git
- Python 3.10 or newer
- Docker, running, with Compose
- A Groq API key
- Node.js 18 or newer (the frontend)

## 1. Clone and enter the repo

```bash
git clone https://github.com/ShantanuGarg04/FinPilot.git
cd FinPilot
```

## 2. Python environment

From the repo root:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install waitress
```

macOS or Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

On Linux, install Gunicorn instead of Waitress when this host will serve traffic: `pip install gunicorn`. The command is in `CAPACITY_RUNBOOK.md`.

## 3. Environment file

Copy `.env.example` to `.env` in the repo root. Fill in the three required values. Mail also needs `EMAIL_API_KEY`, `EMAIL_FROM=Monetra <noreply@monetra.site>`, and `APP_PUBLIC_URL=http://localhost:5173` when you want confirmation and sign-in messages. Do not commit `.env`.

```env
GROQ_API_KEY=your-groq-api-key
API_SECRET_KEY=your-chosen-api-secret
SESSION_SECRET=replace-with-a-different-32-character-secret
FLASK_ENV=development
RATELIMIT_STORAGE_BACKEND=sql
RATELIMIT_DATABASE_URL=postgresql+psycopg://finpilot:finpilot_dev_password@127.0.0.1:5432/finpilot_ratelimit
APP_DATABASE_URL=postgresql+psycopg://finpilot:finpilot_dev_password@127.0.0.1:5432/finpilot
```

`SESSION_SECRET` signs the browser cookie. It must be at least 32 characters and it must not equal `API_SECRET_KEY`. `FLASK_ENV=development` turns Swagger on and allows the local database URL above. Outside `development`, `dev`, or `local`, the app refuses to start when `APP_DATABASE_URL` is still this Compose default.

`APP_DATABASE_URL` is application data (`finpilot`). `RATELIMIT_DATABASE_URL` is only the limiter (`finpilot_ratelimit`).

## 4. PostgreSQL

Docker must be running.

```bash
docker compose up -d
```

Compose starts `postgres:16-alpine` as `finpilot-postgres` on port 5432. The volume applies `database/sql/rate_limit_schema.sql` to `finpilot_ratelimit` on a new volume. The `finpilot` database is created when the API starts. A normal start does not import `finance.db`.

Wait until the container is healthy (`docker compose ps`) before the next step.

## 5. API with Waitress, and the worker

Use two terminals, both with the virtual environment active and the current directory at the repo root.

Terminal A, Windows, Waitress:

```powershell
python -m waitress --host=127.0.0.1 --port=5000 --threads=6 --channel-timeout=120 --call app:create_app
```

`--threads=6` matches the default in the capacity runbook (`PEAK_CONCURRENT_LLM=4` and `WORKER_HEADROOM=2`). `--channel-timeout=120` matches `WORKER_TIMEOUT_SECONDS`.

Terminal B, the worker:

```powershell
python -m services.jobs.worker
```

Leave the worker at `WORKER_CLAIM_THREADS=1` unless you have decided otherwise. Reports and chat stay queued until this process is running.

Check the API:

- `http://127.0.0.1:5000/api/health` returns `status`, `database_ok`, and `ratelimit_store_ok`
- `http://127.0.0.1:5000/apidocs/` is Swagger when `FLASK_ENV` is `development`, `dev`, or `local`. The Basic-auth password is `API_SECRET_KEY`. Any username works. That password does not list profiles.

The local debugger, only while `FLASK_ENV` is `development`, `dev`, or `local`, is `python app.py` in place of the Waitress line. It does not replace the worker.

## 6. Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite serves `http://localhost:5173` and proxies `/api` to Flask, so the session cookie stays on one origin. `frontend/.env` should contain:

```env
VITE_API_URL=/api
```

Open `http://localhost:5173`, create an account, and save a profile. Generating a report or sending a chat message needs the worker in terminal B.

## Processes that must be up

| Process | Command | Role |
| --- | --- | --- |
| PostgreSQL | `docker compose up -d` | `finpilot` and `finpilot_ratelimit` |
| HTTP | Waitress command above | The API on port 5000 |
| Worker | `python -m services.jobs.worker` | Groq for reports and chat |
| Vite | `npm run dev` in `frontend/` | The browser app on port 5173 |

## Tests on the new machine

With Docker up and the virtual environment active, from the repo root:

```bash
python -m pytest -q
```

Tests use the `finpilot_test` database. They do not call live Groq. Frontend tests, from `frontend/`:

```bash
npm test
```

## Optional pieces

- `BOOTSTRAP_ACCOUNT_EMAIL` and `BOOTSTRAP_ACCOUNT_PASSWORD` in `.env` only when an existing database has profiles and no account. The password is hashed on startup.
- `python scripts/issue_api_credential.py` prints a scoped API key once. The React app does not use that key.
- `SQLITE_IMPORT` stays off. Turn it on only to copy an old `finance.db` into an empty schema.
