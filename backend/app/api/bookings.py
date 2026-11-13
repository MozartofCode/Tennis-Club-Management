"""Court availability, bookings and cancellations."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import pricing
from app.ai.pricing import quote
from app.ai.waitlist import active_holds, process_slot
from app.db import get_db
from app.models import Booking, BookingPlayer, Club, Coach, Court, User
from app.schemas import BookingOut
from app.security import STAFF_ROLES, current_club, current_user, require_staff
from app.services.core import (
    booking_out,
    bookings_out,
    club_hours,
    create_booking,
    day_bounds,
    load_bookings,
    notify,
)
from app.timeutil import club_now, utcnow

router = APIRouter(tags=["bookings"])


class Cell(BaseModel):
    court_id: int
    hour: int
    start_at: datetime
    status: str  # free|booked|mine|held|offered|past
    price: float
    base_price: float
    suggested: float
    demand: float
    breakdown: list


class Availability(BaseModel):
    date: date
    hours: list[int]
    courts: list[dict]
    cells: list[Cell]


@router.get("/availability", response_model=Availability)
def availability(
    day: date,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    courts = db.scalars(
        select(Court).where(Court.club_id == club.id, Court.is_active).order_by(Court.id)
    ).all()
    start, end = day_bounds(day)
    booked = load_bookings(
        db,
        Booking.club_id == club.id,
        Booking.start_at >= start,
        Booking.start_at < end,
        Booking.status.in_(("booked", "completed")),
    )
    taken = {(b.court_id, b.start_at.hour): b for b in booked}
    holds = active_holds(db, club, day)
    ctx = pricing.context(db, club, user, [day])
    now = ctx.now
    cells = []
    for court in courts:
        for hour in club_hours(club):
            start_at = datetime.combine(day, datetime.min.time()).replace(hour=hour)
            b = taken.get((court.id, hour))
            if start_at <= now:
                status = "past"
            elif b is not None:
                mine = any(p.user_id == user.id for p in b.players)
                status = "mine" if mine else "booked"
            elif (court.id, start_at) in holds:
                status = "offered" if holds[(court.id, start_at)] == user.id else "held"
            else:
                status = "free"
            q = pricing.price_slot(ctx, court, start_at)
            cells.append(
                Cell(
                    court_id=court.id,
                    hour=hour,
                    start_at=start_at,
                    status=status,
                    price=q.price,
                    base_price=q.base_price,
                    suggested=q.suggested,
                    demand=q.demand,
                    breakdown=q.breakdown,
                )
            )
    return Availability(
        date=day,
        hours=club_hours(club),
        courts=[
            {"id": c.id, "name": c.name, "surface": c.surface, "indoor": c.indoor} for c in courts
        ],
        cells=cells,
    )


class BookingIn(BaseModel):
    court_id: int
    start_at: datetime
    member_id: int | None = None  # staff booking on behalf of a member
    partner_ids: list[int] = []
    type: str = "casual"
    coach_id: int | None = None
    title: str | None = None


@router.post("/bookings", response_model=BookingOut)
def book(
    body: BookingIn,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    is_staff = user.role in STAFF_ROLES
    if body.member_id and not is_staff:
        raise HTTPException(403, "Only staff can book for someone else")
    if body.type in ("clinic",) and not is_staff:
        raise HTTPException(403, "Only staff can schedule clinics")

    booker = db.get(User, body.member_id) if body.member_id else user
    if booker is None or booker.club_id != club.id:
        raise HTTPException(404, "Member not found")
    start_at = body.start_at.replace(tzinfo=None, second=0, microsecond=0)
    if not is_staff and start_at <= club_now(club.timezone):
        raise HTTPException(400, "That time has already passed")

    players = [booker] if booker.role == "member" else []
    for pid in body.partner_ids:
        partner = db.get(User, pid)
        if partner is None or partner.club_id != club.id:
            raise HTTPException(404, "Partner not found")
        if partner not in players:
            players.append(partner)

    coach_id = None
    booking_type = body.type if body.type in ("casual", "lesson", "match", "clinic") else "casual"
    if body.coach_id:
        coach = db.get(Coach, body.coach_id)
        if coach is None or coach.club_id != club.id:
            raise HTTPException(404, "Coach not found")
        coach_id = coach.id
        if booking_type == "casual":
            booking_type = "lesson"

    court = db.get(Court, body.court_id)
    q = quote(db, club, court, start_at, booker) if court else None
    price = q.price if q else 0
    if coach_id:
        price += db.get(Coach, coach_id).hourly_rate
    booking = create_booking(
        db,
        club=club,
        court=court,
        start_at=start_at,
        booker=booker if booker.role == "member" else None,
        players=players,
        type=booking_type,
        source="staff" if is_staff else "member",
        price=price,
        base_price=q.base_price if q else 0,
        breakdown=q.breakdown if q else [],
        coach_id=coach_id,
        title=body.title,
    )
    db.commit()
    return booking_out(load_bookings(db, Booking.id == booking.id)[0])


@router.get("/bookings", response_model=list[BookingOut])
def list_bookings(
    day: date,
    days: int = 1,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    start, _end = day_bounds(day)
    _s, end = day_bounds(date.fromordinal(day.toordinal() + max(1, min(days, 14)) - 1))
    return bookings_out(
        db,
        load_bookings(
            db,
            Booking.club_id == club.id,
            Booking.start_at >= start,
            Booking.start_at < end,
            Booking.status != "cancelled",
        ),
    )


@router.get("/me/bookings", response_model=list[BookingOut])
def my_bookings(
    scope: str = "upcoming",
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    now = club_now(club.timezone)
    mine = select(BookingPlayer.booking_id).where(BookingPlayer.user_id == user.id)
    conditions = [Booking.id.in_(mine)]
    if scope == "upcoming":
        conditions += [Booking.start_at >= now.replace(minute=0), Booking.status == "booked"]
        bookings = load_bookings(db, *conditions)
    else:
        conditions += [Booking.start_at < now]
        bookings = list(reversed(load_bookings(db, *conditions)))[:30]
    return bookings_out(db, bookings)


def _get_booking(db: Session, club: Club, booking_id: int) -> Booking:
    rows = load_bookings(db, Booking.id == booking_id, Booking.club_id == club.id)
    if not rows:
        raise HTTPException(404, "Booking not found")
    return rows[0]


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel(
    booking_id: int,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    booking = _get_booking(db, club, booking_id)
    is_player = any(p.user_id == user.id for p in booking.players)
    if user.role not in STAFF_ROLES and not is_player:
        raise HTTPException(403, "You can only cancel your own bookings")
    if booking.status != "booked":
        raise HTTPException(400, "This booking can't be cancelled")
    if user.role not in STAFF_ROLES and booking.start_at <= club_now(club.timezone):
        raise HTTPException(400, "This booking has already started")
    if booking.type == "clinic" and user.role not in STAFF_ROLES:
        # Leaving a group clinic frees your spot; the clinic itself goes ahead.
        booking.players = [p for p in booking.players if p.user_id != user.id]
        db.commit()
        return booking_out(load_bookings(db, Booking.id == booking.id)[0])
    when = booking.start_at.strftime("%a %b %-d, %-I:%M %p")
    for p in booking.players:
        if p.user_id != user.id:
            notify(
                db,
                p.user_id,
                "booking_cancelled",
                f"Your {booking.court.name} booking on {when} was cancelled",
                f"Cancelled by {user.full_name}.",
                "/app",
            )
    booking.status = "cancelled"
    booking.cancelled_at = utcnow()
    db.flush()
    on_slot_freed(db, club, booking)
    db.commit()
    return booking_out(booking)


def on_slot_freed(db: Session, club: Club, booking: Booking) -> None:
    """Called whenever a booked slot opens up again: offer it to the waitlist."""
    process_slot(db, club, booking.court, booking.start_at)


class BookingPatch(BaseModel):
    paid: bool | None = None
    status: str | None = None  # completed|no_show


@router.patch("/bookings/{booking_id}", response_model=BookingOut)
def update_booking(
    booking_id: int,
    body: BookingPatch,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    booking = _get_booking(db, club, booking_id)
    if body.paid is not None:
        booking.paid = body.paid
    if body.status in ("completed", "no_show", "booked"):
        booking.status = body.status
    db.commit()
    return booking_out(booking)
