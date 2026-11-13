"""Retention and upsell offers.

Rules decide *what* to offer from a member's churn reasons (or, for engaged
members, an upsell). Claude, when configured, writes the message in the club's
voice; otherwise a template does. Every offer starts as a draft the owner
reviews, edits and sends: nothing goes to a member automatically.
"""

import json
import logging
from dataclasses import dataclass
from datetime import timedelta

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ChurnScore, Club, Coach, MembershipPlan, Offer, User
from app.timeutil import utcnow

log = logging.getLogger("courtiq.offers")

COOLDOWN_DAYS = 21  # don't pile offers on the same member


@dataclass
class OfferPlan:
    kind: str
    source: str  # churn|upsell
    title: str
    discount_pct: float
    reason: str
    template: str  # uses {first}, {club}


PLANS = {
    "partner": OfferPlan(
        "match_intro",
        "churn",
        "We found you some new hitting partners",
        0,
        "Regular partner stopped playing",
        "Hi {first}, we noticed your usual hitting partner hasn't been around lately. We've "
        "lined up a few players at your level who play when you do. Open Find a match in the app "
        "and your first match court is on us this month.",
    ),
    "visits": OfferPlan(
        "free_session",
        "churn",
        "Your next court hour is on us",
        100,
        "Playing less often",
        "Hi {first}, we've missed you on court at {club}! Your next court hour is on us: book "
        "any quiet-hour slot in the next two weeks and we'll take care of it at the desk.",
    ),
    "renewal": OfferPlan(
        "renewal_discount",
        "churn",
        "15% off when you renew",
        15,
        "Membership ending",
        "Hi {first}, your membership at {club} is up for renewal soon. Renew in the next two "
        "weeks and we'll take 15% off your next month. Thanks for being part of the club.",
    ),
    "lessons": OfferPlan(
        "lesson_upsell",
        "upsell",
        "A free 20-minute session with a coach",
        0,
        "Plays often, no lessons yet",
        "Hi {first}, you've been on court a lot lately: great to see! Want to take your game "
        "up a level? Book a lesson this month and the first 20 minutes with one of our coaches "
        "are free.",
    ),
    "clinic": OfferPlan(
        "clinic_invite",
        "upsell",
        "Try a group clinic, first one free",
        100,
        "Takes lessons, could enjoy clinics",
        "Hi {first}, our weekly clinics are a fun way to drill with players at your level. "
        "Your first clinic is free, ask at the desk or reply to book a spot.",
    ),
}


def plan_for(score: ChurnScore | None, features: dict) -> OfferPlan | None:
    if score is not None and score.band in ("high", "medium"):
        keys = [r["key"] for r in score.reasons]
        if "days_to_end" in keys or "auto_renew_off" in keys:
            return PLANS["renewal"]
        if "partner_lost" in keys:
            return PLANS["partner"]
        if keys:
            return PLANS["visits"]
        return None
    # Upsells for engaged, low-risk members.
    if features.get("visits_30", 0) >= 6 and features.get("lesson_share", 1) == 0:
        return PLANS["lessons"]
    if 0 < features.get("lesson_share", 0) < 0.5 and features.get("visits_30", 0) >= 3:
        return PLANS["clinic"]
    return None


