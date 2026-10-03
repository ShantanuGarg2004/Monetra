# Documents

Files under `docs/` are grouped by what they are for.

## architecture

How the running system works.

- `ARCHITECTURE.md` — request path, worker, and databases
- `NEW_DEVICE_SETUP.md` — clone, Docker, `.env`, Waitress, the worker, and the frontend on a new machine
- `AUTH_ARCHITECTURE.md` — cookie, scoped key, and the docs password
- `CAPACITY_RUNBOOK.md` — Waitress or Gunicorn, threads, and timeouts
- `APP_DATABASE_POSTGRES.md` — the application database
- `RATE_LIMITER_ARCHITECTURE.md` — limiter design
- `IDENTITY_SEAM.md` — who a request is
- `USER_EXPERIENCE.md` — what a person using the app sees
- `FRONTEND_ERROR_HANDLING.md` — toasts and error states

## planning

What was going to be built, and in what order.

- `PLATFORM_QUALITY_WAVES.md` — Q1 through Q6
- `IMPLEMENTATION_PLAN_RATE_LIMITER_AND_BOTTLENECKS.md` — Waves 0 through 3
- `ARCHITECTURE_REMEDIATION_PLAN.md` — issues 1 through 11
- `ARCHITECTURE_REVIEW_FOLLOWUP_PLAN.md` — the later review, issues 1 through 8
- `ISSUE_REMEDIATION_PLAN.md` — debt, chat memory, and prompts
- `GROQ_MIGRATION.md` — why the provider moved to Groq
- `GROQ_PATH_B_IMPLEMENTATION.md` — the steps for that move

## analysis

Reviews and measurements. These record what was found.

- `PLATFORM_ARCHITECTURE_BOTTLENECKS.md`
- `ARCHITECTURE_AND_ISSUE_6_ANALYSIS.md`
- `BACK_BUTTON_PREVIOUS_ACCOUNT.md` — back button can show the previous account’s profile

## execution

What was built, and the reports from running it.

- `GROQ_PATH_B_IMPLEMENTATION_REPORT.md` — what the Groq move changed
- `testing_reports/` — one report for each quality wave, remediation issue, the database move, and each review follow-up

## deployment

How the system is meant to be hosted.

- `VERCEL_RAILWAY_DEPLOY_GUIDE.md` — step-by-step: Docker image, Docker Hub, Railway, Vercel (locked path)
- `DEPLOYMENT_STRATEGY.md` — Vercel, Railway trial, Docker Hub, GitHub Actions (strategy)
- `GCP_FREE_CREDITS_DEPLOYMENT.md` — GCP services and setup on free credits (alternate)

## product-audit

What the running product is, judged from the repository. These are reviews, not setup steps.

- `01-product-360-audit.md` — product identity, journey, and maturity
- `02-feature-service-audit.md` — feature map
- `feature-matrix.csv` — the same features in a table
- `03-personas-jtbd.md` — personas and jobs
- `04-ux-audit.md` — screen-by-screen UX
- `user-flows.md` — workflows and the proposed first session
- `05-ui-design-system-audit.md` — visual audit
- `design-system.md` — the tokens and components that exist
- `06-ai-product-audit.md` — what the model actually receives and returns
- `07-trust-safety-audit.md` — scores, advice, and data claims
- `08-product-metrics.md` — what can be measured
- `09-monetization-packaging.md` — units the product could charge for
- `product-inventory.json` — structured inventory

`architecture/ARCHITECTURE.md` is the current system. `architecture/NEW_DEVICE_SETUP.md` is how to run it on a new machine. `planning/` is the order the work was planned. `deployment/VERCEL_RAILWAY_DEPLOY_GUIDE.md` is the locked how-to for Vercel + Railway + Docker Hub.
