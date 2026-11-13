"""Self-running waitlist.

When a booked slot frees up, the best-placed waiting member gets it on hold
for a short time (club.waitlist_hold_minutes). They accept with one tap, or
the hold expires and the next member is offered it. Nobody has to phone
around.

Who goes first is a transparent score; every part of it is recorded as a
reason the front desk can read:
  - membership tier (Premium before Plus before Basic)
  - how long they have been waiting
  - churn risk: members at risk of leaving get a boost, so the waitlist also
    works as a retention tool
  - fairness: members who recently got offers rank a little lower
  - exact match: the freed hour is exactly the one they asked for
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.ai import pricing
from app.models import Booking, ChurnScore, Club, Court, User, WaitlistEntry
from app.services.core import (
    active_membership,
    create_booking,
    member_busy,
    notify,
    slot_taken,
)
from app.services.email import send_email
from app.timeutil import club_now, utcnow

TIER_POINTS = 15
WAIT_POINTS_PER_HOUR = 2
WAIT_POINTS_MAX = 20
CHURN_POINTS = {"high": 12, "medium": 6}
RECENT_OFFER_PENALTY = 8
EXACT_MATCH_POINTS = 5
MIN_NOTICE = timedelta(minutes=20)  # don't offer slots that start sooner than this


def active_holds(db: Session, club: Club, day: date) -> dict[tuple[int, datetime], int]:
    start = datetime.combine(day, datetime.min.time())
    rows = db.execute(
        select(
            WaitlistEntry.offer_court_id, WaitlistEntry.offer_start_at, WaitlistEntry.user_id
        ).where(
            WaitlistEntry.club_id == club.id,
            WaitlistEntry.status == "offered",
            WaitlistEntry.offer_start_at >= start,
            WaitlistEntry.offer_start_at < start + timedelta(days=1),
        )
    ).all()
    return {(court_id, start_at): user_id for court_id, start_at, user_id in rows}


def priority(
    db: Session, entry: WaitlistEntry, slot_hour: int | None, slot_court: int | None, now_utc
) -> tuple[float, list[str]]:
    score, reasons = 0.0, []
    membership = active_membership(db, entry.user_id, entry.date)
    if membership and membership.plan.priority:
        pts = TIER_POINTS * membership.plan.priority
        score += pts
        reasons.append(f"{membership.plan.name} member (+{pts})")

    hours = (now_utc - entry.created_at).total_seconds() / 3600
    pts = min(WAIT_POINTS_MAX, round(hours * WAIT_POINTS_PER_HOUR, 1))
    if pts >= 1:
        score += pts
        reasons.append(f"Waiting {_ago(hours)} (+{pts:g})")

    churn = db.scalar(
        select(ChurnScore)
        .where(ChurnScore.user_id == entry.user_id)
        .order_by(ChurnScore.computed_at.desc())
        .limit(1)
    )
    if churn and churn.band in CHURN_POINTS:
        pts = CHURN_POINTS[churn.band]
        score += pts
        reasons.append(f"{churn.band.title()} churn risk: retention boost (+{pts})")

    recent = db.scalar(
        select(func.coalesce(func.sum(WaitlistEntry.offers_received), 0)).where(
            WaitlistEntry.user_id == entry.user_id,
            WaitlistEntry.id != entry.id,
            WaitlistEntry.created_at >= now_utc - timedelta(days=30),
        )
    )
    if recent:
        pts = RECENT_OFFER_PENALTY * min(recent, 3)
        score -= pts
        reasons.append(f"Got {recent} offer{'s' if recent > 1 else ''} recently (-{pts})")

    if slot_hour is not None and slot_hour == entry.start_hour == entry.end_hour:
        if entry.court_id in (None, slot_court):
            score += EXACT_MATCH_POINTS
            reasons.append(f"Exact time they asked for (+{EXACT_MATCH_POINTS})")
    return round(score, 1), reasons


def _ago(hours: float) -> str:
    if hours < 1:
        return f"{max(1, round(hours * 60))} min"
    if hours < 48:
        return f"{round(hours)}h"
    return f"{round(hours / 24)} days"


def candidates(db: Session, club: Club, court: Court, start_at: datetime) -> list[WaitlistEntry]:
    rows = db.scalars(
        select(WaitlistEntry)
        .options(selectinload(WaitlistEntry.user))
        .where(
            WaitlistEntry.club_id == club.id,
            WaitlistEntry.status == "waiting",
            WaitlistEntry.date == start_at.date(),
            WaitlistEntry.start_hour <= start_at.hour,
            WaitlistEntry.end_hour >= start_at.hour,
        )
    ).all()
    return [
        e
        for e in rows
        if e.court_id in (None, court.id) and not member_busy(db, e.user_id, start_at)
    ]


def ranked(db: Session, club: Club, court: Court, start_at: datetime) -> list[WaitlistEntry]:
    now_utc = utcnow()
    entries = candidates(db, club, court, start_at)
    for e in entries:
        e.priority_score, e.priority_reasons = priority(db, e, start_at.hour, court.id, now_utc)
    return sorted(entries, key=lambda e: (-e.priority_score, e.created_at))


def process_slot(db: Session, club: Club, court: Court, start_at: datetime) -> WaitlistEntry | None:
    """Offer a free slot to the best-placed waiting member. Returns the entry offered."""
    now = club_now(club.timezone)
    if start_at - now < MIN_NOTICE or slot_taken(db, court.id, start_at):
        return None
    already = db.scalar(
        select(WaitlistEntry.id).where(
            WaitlistEntry.status == "offered",
            WaitlistEntry.offer_court_id == court.id,
            WaitlistEntry.offer_start_at == start_at,
        )
    )
    if already:
        return None
    queue = ranked(db, club, court, start_at)
    if not queue:
        return None
    entry = queue[0]
    user = entry.user
    q = pricing.quote(db, club, court, start_at, user)
    hold_until = min(
        now + timedelta(minutes=club.waitlist_hold_minutes), start_at - timedelta(minutes=10)
    )
    entry.status = "offered"
    entry.offer_court_id = court.id
    entry.offer_start_at = start_at
    entry.offer_price = q.price
    entry.offer_expires_at = hold_until
    entry.offers_received += 1
    when = start_at.strftime("%a %b %-d, %-I:%M %p")
    minutes = max(1, round((hold_until - now).total_seconds() / 60))
    notify(
        db,
        user.id,
        "waitlist_offer",
        f"A court opened up: {court.name}, {when}",
        f"It's held for you for {minutes} minutes at ${q.price:.0f}. Tap to book it.",
        "/app",
    )
    send_email(
        user.email,
        f"Court available: {when}",
        f"Hi {user.full_name.split(' ')[0]},\n\n{court.name} on {when} just opened up and is "
        f"held for you for {minutes} minutes (${q.price:.0f}). Open CourtIQ to book it.\n",
    )
    db.flush()
    return entry


def accept(db: Session, club: Club, entry: WaitlistEntry) -> Booking:
    from fastapi import HTTPException

    now = club_now(club.timezone)
    if entry.status != "offered" or entry.offer_expires_at is None:
        raise HTTPException(400, "There's no open offer on this waitlist entry")
    if entry.offer_expires_at < now:
        raise HTTPException(400, "Sorry, this offer has expired")
    court = db.get(Court, entry.offer_court_id)
    user = db.get(User, entry.user_id)
    q = pricing.quote(db, club, court, entry.offer_start_at, user)
    booking = create_booking(
        db,
        club=club,
        court=court,
        start_at=entry.offer_start_at,
        booker=user,
        players=[user],
        source="waitlist",
        price=entry.offer_price if entry.offer_price is not None else q.price,
        base_price=q.base_price,
        breakdown=q.breakdown + [{"label": "Filled from waitlist", "pct": 0}],
    )
    entry.status = "accepted"
    entry.booking_id = booking.id
    entry.resolved_at = utcnow()
    db.flush()
    return booking


def release(db: Session, club: Club, entry: WaitlistEntry, status: str) -> None:
    """Close an offer (declined or expired) and pass the slot to the next person."""
    court = db.get(Court, entry.offer_court_id)
    start_at = entry.offer_start_at
    entry.status = status
    entry.resolved_at = utcnow()
    db.flush()
    if court is not None and start_at is not None:
        process_slot(db, club, court, start_at)


def sweep(db: Session, club: Club) -> dict:
    """Expire overdue holds, close entries whose time has passed, and fill any free slots."""
    now = club_now(club.timezone)
    expired = 0
    for entry in db.scalars(
        select(WaitlistEntry).where(
            WaitlistEntry.club_id == club.id,
            WaitlistEntry.status == "offered",
            WaitlistEntry.offer_expires_at < now,
        )
    ).all():
        notify(
            db,
            entry.user_id,
            "waitlist_expired",
            "Your court offer expired",
            "We passed it to the next person. You can join the waitlist again any time.",
        )
        release(db, club, entry, "expired")
        expired += 1

    stale = db.scalars(
        select(WaitlistEntry).where(
            WaitlistEntry.club_id == club.id,
            WaitlistEntry.status == "waiting",
            WaitlistEntry.date <= now.date(),
        )
    ).all()
    for entry in stale:
        if entry.date < now.date() or entry.end_hour <= now.hour:
            entry.status = "expired"
            entry.resolved_at = utcnow()

    # Free slots that waiting members would take (e.g. a court reopened by staff).
    offered = 0
    courts = db.scalars(select(Court).where(Court.club_id == club.id, Court.is_active)).all()
    waiting = db.scalars(
        select(WaitlistEntry).where(
            WaitlistEntry.club_id == club.id,
            WaitlistEntry.status == "waiting",
            WaitlistEntry.date >= now.date(),
        )
    ).all()
    slots = {(e.date, h) for e in waiting for h in range(e.start_hour, e.end_hour + 1)}
    for day, hour in sorted(slots):
        start_at = datetime.combine(day, datetime.min.time()).replace(hour=hour)
        for court in courts:
            if process_slot(db, club, court, start_at):
                offered += 1
    db.commit()
    return {"expired": expired, "offered": offered}


def alternatives(
    db: Session, club: Club, user: User, day: date, hour: int, limit: int = 4
) -> list[dict]:
    """Nearby open slots to suggest when the hour someone wants is full."""
    ctx = pricing.context(db, club, user, [day + timedelta(days=d) for d in range(0, 8)])
    courts = db.scalars(select(Court).where(Court.club_id == club.id, Court.is_active)).all()
    options: list[tuple[int, dict]] = []
    tries = [(0, h) for h in (hour - 1, hour + 1, hour - 2, hour + 2)] + [(7, hour), (1, hour)]
    for offset, h in tries:
        if h < club.open_hour or h >= club.close_hour:
            continue
        d = day + timedelta(days=offset)
        start_at = datetime.combine(d, datetime.min.time()).replace(hour=h)
        if start_at <= ctx.now:
            continue
        for court in courts:
            if not slot_taken(db, court.id, start_at):
                q = pricing.price_slot(ctx, court, start_at)
                distance = abs(h - hour) + offset * 3
                options.append(
                    (
                        distance,
                        {
                            "court_id": court.id,
                            "court_name": court.name,
                            "start_at": start_at.isoformat(),
                            "price": q.price,
                            "cheaper": any(a.pct < 0 for a in q.dynamic)
                            and club.pricing_mode == "on",
                        },
                    )
                )
                break
    options.sort(key=lambda o: (o[0], o[1]["price"]))
    return [o for _, o in options[:limit]]
