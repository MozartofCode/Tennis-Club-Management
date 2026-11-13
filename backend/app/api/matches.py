"""Find a match, invites with automatic court booking, results, league and clinics."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.ai import matchmaking
from app.db import get_db
from app.models import Booking, BookingPlayer, Club, Coach, Court, Match, User
from app.schemas import BookingOut
from app.security import current_club, current_user, require_roles, require_staff
from app.services.core import booking_out, bookings_out, create_booking, load_bookings, notify
from app.timeutil import club_now

router = APIRouter(tags=["matches"])
require_member = require_roles("member")


class SuggestionOut(BaseModel):
    user_id: int
    full_name: str
    skill_level: float
    play_style: str | None
    score: float
    reasons: list[str]
    slots: list[dict]


@router.get("/matches/suggestions", response_model=list[SuggestionOut])
def suggestions(
    user: User = Depends(require_member),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    out = []
    for c in matchmaking.suggest(db, club, user, limit=5):
        out.append(
            SuggestionOut(
                user_id=c.user.id,
                full_name=c.user.full_name,
                skill_level=c.user.skill_level,
                play_style=c.user.play_style,
                score=c.score,
                reasons=c.reasons,
                slots=matchmaking.slot_options(db, club, user, c.user, limit=3),
            )
        )
    return out


class MatchOut(BaseModel):
    id: int
    status: str
    source: str
    requester_id: int
    requester_name: str
    opponent_id: int
    opponent_name: str
    proposed_start: datetime
    court_name: str | None
    booking_id: int | None
    reasons: list[str]
    winner_id: int | None
    score_text: str | None


def match_out(m: Match) -> MatchOut:
    return MatchOut(
        id=m.id,
        status=m.status,
        source=m.source,
        requester_id=m.requester_id,
        requester_name=m.requester.full_name,
        opponent_id=m.opponent_id,
        opponent_name=m.opponent.full_name,
        proposed_start=m.proposed_start,
        court_name=m.court.name if m.court else None,
        booking_id=m.booking_id,
        reasons=m.match_reasons or [],
        winner_id=m.winner_id,
        score_text=m.score_text,
    )


def _load(db: Session, *conditions) -> list[Match]:
    return list(
        db.scalars(
            select(Match)
            .options(
                selectinload(Match.requester),
                selectinload(Match.opponent),
                selectinload(Match.court),
            )
            .where(*conditions)
            .order_by(Match.proposed_start)
        )
    )


class InviteIn(BaseModel):
    opponent_id: int
    start_at: datetime
    court_id: int | None = None


@router.post("/matches", response_model=MatchOut)
def create_invite(
    body: InviteIn,
    user: User = Depends(require_member),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    opponent = db.get(User, body.opponent_id)
    if opponent is None:
        raise HTTPException(404, "Player not found")
    open_invite = db.scalar(
        select(Match.id).where(
            Match.requester_id == user.id,
            Match.opponent_id == opponent.id,
            Match.status == "pending",
        )
    )
    if open_invite:
        raise HTTPException(409, "You already have an open invite with this player")
    cand = next(
        (c for c in matchmaking.suggest(db, club, user, 50) if c.user.id == opponent.id), None
    )
    m = matchmaking.invite(
        db,
        club,
        user,
        opponent,
        body.start_at.replace(tzinfo=None, minute=0, second=0, microsecond=0),
        body.court_id,
        cand.score if cand else 0,
        cand.reasons if cand else [],
    )
    db.commit()
    return match_out(_load(db, Match.id == m.id)[0])


class MyMatches(BaseModel):
    incoming: list[MatchOut]
    outgoing: list[MatchOut]
    upcoming: list[MatchOut]
    to_report: list[MatchOut]
    results: list[MatchOut]


@router.get("/matches/mine", response_model=MyMatches)
def mine(
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    now = club_now(club.timezone)
    rows = _load(db, or_(Match.requester_id == user.id, Match.opponent_id == user.id))
    pending = [m for m in rows if m.status == "pending" and m.proposed_start > now]
    return MyMatches(
        incoming=[
            match_out(m)
            for m in pending
            if m.opponent_id == user.id or (m.source == "league" and m.requester_id == user.id)
        ],
        outgoing=[
            match_out(m) for m in pending if m.requester_id == user.id and m.source != "league"
        ],
        upcoming=[match_out(m) for m in rows if m.status == "accepted" and m.proposed_start > now],
        to_report=[
            match_out(m) for m in rows if m.status == "accepted" and m.proposed_start <= now
        ],
        results=[match_out(m) for m in reversed(rows) if m.status == "completed"][:10],
    )


def _own(db: Session, user: User, match_id: int) -> Match:
    rows = _load(db, Match.id == match_id)
    if not rows or user.id not in (rows[0].requester_id, rows[0].opponent_id):
        raise HTTPException(404, "Match not found")
    return rows[0]


@router.post("/matches/{match_id}/accept", response_model=MatchOut)
def accept(
    match_id: int,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    m = _own(db, user, match_id)
    matchmaking.accept(db, club, m, user)
    db.commit()
    return match_out(_load(db, Match.id == m.id)[0])


@router.post("/matches/{match_id}/decline", response_model=MatchOut)
def decline(match_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own(db, user, match_id)
    if m.status != "pending":
        raise HTTPException(400, "This invite is no longer open")
    m.status = "declined"
    other = m.requester_id if user.id == m.opponent_id else m.opponent_id
    notify(
        db, other, "match_declined", f"{user.full_name} can't make that match", None, "/app/matches"
    )
    db.commit()
    return match_out(m)


class ResultIn(BaseModel):
    winner_id: int
    score_text: str = Field(default="", max_length=40)


@router.post("/matches/{match_id}/result", response_model=MatchOut)
def result(
    match_id: int,
    body: ResultIn,
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    m = _own(db, user, match_id)
    if m.status != "accepted" or m.proposed_start > club_now(club.timezone):
        raise HTTPException(400, "You can report the result after the match")
    if body.winner_id not in (m.requester_id, m.opponent_id):
        raise HTTPException(400, "The winner must be one of the two players")
    loser_id = m.opponent_id if body.winner_id == m.requester_id else m.requester_id
    matchmaking.record_result(
        db, m, db.get(User, body.winner_id), db.get(User, loser_id), body.score_text
    )
    db.commit()
    return match_out(m)


# --- League (staff) ----------------------------------------------------------


@router.post("/league/run", response_model=list[MatchOut])
def run_league(
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    created = matchmaking.run_league(db, club)
    db.commit()
    ids = [m.id for m in created]
    return [match_out(m) for m in _load(db, Match.id.in_(ids))] if ids else []


@router.get("/league", response_model=list[MatchOut])
def league(
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    now = club_now(club.timezone)
    return [
        match_out(m)
        for m in _load(
            db,
            Match.club_id == club.id,
            Match.source == "league",
            Match.proposed_start >= now.replace(hour=0, minute=0),
        )
    ]


# --- Clinics -------------------------------------------------------------------


@router.get("/clinics/suggestions")
def clinic_suggestions(
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    return matchmaking.clinic_suggestions(db, club)


class ClinicIn(BaseModel):
    court_id: int
    start_at: datetime
    coach_id: int
    title: str = Field(min_length=1, max_length=120)
    capacity: int = Field(default=6, ge=2, le=12)
    invite_ids: list[int] = []


@router.post("/clinics", response_model=BookingOut)
def create_clinic(
    body: ClinicIn,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    coach = db.get(Coach, body.coach_id)
    court = db.get(Court, body.court_id)
    if coach is None or coach.club_id != club.id:
        raise HTTPException(404, "Coach not found")
    booking = create_booking(
        db,
        club=club,
        court=court,
        start_at=body.start_at.replace(tzinfo=None),
        booker=None,
        players=[],
        type="clinic",
        source="staff",
        price=club.base_price + coach.hourly_rate,  # whole session; members split it
        base_price=club.base_price,
        coach_id=coach.id,
        title=body.title,
        capacity=body.capacity,
    )
    when = booking.start_at.strftime("%a %b %-d, %-I:%M %p")
    for uid in body.invite_ids:
        invitee = db.get(User, uid)
        if invitee and invitee.club_id == club.id:
            notify(
                db,
                uid,
                "clinic_invite",
                f"You're invited: {body.title}",
                f"{when} with {coach.user.full_name}. Spots are limited.",
                "/app/matches",
            )
    db.commit()
    return booking_out(load_bookings(db, Booking.id == booking.id)[0])


@router.get("/clinics/open", response_model=list[BookingOut])
def open_clinics(
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    now = club_now(club.timezone)
    rows = load_bookings(
        db,
        Booking.club_id == club.id,
        Booking.type == "clinic",
        Booking.status == "booked",
        Booking.start_at > now,
    )
    return bookings_out(db, [b for b in rows if len(b.players) < b.capacity][:10])


@router.post("/clinics/{booking_id}/join", response_model=BookingOut)
def join_clinic(
    booking_id: int,
    user: User = Depends(require_member),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    rows = load_bookings(db, Booking.id == booking_id, Booking.club_id == club.id)
    if not rows or rows[0].type != "clinic" or rows[0].status != "booked":
        raise HTTPException(404, "Clinic not found")
    b = rows[0]
    if any(p.user_id == user.id for p in b.players):
        raise HTTPException(409, "You're already signed up")
    if len(b.players) >= b.capacity:
        raise HTTPException(409, "This clinic is full")
    b.players.append(BookingPlayer(user_id=user.id))
    db.commit()
    return booking_out(load_bookings(db, Booking.id == booking_id)[0])
