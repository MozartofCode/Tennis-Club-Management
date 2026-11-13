"""Club analytics: revenue, utilization, members, and what the AI features did."""

from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.demand import peak_set
from app.db import get_db
from app.models import (
    Booking,
    CheckIn,
    ChurnScore,
    Club,
    Court,
    Match,
    Membership,
    Offer,
    User,
    WaitlistEntry,
)
from app.security import current_club, require_staff
from app.timeutil import club_now, utcnow

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


@router.get("")
def analytics(
    weeks: int = 12,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    weeks = max(4, min(weeks, 26))
    now = club_now(club.timezone)
    today = now.date()
    first_week = _week_start(today) - timedelta(weeks=weeks - 1)
    since = datetime.combine(first_week, datetime.min.time())
    courts = (
        db.scalar(
            select(func.count()).select_from(Court).where(Court.club_id == club.id, Court.is_active)
        )
        or 1
    )
    hours_per_day = club.close_hour - club.open_hour
    peak = peak_set(club)

    bookings = db.execute(
        select(Booking.start_at, Booking.price, Booking.status, Booking.type, Booking.source).where(
            Booking.club_id == club.id, Booking.start_at >= since, Booking.start_at < now
        )
    ).all()
    visits = db.execute(
        select(CheckIn.user_id, CheckIn.created_at).where(
            CheckIn.club_id == club.id, CheckIn.created_at >= since
        )
    ).all()

    # --- Weekly series ---------------------------------------------------------
    series: dict[date, dict] = {}
    for i in range(weeks):
        wk = first_week + timedelta(weeks=i)
        days = min(7, (today - wk).days + 1) if wk <= today else 0
        series[wk] = {
            "week": wk.isoformat(),
            "revenue": 0.0,
            "bookings": 0,
            "capacity": courts * hours_per_day * max(days, 1),
            "visits": 0,
            "active": set(),
        }
    played = [b for b in bookings if b.status in ("completed", "no_show", "booked")]
    for b in played:
        row = series.get(_week_start(b.start_at.date()))
        if row:
            row["revenue"] += b.price
            row["bookings"] += 1
    for user_id, at in visits:
        row = series.get(_week_start(at.date()))
        if row:
            row["visits"] += 1
            row["active"].add(user_id)
    weekly = [
        {
            "week": r["week"],
            "revenue": round(r["revenue"], 2),
            "bookings": r["bookings"],
            "utilization": round(r["bookings"] / r["capacity"], 3),
            "visits": r["visits"],
            "active_members": len(r["active"]),
        }
        for r in series.values()
    ]

    # --- Utilization by hour (last 8 weeks) ------------------------------------
    eight = now - timedelta(weeks=8)
    counts: dict[tuple[bool, int], int] = defaultdict(int)
    for b in played:
        if b.start_at >= eight:
            counts[(b.start_at.weekday() >= 5, b.start_at.hour)] += 1
    weekdays = sum(1 for i in range(56) if (today - timedelta(days=i + 1)).weekday() < 5)
    weekend_days = 56 - weekdays
    by_hour = [
        {
            "hour": h,
            "weekday": round(counts[(False, h)] / (weekdays * courts), 3),
            "weekend": round(counts[(True, h)] / (weekend_days * courts), 3),
            "weekday_peak": (False, h) in peak,
            "weekend_peak": (True, h) in peak,
        }
        for h in range(club.open_hour, club.close_hour)
    ]

    # --- Last 30 days: operations and AI impact ---------------------------------
    month = now - timedelta(days=30)
    recent = [b for b in bookings if b.start_at >= month]
    total = len(recent) or 1
    court_only = [b for b in recent if b.type in ("casual", "match") and b.status != "cancelled"]
    peak_prices = [
        b.price for b in court_only if (b.start_at.weekday() >= 5, b.start_at.hour) in peak
    ]
    off_prices = [
        b.price for b in court_only if (b.start_at.weekday() >= 5, b.start_at.hour) not in peak
    ]
    matches_recent = [b for b in recent if b.source in ("match", "league")]
    utc_month = utcnow() - timedelta(days=30)
    waitlist_filled = db.execute(
        select(func.count(), func.coalesce(func.sum(Booking.price), 0)).where(
            Booking.club_id == club.id,
            Booking.source == "waitlist",
            Booking.created_at >= utc_month,
        )
    ).one()
    offers = dict(
        db.execute(
            select(Offer.status, func.count())
            .where(Offer.club_id == club.id, Offer.created_at >= utc_month)
            .group_by(Offer.status)
        ).all()
    )
    risk = dict(
        db.execute(
            select(ChurnScore.band, func.count())
            .where(ChurnScore.club_id == club.id)
            .group_by(ChurnScore.band)
        ).all()
    )
    members = db.scalar(select(func.count()).where(User.club_id == club.id, User.role == "member"))
    active_memberships = db.scalar(
        select(func.count(func.distinct(Membership.user_id)))
        .join(User, User.id == Membership.user_id)
        .where(
            User.club_id == club.id,
            Membership.status == "active",
            Membership.start_date <= today,
            Membership.end_date >= today,
        )
    )
    ended = db.scalars(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            User.club_id == club.id,
            Membership.end_date >= today - timedelta(days=30),
            Membership.end_date < today,
        )
    ).all()
    renewed = 0
    for m in ended:
        nxt = db.scalar(
            select(Membership.id).where(
                Membership.user_id == m.user_id,
                Membership.start_date > m.end_date,
                Membership.start_date <= m.end_date + timedelta(days=7),
            )
        )
        renewed += bool(nxt)
    new_members = db.scalar(
        select(func.count()).where(
            User.club_id == club.id, User.role == "member", User.created_at >= utc_month
        )
    )
    waiting = db.scalar(
        select(func.count()).where(
            WaitlistEntry.club_id == club.id, WaitlistEntry.status.in_(("waiting", "offered"))
        )
    )
    league_week = db.scalar(
        select(func.count()).where(
            Match.club_id == club.id, Match.source == "league", Match.created_at >= utc_month
        )
    )

    def avg(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 2) if xs else 0.0

    return {
        "weekly": weekly,
        "by_hour": by_hour,
        "last_30": {
            "revenue": round(sum(b.price for b in recent if b.status != "cancelled"), 2),
            "bookings": len(recent),
            "cancel_rate": round(sum(1 for b in recent if b.status == "cancelled") / total, 3),
            "no_show_rate": round(sum(1 for b in recent if b.status == "no_show") / total, 3),
            "avg_peak_price": avg(peak_prices),
            "avg_offpeak_price": avg(off_prices),
            "lesson_share": round(
                sum(1 for b in recent if b.type in ("lesson", "clinic")) / total, 3
            ),
        },
        "members": {
            "total": members,
            "active_memberships": active_memberships,
            "new_30d": new_members,
            "renewal_rate_30d": round(renewed / len(ended), 3) if ended else None,
            "lapsed_30d": len(ended) - renewed,
        },
        "ai": {
            "pricing_mode": club.pricing_mode,
            "waitlist_refills_30d": waitlist_filled[0],
            "waitlist_revenue_30d": round(float(waitlist_filled[1]), 2),
            "waiting_now": waiting,
            "match_bookings_30d": len(matches_recent),
            "match_offpeak_share": round(
                sum(
                    1
                    for b in matches_recent
                    if (b.start_at.weekday() >= 5, b.start_at.hour) not in peak
                )
                / len(matches_recent),
                3,
            )
            if matches_recent
            else None,
            "league_matches_30d": league_week,
            "offers_30d": offers,
            "risk": risk,
        },
    }
