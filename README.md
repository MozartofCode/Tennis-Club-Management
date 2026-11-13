# CourtIQ: tennis club management with explainable AI

An MVP club owners can actually run: bookings, memberships, coaches, QR check-in, plus four AI features:

1. **Dynamic pricing + waitlist**: prices follow predicted demand inside owner-set limits, and cancelled slots are offered automatically to the best-placed waiting member.
2. **Churn prediction**: members at risk are flagged with plain-English reasons and a drafted retention or upsell offer the owner approves.
3. **Matchmaking + auto-booking**: members are matched by level and availability, and a court is booked for them (preferably off-peak).
4. **QR check-in**: a kiosk page on any tablet logs visits, which also feed churn tracking.

See [docs/PLAN.md](docs/PLAN.md) for the full plan.

## Run it locally

Requirements: [uv](https://docs.astral.sh/uv/) and Node 22+.

```bash
make install
make dev
```

Open http://localhost:5173.
