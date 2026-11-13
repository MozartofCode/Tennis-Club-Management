"""Matchmaking, automatic court booking, weekly league and clinic suggestions.

Match score (0-1), each part shown as a reason:
  - level: hidden Elo rating gap (updates after every reported result)
  - availability: overlap of the times both members said they can play
  - style and format: same play style, compatible singles/doubles preference
  - variety: a bonus for people they haven't played recently
  - activity: members who are actually coming in respond to invites

Courts are booked in the slot both can play that is *least* in demand, so
matches fill quiet hours instead of competing for peak ones. That is the
crowd-smoothing half of the pricing story.
"""

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import pricing
from app.models import Booking, BookingPlayer, CheckIn, Club, Coach, Court, Match, User
from app.services.core import active_membership, create_booking, notify, slot_taken
from app.timeutil import BLOCKS, DAY_KEYS, availability_key, club_now

W_LEVEL, W_AVAIL, W_STYLE, W_VARIETY, W_ACTIVE = 0.45, 0.25, 0.1, 0.1, 0.1
RATING_SPAN = 300  # rating gap at which level fit reaches zero
ELO_K = 32


@dataclass
class Candidate:
    user: User
    score: float
    reasons: list[str] = field(default_factory=list)
    shared: list[str] = field(default_factory=list)  # shared availability keys


def _nice_slots(keys: list[str]) -> str:
    by_block: dict[str, list[str]] = {}
    for k in sorted(keys, key=lambda k: DAY_KEYS.index(k.split(":")[0])):
        day, block = k.split(":")
        by_block.setdefault(block, []).append(day.title())
    parts = [f"{' & '.join(days[:3])} {block}s" for block, days in by_block.items()]
    return ", ".join(parts[:2])


def occupancy(db: Session, club: Club, start: datetime, end: datetime):
    """Taken (court, time) pairs and busy (member, time) pairs in a window, in two queries."""
    taken = set(
        db.execute(
            select(Booking.court_id, Booking.start_at).where(
                Booking.club_id == club.id,
                Booking.start_at >= start,
                Booking.start_at < end,
                Booking.status.in_(("booked", "completed")),
            )
        ).all()
    )
    busy = set(
        db.execute(
            select(BookingPlayer.user_id, Booking.start_at)
            .join(Booking, Booking.id == BookingPlayer.booking_id)
            .where(
                Booking.club_id == club.id,
                Booking.start_at >= start,
                Booking.start_at < end,
                Booking.status == "booked",
            )
        ).all()
    )
    return taken, busy


def recent_opponents(db: Session, user_id: int, since: datetime) -> Counter:
    mine = select(BookingPlayer.booking_id).where(BookingPlayer.user_id == user_id)
    rows = db.execute(
        select(BookingPlayer.user_id)
        .join(Booking, Booking.id == BookingPlayer.booking_id)
        .where(
            BookingPlayer.booking_id.in_(mine),
            BookingPlayer.user_id != user_id,
            Booking.start_at >= since,
            Booking.status != "cancelled",
        )
    ).scalars()
    return Counter(rows)


def active_ids(db: Session, club: Club, now: datetime) -> set[int]:
    return set(
        db.scalars(
            select(CheckIn.user_id).where(
                CheckIn.club_id == club.id, CheckIn.created_at >= now - timedelta(days=30)
            )
        )
    )


