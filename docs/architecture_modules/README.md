# Architecture modules

**Date:** 2026-10-29  
**Product:** Monetra

Each file is one module of the running system. It has four parts:

1. **Explanation** — what the module is responsible for.
2. **High-level design** — how it sits next to the rest of the system.
3. **Low-level design** — the files and the rules inside the module.
4. **Sequence** — one real path through the module.

`docs/architecture/ARCHITECTURE.md` is the short as-built overview. These files are the diagrams. Planning notes, test reports, and product audits stay in their own folders and describe the day they were written.

| Module | File |
|---|---|
| Platform | [01-platform.md](01-platform.md) |
| Identity and sessions | [02-identity-and-sessions.md](02-identity-and-sessions.md) |
| Account lifecycle | [03-account-lifecycle.md](03-account-lifecycle.md) |
| Email | [04-email.md](04-email.md) |
| Rate limiting | [05-rate-limiting.md](05-rate-limiting.md) |
| Profiles | [06-profiles.md](06-profiles.md) |
| Reports and PDF | [07-reports-and-pdf.md](07-reports-and-pdf.md) |
| Chat | [08-chat.md](08-chat.md) |
| Goals | [09-goals.md](09-goals.md) |
| Frontend | [10-frontend.md](10-frontend.md) |
| Jobs worker | [11-jobs-worker.md](11-jobs-worker.md) |
| Data stores | [12-data-stores.md](12-data-stores.md) |
