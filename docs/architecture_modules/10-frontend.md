# Frontend

## Explanation

The React app is one page. Paths are read from `window.location`. There is no router package. Vercel rewrites unknown paths to `index.html`, so a mail link loads the app instead of a platform 404.

The confirmation, reset, and email-change pages capture `id` and `token` on the first render. A later navigation that stays on the same path keeps the query. A missing session on those paths does not send the person to the landing page.

## High-level design

```mermaid
flowchart TD
  url[Path and query] --> app[App]
  app --> mail{Mail link?}
  mail -->|yes| proof[Keep id and token]
  mail -->|no| screen[Landing, app, or settings]
  proof --> confirm[Confirm button posts the proof]
```

## Low-level design

| Piece | Detail |
|---|---|
| Paths | `/`, `/profile`, `/dashboard`, `/advisory`, `/chat`, `/goals`, `/settings`, `/verify-email`, `/reset-password`, `/confirm-email` |
| API | `VITE_API_URL` or `/api`. `credentials: include`. |
| Refresh | One retry through `POST /api/auth/refresh` after `session_expired`. |
| Mail proof | `useState` initializer reads the query before effects. Pages submit `proof.id` and `proof.token`. |
| Same-path navigation | `locationForSamePath` keeps `search` and `hash`. Leaving the path drops them. |
| Session-expired event | `finpilot:session-expired`. On a mail link, the handler clears account state and does not call `go("/")`. |
| Product copy | The visible name is Monetra. |

Files: `frontend/src/App.jsx`, `frontend/src/lib/routes.js`, `frontend/vercel.json`, `frontend/src/pages/VerifyEmail.jsx`.

## Sequence

```mermaid
sequenceDiagram
  participant M as Mail client
  participant V as Vercel
  participant R as React
  participant A as API

  M->>V: GET /verify-email?id=4&token=abc
  V-->>R: index.html
  R->>R: Store id and token
  R->>A: GET /api/auth/me
  A-->>R: 401
  R->>R: Stay on the page
  R->>A: POST /api/auth/verify-email with the stored proof
  A-->>R: Email confirmed
```