def write_message(
    club: Club, user: User, plan: OfferPlan, reasons: list[str], coach_names: list[str]
) -> tuple[str, str, str]:
    """Returns (title, message, written_by)."""
    first = user.full_name.split(" ")[0]
    fallback = (plan.title, plan.template.format(first=first, club=club.name), "template")
    settings = get_settings()
    if not settings.llm_enabled:
        return fallback
    prompt = (
        f"Write a short, warm message from {club.name}, a tennis club, to a member.\n"
        f"Member first name: {first}. Level: NTRP {user.skill_level:.1f}. "
        f"Their goals: {user.goals or 'not stated'}.\n"
        f"What we noticed (private, never quote numbers or say we track them): "
        f"{'; '.join(reasons) or 'they are a regular'}.\n"
        f"The offer (must be stated exactly, no other perks): {plan.template}\n"
        f"Coaches at the club: {', '.join(coach_names) or 'our coaches'}.\n"
        "Rules: under 70 words, friendly and personal, no guilt or pressure, no emojis, "
        "no made-up facts, don't mention churn, data or tracking. The title is under 8 words."
    )
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2)
        response = client.beta.messages.create(
            model=settings.offer_model,
            max_tokens=1024,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={
                "effort": "low",
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "message": {"type": "string"},
                        },
                        "required": ["title", "message"],
                        "additionalProperties": False,
                    },
                },
            },
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError:
        log.warning("Offer writer rate limited; using template")
        return fallback
    except anthropic.APIStatusError as exc:
        log.warning("Offer writer API error %s; using template", exc.status_code)
        return fallback
    except anthropic.APIConnectionError:
        log.warning("Offer writer could not reach the API; using template")
        return fallback

    if response.stop_reason in ("refusal", "max_tokens"):
        return fallback
    text = next((b.text for b in response.content if b.type == "text"), None)
    try:
        data = json.loads(text or "")
        title, message = data["title"].strip(), data["message"].strip()
    except (ValueError, KeyError, AttributeError):
        return fallback
    # Check the output in code: sane lengths, and the offer itself still present.
    if not title or not message or len(title) > 80 or len(message.split()) > 110:
        return fallback
    if (
        plan.discount_pct
        and f"{int(plan.discount_pct)}%" not in message
        and plan.discount_pct != 100
    ):
        return fallback
    return title, message, "claude"


def draft_for(db: Session, club: Club, user: User, score: ChurnScore | None) -> Offer | None:
    features = score.features if score else {}
    plan = plan_for(score, features)
    if plan is None:
        return None
    reasons = [r["text"] for r in (score.reasons if score else [])]
    coach_names = [
        c.user.full_name for c in db.scalars(select(Coach).where(Coach.club_id == club.id))
    ]
    title, message, written_by = write_message(club, user, plan, reasons, coach_names)
    offer = Offer(
        club_id=club.id,
        user_id=user.id,
        kind=plan.kind,
        source=plan.source,
        title=title,
        message=message,
        discount_pct=plan.discount_pct,
        reason=reasons[0] if reasons else plan.reason,
        written_by=written_by,
        status="draft",
    )
    db.add(offer)
    return offer


def generate(db: Session, club: Club, limit: int = 25, user_ids: list[int] | None = None) -> int:
    """Draft offers for at-risk members (highest risk first) and a few upsells."""
    since = utcnow() - timedelta(days=COOLDOWN_DAYS)
    recent = set(
        db.scalars(select(Offer.user_id).where(Offer.club_id == club.id, Offer.created_at >= since))
    )
    scores = db.scalars(
        select(ChurnScore).where(ChurnScore.club_id == club.id).order_by(ChurnScore.score.desc())
    ).all()
    if user_ids is not None:
        scores = [s for s in scores if s.user_id in user_ids]
    created = 0
    risky = [s for s in scores if s.band in ("high", "medium")]
    upsell = [s for s in scores if s.band == "low"]
    for s in risky + upsell:
        if created >= limit:
            break
        if s.user_id in recent:
            continue
        offer = draft_for(db, club, s.user, s)
        if offer is not None:
            recent.add(s.user_id)
            created += 1
    db.commit()
    return created


def revenue_at_risk(db: Session, club: Club) -> float:
    """Monthly membership revenue from members in the high-risk band."""
    total = 0.0
    plans = {p.id: p for p in db.scalars(select(MembershipPlan))}
    for s in db.scalars(
        select(ChurnScore).where(ChurnScore.club_id == club.id, ChurnScore.band == "high")
    ):
        plan = plans.get((s.features or {}).get("plan_id"))
        if plan:
            total += plan.monthly_price
    return round(total, 2)
