"""QR check-in at the front desk kiosk, and the check-in log."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Booking, BookingPlayer, CheckIn, Club, User
from app.schemas import BookingOut, CheckInOut
from app.security import current_club, require_staff
from app.services.core import active_membership, booking_out, day_bounds, load_bookings
from app.timeutil import club_now

router = APIRouter(prefix="/checkin", tags=["check-in"])

# A booking counts as "now" from an hour before it starts until it ends.
EARLY = timedelta(minutes=60)


class ScanIn(BaseModel):
    token: str


class ManualIn(BaseModel):
    user_id: int


class ScanResult(BaseModel):
    status: str  # welcome|no_booking|already
    member_name: str
    member_id: int
    skill_level: float
    membership: str | None
    membership_ok: bool
    booking: BookingOut | None
    message: str


def _check_in(db: Session, club: Club, user: User, method: str) -> ScanResult:
    now = club_now(club.timezone)
    mine = select(BookingPlayer.booking_id).where(BookingPlayer.user_id == user.id)
    current = load_bookings(
        db,
        Booking.id.in_(mine),
        Booking.status == "booked",
        Booking.start_at <= now + EARLY,
        Booking.end_at > now,
    )
    booking = current[0] if current else None
    membership = active_membership(db, user.id, now.date())
    first = user.full_name.split(" ")[0]

    recent = db.scalar(
        select(CheckIn).where(
            CheckIn.user_id == user.id, CheckIn.created_at >= now - timedelta(minutes=30)
        )
    )
    if recent is not None:
        status, message = "already", f"{first} is already checked in."
    else:
        db.add(
            CheckIn(
                club_id=club.id,
                user_id=user.id,
                booking_id=booking.id if booking else None,
                method=method,
                created_at=now,
            )
        )
        db.commit()
        if booking:
            when = booking.start_at.strftime("%-I:%M %p")
            status, message = "welcome", f"Welcome, {first}! {booking.court.name} at {when}."
        else:
            status, message = "no_booking", f"Welcome, {first}. No court booked right now."

    return ScanResult(
        status=status,
        member_name=user.full_name,
        member_id=user.id,
        skill_level=user.skill_level,
        membership=membership.plan.name if membership else None,
        membership_ok=membership is not None,
        booking=booking_out(booking, {booking.id}) if booking else None,
        message=message,
    )


@router.post("/scan", response_model=ScanResult)
def scan(
    body: ScanIn,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.qr_token == body.token.strip()))
    if user is None or user.club_id != club.id or not user.is_active:
        raise HTTPException(404, "This code isn't recognised. Ask the member to refresh their QR.")
    return _check_in(db, club, user, "qr")


@router.post("/manual", response_model=ScanResult)
def manual(
    body: ManualIn,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    user = db.get(User, body.user_id)
    if user is None or user.club_id != club.id:
        raise HTTPException(404, "Member not found")
    return _check_in(db, club, user, "manual")


@router.get("", response_model=list[CheckInOut])
def log(
    day: date | None = None,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    day = day or club_now(club.timezone).date()
    start, end = day_bounds(day)
    rows = db.scalars(
        select(CheckIn)
        .options(selectinload(CheckIn.user), selectinload(CheckIn.booking))
        .where(CheckIn.club_id == club.id, CheckIn.created_at >= start, CheckIn.created_at < end)
        .order_by(CheckIn.created_at.desc())
    ).all()
    return [
        CheckInOut(
            id=c.id,
            user_id=c.user_id,
            member_name=c.user.full_name,
            booking_id=c.booking_id,
            court_name=c.booking.court.name if c.booking else None,
            method=c.method,
            created_at=c.created_at,
        )
        for c in rows
    ]
