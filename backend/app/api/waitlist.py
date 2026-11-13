"""Waitlist: members join for full hours; freed slots are offered automatically."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.ai import waitlist
from app.db import get_db
from app.models import Booking, Club, Court, User, WaitlistEntry
from app.schemas import BookingOut
from app.security import STAFF_ROLES, current_club, current_user, require_staff
from app.services.core import booking_out, load_bookings
from app.timeutil import club_now, utcnow

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


class EntryOut(BaseModel):
    id: int
    user_id: int
    member_name: str
    date: date
    start_hour: int
    end_hour: int
    court_id: int | None
    status: str
    priority_score: float
    priority_reasons: list[str]
    offer_court_name: str | None
    offer_start_at: datetime | None
    offer_price: float | None
    offer_expires_at: datetime | None
    created_at: datetime


def entry_out(e: WaitlistEntry) -> EntryOut:
    return EntryOut(
        id=e.id,
        user_id=e.user_id,
        member_name=e.user.full_name,
        date=e.date,
        start_hour=e.start_hour,
        end_hour=e.end_hour,
        court_id=e.court_id,
        status=e.status,
        priority_score=e.priority_score,
        priority_reasons=e.priority_reasons or [],
        offer_court_name=e.offer_court.name if e.offer_court else None,
        offer_start_at=e.offer_start_at,
        offer_price=e.offer_price,
        offer_expires_at=e.offer_expires_at,
        created_at=e.created_at,
    )


class JoinIn(BaseModel):
    date: date
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=0, le=23)
    court_id: int | None = None


class JoinOut(BaseModel):
    entry: EntryOut
    position: int
    alternatives: list[dict]


@router.post("", response_model=JoinOut)
def join(
    body: JoinIn,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    if user.role != "member":
        raise HTTPException(403, "Only members can join the waitlist")
    now = club_now(club.timezone)
    if body.end_hour < body.start_hour:
        raise HTTPException(400, "The end of your window must be after the start")
    if body.start_hour < club.open_hour or body.end_hour >= club.close_hour:
        raise HTTPException(400, "Pick hours within opening times")
    if body.date < now.date() or (body.date == now.date() and body.end_hour <= now.hour):
        raise HTTPException(400, "That time has already passed")
    if body.court_id:
        court = db.get(Court, body.court_id)
        if court is None or court.club_id != club.id:
            raise HTTPException(404, "Court not found")
    duplicate = db.scalar(
        select(WaitlistEntry.id).where(
            WaitlistEntry.user_id == user.id,
            WaitlistEntry.date == body.date,
            WaitlistEntry.status.in_(("waiting", "offered")),
            WaitlistEntry.start_hour <= body.end_hour,
            WaitlistEntry.end_hour >= body.start_hour,
        )
    )
    if duplicate:
        raise HTTPException(409, "You're already on the waitlist for that time")
    entry = WaitlistEntry(club_id=club.id, user_id=user.id, **body.model_dump())
    db.add(entry)
    db.flush()
    entry.priority_score, entry.priority_reasons = waitlist.priority(
        db, entry, None, None, utcnow()
    )
    ahead = db.scalar(
        select(func.count()).where(
            WaitlistEntry.club_id == club.id,
            WaitlistEntry.status == "waiting",
            WaitlistEntry.date == body.date,
            WaitlistEntry.start_hour <= body.end_hour,
            WaitlistEntry.end_hour >= body.start_hour,
            WaitlistEntry.id != entry.id,
            WaitlistEntry.priority_score > entry.priority_score,
        )
    )
    alternatives = waitlist.alternatives(db, club, user, body.date, body.start_hour)
    db.commit()
    db.refresh(entry)
    return JoinOut(entry=entry_out(entry), position=(ahead or 0) + 1, alternatives=alternatives)


def _load(db: Session, *conditions) -> list[WaitlistEntry]:
    return list(
        db.scalars(
            select(WaitlistEntry)
            .options(selectinload(WaitlistEntry.user), selectinload(WaitlistEntry.offer_court))
            .where(*conditions)
            .order_by(WaitlistEntry.date, WaitlistEntry.start_hour, WaitlistEntry.created_at)
        )
    )


@router.get("/mine", response_model=list[EntryOut])
def mine(
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    today = club_now(club.timezone).date()
    return [
        entry_out(e)
        for e in _load(
            db,
            WaitlistEntry.user_id == user.id,
            WaitlistEntry.date >= today,
            WaitlistEntry.status.in_(("waiting", "offered")),
        )
    ]


class QueueOut(BaseModel):
    entries: list[EntryOut]
    filled_30d: int
    offers_30d: int
    expired_30d: int


@router.get("", response_model=QueueOut)
def queue(
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    now = club_now(club.timezone)
    entries = _load(
        db,
        WaitlistEntry.club_id == club.id,
        WaitlistEntry.date >= now.date(),
        WaitlistEntry.status.in_(("waiting", "offered")),
    )
    now_utc = utcnow()
    for e in entries:
        if e.status == "waiting":
            hour = e.start_hour if e.start_hour == e.end_hour else None
            e.priority_score, e.priority_reasons = waitlist.priority(db, e, hour, None, now_utc)
    db.commit()
    since = now_utc - timedelta(days=30)
    resolved = db.execute(
        select(WaitlistEntry.status, func.count())
        .where(WaitlistEntry.club_id == club.id, WaitlistEntry.resolved_at >= since)
        .group_by(WaitlistEntry.status)
    ).all()
    counts = dict(resolved)
    filled = db.scalar(
        select(func.count()).where(
            Booking.club_id == club.id, Booking.source == "waitlist", Booking.created_at >= since
        )
    )
    entries.sort(key=lambda e: (e.date, e.start_hour, -e.priority_score))
    return QueueOut(
        entries=[entry_out(e) for e in entries],
        filled_30d=filled or 0,
        offers_30d=sum(counts.get(s, 0) for s in ("accepted", "declined", "expired")),
        expired_30d=counts.get("expired", 0),
    )


def _own_entry(db: Session, user: User, entry_id: int) -> WaitlistEntry:
    entry = db.get(WaitlistEntry, entry_id)
    if entry is None or entry.club_id != user.club_id:
        raise HTTPException(404, "Waitlist entry not found")
    if entry.user_id != user.id and user.role not in STAFF_ROLES:
        raise HTTPException(404, "Waitlist entry not found")
    return entry


@router.post("/{entry_id}/accept", response_model=BookingOut)
def accept(
    entry_id: int,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    entry = _own_entry(db, user, entry_id)
    booking = waitlist.accept(db, club, entry)
    db.commit()
    return booking_out(load_bookings(db, Booking.id == booking.id)[0])


@router.post("/{entry_id}/decline")
def decline(
    entry_id: int,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    entry = _own_entry(db, user, entry_id)
    if entry.status != "offered":
        raise HTTPException(400, "There's no open offer to decline")
    waitlist.release(db, club, entry, "declined")
    db.commit()
    return {"ok": True}


@router.delete("/{entry_id}")
def leave(
    entry_id: int,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    entry = _own_entry(db, user, entry_id)
    if entry.status == "offered":
        waitlist.release(db, club, entry, "left")
    elif entry.status == "waiting":
        entry.status = "left"
        entry.resolved_at = utcnow()
    db.commit()
    return {"ok": True}


@router.get("/alternatives")
def alternatives(
    day: date,
    hour: int,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    return waitlist.alternatives(db, club, user, day, hour)
