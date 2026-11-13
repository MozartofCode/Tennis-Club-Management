# CourtIQ: AI-Assisted Tennis Club Management MVP

## Context
Bertan is writing an article on how AI can improve tennis club operations, and wants a working MVP that backs it up. It should be good enough that a normal club owner (not a developer) could actually run their club on it. The repo is empty (`README.md` + `LICENSE` only), so this is a greenfield build.

Decisions made:
- **Stack:** React + FastAPI + Supabase
- **QR codes:** check-in only, no gate hardware
- **Payments:** none in the MVP. Pay at the desk, and bookings are marked paid or unpaid.
- **Automatic gates:** dropped from scope

The four AI features the article describes:
1. Dynamic pricing + waitlist management
2. Churn prediction, with retention incentives and upsells
3. Automatic booking + matchmaking by level, which also spreads demand away from crowded hours
4. *(Gates are out of scope; QR check-in replaces them as the visit/"movement" tracker.)*

"CourtIQ" is a placeholder name.

---

## 1. Product shape: four surfaces, one app

| Surface | Who | Core screens |
|---|---|---|
| **Member app** (mobile-first web) | Members | Sign up / profile (skill level, availability, goals), my QR code, book a court (live prices), join waitlist, "Find me a match", my bookings, offers inbox |
| **Management dashboard** | Owner / front desk | Club setup wizard (courts, hours, coaches, membership plans, base prices), live court calendar, members list + visit history, check-in log, **Churn Risk** board, **Pricing** rules + preview, waitlist queue, analytics |
| **Coach view** (light) | Coaches | My schedule, my students, students' levels, lesson booking slots |
| **Check-in kiosk** | Tablet at front desk | Full-screen camera QR scanner → "Welcome, Alex — Court 3 at 6pm" or "No booking — book now?" |

Role-based routing uses one React app with a `role` claim (`member`, `staff`, `owner`, `coach`) from Supabase Auth. Every table has `club_id` so the app can become multi-club later, but the UI assumes one club per owner for the MVP.

## 2. Data model (Supabase Postgres)
- `clubs` — name, timezone, opening hours, peak-hour definition, pricing settings
- `courts` — club_id, name, surface, indoor/outdoor, lights, active
- `coaches` — club_id, profile_id, specialties, hourly rate, availability
- `profiles` — auth user ↔ role, club_id, name, phone, **skill_level (NTRP 1.0–7.0)**, **rating (Elo-style, hidden)**, preferred times (JSON), goals, qr_token (random, rotatable)
- `membership_plans` / `memberships` — plan, start/end, status, auto-renew flag, price
- `bookings` — court_id, member_id(s), start/end, type (`casual`/`lesson`/`match`/`clinic`), **price_charged**, **price_breakdown (JSON: base + reasons)**, paid flag, status (`booked`/`cancelled`/`no_show`/`completed`)
- `waitlist_entries` — member, desired window, court prefs, priority score, status (`waiting`/`offered`/`accepted`/`expired`), offer_expires_at
- `check_ins` — member, timestamp, booking_id (nullable), method (`qr`/`manual`)
- `match_requests` / `matches` — requester, desired window, level range, format (singles/doubles); result scores → rating update
- `churn_scores` — member, score 0–1, risk band, top reasons (JSON), computed_at
- `offers` — member, type (`discount`/`free_lesson`/`upsell_package`), message, status (`draft`/`approved`/`sent`/`redeemed`), source (`churn`/`upsell`)
- `pricing_rules` — club-level multipliers and owner-set bounds (min/max price, max surge %)

Row Level Security: members see their own rows plus public court availability. Staff, owners and coaches see rows for their club. Write it once in SQL migrations under `supabase/migrations/`.

## 3. The AI features in detail
Each feature follows the same pattern, which is also the article's thesis: **simple, explainable model → clear recommendation → human can override.** That's what makes it safe for a non-technical owner.

### 3a. Dynamic pricing
- **Inputs:** hour of day, day of week, historical utilization for that slot (last 8 weeks), current fill level for that day, lead time, weather (optional, outdoor only, via a free API like Open-Meteo), and membership tier.
- **Model:** start with a transparent formula: `price = base × demand_multiplier × lead_time_multiplier × member_discount`. Clamp it to the owner's min/max and max-surge settings. The demand multiplier comes from predicted utilization, using a scikit-learn `GradientBoostingRegressor` trained on booking history (synthetic at first). If there isn't enough data, it falls back to a lookup on the historical average.
- **Output:** a price plus a human-readable breakdown, e.g. "Peak hour +20%, 85% booked +10%, member −15%". It's stored on the booking.
- **Owner UI:** a heatmap of next week's prices and predicted utilization, sliders for the bounds, and a "simulate revenue" comparison of flat vs. dynamic pricing.
- **Off-peak nudges:** quiet slots get discounts automatically ("Tue 2pm is 30% off"), which feeds into crowd-smoothing.

