<div align="center">

# Monetra

### AI-Powered Personal Financial Advisor

A production-oriented **Flask + React** application that pairs deterministic financial-scoring
engines with an LLM advisory layer (**Groq**) to deliver personalised financial
health assessments, AI-generated advisory reports, conversational guidance, and
goal-feasibility simulations for Indian retail investors.

<br/>

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Backend-000000?logo=flask&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-Frontend-646CFF?logo=vite&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLM-F55036?logo=groq&logoColor=white)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Request Lifecycle](#request-lifecycle)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Financial Health Scoring Model](#financial-health-scoring-model)
- [Goal Feasibility Simulator](#goal-feasibility-simulator)
- [Database Schema](#database-schema)
- [Roadmap](#roadmap)
- [Disclaimer](#disclaimer)
- [Author](#author)

---

## Overview

Monetra ingests a user's financial profile — age, income, expenses, savings, risk
appetite, goals, and an optional EMI figure — and layers three independent engines on top of it:

1. **Deterministic financial-health scorer** — a 7-pillar, rule-based engine that produces a
   0–100 score with no AI involvement, so results are reproducible and explainable.
2. **LLM advisory layer** — turns the scored profile into a structured, SEBI-advisor-style
   report and a conversational chat assistant, grounded in the user's actual numbers. Powered
   by **Groq**. The HTTP request queues the work. A worker process calls the model.
3. **Goal-feasibility simulator** — SIP (Systematic Investment Plan) annuity-due mathematics
   that projects Conservative / Balanced / Aggressive investment scenarios.

Reports are rendered to branded PDF documents on disk. Profiles, reports, chat, and jobs live in
PostgreSQL. The browser signs in with an email and password and keeps an HttpOnly session
cookie. A scoped API key can call the same account. `API_SECRET_KEY` opens local Swagger only.
A rate-limit gateway sits in front of the API, with its own PostgreSQL database. Swagger is on
when `FLASK_ENV` is `development`, `dev`, or `local`. Groq runs in `python -m services.jobs.worker`, not in the HTTP request.

---

## Key Features

- **Financial Health Score** — 7-pillar rule-based engine (savings rate, expense control,
  emergency fund, debt-to-income, retirement adequacy, tax efficiency, surplus buffer).
- **AI-Generated Advisory Reports** — structured, section-based reports grounded in the
  user's real figures, produced via Groq (`openai/gpt-oss-120b` by default).
- **Conversational Advisor Chat** — per-profile chat with history stored in PostgreSQL.
- **Goal Feasibility Simulator** — SIP PMT–based required-contribution calculator with three
  CAGR scenarios, feasibility scoring, and a recommended timeline.
- **PDF Report Generation** — branded, multi-section advisory PDFs via ReportLab (cover page,
  snapshot, insights, warnings, AI recommendations, action checklist, disclaimer).
- **Persistent storage** — PostgreSQL database `finpilot` for accounts, profiles, reports,
  chat, jobs, and scoped API keys. PDF files live under `data/pdfs`. The limiter uses a
  separate database, `finpilot_ratelimit`.
- **Sign-in** — email and a Werkzeug password hash. The browser session is an HttpOnly cookie,
  `finpilot_session`, signed with `SESSION_SECRET`. A signed-in person only sees their own profiles.
- **Scoped API key** — `scripts/issue_api_credential.py` prints a key once. The database stores
  a hash. Scopes are `data` and `llm`. The key is that account, not every account.
  `API_SECRET_KEY` opens Swagger and does not list profiles. The React app does not send a key.
- **Rate limiting** — one gateway. Quotas come from config. Unknown `/api` routes are denied.
- **Swagger / OpenAPI** — `http://127.0.0.1:5000/apidocs/` when `FLASK_ENV` is `development`,
  `dev`, or `local`. Password is `API_SECRET_KEY` (any username).
- **Strict Request Validation** — Marshmallow schemas on every mutating endpoint.
- **React + Vite Frontend** — a polished single-page client (`frontend/`) that consumes the API.

---

## Architecture

```mermaid
flowchart LR
    subgraph CLIENT["Frontend — React + Vite"]
        UI["Landing, then Profile · Dashboard · Advisory · Chat · Goals"]
    end

    subgraph API["Flask — app.py"]
        MW["Actor<br/>cookie, else scoped key"]
        RL["Rate-limit gateway"]
        UB["user_routes"]
        RB["report_routes<br/>enqueue 202"]
        CB["chat_routes<br/>enqueue 202"]
        GB["goal_routes"]
    end

    subgraph WORKER["python -m services.jobs.worker"]
        JW["Claim jobs<br/>Groq, then save"]
    end

    subgraph SERVICES["Service Layer"]
        HS["health_service"]
        GS["goal_service"]
        AS["ai_service"]
        PS["pdf_service"]
    end

    subgraph EXTERNAL["External"]
        OAI["Groq API"]
    end

    subgraph DATA["PostgreSQL and disk"]
        DB[("finpilot<br/>accounts · users · reports · chat · jobs · api_credentials")]
        RLDB[("finpilot_ratelimit")]
        PDF["data/pdfs"]
    end

    UI -- "HTTP + finpilot_session" --> MW
    MW --> RL
    RL --> UB & RB & CB & GB
    RL --> RLDB
    RB --> DB
    CB --> DB
    UB --> DB
    GB --> GS & DB
    JW --> DB
    JW --> AS
    JW --> HS & PS
    PS --> PDF
    AS --> OAI
```

**Layer summary**

1. Every `/api/*` request except `OPTIONS`, health, sign-in, sign-up, and sign-out needs a
   session cookie or a scoped `X-API-Key`, then the rate-limit gateway, before a blueprint runs.
   `API_SECRET_KEY` opens local Swagger only.
2. `POST /api/generate-report` and `POST /api/chat` return `202` and a `job_id`. The worker
   process calls Groq. Other routes validate JSON with Marshmallow, then call a service.
3. `health_service` scores a profile, `goal_service` runs SIP math in the request, `ai_service`
   calls Groq from the worker, and `pdf_service` writes a file under `data/pdfs`.
4. Accounts, profiles, reports, chat, jobs, and API credentials live in PostgreSQL database
   `finpilot`. Rate-limit counters live in `finpilot_ratelimit`.

> The request path, the worker, and the two databases are written up in
> [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md).

---

## Request Lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant API as Flask API
    participant W as Job worker
    participant DB as PostgreSQL

    C->>API: Cookie or scoped X-API-Key
    API->>API: Actor check, then rate-limit gateway
    alt POST generate-report or POST chat
        API->>DB: Insert jobs row
        API-->>C: 202 job_id
        W->>DB: Claim the job
        W->>W: Groq, then save the report or the chat turn
    else other JSON route
        API->>DB: read or write
        API-->>C: JSON
    end
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | Flask, Flask-CORS, rate-limit gateway |
| API documentation | Flasgger (Swagger UI) |
| Validation | Marshmallow |
| Database | PostgreSQL 16 (`finpilot` for app data, `finpilot_ratelimit` for quotas) |
| AI / LLM | Groq (`openai/gpt-oss-120b` report · `openai/gpt-oss-20b` chat) |
| PDF generation | ReportLab |
| Frontend | React 19, Vite, Tailwind, ESLint |
| Config | python-dotenv |

---

## Project Structure

```
FinPilot/
├── app.py                     # App factory: CORS, auth middleware, rate limiter, Swagger, blueprints
├── config.py                  # Environment variable loading and validation
├── extensions.py              # Shared Flask-Limiter instance
├── schemas.py                 # Marshmallow request schemas (Profile, Report, Chat, GoalPlan)
├── requirements.txt           # Python dependencies
├── database/
│   ├── db.py                  # PostgreSQL pool, named binds, test schema
│   ├── models.py              # Tables, including jobs and api_credentials
│   ├── repository.py          # Profile, report, chat, job, and account SQL
│   ├── pdf_files.py           # PDF files under data/pdfs
│   └── sqlite_import.py       # Optional copy from finance.db (SQLITE_IMPORT, default off)
├── routes/
│   ├── auth_routes.py         # Sign-up, sign-in, sign-out, current account
│   ├── user_routes.py         # Profile CRUD (/api/profile, /api/users)
│   ├── report_routes.py       # Queue a report, fetch it, download the PDF
│   ├── chat_routes.py         # Queue a chat turn, read or clear history
│   └── goal_routes.py         # Goal feasibility simulation endpoint
├── services/
│   ├── actor.py               # Cookie, then scoped credential, then docs password
│   ├── sessions.py            # finpilot_session
│   ├── jobs/worker.py         # python -m services.jobs.worker
│   ├── health_service.py      # 7-pillar financial-health scoring engine
│   ├── goal_service.py        # SIP PMT math, scenario simulation, feasibility scoring
│   ├── ai_service.py          # Groq client wrapper, report + chat generation
│   └── pdf_service.py         # ReportLab PDF report builder
├── scripts/
│   └── issue_api_credential.py # Print a scoped key once, or revoke one
├── frontend/
│   └── src/                   # Sign-in gate, profile, dashboard, chat, goals
├── tests/                     # Pytest. Groq is mocked. App DB is finpilot_test.
├── conftest.py                # Pytest bootstrap (sys.path + deterministic test env)
└── docs/
    ├── README.md              # Which folder holds which documents
    ├── architecture/          # How the running system works
    ├── planning/              # Plans and the order work was meant to ship
    ├── analysis/              # Reviews and the issue 6 measurement write-up
    └── execution/             # What was built, and testing_reports/
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Docker (local PostgreSQL 16)
- A Groq API key
- Node.js 18+ (for the frontend)

### 1. Clone the repository

```bash
git clone https://github.com/ShantanuGarg2004/FinPilot.git
cd FinPilot
```

### 2. Backend setup

```bash
# (recommended) create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your-groq-api-key
API_SECRET_KEY=your-chosen-api-secret
SESSION_SECRET=replace-with-a-different-32-character-secret
FLASK_ENV=development
RATELIMIT_STORAGE_BACKEND=sql
RATELIMIT_DATABASE_URL=postgresql+psycopg://finpilot:finpilot_dev_password@127.0.0.1:5432/finpilot_ratelimit
APP_DATABASE_URL=postgresql+psycopg://finpilot:finpilot_dev_password@127.0.0.1:5432/finpilot

# Optional — per-service model overrides (defaults shown)
GROQ_REPORT_MODEL=openai/gpt-oss-120b
GROQ_CHAT_MODEL=openai/gpt-oss-20b
```

> `GROQ_API_KEY`, `API_SECRET_KEY`, and `SESSION_SECRET` are **required**. `SESSION_SECRET` signs the browser cookie and must differ from `API_SECRET_KEY`. `FLASK_ENV=development` turns Swagger on.
> `APP_DATABASE_URL` is the application database. `RATELIMIT_DATABASE_URL` is only the limiter.
> See `.env.example`. Do not commit `.env`.

**Local PostgreSQL:**

```bash
docker compose up -d
```

The limiter schema is applied from `database/sql/rate_limit_schema.sql` on a new volume. The `finpilot` database is created when the API starts. `SQLITE_IMPORT` defaults off, so a normal start does not open `finance.db`. Set `BOOTSTRAP_ACCOUNT_EMAIL` and `BOOTSTRAP_ACCOUNT_PASSWORD` when existing profiles have no account.

Run the API and the worker in two terminals when `FLASK_ENV` is `development`, `dev`, or `local`:

```bash
python app.py
python -m services.jobs.worker
```

`python app.py` is the local debugger. Outside `development`, `dev`, or `local` it exits before it listens. Traffic on a host uses Waitress or Gunicorn. See `docs/architecture/CAPACITY_RUNBOOK.md`. The Groq worker command stays `python -m services.jobs.worker`. On Windows, Waitress; on Linux, Gunicorn. Install those only on the host that serves traffic (`pip install waitress` or `pip install gunicorn`).

- API base: `http://127.0.0.1:5000`
- Interactive docs: `http://127.0.0.1:5000/apidocs/` when `FLASK_ENV` is `development`, `dev`, or `local`

Sign in from the React app. Swagger asks for HTTP Basic auth. The password is `API_SECRET_KEY`. Any username works. That password does not list profiles. A script uses a scoped key from `python scripts/issue_api_credential.py`.

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` and proxies `/api` to Flask, so the session cookie stays on one origin. `frontend/.env`:

```env
VITE_API_URL=/api
```

Do not put the API key in the frontend. Details are in [`frontend/README.md`](frontend/README.md).

### 4. Running tests

Groq calls are mocked. Tests use PostgreSQL database `finpilot_test` (Docker must be up locally; GitHub Actions starts its own Postgres):

```bash
python -m pytest tests/ -q --tb=line --deselect tests/test_wave1_integration.py::test_sql_backend_ping_when_configured
```

---

## API Reference

Health, sign-up, sign-in, and sign-out are public. `/api/auth/me` needs the session cookie. Other `/api/*` routes accept that cookie or a scoped key for the same account. `API_SECRET_KEY` does not open those routes.

| Endpoint | Method | Who | Description |
|---|---|---|---|
| `/api/health` | GET | public | Liveness. Body is `status`, `database_ok`, and `ratelimit_store_ok`. `503` when the app database or the rate-limit store is down. |
| `/apidocs/` | GET | local env + Basic password `API_SECRET_KEY` | Swagger UI |
| `/api/auth/signup` | POST | public | Create an account and set the session cookie |
| `/api/auth/login` | POST | public | Sign in and set the session cookie |
| `/api/auth/logout` | POST | public | Bump `session_version` and clear the cookie |
| `/api/auth/me` | GET | session cookie | Current account |
| `/api/users` | GET | cookie or scoped key (`data`) | List that account’s profiles |
| `/api/profile` | POST | cookie or scoped key (`data`) | Create a profile |
| `/api/profile/<user_id>` | DELETE | cookie or scoped key (`data`) | Delete a profile, its report, and its chat |
| `/api/generate-report` | POST | cookie or scoped key (`llm`) | Queue a report. `202` and `job_id`. |
| `/api/report/<user_id>` | GET | cookie or scoped key (`data`) | Stored report, plus `job` while one is queued, running, or failed |
| `/api/download-report/<user_id>` | GET | cookie or scoped key (`data`) | Download the PDF file |
| `/api/chat` | POST | cookie or scoped key (`llm`) | Queue a chat turn. `202` and `job_id`. |
| `/api/chat/history/<user_id>` | GET, DELETE | cookie or scoped key (`data`) | Read or clear chat history. GET adds `job` while a chat job is active or failed. |
| `/api/goal-plan` | POST | cookie or scoped key (`data`) | Run the goal feasibility simulation |

Quotas are per route class in config (for example chat 15 per minute, report generation 5 per minute). The gateway is the only limiter. Unknown `/api` paths return 429 `rate_policy_missing`.

<details>
<summary>Example: create a profile</summary>

Sign in first and send the `finpilot_session` cookie, or send a scoped key from `scripts/issue_api_credential.py` as `X-API-Key`. `API_SECRET_KEY` is not accepted on this route.

```bash
curl -X POST http://127.0.0.1:5000/api/profile \
  -H "Content-Type: application/json" \
  -H "X-API-Key: a-scoped-key" \
  -d '{
    "age": 28,
    "income": 90000,
    "expenses": 50000,
    "savings": 25000,
    "risk_appetite": "medium",
    "financial_goals": "Buy a house in 7 years",
    "debt_emi": 8000
  }'
```
</details>

---

## Financial Health Scoring Model

The health score is computed across seven weighted pillars, totalling 100 points:

| Pillar | Max points | Full-marks threshold |
|---|---|---|
| Savings rate | 25 | 30% of income or higher |
| Expense control | 20 | Expenses ≤ 50% of income |
| Emergency fund | 20 | 6+ months of expenses covered |
| Debt-to-income ratio | 15 | ≤ 20% DTI (partial credit if EMI not provided) |
| Retirement adequacy | 10 | Age-adjusted corpus projection vs. a 25× annual-expense target |
| Tax efficiency | 5 | Estimated Section 80C utilisation |
| Surplus buffer | 5 | Any positive monthly surplus |

Each pillar independently returns point contributions, human-readable insights, and warnings,
which are aggregated into the final score and passed to the AI report generator for grounded advice.

---

## Goal Feasibility Simulator

The simulator uses the standard SIP PMT (annuity-due) formula to compute the monthly
contribution required to reach a target amount within a given horizon:

```
P = FV × r / [ ((1 + r)^n − 1) × (1 + r) ]
```

Where `P` is the required monthly SIP, `FV` is the target amount, `r` is the monthly rate, and
`n` is the number of months. The engine:

- Selects instrument recommendations and CAGR assumptions from risk appetite and horizon
  (Low / Medium / High tiers).
- Produces Conservative, Balanced, and Aggressive scenario projections.
- Computes a rule-based feasibility score (0–100) from savings coverage, horizon bonus, and
  risk-alignment bonus.
- Binary-searches the achievable timeline at the current savings rate.

---

## Database Schema

Database `finpilot` on PostgreSQL:

| Table | Purpose | Key constraints |
|---|---|---|
| `accounts` | Email and password hash | Unique email. `session_version` bumps on logout. |
| `users` | Financial profiles owned by an account | `account_id` references `accounts` |
| `reports` | Advisory text and the PDF file name | `user_id` unique, cascade delete |
| `chat_history` | Per-profile chat messages | Cascade delete, `role ∈ {user, ai}` |
| `jobs` | Queued report and chat work | `kind` is `report` or `chat` |
| `api_credentials` | Hashed scoped keys | `scopes` is `data`, `llm`, or both. `revoked_at` retires a key. |

Indexes cover `reports(user_id)`, `chat_history(user_id, id DESC)`, and `users(account_id)`. One active report job per profile is a partial unique index. PDF files are named `profile_<user_id>.pdf` under `data/pdfs`. The row stores the file name, not the bytes.

Rate-limit counters stay in database `finpilot_ratelimit`, not in these tables.

---

## Roadmap

- This host does not meet the written pass lines for 100 concurrent health checks or 100 concurrent profile lists. Report enqueue does. Eighty lists while 10 report jobs were running, and the chat gate after chat was queued, are both still over 300 ms. It is not fair to say that about 100 people can load the app and list their profiles at once, or that a report no longer freezes those reads. Measurement: `docs/execution/testing_reports/REMEDIATION_6_LOAD_TEST_REPORT.md`.
- Support live market data for CAGR assumptions instead of static tiers.

---

## Disclaimer

This system provides AI-assisted **educational** financial guidance and does **not** constitute
regulated investment advice. Independent professional consultation is recommended before making
investment decisions.

---

## Author

**Shantanu Garg**
B.Tech CSE-AI, Graphic Era (Deemed to be University), Dehradun 
