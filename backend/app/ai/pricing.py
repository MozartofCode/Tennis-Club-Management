"""Dynamic court pricing.

price = base x demand adjustment x last-minute adjustment x member discount

- The demand adjustment comes from expected demand for that hour: the larger
  of the forecast (app.ai.demand) and how full the hour already is. Busy hours
  get up to +max_surge_pct, quiet hours down to -max_discount_pct.
- Slots starting soon that are still mostly empty get an extra last-minute deal.
- The owner's guard rails always win: the result is clamped to min/max price.
- pricing_mode "off" never adjusts; "suggest" shows the dynamic price to staff
  but charges the standard price; "on" charges it.

Every adjustment is recorded as a human-readable line so members and staff
can see why a price is what it is.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.demand import DemandModel, get_model, peak_set
from app.models import Booking, Club, Court, User
from app.services.core import active_membership
from app.timeutil import club_now

BUSY_FROM = 0.6  # expected demand where surcharges start
BUSY_FULL = 0.95  # ... and reach the maximum
QUIET_BELOW = 0.35  # expected demand where discounts start
QUIET_FULL = 0.05  # ... and reach the maximum
LAST_MINUTE_HOURS = 6
LAST_MINUTE_PCT = 10.0


@dataclass
class Adjustment:
    label: str
    pct: float  # +20 means +20%

    def as_dict(self) -> dict:
        return {"label": self.label, "pct": round(self.pct, 1)}


@dataclass
class Quote:
    base_price: float
    price: float  # what is charged
    suggested: float  # the dynamic price (equals price when pricing is on)
    demand: float  # expected share of courts booked, 0-1
    adjustments: list[Adjustment] = field(default_factory=list)  # what was applied
    dynamic: list[Adjustment] = field(default_factory=list)  # demand-based, applied or not

    @property
    def breakdown(self) -> list[dict]:
        return [a.as_dict() for a in self.adjustments]


@dataclass
class PricingContext:
    club: Club
    now: datetime
    model: DemandModel
    peak: set
    courts: int
    fills: dict[tuple[date, int], int]
    discount: Adjustment | None


def member_discount(db: Session, user: User | None, on: date | None = None) -> Adjustment | None:
    if user is None or user.role != "member":
        return None
    membership = active_membership(db, user.id, on)
    if membership and membership.plan.court_discount_pct:
        return Adjustment(f"{membership.plan.name} member", -membership.plan.court_discount_pct)
    return None


def fills_for(db: Session, club: Club, days: list[date]) -> dict[tuple[date, int], int]:
    if not days:
        return {}
    start = datetime.combine(min(days), datetime.min.time())
    end = datetime.combine(max(days), datetime.min.time()) + timedelta(days=1)
    out: dict[tuple[date, int], int] = {}
    for start_at in db.scalars(
        select(Booking.start_at).where(
            Booking.club_id == club.id,
            Booking.status.in_(("booked", "completed")),
            Booking.start_at >= start,
            Booking.start_at < end,
        )
    ):
        key = (start_at.date(), start_at.hour)
        out[key] = out.get(key, 0) + 1
    return out


def context(
    db: Session, club: Club, user: User | None, days: list[date] | None = None
) -> PricingContext:
    now = club_now(club.timezone)
    courts = db.scalar(
        select(func.count()).select_from(Court).where(Court.club_id == club.id, Court.is_active)
    )
    return PricingContext(
        club=club,
        now=now,
        model=get_model(db, club, now.date()),
        peak=peak_set(club),
        courts=courts or 1,
        fills=fills_for(db, club, days or []),
        discount=member_discount(db, user, now.date()),
    )


def demand_adjustment(demand: float, club: Club) -> Adjustment | None:
    if demand >= BUSY_FROM:
        share = min(1.0, (demand - BUSY_FROM) / (BUSY_FULL - BUSY_FROM))
        pct = club.max_surge_pct * share
        if pct >= 1:
            return Adjustment(f"Busy hour (~{round(demand * 100)}% of courts booked)", pct)
    elif demand <= QUIET_BELOW:
        share = min(1.0, (QUIET_BELOW - demand) / (QUIET_BELOW - QUIET_FULL))
        pct = club.max_discount_pct * share
        if pct >= 1:
            return Adjustment(f"Quiet hour (~{round(demand * 100)}% of courts booked)", -pct)
    return None


def price_slot(ctx: PricingContext, court: Court, start_at: datetime) -> Quote:
    club = ctx.club
    base = club.base_price
    day, hour = start_at.date(), start_at.hour
    forecast = ctx.model.predict(day, hour, ctx.peak)
    current = ctx.fills.get((day, hour), 0) / ctx.courts
    demand = max(forecast, current)

    dynamic: list[Adjustment] = []
    adj = demand_adjustment(demand, club)
    if adj:
        dynamic.append(adj)
    hours_until = (start_at - ctx.now).total_seconds() / 3600
    if 0 < hours_until <= LAST_MINUTE_HOURS and current < 0.5:
        dynamic.append(Adjustment("Last-minute deal", -LAST_MINUTE_PCT))

    # Total dynamic movement stays inside the owner's surge/discount limits.
    total = sum(a.pct for a in dynamic)
    capped = max(-club.max_discount_pct, min(club.max_surge_pct, total))
    if dynamic and capped != total:
        dynamic.append(Adjustment("Capped by your limits", capped - total))
    suggested = base * (1 + capped / 100)

    # The owner's absolute price limits always apply to the dynamic price.
    bounded = max(club.min_price, min(club.max_price, suggested))
    if dynamic and abs(bounded - suggested) > 0.01:
        dynamic.append(Adjustment("Kept within your price range", (bounded / suggested - 1) * 100))
        suggested = bounded

    apply_dynamic = club.pricing_mode == "on"
    adjustments = list(dynamic) if apply_dynamic else []
    charged = suggested if apply_dynamic else base
    if ctx.discount:
        adjustments.append(ctx.discount)
        charged *= 1 + ctx.discount.pct / 100
        suggested *= 1 + ctx.discount.pct / 100
    return Quote(
        base_price=base,
        price=round(charged, 2),
        suggested=round(suggested, 2),
        demand=round(demand, 3),
        adjustments=adjustments,
        dynamic=dynamic,
    )


def quote(db: Session, club: Club, court: Court, start_at: datetime, user: User | None) -> Quote:
    """Price one slot. For many slots at once, build a context() and call price_slot()."""
    ctx = context(db, club, user, [start_at.date()])
    return price_slot(ctx, court, start_at)