### 3b. Waitlist management
- A member joins a waitlist for a full slot (a time window plus flexible court).
- On cancellation, a Postgres trigger or API hook runs `waitlist.process(slot)`:
  - Rank waiting members by a priority score: membership tier, how long they've waited, churn risk (at-risk members get a boost, so the waitlist doubles as a retention tool), fairness (fewer recent offers ranks higher), and match to their requested window.
  - Offer the slot to the top member with a 15-minute hold (email via Resend, plus an in-app banner).
  - Accept → convert to a booking. Expire → move on to the next member.
- When there's no exact match, suggest alternatives such as an adjacent hour or a different court at a lower price.
- A background job (APScheduler in FastAPI) expires holds.

### 3c. Churn prediction + incentives/upsells
- **Features per member** (computed nightly): visits in the last 14/30/60 days and the trend, days since last visit, booking frequency trend, cancellation and no-show rate, days to membership end, auto-renew off, lesson participation, match participation, number of regular playing partners, offer response history, tenure.
- **Model:** logistic regression (scikit-learn) at first, because its coefficients give plain-English **reason codes**. Example: "Visits down 60% vs last month", "Membership ends in 12 days, auto-renew off", "Regular partner stopped playing". It trains on synthetic history with realistic churn patterns, and can be retrained later on real data with a gradient-boosted model.
- **Risk board** (owner): members sorted by risk, colored bands, and the top three reasons for each.
- **Incentive engine:** rules map reasons to offer types:
  - Dropped visits → free hitting session or match invite
  - Lost partner → matchmaking intro
  - Renewal soon → renewal discount
  - High engagement + no lessons → **upsell** a lesson package
- **Claude API** (`claude-sonnet-5-5`) drafts a personalized message from the member's context. The **owner approves before sending**, then tracks redemptions.

### 3d. Automatic booking + matchmaking
- Members set their level (self-rated NTRP, which coaches can adjust), availability, and format.
- **Matching score** = level closeness (from a hidden Elo-style rating that updates after reported results) + availability overlap + play-style/goal similarity + a "haven't played together recently" variety bonus.
- **"Find me a match"** returns the top three opponents (or doubles partners) with open overlapping windows. One tap sends an invite, and when the other player accepts, the court is **auto-booked**, preferring off-peak or discounted slots (crowd-smoothing).
- **Weekly auto-league (stretch):** every Sunday, pair opted-in members and pre-book courts in low-utilization windows.
- **Coaches:** group students of similar level into clinics to fill under-used slots.

### Cold-start: synthetic data generator
This is essential both for the demo and for the article's screenshots. `backend/scripts/seed.py` creates one club with 6 courts, 4 coaches, about 250 members across different personas (regulars, weekend warriors, fading members, new joiners), and 6 months of bookings, check-ins and match results with realistic seasonality and churn. Every model trains on this data, so the dashboard looks alive on day one.

## 4. Architecture & repo layout
```
Tennis-Club-Management/
  frontend/            React 19 + Vite + TS + Tailwind v4 + Zustand + React Router + TanStack Query
    src/routes/member/ src/routes/admin/ src/routes/coach/ src/routes/kiosk/
  backend/             FastAPI + SQLAlchemy/psycopg + pydantic, managed with uv
    app/api/           bookings, pricing, waitlist, checkin, matches, churn, offers, club
    app/ai/            pricing_model.py, churn_model.py, matchmaking.py, waitlist.py, offer_writer.py (Claude)
    app/jobs/          APScheduler: nightly churn scoring, hold expiry, weekly league
    scripts/seed.py    synthetic data
    tests/
  supabase/migrations/ schema + RLS
  CLAUDE.md, Makefile, docker-compose.yml
```
- **Auth:** Supabase Auth with magic link and email/password. FastAPI verifies the Supabase JWT with pyjwt (same pattern as Tank Day).
- **QR:** `qr_token` is a random value (never the user id) rendered with `qrcode.react`. The kiosk scans with `html5-qrcode`, then `POST /checkin {token}` → a check-in row, matched to the member's current booking. Tokens can be rotated if a code leaks.
- **Realtime:** Supabase Realtime pushes calendar updates and waitlist offers.
- **Deploy:** frontend on Vercel, backend on Fly.io or Render via Docker, Sentry for errors.

