"""Coach view: their lessons and clinics, and the students they teach."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Booking, Club, Coach, User
from app.schemas import BookingOut
from app.security import current_club, require_roles
from app.services.core import bookings_out, load_bookings
from app.timeutil import club_now

router = APIRouter(prefix="/coach", tags=["coach"])


def _coach(db: Session, user: User) -> Coach:
    coach = db.scalar(select(Coach).where(Coach.user_id == user.id))
    if coach is None:
        raise HTTPException(404, "No coach profile for this account")
    return coach


@router.get("/schedule", response_model=list[BookingOut])
def schedule(
    days: int = 14,
    user: User = Depends(require_roles("coach")),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    coach = _coach(db, user)
    now = club_now(club.timezone)
    start = now.replace(hour=0, minute=0)
    return bookings_out(
        db,
        load_bookings(
            db,
            Booking.coach_id == coach.id,
            Booking.status != "cancelled",
            Booking.start_at >= start,
            Booking.start_at < start + timedelta(days=max(1, min(days, 60))),
        ),
    )


class Student(BaseModel):
    id: int
    full_name: str
    skill_level: float
    sessions: int
    last_session: str | None


@router.get("/students", response_model=list[Student])
def students(
    user: User = Depends(require_roles("coach")),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    coach = _coach(db, user)
    seen: dict[int, Student] = {}
    for b in load_bookings(db, Booking.coach_id == coach.id, Booking.status != "cancelled"):
        for p in b.players:
            s = seen.get(p.user_id)
            if s is None:
                s = seen[p.user_id] = Student(
                    id=p.user_id,
                    full_name=p.user.full_name,
                    skill_level=p.user.skill_level,
                    sessions=0,
                    last_session=None,
                )
            s.sessions += 1
            s.last_session = b.start_at.isoformat()
    return sorted(seen.values(), key=lambda s: (-s.sessions, s.full_name))


class LevelIn(BaseModel):
    skill_level: float


@router.patch("/students/{student_id}/level")
def set_level(
    student_id: int,
    body: LevelIn,
    user: User = Depends(require_roles("coach")),
    db: Session = Depends(get_db),
):
    """Coaches can correct a student's self-rated level."""
    student = db.get(User, student_id)
    if student is None or student.club_id != user.club_id or student.role != "member":
        raise HTTPException(404, "Student not found")
    student.skill_level = min(7.0, max(1.0, body.skill_level))
    db.commit()
    return {"ok": True, "skill_level": student.skill_level}
