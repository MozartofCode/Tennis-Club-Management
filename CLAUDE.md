# CourtIQ: notes for AI assistants

Tennis club management MVP with explainable AI. Plan and phases: `docs/PLAN.md`.

## Layout
- `backend/`: FastAPI + SQLAlchemy 2 (ORM), managed with uv. Entry `app/main.py`.
  - `app/models.py`: all tables. Every club-owned row has `club_id`.
  - `app/api/`: one router per area, mounted under `/api`.
  - `app/ai/`: demand (forecast), pricing, waitlist, churn, offers (Claude writer), matchmaking. Pure functions where possible so they're unit-testable.
  - `app/jobs.py`: APScheduler jobs (waitlist sweep each minute, nightly churn, Sunday ladder). Off when `JOBS_ENABLED=false` (tests).
  - `scripts/seed.py`: synthetic demo club. `scripts/train.py`: model metrics.
- `frontend/`: React 19 + Vite + TS + Tailwind v4 + React Router + TanStack Query + Zustand.
  - `src/routes/{public,admin,member,coach,kiosk}`, shared UI in `src/components/ui.tsx`.

## Conventions
- Booking times are **club-local naive datetimes** (`app/timeutil.club_now`). Audit columns are naive UTC (`utcnow`). The frontend parses booking ISO strings with `parseLocal` so they never shift.
- Auth: the API issues HS256 JWTs (`app/security.py`). Roles: owner, staff, coach, member. Use `require_staff` / `require_roles` dependencies; members only ever see their own rows.
- Every AI output carries human-readable reasons (`price_breakdown`, `priority_reasons`, churn `reasons`, `match_reasons`). Keep it that way: the owner must be able to see *why*.
- Claude is optional (`ANTHROPIC_API_KEY`); every LLM path has a template fallback.
- SQLite locally, Supabase Postgres in production via `DATABASE_URL`; tables are created with `create_all`.

## Commands
- `make setup`, `make dev` (API :8787, web :5173; override with `API_PORT=`/`WEB_PORT=`), `make test`, `make lint`, `make seed`, `make train`.
- Vite proxies `/api` to `API_PORT` (default 8787). In production the API also serves `frontend/dist` (see `Dockerfile`).
