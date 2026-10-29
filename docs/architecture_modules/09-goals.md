# Goals

## Explanation

Goal math runs inside the request. It does not call Groq and it does not write a job. The SIP payment, the three scenarios, the feasibility score, and the timeline search are deterministic.

Saved goals stay in the browser. The server does not keep a goal list.

## High-level design

```mermaid
flowchart LR
  form[Goal form] --> api[POST goal-plan]
  api --> math[goal_service]
  math --> body[Scenarios and score]
  body --> memory[Browser memory]
```

## Low-level design

| Piece | Detail |
|---|---|
| Route | `POST /api/goal-plan`. The body names the profile. Owner and confirmed email. |
| Inputs | Goal amount, years, monthly savings, risk appetite. |
| Instruments | Static CAGR tiers for Low, Medium, and High. |
| Output | Conservative, Balanced, and Aggressive projections, a 0–100 score, and an achievable timeline. |
| Persistence | None on the server. |

Files: `routes/goal_routes.py`, `services/goal_service.py`.

## Sequence

```mermaid
sequenceDiagram
  participant B as Browser
  participant A as API
  participant M as goal_service

  B->>A: POST /api/goal-plan for profile 12
  A->>M: SIP and scenario math
  M-->>A: Score and timelines
  A-->>B: JSON
  B->>B: Keep the plan in memory
```
