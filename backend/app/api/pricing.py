"""Pricing dashboard: next week's forecast and prices, and a revenue simulation."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import pricing
from app.ai.demand import get_model, utilization_history
from app.db import get_db
from app.models import Club, Court, User
from app.security import current_club, require_staff
from app.services.core import club_hours

router = APIRouter(prefix="/pricing", tags=["pricing"])


class Slot(BaseModel):
    date: date
    hour: int
    forecast: float
    booked: float
    price: float
    suggested: float
    reasons: list[dict]


class WeekOut(BaseModel):
    mode: str
    base_price: float
    days: list[date]
    hours: list[int]
    slots: list[Slot]
    model: dict


@router.get("/week", response_model=WeekOut)
def week(
    start: date | None = None,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    ctx = pricing.context(db, club, None)
    start = start or ctx.now.date()
    days = [start + timedelta(days=i) for i in range(7)]
    ctx.fills = pricing.fills_for(db, club, days)
    court = db.scalars(select(Court).where(Court.club_id == club.id, Court.is_active)).first()
    slots = []
    for d in days:
        for h in club_hours(club):
            start_at = datetime.combine(d, datetime.min.time()).replace(hour=h)
            q = pricing.price_slot(ctx, court, start_at) if court else None
            slots.append(
                Slot(
                    date=d,
                    hour=h,
                    forecast=round(ctx.model.predict(d, h, ctx.peak), 3),
                    booked=round(ctx.fills.get((d, h), 0) / ctx.courts, 3),
                    price=q.price if q else club.base_price,
                    suggested=q.suggested if q else club.base_price,
                    reasons=[a.as_dict() for a in q.dynamic] if q else [],
                )
            )
    m = ctx.model
    return WeekOut(
        mode=club.pricing_mode,
        base_price=club.base_price,
        days=days,
        hours=club_hours(club),
        slots=slots,
        model={
            "kind": "gradient boosting" if m.model is not None else "recent averages",
            "training_rows": m.rows,
            "mae": round(m.mae, 3) if m.mae is not None else None,
        },
    )


class SimOut(BaseModel):
    weeks: int
    elasticity: float
    unmet_at_full: float
    flat_revenue: float
    dynamic_revenue: float
    flat_hours: float
    dynamic_hours: float
    peak_util_flat: float
    peak_util_dynamic: float
    offpeak_util_flat: float
    offpeak_util_dynamic: float
    by_hour: list[dict]


@router.get("/simulate", response_model=SimOut)
def simulate(
    weeks: int = 8,
    elasticity: float = 0.6,
    unmet: float = 0.15,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    """What would the last few weeks have earned with dynamic pricing, on the same demand?

    Simple, stated assumptions instead of a black box:
    - demand responds to price with constant elasticity (bookings x (p1/p0)^-elasticity)
    - full hours had `unmet` extra demand that got turned away (people who couldn't book)
    - an hour can never exceed the number of courts
    Prices are the standard (non-member) rates.
    """
    ctx = pricing.context(db, club, None)
    today = ctx.now.date()
    since = today - timedelta(weeks=max(1, min(weeks, 12)))
    history = utilization_history(db, club, since, today)
    model = get_model(db, club, today)
    courts = ctx.courts
    peak = ctx.peak
    p0 = club.base_price
    flat_rev = dyn_rev = flat_hours = dyn_hours = 0.0
    buckets = {"peak": [0.0, 0.0, 0], "off": [0.0, 0.0, 0]}
    hourly: dict[int, list[float]] = {}
    for (d, h), util in history.items():
        booked = util * courts
        demand = booked * (1 + unmet) if util >= 0.999 else booked
        forecast = model.predict(d, h, peak)
        adj = pricing.demand_adjustment(forecast, club)
        pct = adj.pct if adj else 0.0
        p1 = max(club.min_price, min(club.max_price, p0 * (1 + pct / 100)))
        dyn_booked = min(courts, demand * (p1 / p0) ** (-elasticity))
        flat_rev += booked * p0
        dyn_rev += dyn_booked * p1
        flat_hours += booked
        dyn_hours += dyn_booked
        key = "peak" if (d.weekday() >= 5, h) in peak else "off"
        buckets[key][0] += booked / courts
        buckets[key][1] += dyn_booked / courts
        buckets[key][2] += 1
        hourly.setdefault(h, [0.0, 0.0, 0])
        hourly[h][0] += booked / courts
        hourly[h][1] += dyn_booked / courts
        hourly[h][2] += 1

    def avg(k: str, i: int) -> float:
        n = buckets[k][2]
        return round(buckets[k][i] / n, 3) if n else 0.0

    return SimOut(
        weeks=weeks,
        elasticity=elasticity,
        unmet_at_full=unmet,
        flat_revenue=round(flat_rev, 2),
        dynamic_revenue=round(dyn_rev, 2),
        flat_hours=round(flat_hours, 1),
        dynamic_hours=round(dyn_hours, 1),
        peak_util_flat=avg("peak", 0),
        peak_util_dynamic=avg("peak", 1),
        offpeak_util_flat=avg("off", 0),
        offpeak_util_dynamic=avg("off", 1),
        by_hour=[
            {"hour": h, "flat": round(v[0] / v[2], 3), "dynamic": round(v[1] / v[2], 3)}
            for h, v in sorted(hourly.items())
        ],
    )
