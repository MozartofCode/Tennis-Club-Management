# CourtIQ: tennis club management with explainable AI

An MVP a club owner can actually run: bookings, memberships, coaches, staff, and QR check-in. On top of that it has four AI features, and each one explains itself and leaves the owner in control.

| Feature | What it does | How it works |
|---|---|---|
| **Dynamic pricing** | Busy hours cost more, quiet hours get discounts, and every price lists its reasons. | A gradient-boosted demand forecast (scikit-learn) plus a transparent price formula, clamped to the owner's min/max and surge/discount limits. Modes: off, suggest only, on. |
| **Self-running waitlist** | When a booking is cancelled, the slot is offered to the best-placed waiting member with a timed hold. | Priority score from membership tier, time waiting, churn risk, fairness and exact time match, each shown as a reason. A background sweep expires holds and moves on to the next member. |
| **Churn prediction + offers** | Flags members likely to leave, gives plain-English reasons, and drafts a retention or upsell offer. | A logistic regression on habit features, tested on a time-split holdout. Coefficients become the reasons. Claude writes the offer message (optional), and the owner approves every send. |
| **Matchmaking + auto-booking** | Suggests players at your level who are free when you are. Accepting an invite books the court, preferably in a quiet hour. | Elo rating, availability overlap, style and variety scoring. Also runs a weekly ladder and suggests clinics for quiet hours. |

Plus: a 5-step setup wizard, CSV member import, a court calendar, a member app (booking, QR code, profile, offers), a coach view, a full-screen check-in kiosk (camera or USB scanner), and analytics.

See [docs/PLAN.md](docs/PLAN.md) for the original plan and [docs/ARTICLE-NOTES.md](docs/ARTICLE-NOTES.md) for numbers and screenshots to use in the article.

## Run it locally

Requirements: [uv](https://docs.astral.sh/uv/) and Node 22+.

```bash
make install
make seed      # demo club: 250 members, 6 months of history
make dev       # API on :8000, web app on :5173
```

Open http://localhost:5173 and use the demo buttons on the sign-in page, or sign in with `owner@courtiq.demo`, `desk@courtiq.demo`, `coach@courtiq.demo` or `member@courtiq.demo` (password `courtiq-demo`).

The kiosk is at `/kiosk` (sign in as owner or desk). To try a check-in without a camera, copy a member's code from their **My QR code** page into the kiosk's text box.

Other commands:

```bash
make test      # backend tests (pytest)
make lint      # ruff + oxlint
make train     # model accuracy + pricing simulation on the local database
make build     # production build of the web app
```

## Configuration

Copy `.env.example` to `.env`. Every setting is optional for local development.

- `DATABASE_URL`: SQLite by default. In production, use your Supabase Postgres connection string; tables are created on startup.
- `JWT_SECRET`: **required in production.** The app refuses to start with the dev default when `ENVIRONMENT=production`.
- `ANTHROPIC_API_KEY`: when set, Claude (`claude-sonnet-5-5`) writes personalised offer messages. Without it, templates are used.
- `RESEND_API_KEY`: when set, sends email for waitlist offers and member offers. Without it, emails are logged.

## Deploy

The `Dockerfile` builds one container in which FastAPI serves both the API and the web app.

- **Render:** `render.yaml` is a blueprint. Set `DATABASE_URL` to the Supabase session-pooler connection string.
- **Fly.io:** `fly.toml` is included. Run `fly launch --no-deploy`, then `fly secrets set DATABASE_URL=... JWT_SECRET=...`, then `fly deploy`.

Keep at least one machine running: background jobs (waitlist holds every minute, churn scoring nightly, ladder pairing on Sundays) run inside the API process.

## Architecture

```
frontend/   React 19 + Vite + TypeScript + Tailwind v4 + React Router + TanStack Query + Zustand
backend/    FastAPI + SQLAlchemy 2, scikit-learn, APScheduler, Anthropic SDK (managed with uv)
  app/ai/        demand.py, pricing.py, waitlist.py, churn.py, offers.py, matchmaking.py
  app/api/       one router per area, all under /api
  scripts/       seed.py (demo club), train.py (model metrics)
```

Roles: owner, staff (front desk), coach, member. Every table carries `club_id`, so the app can host several clubs later.

## Honest notes

- **The demo data is synthetic.** Members follow personas, and fading members slow down before they leave, which is what the churn model learns. The last 30 days include **simulated** AI activity (waitlist refills, matchmaking bookings, a few offers) so the analytics page isn't empty. Model metrics on this data show the method works; they are not evidence from a real club.
- **The pricing revenue figure is a simulation** with two stated, adjustable assumptions: price sensitivity, and demand turned away at full hours. Both are shown on the Pricing page.
- **No payments in the MVP:** members pay at the desk, and staff mark bookings paid. Stripe is the obvious next step.
- **Auth is built into the API** (JWT + bcrypt), so it works the same on SQLite and Supabase Postgres. Access rules are enforced in the API, not with Supabase RLS.
