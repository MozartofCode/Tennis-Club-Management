"""The signed-in member's own profile, QR code, membership and notifications."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Club, Notification, User
from app.schemas import MembershipOut, NotificationOut, UserOut
from app.security import current_club, current_user, new_qr_token
from app.services.core import active_membership
from app.timeutil import BLOCKS, DAY_KEYS, club_now

router = APIRouter(prefix="/me", tags=["me"])

VALID_SLOTS = {f"{d}:{b}" for d in DAY_KEYS for b in BLOCKS}


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = None
    skill_level: float | None = Field(default=None, ge=1, le=7)
    availability: list[str] | None = None
    play_style: str | None = None
    goals: str | None = None
    preferred_format: str | None = Field(default=None, pattern="^(singles|doubles|either)$")
    league_opt_in: bool | None = None


@router.patch("", response_model=UserOut)
def update_profile(
    body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    data = body.model_dump(exclude_unset=True)
    if "availability" in data:
        data["availability"] = sorted(set(data["availability"]) & VALID_SLOTS)
    if "skill_level" in data and user.matches_played == 0:
        # Before any results come in, the hidden rating follows the self-rated level.
        user.rating = 1000 + data["skill_level"] * 150
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    return user


class QrOut(BaseModel):
    token: str
    name: str
    club: str


@router.get("/qr", response_model=QrOut)
def my_qr(user: User = Depends(current_user), club: Club = Depends(current_club)):
    return QrOut(token=user.qr_token, name=user.full_name, club=club.name)


@router.post("/qr/rotate", response_model=QrOut)
def rotate_qr(
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    user.qr_token = new_qr_token()
    db.commit()
    return QrOut(token=user.qr_token, name=user.full_name, club=club.name)


@router.get("/membership", response_model=MembershipOut | None)
def my_membership(
    user: User = Depends(current_user),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    return active_membership(db, user.id, club_now(club.timezone).date())


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(30)
    ).all()


@router.post("/notifications/read")
def mark_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read.is_(False))
        .values(read=True)
    )
    db.commit()
    return {"ok": True}
