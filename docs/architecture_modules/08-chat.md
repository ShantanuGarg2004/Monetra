# Chat

## Explanation

A chat turn inserts a job and returns `202`. The worker writes the user line, calls Groq, and writes the assistant line. The browser polls history. Clearing history does not cancel a job that is already running.

The model system prompt identifies the assistant as Monetra and keeps the educational disclaimer.

## High-level design

```mermaid
flowchart LR
  browser[Browser] --> post[POST chat]
  post --> jobs[(jobs)]
  worker[Worker] --> jobs
  worker --> groq[Groq]
  worker --> history[(chat_history)]
  browser --> get[GET history]
  get --> history
```

## Low-level design

| Route | Rule |
|---|---|
| `POST /api/chat` | Body names the profile. Owner, confirmed email, non-empty message. `202` and `job_id`. |
| `GET /api/chat/history/<user_id>` | History for that profile. |
| `DELETE /api/chat/history/<user_id>` | Deletes the history rows. |

`chat_history.role` is `user` or `ai`. Rows cascade when the profile is deleted. The header `X-FinPilot-Stub-Delay-Ms` is a test stub only.

Files: `routes/chat_routes.py`, `services/jobs/worker.py`, `services/ai_service.py`.

## Sequence

```mermaid
sequenceDiagram
  participant B as Browser
  participant A as API
  participant W as Worker
  participant G as Groq

  B->>A: POST /api/chat for profile 12
  A-->>B: 202
  W->>W: Insert user line
  W->>G: History plus the new line
  G-->>W: Reply
  W->>W: Insert ai line
  B->>A: GET /api/chat/history/12
  A-->>B: Both lines
```
