"""Shared booking, membership and notification helpers used by several routers."""

from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Booking,
    BookingPlayer,
    CheckIn,
    Club,
    Court,
    Membership,
    Notification,
    User,
    WaitlistEntry,
)
from app.schemas import BookingOut, PlayerOut

SLOT = timedelta(hours=1)


def active_membership(db: Session, user_id: int, on: date | None = None) -> Membership | None:
    on = on or date.today()
    return db.scalar(
        select(Membership)
        .options(selectinload(Membership.plan))
        .where(
            Membership.user_id == user_id,
            Membership.status == "active",
            Membership.start_date <= on,
            Membership.end_date >= on,
        )
        .order_by(Membership.end_date.desc())
        .limit(1)
    )


def club_hours(club: Club) -> list[int]:
    return list(range(club.open_hour, club.close_hour))


def validate_slot(club: Club, court: Court | None, start_at: datetime) -> None:
    if court is None or court.club_id != club.id or not court.is_active:
        raise HTTPException(404, "Court not found")
    if start_at.minute != 0 or start_at.hour not in club_hours(club):
        raise HTTPException(400, "Pick a start time on the hour, within opening hours")


def slot_taken(db: Session, court_id: int, start_at: datetime) -> bool:
    return (
        db.scalar(
            select(Booking.id).where(
                Booking.court_id == court_id,
                Booking.start_at == start_at,
                Booking.status.in_(("booked", "completed")),
            )
        )
        is not None
    )


def hold_owner(db: Session, court_id: int, start_at: datetime) -> int | None:
    """The member a freed slot is currently offered to, if any."""
    return db.scalar(
        select(WaitlistEntry.user_id).where(
            WaitlistEntry.status == "offered",
            WaitlistEntry.offer_court_id == court_id,
            WaitlistEntry.offer_start_at == start_at,
        )
    )


def member_busy(db: Session, user_id: int, start_at: datetime) -> bool:
    return (
        db.scalar(
            select(Booking.id)
            .join(BookingPlayer, BookingPlayer.booking_id == Booking.id)
            .where(
                BookingPlayer.user_id == user_id,
                Booking.start_at == start_at,
                Booking.status == "booked",
            )
        )
        is not None
    )


def create_booking(
    db: Session,
    *,
    club: Club,
    court: Court,
    start_at: datetime,
    booker: User | None,
    players: list[User],
    type: str = "casual",
    source: str = "member",
    price: float = 0.0,
    base_price: float = 0.0,
    breakdown: list | None = None,
    coach_id: int | None = None,
    title: str | None = None,
    capacity: int = 4,
) -> Booking:
    validate_slot(club, court, start_at)
    held_for = hold_owner(db, court.id, start_at)
    if held_for is not None and source != "waitlist":
        raise HTTPException(409, "That slot is on hold for someone on the waitlist.")
    if slot_taken(db, court.id, start_at):
        raise HTTPException(
            409, "That court was just booked. Pick another slot or join the waitlist."
        )
    for p in players:
        if member_busy(db, p.id, start_at):
            raise HTTPException(409, f"{p.full_name} already has a booking at that time")
    booking = Booking(
        club_id=club.id,
        court_id=court.id,
        user_id=booker.id if booker else None,
        coach_id=coach_id,
        start_at=start_at,
        end_at=start_at + SLOT,
        type=type,
        source=source,
        price=round(price, 2),
        base_price=round(base_price, 2),
        price_breakdown=breakdown or [],
        title=title,
        capacity=capacity,
    )
    booking.players = [BookingPlayer(user_id=p.id) for p in players]
    db.add(booking)
    db.flush()
    return booking


def load_bookings(db: Session, *conditions) -> list[Booking]:
    return list(
        db.scalars(
            select(Booking)
            .options(
                selectinload(Booking.court),
                selectinload(Booking.user),
                selectinload(Booking.coach),
                selectinload(Booking.players).selectinload(BookingPlayer.user),
            )
            .where(*conditions)
            .order_by(Booking.start_at, Booking.court_id)
        )
    )


def checked_in_booking_ids(db: Session, booking_ids: list[int]) -> set[int]:
    if not booking_ids:
        return set()
    return set(
        db.scalars(select(CheckIn.booking_id).where(CheckIn.booking_id.in_(booking_ids))).all()
    )


def booking_out(b: Booking, checked: set[int] | None = None) -> BookingOut:
    return BookingOut(
        id=b.id,
        court_id=b.court_id,
        court_name=b.court.name,
        user_id=b.user_id,
        booker_name=b.user.full_name if b.user else None,
        coach_id=b.coach_id,
        coach_name=b.coach.user.full_name if b.coach else None,
        start_at=b.start_at,
        end_at=b.end_at,
        type=b.type,
        status=b.status,
        title=b.title,
        capacity=b.capacity,
        base_price=b.base_price,
        price=b.price,
        price_breakdown=b.price_breakdown or [],
        paid=b.paid,
        source=b.source,
        players=[PlayerOut.model_validate(p.user) for p in b.players],
        checked_in=b.id in (checked or set()),
    )


def bookings_out(db: Session, bookings: list[Booking]) -> list[BookingOut]:
    checked = checked_in_booking_ids(db, [b.id for b in bookings])
    return [booking_out(b, checked) for b in bookings]


def notify(
    db: Session,
    user_id: int,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> None:
    db.add(Notification(user_id=user_id, kind=kind, title=title, body=body, link=link))


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time())
    return start, start + timedelta(days=1)
