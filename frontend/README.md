# Monetra frontend

React 19 and Vite client. The browser does not send `X-API-Key`.

The platform overview lives in the repository [README](../README.md). Module diagrams live in [docs/architecture_modules](../docs/architecture_modules/README.md).

## Run it

PostgreSQL and the Flask API must already be up. From the repo root that is `docker compose up -d`, then `python app.py` on port 5000.

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to `http://127.0.0.1:5000`.

Production sets `VITE_API_URL` to the Railway API prefix ending in `/api`. There is no router package. `frontend/vercel.json` rewrites unknown paths to `index.html` so `/verify-email`, `/reset-password`, `/confirm-email`, and `/settings` load the app.

## What the screens do

| Screen | Behavior |
|---|---|
| Create account | `POST /api/auth/signup`. A confirmation link is emailed to that address. The app stays on the confirm screen until the link is used. |
| Sign in | `POST /api/auth/login`, then `POST /api/auth/login-code` with the 6-digit code. Cookies are `finpilot_access` and `finpilot_refresh`. |
| Mail links | The id and token are captured on first load. A missing session does not send the page back to the landing page. |
| Profiles, report, chat, goals | `src/config/api.js` with `credentials: "include"`. A dead access cookie refreshes once. |
| Settings | Change password, change email, delete account. |
| Sign out | `POST /api/auth/logout` revokes this session only. |

Do not put `API_SECRET_KEY` in this folder.