## 5. Build phases
| Phase | Scope | Done when |
|---|---|---|
| **0. Scaffold** (~2 days) | Monorepo, Supabase project + migrations, auth + roles, CI (ruff, pytest, oxlint, Vitest), CLAUDE.md | Each role can log in and lands on its own empty dashboard |
| **1. Core club ops** (~1 week) | Club setup wizard, courts/coaches/plans CRUD, court calendar, member booking at flat prices, member QR + kiosk check-in, members list + visit history | An owner can set up a club and members can book and check in, with no AI yet |
| **2. Synthetic data** (~2 days) | `seed.py` personas + 6 months of history | Dashboards show realistic data |
| **3. Dynamic pricing + waitlist** (~1 week) | Utilization model, pricing engine with breakdown, owner bounds + heatmap, waitlist queue + hold/offer flow | A cancelled peak slot is offered to the right person; prices change by slot with explanations |
| **4. Churn + offers** (~1 week) | Feature pipeline, logistic model, risk board with reasons, rules → offers, Claude message drafts, approve/send/redeem | The owner sees the top at-risk members and sends an approved offer |
| **5. Matchmaking + auto-booking** (~1 week) | Ratings, match scoring, invites, auto-book off-peak, coach clinics | Two members get matched and a court is booked automatically |
| **6. Polish + article assets** (~3–4 days) | Analytics page (revenue lift, utilization smoothing, retention), onboarding copy, empty states, mobile QA, deploy, screenshots/GIFs | Public demo link + seeded demo logins for each role |

## 6. Skills you already have, and where they fit
Based on your other repos:
- **React 19 + Vite + TS + Tailwind v4 + Zustand** (Tank Day, Blackjack V2, AgentReady) → the whole frontend.
- **FastAPI + SQLAlchemy + psycopg + uv** (Tank Day, AgentReady, Agent Monitor) → the backend API.
- **Supabase Postgres, Auth (magic link + JWT verification), migrations** (Tank Day, Stock-Portfolio-Tracker, Wine-LLM) → database, auth, roles.
- **scikit-learn, pandas, numpy, model persistence with joblib** (Blackjack ML bots, sp500-sector-rotation) → churn model, utilization/pricing model, feature pipelines.
- **Backtesting discipline / avoiding look-ahead bias** (sp500-sector-rotation) → train/test splitting churn by time so the article's accuracy numbers are honest.
- **Reinforcement learning / Q-learning** (Blackjack) → an optional "v2" pricing agent you can mention in the article as future work.
- **Anthropic SDK + Groq; LLM output checked in code** (Tank Day, AgentReady, Earnings Agent) → offer writer and an optional "Ask your club" assistant.
- **Charts with Recharts / Plotly** (Stock tracker, Wine-LLM, sp500) → pricing heatmap, utilization, churn trends.
- **Spreadsheet import with xlsx/papaparse** (Pana, Stock tracker) → **import an existing member list from Excel/CSV**. This is a big deal for real owners switching from spreadsheets.
- **Celery or background jobs, scheduled runs** (Earnings Agent) → nightly churn scoring and hold expiry (APScheduler is simpler here).
- **Realtime: WebSocket / SSE** (Agent Monitor, Tank Day) → live calendar and waitlist offers.
- **Docker, Fly/Render, Vercel, Sentry, ruff/pytest/oxlint** (Tank Day) → deploy and quality tooling.
- **MCP server building** (Pana) → stretch goal: expose the club as an MCP server so an owner can ask Claude "who's at risk this week?"
- **Swift / SwiftUI + Vision** (Check-Splitter) → a possible native member app later. Not needed for the MVP, because the web app's QR code works on any phone.

**New things you'll pick up:** QR generation and scanning in the browser, multi-role Supabase RLS policies, time-slot/scheduling logic (overlaps, timezones, holds), transactional email (Resend), and explainable-ML reason codes.

## 7. Making it usable by a real owner
- A setup wizard in under 10 minutes: club → courts → hours → base prices → coaches → import members.
- Every AI output says *why* in plain English, and every AI action can be overridden or turned off. Pricing has hard bounds, and offers need approval.
- Sensible defaults: pricing starts in "suggest only" mode until the owner turns it on.
- Mobile-first member UI; the kiosk works on any tablet browser.

## 8. Article tie-ins
Measure on the synthetic data and present the results as a simulation:
- **Revenue:** dynamic vs. flat pricing over the same demand
- **Utilization:** peak/off-peak spread before vs. after nudges and matchmaking
- **Churn:** model precision/recall on a time-based holdout; members "saved" by offers in the simulation
- **Staff time:** waitlist slots refilled automatically vs. phone calls
- Screenshots: risk board with reasons, pricing heatmap, match suggestion, kiosk check-in

*Paste your article draft whenever you're ready, and I'll align feature names, metrics and screenshots with its sections.*

## 9. Verification
- **Backend:** pytest unit tests for the pricing formula bounds, waitlist ranking and hold expiry, match scoring, churn feature extraction, plus RLS tests (a member can't read another member's bookings).
- **Models:** `make train` prints churn AUC, precision and recall on a time-split holdout, and pricing-model MAE on utilization.
- **End to end** (in the browser, after `make seed && make dev`):
  1. Owner runs the setup wizard.
  2. A member books a peak slot and sees the price breakdown.
  3. A second member joins the waitlist.
  4. The first member cancels, and the second gets an offer and accepts it.
  5. The kiosk scans the member's QR code, and the check-in appears in the admin log.
  6. The churn board shows at-risk members with reasons, and the owner approves a Claude-drafted offer.
  7. "Find me a match" returns similar-level players and auto-books an off-peak court.
- **Mobile:** check the member and kiosk views at phone width.
