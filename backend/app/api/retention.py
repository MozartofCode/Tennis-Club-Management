"""Churn risk board and retention/upsell offers."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.ai import churn, offers
from app.db import get_db
from app.models import ChurnScore, Club, Offer, User
from app.security import current_club, current_user, require_staff
from app.services.core import notify
from app.services.email import send_email
from app.timeutil import utcnow

router = APIRouter(tags=["retention"])


class RiskRow(BaseModel):
    user_id: int
    member_name: str
    email: str
    skill_level: float
    score: float
    band: str
    reasons: list[dict]
    visits_30: int
    days_since_visit: int
    membership_end: str | None
    offer_status: str | None
    offer_id: int | None


class BoardOut(BaseModel):
    rows: list[RiskRow]
    counts: dict
    revenue_at_risk: float
    model: dict
    computed_at: datetime | None
    offers: dict


def _ensure_scores(db: Session, club: Club) -> None:
    if not db.scalar(select(func.count()).where(ChurnScore.club_id == club.id)):
        churn.score_club(db, club)


@router.get("/churn", response_model=BoardOut)
def board(
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    _ensure_scores(db, club)
    scores = db.scalars(
        select(ChurnScore)
        .options(selectinload(ChurnScore.user))
        .where(ChurnScore.club_id == club.id)
        .order_by(ChurnScore.score.desc())
    ).all()
    latest_offer: dict[int, Offer] = {}
    for o in db.scalars(select(Offer).where(Offer.club_id == club.id).order_by(Offer.created_at)):
        latest_offer[o.user_id] = o
    model = churn.get_model(db, club)
    status_counts = dict(
        db.execute(
            select(Offer.status, func.count())
            .where(Offer.club_id == club.id)
            .group_by(Offer.status)
        ).all()
    )
    rows = []
    for s in scores:
        o = latest_offer.get(s.user_id)
        f = s.features or {}
        rows.append(
            RiskRow(
                user_id=s.user_id,
                member_name=s.user.full_name,
                email=s.user.email,
                skill_level=s.user.skill_level,
                score=s.score,
                band=s.band,
                reasons=s.reasons,
                visits_30=f.get("visits_30", 0),
                days_since_visit=f.get("days_since_visit", 0),
                membership_end=f.get("membership_end"),
                offer_status=o.status if o else None,
                offer_id=o.id if o else None,
            )
        )
    return BoardOut(
        rows=rows,
        counts={b: sum(1 for s in scores if s.band == b) for b in ("high", "medium", "low")},
        revenue_at_risk=offers.revenue_at_risk(db, club),
        model={"kind": model.kind, **model.metrics},
        computed_at=scores[0].computed_at if scores else None,
        offers=status_counts,
    )


@router.post("/churn/recompute")
def recompute(
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    return churn.score_club(db, club)


class OfferOut(BaseModel):
    id: int
    user_id: int
    member_name: str
    kind: str
    source: str
    title: str
    message: str
    discount_pct: float
    reason: str | None
    written_by: str
    status: str
    created_at: datetime
    sent_at: datetime | None
    redeemed_at: datetime | None


def offer_out(o: Offer) -> OfferOut:
    return OfferOut(
        id=o.id,
        user_id=o.user_id,
        member_name=o.user.full_name,
        kind=o.kind,
        source=o.source,
        title=o.title,
        message=o.message,
        discount_pct=o.discount_pct,
        reason=o.reason,
        written_by=o.written_by,
        status=o.status,
        created_at=o.created_at,
        sent_at=o.sent_at,
        redeemed_at=o.redeemed_at,
    )


@router.get("/offers", response_model=list[OfferOut])
def list_offers(
    status: str | None = None,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Offer)
        .options(selectinload(Offer.user))
        .where(Offer.club_id == club.id)
        .order_by(Offer.created_at.desc())
    )
    if status:
        stmt = stmt.where(Offer.status == status)
    return [offer_out(o) for o in db.scalars(stmt.limit(200))]


class GenerateIn(BaseModel):
    user_ids: list[int] | None = None
    limit: int = Field(default=10, ge=1, le=50)


@router.post("/offers/generate")
def generate(
    body: GenerateIn,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    _ensure_scores(db, club)
    return {"created": offers.generate(db, club, limit=body.limit, user_ids=body.user_ids)}


def _own_offer(db: Session, club: Club, offer_id: int) -> Offer:
    o = db.get(Offer, offer_id)
    if o is None or o.club_id != club.id:
        raise HTTPException(404, "Offer not found")
    return o


class OfferPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    message: str | None = Field(default=None, min_length=1, max_length=2000)


@router.patch("/offers/{offer_id}", response_model=OfferOut)
def edit_offer(
    offer_id: int,
    body: OfferPatch,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    o = _own_offer(db, club, offer_id)
    if o.status != "draft":
        raise HTTPException(400, "Only drafts can be edited")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(o, k, v)
    db.commit()
    return offer_out(o)


@router.post("/offers/{offer_id}/send", response_model=OfferOut)
def send_offer(
    offer_id: int,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    o = _own_offer(db, club, offer_id)
    if o.status != "draft":
        raise HTTPException(400, "This offer was already handled")
    o.status = "sent"
    o.sent_at = utcnow()
    notify(db, o.user_id, "offer", o.title, o.message, "/app/offers")
    send_email(o.user.email, o.title, f"{o.message}\n\n{club.name}")
    db.commit()
    return offer_out(o)


@router.post("/offers/{offer_id}/dismiss", response_model=OfferOut)
def dismiss_offer(
    offer_id: int,
    _: User = Depends(require_staff),
    club: Club = Depends(current_club),
    db: Session = Depends(get_db),
):
    o = _own_offer(db, club, offer_id)
    if o.status == "draft":
        o.status = "dismissed"
        db.commit()
    return offer_out(o)


@router.get("/me/offers", response_model=list[OfferOut])
def my_offers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        offer_out(o)
        for o in db.scalars(
            select(Offer)
            .options(selectinload(Offer.user))
            .where(Offer.user_id == user.id, Offer.status.in_(("sent", "redeemed")))
            .order_by(Offer.sent_at.desc())
        )
    ]


@router.post("/me/offers/{offer_id}/redeem", response_model=OfferOut)
def redeem(offer_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = db.get(Offer, offer_id)
    if o is None or o.user_id != user.id:
        raise HTTPException(404, "Offer not found")
    if o.status != "sent":
        raise HTTPException(400, "This offer can't be claimed")
    o.status = "redeemed"
    o.redeemed_at = utcnow()
    db.commit()
    return offer_out(o)