def suggest(db: Session, club: Club, user: User, limit: int = 5) -> list[Candidate]:
    now = club_now(club.timezone)
    played = recent_opponents(db, user.id, now - timedelta(days=45))
    active = active_ids(db, club, now)
    mine = set(user.availability or [])
    out = []
    for other in db.scalars(
        select(User).where(
            User.club_id == club.id, User.role == "member", User.is_active, User.id != user.id
        )
    ):
        if other.id not in active and active_membership(db, other.id, now.date()) is None:
            continue  # gone quiet and no membership: don't send invites into the void
        gap = abs(other.rating - user.rating)
        level = max(0.0, 1 - gap / RATING_SPAN)
        theirs = set(other.availability or [])
        shared = sorted(mine & theirs)
        avail = len(shared) / max(1, len(mine | theirs)) if mine and theirs else 0.2
        style = 0.0
        if user.play_style and user.play_style == other.play_style:
            style += 0.6
        if "either" in (user.preferred_format, other.preferred_format) or (
            user.preferred_format == other.preferred_format
        ):
            style += 0.4
        times = played.get(other.id, 0)
        variety = 1.0 if times == 0 else 0.5 if times <= 2 else 0.0
        activity = 1.0 if other.id in active else 0.3
        score = (
            W_LEVEL * level
            + W_AVAIL * avail
            + W_STYLE * style
            + W_VARIETY * variety
            + W_ACTIVE * activity
        )
        if not shared and mine and theirs:
            score *= 0.6  # hard to find a time
        reasons = []
        if level >= 0.7:
            reasons.append(f"Similar level on match results (NTRP {other.skill_level:.1f})")
        elif other.rating > user.rating:
            reasons.append(f"A step up (NTRP {other.skill_level:.1f}), good challenge")
        else:
            reasons.append(f"NTRP {other.skill_level:.1f}")
        if shared:
            reasons.append(f"Both free {_nice_slots(shared)}")
        if user.play_style and user.play_style == other.play_style:
            reasons.append(f"Also plays {other.play_style.replace('-', ' ')}")
        if times == 0:
            reasons.append("You haven't played each other recently")
        out.append(Candidate(other, round(score, 3), reasons, shared))
    out.sort(key=lambda c: -c.score)
    return out[:limit]


def slot_options(
    db: Session, club: Club, a: User, b: User, days: int = 7, limit: int = 3
) -> list[dict]:
    """Bookable slots both can play, quietest (cheapest) first."""
    ctx = pricing.context(db, club, a, [])
    now = ctx.now
    day_list = [(now + timedelta(days=d)).date() for d in range(0, days + 1)]
    ctx.fills = pricing.fills_for(db, club, day_list)
    shared = set(a.availability or []) & set(b.availability or [])
    if not shared:
        shared = set(a.availability or []) | set(b.availability or [])
    if not shared:
        shared = {f"{d}:{blk}" for d in DAY_KEYS for blk in BLOCKS}
    courts = db.scalars(select(Court).where(Court.club_id == club.id, Court.is_active)).all()
    window_start = datetime.combine(day_list[0], datetime.min.time())
    taken, busy = occupancy(db, club, window_start, window_start + timedelta(days=days + 1))
    options = []
    for day in day_list:
        for hour in range(club.open_hour, club.close_hour):
            start = datetime.combine(day, datetime.min.time()).replace(hour=hour)
            if start <= now + timedelta(hours=2) or availability_key(start) not in shared:
                continue
            if (a.id, start) in busy or (b.id, start) in busy:
                continue
            court = next((c for c in courts if (c.id, start) not in taken), None)
            if court is None:
                continue
            q = pricing.price_slot(ctx, court, start)
            days_out = (day - now.date()).days
            options.append(
                (
                    q.demand + days_out * 0.01,
                    {
                        "start_at": start.isoformat(),
                        "court_id": court.id,
                        "court_name": court.name,
                        "price": q.price,
                        "per_person": round(q.price / 2, 2),
                        "quiet": q.demand < pricing.QUIET_BELOW,
                    },
                )
            )
    options.sort(key=lambda o: o[0])
    picked, used_days = [], set()
    for _, o in options:  # spread suggestions over different days
        day = o["start_at"][:10]
        if day in used_days:
            continue
        picked.append(o)
        used_days.add(day)
        if len(picked) == limit:
            break
    return picked


