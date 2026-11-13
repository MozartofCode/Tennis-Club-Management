"""Member management for staff: list, profile, memberships, and spreadsheet import."""

import csv
import io
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Booking,
    BookingPlayer,
    CheckIn,
    ChurnScore,
    Club,
    Membership,
    MembershipPlan,
    User,
)
from app.schemas import BookingOut, CheckInOut, MembershipOut, UserOut
from app.security import current_club, new_qr_token, require_staff
from app.services.core import active_membership, bookings_out, load_bookings
from app.timeutil import club_now

router = APIRouter(prefix="/members", tags=["members"])


class MemberRow(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str | None
    skill_level: float
    plan: str | None
    membership_status: str  # active|expiring|expired|none
    membership_end: date | None
    last_visit: datetime | None
    visits_30d: int
    upcoming_bookings: int
    churn_score: float | None = None
    churn_band: str | None = None
    created_at: datetime


def _membership_status(m: Membership | None, today: date) -> str:
    if m is None:
        return "none"
    if m.end_date < today or m.status != "active":
        return "expired"
    if (m.end_date - today).days <= 21:
        return "expiring"
    return "active"


@router.get("", response_model=list[MemberRow])
def list_members(
    q: str | None = None,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    now = club_now(club.timezone)
    today = now.date()
    stmt = select(User).where(User.club_id == club.id, User.role == "member")
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(User.full_name).like(like) | func.lower(User.email).like(like))
    members = db.scalars(stmt.order_by(User.full_name)).all()
    ids = [m.id for m in members]
    if not ids:
        return []

    last_visit = dict(
        db.execute(
            select(CheckIn.user_id, func.max(CheckIn.created_at))
            .where(CheckIn.user_id.in_(ids))
            .group_by(CheckIn.user_id)
        ).all()
    )
    visits = dict(
        db.execute(
            select(CheckIn.user_id, func.count())
            .where(CheckIn.user_id.in_(ids), CheckIn.created_at >= now - timedelta(days=30))
            .group_by(CheckIn.user_id)
        ).all()
    )
    upcoming = dict(
        db.execute(
            select(BookingPlayer.user_id, func.count())
            .join(Booking, Booking.id == BookingPlayer.booking_id)
            .where(
                BookingPlayer.user_id.in_(ids),
                Booking.start_at >= now,
                Booking.status == "booked",
            )
            .group_by(BookingPlayer.user_id)
        ).all()
    )
    latest: dict[int, Membership] = {}
    for m in db.scalars(
        select(Membership).where(Membership.user_id.in_(ids)).order_by(Membership.end_date)
    ):
        latest[m.user_id] = m
    plans = {p.id: p.name for p in db.scalars(select(MembershipPlan))}
    churn = _latest_churn(db, ids)

    rows = []
    for u in members:
        m = latest.get(u.id)
        score = churn.get(u.id)
        rows.append(
            MemberRow(
                id=u.id,
                full_name=u.full_name,
                email=u.email,
                phone=u.phone,
                skill_level=u.skill_level,
                plan=plans.get(m.plan_id) if m else None,
                membership_status=_membership_status(m, today),
                membership_end=m.end_date if m else None,
                last_visit=last_visit.get(u.id),
                visits_30d=visits.get(u.id, 0),
                upcoming_bookings=upcoming.get(u.id, 0),
                churn_score=score.score if score else None,
                churn_band=score.band if score else None,
                created_at=u.created_at,
            )
        )
    return rows


def _latest_churn(db: Session, ids: list[int]) -> dict:
    out = {}
    for s in db.scalars(
        select(ChurnScore).where(ChurnScore.user_id.in_(ids)).order_by(ChurnScore.computed_at)
    ):
        out[s.user_id] = s
    return out


class MemberDetail(BaseModel):
    user: UserOut
    membership: MembershipOut | None
    memberships: list[MembershipOut]
    upcoming: list[BookingOut]
    recent: list[BookingOut]
    check_ins: list[CheckInOut]
    stats: dict


def _own_member(db: Session, club: Club, member_id: int) -> User:
    user = db.get(User, member_id)
    if user is None or user.club_id != club.id:
        raise HTTPException(404, "Member not found")
    return user


@router.get("/{member_id}", response_model=MemberDetail)
def member_detail(
    member_id: int,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    user = _own_member(db, club, member_id)
    now = club_now(club.timezone)
    mine = select(BookingPlayer.booking_id).where(BookingPlayer.user_id == user.id)
    upcoming = load_bookings(
        db, Booking.id.in_(mine), Booking.start_at >= now, Booking.status == "booked"
    )
    recent = list(reversed(load_bookings(db, Booking.id.in_(mine), Booking.start_at < now)))[:20]
    check_ins = db.scalars(
        select(CheckIn).where(CheckIn.user_id == user.id).order_by(CheckIn.created_at.desc())
    ).all()
    all_past = [b for b in load_bookings(db, Booking.id.in_(mine), Booking.start_at < now)]
    stats = {
        "total_visits": len(check_ins),
        "visits_30d": sum(1 for c in check_ins if c.created_at >= now - timedelta(days=30)),
        "bookings_total": len(all_past),
        "cancellations": sum(1 for b in all_past if b.status == "cancelled"),
        "no_shows": sum(1 for b in all_past if b.status == "no_show"),
        "lessons": sum(1 for b in all_past if b.type in ("lesson", "clinic")),
        "spend_90d": round(
            sum(
                b.price
                for b in all_past
                if b.status != "cancelled" and b.start_at >= now - timedelta(days=90)
            ),
            2,
        ),
    }
    memberships = db.scalars(
        select(Membership).where(Membership.user_id == user.id).order_by(Membership.start_date)
    ).all()
    return MemberDetail(
        user=UserOut.model_validate(user),
        membership=active_membership(db, user.id, now.date()),
        memberships=list(memberships),
        upcoming=bookings_out(db, upcoming),
        recent=bookings_out(db, recent),
        check_ins=[
            CheckInOut(
                id=c.id,
                user_id=c.user_id,
                member_name=user.full_name,
                booking_id=c.booking_id,
                court_name=c.booking.court.name if c.booking else None,
                method=c.method,
                created_at=c.created_at,
            )
            for c in check_ins[:30]
        ],
        stats=stats,
    )


class MemberIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = None
    skill_level: float = Field(default=3.0, ge=1, le=7)
    plan_id: int | None = None


def _add_membership(db: Session, user: User, plan_id: int, start: date, months: int = 1):
    plan = db.get(MembershipPlan, plan_id)
    if plan is None or plan.club_id != user.club_id:
        raise HTTPException(404, "Plan not found")
    for m in db.scalars(
        select(Membership).where(Membership.user_id == user.id, Membership.status == "active")
    ):
        if m.end_date >= start:
            m.end_date = start - timedelta(days=1)
            m.status = "expired"
    m = Membership(
        user_id=user.id,
        plan_id=plan.id,
        start_date=start,
        end_date=start + timedelta(days=30 * months),
        status="active",
        auto_renew=True,
    )
    db.add(m)
    return m


@router.post("", response_model=UserOut)
def add_member(
    body: MemberIn,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "A member with this email already exists")
    user = User(
        club_id=club.id,
        email=email,
        full_name=body.full_name,
        phone=body.phone,
        skill_level=body.skill_level,
        rating=1000 + body.skill_level * 150,
        role="member",
        qr_token=new_qr_token(),
    )
    db.add(user)
    db.flush()
    if body.plan_id:
        _add_membership(db, user, body.plan_id, club_now(club.timezone).date())
    db.commit()
    return user


class MemberPatch(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    skill_level: float | None = Field(default=None, ge=1, le=7)
    is_active: bool | None = None


@router.patch("/{member_id}", response_model=UserOut)
def update_member(
    member_id: int,
    body: MemberPatch,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    user = _own_member(db, club, member_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    return user


class MembershipIn(BaseModel):
    plan_id: int
    months: int = Field(default=1, ge=1, le=24)
    auto_renew: bool = True


@router.post("/{member_id}/membership", response_model=MembershipOut)
def set_membership(
    member_id: int,
    body: MembershipIn,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    user = _own_member(db, club, member_id)
    m = _add_membership(db, user, body.plan_id, club_now(club.timezone).date(), body.months)
    m.auto_renew = body.auto_renew
    db.commit()
    db.refresh(m)
    return m


class ImportResult(BaseModel):
    created: int
    skipped: list[str]


@router.post("/import", response_model=ImportResult)
async def import_members(
    file: UploadFile = File(...),
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    """Import a CSV with columns: name, email, phone, level, plan (header names are flexible)."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(400, "The file is empty")
    cols = {name.strip().lower(): name for name in reader.fieldnames}

    def col(row: dict, *names: str) -> str:
        for n in names:
            if n in cols and row.get(cols[n]):
                return row[cols[n]].strip()
        return ""

    plans = {
        p.name.lower(): p
        for p in db.scalars(select(MembershipPlan).where(MembershipPlan.club_id == club.id))
    }
    existing = set(db.scalars(select(User.email)).all())
    today = club_now(club.timezone).date()
    created, skipped = 0, []
    for i, row in enumerate(reader, start=2):
        email = col(row, "email", "e-mail", "email address").lower()
        name = col(row, "name", "full name", "full_name", "member")
        if not name:
            first, last = col(row, "first name", "first"), col(row, "last name", "last")
            name = f"{first} {last}".strip()
        if not email or "@" not in email or not name:
            skipped.append(f"Row {i}: missing name or email")
            continue
        if email in existing:
            skipped.append(f"Row {i}: {email} already exists")
            continue
        try:
            level = float(col(row, "level", "ntrp", "skill", "skill level") or 3.0)
        except ValueError:
            level = 3.0
        level = min(7.0, max(1.0, level))
        user = User(
            club_id=club.id,
            email=email,
            full_name=name,
            phone=col(row, "phone", "mobile", "phone number") or None,
            skill_level=level,
            rating=1000 + level * 150,
            role="member",
            qr_token=new_qr_token(),
        )
        db.add(user)
        db.flush()
        plan = plans.get(col(row, "plan", "membership", "membership plan").lower())
        if plan:
            _add_membership(db, user, plan.id, today)
        existing.add(email)
        created += 1
    db.commit()
    return ImportResult(created=created, skipped=skipped[:50])
