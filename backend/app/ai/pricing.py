"""Court pricing.

`quote()` is the one entry point every booking path uses, so pricing rules
live in one place. Each adjustment is recorded as a human-readable line.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Club, Court, User
from app.services.core import active_membership


@dataclass
class Adjustment:
    label: str
    pct: float  # +20 means +20%

    def as_dict(self) -> dict:
        return {"label": self.label, "pct": round(self.pct, 1)}


@dataclass
class Quote:
    base_price: float
    price: float
    adjustments: list[Adjustment] = field(default_factory=list)

    @property
    def breakdown(self) -> list[dict]:
        return [a.as_dict() for a in self.adjustments]


def member_discount(db: Session, user: User | None) -> Adjustment | None:
    if user is None or user.role != "member":
        return None
    membership = active_membership(db, user.id)
    if membership and membership.plan.court_discount_pct:
        return Adjustment(f"{membership.plan.name} member", -membership.plan.court_discount_pct)
    return None


def quote(db: Session, club: Club, court: Court, start_at: datetime, user: User | None) -> Quote:
    base = club.base_price
    adjustments: list[Adjustment] = []
    discount = member_discount(db, user)
    if discount:
        adjustments.append(discount)
    price = base
    for a in adjustments:
        price *= 1 + a.pct / 100
    return Quote(base_price=base, price=round(price, 2), adjustments=adjustments)