def invite(
    db: Session,
    club: Club,
    requester: User,
    opponent: User,
    start_at: datetime,
    court_id: int | None,
    score: float = 0.0,
    reasons: list[str] | None = None,
    source: str = "member",
) -> Match:
    if opponent.club_id != club.id or opponent.role != "member" or opponent.id == requester.id:
        raise HTTPException(404, "Player not found")
    if start_at <= club_now(club.timezone):
        raise HTTPException(400, "Pick a time in the future")
    m = Match(
        club_id=club.id,
        requester_id=requester.id,
        opponent_id=opponent.id,
        status="pending",
        proposed_start=start_at,
        court_id=court_id,
        match_score=score,
        match_reasons=reasons or [],
        source=source,
    )
    db.add(m)
    db.flush()
    when = start_at.strftime("%a %b %-d, %-I:%M %p")
    title = (
        f"League match this week: vs {requester.full_name}"
        if source == "league"
        else f"{requester.full_name} invited you to a match"
    )
    notify(
        db,
        opponent.id,
        "match_invite",
        title,
        f"{when}. Accept and the court is booked.",
        "/app/matches",
    )
    if source == "league":
        notify(
            db,
            requester.id,
            "match_invite",
            f"League match this week: vs {opponent.full_name}",
            f"{when}. Either of you can accept to lock in the court.",
            "/app/matches",
        )
    return m


def accept(db: Session, club: Club, match: Match, user: User) -> Booking:
    if user.id != match.opponent_id and not (
        match.source == "league" and user.id == match.requester_id
    ):
        raise HTTPException(403, "Only the invited player can accept")
    if match.status != "pending":
        raise HTTPException(400, "This invite is no longer open")
    a, b = db.get(User, match.requester_id), db.get(User, match.opponent_id)
    start = match.proposed_start
    court = db.get(Court, match.court_id) if match.court_id else None
    if court is None or slot_taken(db, court.id, start):
        court = next(
            (
                c
                for c in db.scalars(select(Court).where(Court.club_id == club.id, Court.is_active))
                if not slot_taken(db, c.id, start)
            ),
            None,
        )
    if court is None:
        options = slot_options(db, club, a, b, limit=1)
        if not options:
            raise HTTPException(409, "No courts left at that time. Try proposing another time.")
        start = datetime.fromisoformat(options[0]["start_at"])
        court = db.get(Court, options[0]["court_id"])
    q = pricing.quote(db, club, court, start, a)
    booking = create_booking(
        db,
        club=club,
        court=court,
        start_at=start,
        booker=a,
        players=[a, b],
        type="match",
        source="match" if match.source != "league" else "league",
        price=q.price,
        base_price=q.base_price,
        breakdown=q.breakdown + [{"label": "Split between 2 players", "pct": 0}],
    )
    match.status = "accepted"
    match.booking_id = booking.id
    match.court_id = court.id
    match.proposed_start = start
    when = start.strftime("%a %b %-d, %-I:%M %p")
    notify(
        db,
        a.id,
        "match_booked",
        f"Match on! {b.full_name} accepted",
        f"{court.name}, {when}. The court is booked for you both.",
        "/app/matches",
    )
    db.flush()
    return booking


def expected(ra: float, rb: float) -> float:
    return 1 / (1 + math.pow(10, (rb - ra) / 400))


def record_result(db: Session, match: Match, winner: User, loser: User, score_text: str) -> None:
    e = expected(winner.rating, loser.rating)
    delta = ELO_K * (1 - e)
    winner.rating += delta
    loser.rating -= delta
    winner.matches_played += 1
    loser.matches_played += 1
    match.winner_id = winner.id
    match.score_text = score_text[:40]
    match.status = "completed"


