# Article notes

Numbers, screenshots and talking points for the article, taken from the demo club (`make seed`, then `make train`). Everything here comes from **synthetic data**, so present it as a simulation of a 6-court club with 250 members, not as results from a real club.

## The thesis the app demonstrates

Every AI feature follows the same pattern:

1. A simple, explainable model.
2. A clear recommendation with reasons attached.
3. The owner can override it, cap it, or switch it off.

That pattern is what makes it usable by a non-technical owner, and it's a good spine for the article.

## 1. Dynamic pricing and waitlist

- **Forecast:** a gradient-boosted model predicts how full each court-hour will be. Typical error on two held-out weeks: **±12% of courts** (MAE 0.121).
- **Rules the owner controls:** standard price $40; never below $24 or above $68; busy hours at most +35%, quiet hours at most -30%.
  - Example: Sunday 9am, ~100% booked → $54. Weekday 7pm in a quiet week → $28.
- **Simulation over 8 weeks of real booking history** (price sensitivity 0.6, 15% demand turned away at full hours):
  - Revenue **$75.4k → $80.8k (+7.2%)**.
  - Peak utilization **83% → 76%**, so peak hours are less overcrowded.
  - Off-peak utilization **21% → 22%**.
  - Say plainly that both assumptions are adjustable on the Pricing page; the lift moves with them.
- **Waitlist, last 30 days in the demo:** 27 cancelled peak slots refilled automatically (~$1,080 that would otherwise have sat empty). This activity is simulated in the seed.
  - What makes it interesting: members at risk of leaving get a priority boost, so the waitlist doubles as a retention tool.

## 2. Churn prediction and incentives

- **Features:** visits and their trend, days since the last visit, booking trend, cancellations, no-shows, membership end date and auto-renew, lessons, matches, and whether a regular partner stopped playing.
- **Honest evaluation:** trained on past snapshots, tested on the most recent snapshot the model never saw (a time split, so no look-ahead).
  - **AUC 0.86:** it ranks a member who left above one who stayed 86% of the time.
  - The high-risk band has low precision on the small holdout (only 8 leavers in it). Worth saying: the real value is the ranked list plus the reasons, not a yes/no verdict.
- **Reasons the owner reads:**
  - "Switched off auto-renew"
  - "Visits down 88% vs the month before (8 → 1)"
  - "Regular partner Leo Nakamura stopped playing"
- **Offers:** rules pick the offer (renewal discount, free court hour, match introduction, lesson or clinic upsell), and Claude writes the message. The output is validated in code with a template fallback, and nothing is sent without the owner clicking Approve.

## 3. Automatic booking and matchmaking

- **Match score:** level from an Elo rating that learns from results, shared free times, play style, variety and activity. Each part is shown as a reason.
- **Accepting an invite books the court**, choosing the quietest slot both players can make. That is the crowd-smoothing link back to pricing.
  - In the demo's last 30 days, 67% of matchmaking bookings were off-peak (simulated).
- **Weekly ladder:** opted-in members are paired every Sunday.
- **Clinic suggestions:** quiet hours where enough similar-level members are free, phrased as "N active NTRP 3.0-3.5 members list this time as free, and only ~X% of courts are usually booked". Demo members list broad availability, so N is large in the demo.

## 4. Operations with fewer staff (QR check-in)

- Members show a QR code from the app, and a tablet at the desk scans it (camera or USB scanner).
- Each check-in is matched to the member's booking and flags unpaid bookings or no membership.
- Visits feed churn prediction. No gate hardware is needed for the MVP; the same scan endpoint could drive a door relay later.

## Screenshots worth taking

1. **Pricing page:** the 7-day price heatmap, with one cell hovered to show its reasons, and the simulation card.
2. **Retention board:** a high-risk member with three reasons, plus the draft offer card next to it.
3. **Member "Find a match":** suggestion cards with reasons and quiet-hour slot buttons.
4. **Waitlist:** the queue with priority reasons, and the member's "held for you" countdown card.
5. **Kiosk:** the green "Welcome, Jordan! Court 2 at 6:00 PM" screen.
6. **Analytics:** the "AI at work" row and the utilization-by-hour chart.

## Regenerating the numbers

```bash
make seed && make train
```

The seed is deterministic, so the numbers above are reproducible. They shift slightly with the current date because history is generated relative to today.
