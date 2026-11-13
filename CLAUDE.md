# CourtIQ: notes for AI assistants

Tennis club management MVP with explainable AI. Plan and phases: `docs/PLAN.md`.

## Layout
- `backend/`: FastAPI + SQLAlchemy 2 (ORM), managed with uv. Entry `app/main.py`.
  - `app/models.py`: all tables. Every club-owned row has `club_id`.
  - `app/api/`: one router per area, mounted under `/api`.
  - `app/ai/`: pricing, waitlist, churn, offers, matchmaking. Pure functions where possible so they're unit-testable.
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
- `make install`, `make dev` (API :8000, web :5173), `make test`, `make lint`, `make seed`, `make train`.