def run_league(db: Session, club: Club) -> list[Match]:
    """Pair everyone who opted in, booking-ready invites in quiet hours for the coming week."""
    now = club_now(club.timezone)
    week_start = now - timedelta(days=now.weekday())
    already = set()
    for m in db.scalars(
        select(Match).where(
            Match.club_id == club.id,
            Match.source == "league",
            Match.created_at >= (week_start - timedelta(hours=12)).replace(hour=0),
            Match.status.in_(("pending", "accepted")),
        )
    ):
        already |= {m.requester_id, m.opponent_id}
    pool = [
        u
        for u in db.scalars(
            select(User).where(
                User.club_id == club.id, User.role == "member", User.league_opt_in, User.is_active
            )
        )
        if u.id not in already
    ]
    active = active_ids(db, club, now)
    pool = [u for u in pool if u.id in active]
    pool.sort(key=lambda u: -u.rating)
    created = []
    taken: set[int] = set()
    for u in pool:
        if u.id in taken:
            continue
        # look at the next few players by rating, pick the best overall fit
        best, best_score = None, -1.0
        for other in [p for p in pool if p.id not in taken and p.id != u.id][:6]:
            gap = abs(other.rating - u.rating)
            shared = set(u.availability or []) & set(other.availability or [])
            s = max(0, 1 - gap / RATING_SPAN) * 0.7 + min(1, len(shared) / 3) * 0.3
            if s > best_score:
                best, best_score = other, s
        if best is None:
            continue
        options = slot_options(db, club, u, best, limit=1)
        if not options:
            continue
        o = options[0]
        m = invite(
            db,
            club,
            u,
            best,
            datetime.fromisoformat(o["start_at"]),
            o["court_id"],
            round(best_score, 3),
            [f"Weekly ladder: ratings {round(u.rating)} vs {round(best.rating)}"],
            source="league",
        )
        created.append(m)
        taken |= {u.id, best.id}
    db.flush()
    return created


def _clinic_reason(n: int, lo: float, hi: float, demand: float) -> str:
    return (
        f"{n} active NTRP {lo:.1f}-{hi:.1f} members list this time as free, "
        f"and only ~{round(demand * 100)}% of courts are usually booked"
    )


def clinic_suggestions(db: Session, club: Club, days: int = 10, limit: int = 4) -> list[dict]:
    """Quiet hours where a group of similar-level members are free: good clinic slots."""
    ctx = pricing.context(db, club, None)
    now = ctx.now
    day_list = [(now + timedelta(days=d)).date() for d in range(1, days + 1)]
    ctx.fills = pricing.fills_for(db, club, day_list)
    active = active_ids(db, club, now)
    members = [
        u
        for u in db.scalars(
            select(User).where(User.club_id == club.id, User.role == "member", User.is_active)
        )
        if u.id in active
    ]
    coaches = db.scalars(select(Coach).where(Coach.club_id == club.id)).all()
    courts = db.scalars(select(Court).where(Court.club_id == club.id, Court.is_active)).all()
    if not coaches or not courts:
        return []
    bands = [(2.0, 3.0), (3.0, 3.5), (3.5, 4.0), (4.0, 5.0)]
    window_start = datetime.combine(day_list[0], datetime.min.time())
    taken, busy = occupancy(db, club, window_start, window_start + timedelta(days=days + 1))
    found = []
    for day in day_list:
        for hour in range(club.open_hour, club.close_hour):
            start = datetime.combine(day, datetime.min.time()).replace(hour=hour)
            forecast = ctx.model.predict(day, hour, ctx.peak)
            current = ctx.fills.get((day, hour), 0) / ctx.courts
            demand = max(forecast, current)
            if demand > 0.3:
                continue
            key = availability_key(start)
            court = next((c for c in courts if (c.id, start) not in taken), None)
            if key is None or court is None:
                continue
            for lo, hi in bands:
                group = [
                    u
                    for u in members
                    if lo <= u.skill_level <= hi
                    and key in (u.availability or [])
                    and (u.id, start) not in busy
                ]
                if len(group) >= 4:
                    found.append(
                        {
                            "start_at": start.isoformat(),
                            "court_id": court.id,
                            "court_name": court.name,
                            "level": f"{lo:.1f}-{hi:.1f}",
                            "demand": round(demand, 2),
                            "members": [
                                {"id": u.id, "name": u.full_name, "level": u.skill_level}
                                for u in group[:8]
                            ],
                            "member_count": len(group),
                            "reason": _clinic_reason(len(group), lo, hi, demand),
                        }
                    )
    found.sort(key=lambda s: (-s["member_count"], s["demand"]))
    picked, used = [], set()
    for s in found:
        k = (s["start_at"][:10], s["level"])
        if k in used:
            continue
        used.add(k)
        picked.append(s)
        if len(picked) == limit:
            break
    return picked
