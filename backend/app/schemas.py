"""Response models shared across routers."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORM):
    id: int
    club_id: int | None
    email: str
    role: str
    full_name: str
    phone: str | None = None
    skill_level: float
    availability: list[str] = []
    play_style: str | None = None
    goals: str | None = None
    preferred_format: str = "singles"
    league_opt_in: bool = False
    matches_played: int = 0
    created_at: datetime


class ClubOut(ORM):
    id: int
    name: str
    timezone: str
    city: str | None
    latitude: float | None
    longitude: float | None
    open_hour: int
    close_hour: int
    peak_hours: dict
    currency: str
    base_price: float
    pricing_mode: str
    min_price: float
    max_price: float
    max_surge_pct: float
    max_discount_pct: float
    waitlist_hold_minutes: int
    setup_complete: bool


class CourtOut(ORM):
    id: int
    name: str
    surface: str
    indoor: bool
    has_lights: bool
    is_active: bool


class PlanOut(ORM):
    id: int
    name: str
    monthly_price: float
    court_discount_pct: float
    priority: int
    description: str | None
    is_active: bool


class MembershipOut(ORM):
    id: int
    plan_id: int
    plan: PlanOut
    start_date: date
    end_date: date
    status: str
    auto_renew: bool


class CoachOut(ORM):
    id: int
    user_id: int
    specialties: str | None
    hourly_rate: float
    bio: str | None
    user: UserOut


class PlayerOut(ORM):
    id: int
    full_name: str
    skill_level: float


class BookingOut(ORM):
    id: int
    court_id: int
    court_name: str
    user_id: int | None
    booker_name: str | None
    coach_id: int | None
    coach_name: str | None
    start_at: datetime
    end_at: datetime
    type: str
    status: str
    title: str | None
    capacity: int
    base_price: float
    price: float
    price_breakdown: list
    paid: bool
    source: str
    players: list[PlayerOut]
    checked_in: bool = False


class CheckInOut(ORM):
    id: int
    user_id: int
    member_name: str
    booking_id: int | None
    court_name: str | None
    method: str
    created_at: datetime


class NotificationOut(ORM):
    id: int
    kind: str
    title: str
    body: str | None
    link: str | None
    read: bool
    created_at: datetime
