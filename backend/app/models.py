"""Database tables.

Every row that belongs to a club carries `club_id`, so the app can host
several clubs later. Times on bookings are club-local (naive) datetimes.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.timeutil import utcnow

ROLES = ("owner", "staff", "coach", "member")
BOOKING_TYPES = ("casual", "lesson", "match", "clinic")
BOOKING_STATUSES = ("booked", "cancelled", "no_show", "completed")


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    city: Mapped[str | None] = mapped_column(String(120))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    open_hour: Mapped[int] = mapped_column(Integer, default=7)
    close_hour: Mapped[int] = mapped_column(Integer, default=22)
    # {"weekday": [17, 18, 19, 20], "weekend": [8, 9, 10, 11]}
    peak_hours: Mapped[dict] = mapped_column(JSON, default=dict)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    base_price: Mapped[float] = mapped_column(Float, default=40.0)  # per court-hour

    # Dynamic pricing guard rails, set by the owner.
    pricing_mode: Mapped[str] = mapped_column(String(16), default="suggest")  # off|suggest|on
    min_price: Mapped[float] = mapped_column(Float, default=20.0)
    max_price: Mapped[float] = mapped_column(Float, default=80.0)
    max_surge_pct: Mapped[float] = mapped_column(Float, default=35.0)
    max_discount_pct: Mapped[float] = mapped_column(Float, default=30.0)

    waitlist_hold_minutes: Mapped[int] = mapped_column(Integer, default=15)
    setup_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    courts: Mapped[list["Court"]] = relationship(back_populates="club", order_by="Court.id")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="member")
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))

    # Tennis profile
    skill_level: Mapped[float] = mapped_column(Float, default=3.0)  # NTRP 1.0-7.0
    rating: Mapped[float] = mapped_column(Float, default=1500.0)  # hidden Elo
    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    availability: Mapped[list] = mapped_column(JSON, default=list)  # ["mon:evening", ...]
    play_style: Mapped[str | None] = mapped_column(String(32))
    goals: Mapped[str | None] = mapped_column(Text)
    preferred_format: Mapped[str] = mapped_column(String(16), default="singles")
    league_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)

    qr_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user", order_by="Membership.start_date"
    )


class Court(Base):
    __tablename__ = "courts"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    surface: Mapped[str] = mapped_column(String(24), default="hard")
    indoor: Mapped[bool] = mapped_column(Boolean, default=False)
    has_lights: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    club: Mapped[Club] = relationship(back_populates="courts")


class Coach(Base):
    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    specialties: Mapped[str | None] = mapped_column(String(200))
    hourly_rate: Mapped[float] = mapped_column(Float, default=70.0)
    bio: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship()


class MembershipPlan(Base):
    __tablename__ = "membership_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    monthly_price: Mapped[float] = mapped_column(Float)
    court_discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # waitlist priority tier
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("membership_plans.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|expired|cancelled
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="memberships")
    plan: Mapped[MembershipPlan] = relationship()


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)  # booker
    coach_id: Mapped[int | None] = mapped_column(ForeignKey("coaches.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    type: Mapped[str] = mapped_column(String(16), default="casual")
    status: Mapped[str] = mapped_column(String(16), default="booked", index=True)
    title: Mapped[str | None] = mapped_column(String(120))  # e.g. clinic name
    capacity: Mapped[int] = mapped_column(Integer, default=4)

    base_price: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    price_breakdown: Mapped[list] = mapped_column(JSON, default=list)
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="member")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)

    court: Mapped[Court] = relationship()
    user: Mapped[User | None] = relationship(foreign_keys=[user_id])
    coach: Mapped[Coach | None] = relationship()
    players: Mapped[list["BookingPlayer"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )


class BookingPlayer(Base):
    """Everyone on court for a booking (booker included), for matches, doubles and clinics."""

    __tablename__ = "booking_players"
    __table_args__ = (UniqueConstraint("booking_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    booking: Mapped[Booking] = relationship(back_populates="players")
    user: Mapped[User] = relationship()


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    start_hour: Mapped[int] = mapped_column(Integer)  # earliest acceptable start
    end_hour: Mapped[int] = mapped_column(Integer)  # latest acceptable start
    court_id: Mapped[int | None] = mapped_column(ForeignKey("courts.id"))  # None = any court
    status: Mapped[str] = mapped_column(String(16), default="waiting", index=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority_reasons: Mapped[list] = mapped_column(JSON, default=list)

    # Set while a freed slot is on hold for this member.
    offer_court_id: Mapped[int | None] = mapped_column(ForeignKey("courts.id"))
    offer_start_at: Mapped[datetime | None] = mapped_column(DateTime)
    offer_price: Mapped[float | None] = mapped_column(Float)
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    offers_received: Mapped[int] = mapped_column(Integer, default=0)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship()
    offer_court: Mapped[Court | None] = relationship(foreign_keys=[offer_court_id])


class CheckIn(Base):
    __tablename__ = "check_ins"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))
    method: Mapped[str] = mapped_column(String(16), default="qr")  # qr|manual
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # club-local

    user: Mapped[User] = relationship()
    booking: Mapped[Booking | None] = relationship()


class Match(Base):
    """A match invite between two members; when accepted a court is auto-booked."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    opponent_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # pending|accepted|declined|expired|completed
    proposed_start: Mapped[datetime] = mapped_column(DateTime)
    court_id: Mapped[int | None] = mapped_column(ForeignKey("courts.id"))
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    match_reasons: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16), default="member")  # member|league
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    score_text: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    opponent: Mapped[User] = relationship(foreign_keys=[opponent_id])
    court: Mapped[Court | None] = relationship()


class ChurnScore(Base):
    __tablename__ = "churn_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(8))  # low|medium|high
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped[User] = relationship()


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    # renewal_discount|free_session|match_intro|lesson_upsell|clinic_invite
    source: Mapped[str] = mapped_column(String(16), default="churn")  # churn|upsell|manual
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str | None] = mapped_column(String(200))
    written_by: Mapped[str] = mapped_column(String(16), default="template")  # template|claude
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # draft|sent|redeemed|dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(200))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
