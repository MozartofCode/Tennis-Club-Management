"""Club setup: details, hours, courts, membership plans, coaches and staff."""

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Club, Coach, Court, MembershipPlan, User
from app.schemas import ClubOut, CoachOut, CourtOut, PlanOut, UserOut
from app.security import (
    current_club,
    current_user,
    hash_password,
    new_qr_token,
    require_owner,
    require_staff,
)

router = APIRouter(prefix="/club", tags=["club"])


class ClubUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    open_hour: int | None = Field(default=None, ge=0, le=23)
    close_hour: int | None = Field(default=None, ge=1, le=24)
    peak_hours: dict | None = None
    currency: str | None = None
    base_price: float | None = Field(default=None, gt=0)
    pricing_mode: str | None = Field(default=None, pattern="^(off|suggest|on)$")
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, gt=0)
    max_surge_pct: float | None = Field(default=None, ge=0, le=200)
    max_discount_pct: float | None = Field(default=None, ge=0, le=90)
    waitlist_hold_minutes: int | None = Field(default=None, ge=5, le=240)
    setup_complete: bool | None = None


@router.get("", response_model=ClubOut)
def get_club(club: Club = Depends(current_club)):
    return club


@router.patch("", response_model=ClubOut)
def update_club(
    body: ClubUpdate,
    _: User = Depends(require_owner),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(club, key, value)
    if club.close_hour <= club.open_hour:
        raise HTTPException(400, "Closing time must be after opening time")
    if club.min_price > club.max_price:
        raise HTTPException(400, "Minimum price can't be above the maximum")
    db.commit()
    return club


# --- Courts ---------------------------------------------------------------


class CourtIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    surface: str = "hard"
    indoor: bool = False
    has_lights: bool = True
    is_active: bool = True


@router.get("/courts", response_model=list[CourtOut])
def list_courts(club: Club = Depends(current_club), db: Session = Depends(get_db)):
    return db.scalars(select(Court).where(Court.club_id == club.id).order_by(Court.id)).all()


@router.post("/courts", response_model=CourtOut)
def add_court(
    body: CourtIn,
    _: User = Depends(require_owner),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    court = Court(club_id=club.id, **body.model_dump())
    db.add(court)
    db.commit()
    return court


def _own_court(db: Session, club: Club, court_id: int) -> Court:
    court = db.get(Court, court_id)
    if court is None or court.club_id != club.id:
        raise HTTPException(404, "Court not found")
    return court


@router.patch("/courts/{court_id}", response_model=CourtOut)
def update_court(
    court_id: int,
    body: CourtIn,
    _: User = Depends(require_owner),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    court = _own_court(db, club, court_id)
    for key, value in body.model_dump().items():
        setattr(court, key, value)
    db.commit()
    return court


@router.delete("/courts/{court_id}")
def retire_court(
    court_id: int,
    _: User = Depends(require_owner),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    # Courts keep their booking history, so they're deactivated rather than deleted.
    _own_court(db, club, court_id).is_active = False
    db.commit()
    return {"ok": True}


# --- Membership plans -----------------------------------------------------


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    monthly_price: float = Field(ge=0)
    court_discount_pct: float = Field(default=0, ge=0, le=100)
    priority: int = Field(default=0, ge=0, le=3)
    description: str | None = None
    is_active: bool = True


@router.get("/plans", response_model=list[PlanOut])
def list_plans(club: Club = Depends(current_club), db: Session = Depends(get_db)):
    return db.scalars(
        select(MembershipPlan)
        .where(MembershipPlan.club_id == club.id)
        .order_by(MembershipPlan.monthly_price)
    ).all()


@router.post("/plans", response_model=PlanOut)
def add_plan(
    body: PlanIn,
    _: User = Depends(require_owner),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    plan = MembershipPlan(club_id=club.id, **body.model_dump())
    db.add(plan)
    db.commit()
    return plan


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: int,
    body: PlanIn,
    _: User = Depends(require_owner),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    plan = db.get(MembershipPlan, plan_id)
    if plan is None or plan.club_id != club.id:
        raise HTTPException(404, "Plan not found")
    for key, value in body.model_dump().items():
        setattr(plan, key, value)
    db.commit()
    return plan


# --- Coaches and staff ----------------------------------------------------


class CoachIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    specialties: str | None = None
    hourly_rate: float = Field(default=70, ge=0)
    bio: str | None = None
    skill_level: float = Field(default=5.0, ge=1, le=7)


class StaffIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NewAccountOut(BaseModel):
    user: UserOut
    temporary_password: str


def _new_account(db: Session, club: Club, email: str, full_name: str, role: str, **extra):
    email = email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    temp = secrets.token_urlsafe(9)
    user = User(
        club_id=club.id,
        email=email,
        full_name=full_name,
        role=role,
        password_hash=hash_password(temp),
        qr_token=new_qr_token(),
        **extra,
    )
    db.add(user)
    db.flush()
    return user, temp


@router.get("/coaches", response_model=list[CoachOut])
def list_coaches(
    _: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(Coach)
        .options(selectinload(Coach.user))
        .where(Coach.club_id == club.id)
        .order_by(Coach.id)
    ).all()


@router.post("/coaches", response_model=NewAccountOut)
def add_coach(
    body: CoachIn,
    _: User = Depends(require_owner),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    user, temp = _new_account(
        db, club, body.email, body.full_name, "coach", skill_level=body.skill_level
    )
    db.add(
        Coach(
            club_id=club.id,
            user_id=user.id,
            specialties=body.specialties,
            hourly_rate=body.hourly_rate,
            bio=body.bio,
        )
    )
    db.commit()
    return NewAccountOut(user=UserOut.model_validate(user), temporary_password=temp)


@router.get("/staff", response_model=list[UserOut])
def list_staff(
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(User)
        .where(User.club_id == club.id, User.role.in_(("owner", "staff")))
        .order_by(User.id)
    ).all()


@router.post("/staff", response_model=NewAccountOut)
def add_staff(
    body: StaffIn,
    _: User = Depends(require_owner),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    user, temp = _new_account(db, club, body.email, body.full_name, "staff")
    db.commit()
    return NewAccountOut(user=UserOut.model_validate(user), temporary_password=temp)
