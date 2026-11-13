"""Sign up, sign in, and the signed-in user's profile."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Club, User
from app.schemas import UserOut
from app.security import (
    create_token,
    current_user,
    hash_password,
    new_qr_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# A light check on purpose: demo and test accounts use reserved domains like .test
Email = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)]


class OwnerSignup(BaseModel):
    email: Email
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=120)
    club_name: str = Field(min_length=1, max_length=120)


class MemberSignup(BaseModel):
    email: Email
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=120)
    club_id: int | None = None
    skill_level: float = Field(default=3.0, ge=1.0, le=7.0)


class Login(BaseModel):
    email: Email
    password: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


def _email_taken(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == email.lower())) is not None


@router.post("/register-owner", response_model=AuthOut)
def register_owner(body: OwnerSignup, db: Session = Depends(get_db)):
    if _email_taken(db, body.email):
        raise HTTPException(409, "An account with this email already exists")
    club = Club(
        name=body.club_name,
        peak_hours={"weekday": [17, 18, 19, 20], "weekend": [8, 9, 10, 11]},
    )
    db.add(club)
    db.flush()
    user = User(
        club_id=club.id,
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role="owner",
        full_name=body.full_name,
        qr_token=new_qr_token(),
    )
    db.add(user)
    db.commit()
    return AuthOut(token=create_token(user), user=UserOut.model_validate(user))


@router.post("/register", response_model=AuthOut)
def register_member(body: MemberSignup, db: Session = Depends(get_db)):
    if _email_taken(db, body.email):
        raise HTTPException(409, "An account with this email already exists")
    club_id = body.club_id or db.scalar(select(Club.id).order_by(Club.id).limit(1))
    if club_id is None or db.get(Club, club_id) is None:
        raise HTTPException(404, "That club doesn't exist yet")
    user = User(
        club_id=club_id,
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role="member",
        full_name=body.full_name,
        skill_level=body.skill_level,
        rating=1000 + body.skill_level * 150,
        qr_token=new_qr_token(),
    )
    db.add(user)
    db.commit()
    return AuthOut(token=create_token(user), user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthOut)
def login(body: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return AuthOut(token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
