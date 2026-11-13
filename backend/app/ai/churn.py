"""Churn prediction.

Scores each member's risk of leaving in the next ~6 weeks from their habits:
visits and their trend, days since the last visit, booking trend,
cancellations and no-shows, membership end date and auto-renew, lessons,
matches, and whether their regular playing partners have stopped coming.

The model is a logistic regression on standardized features, chosen because
its coefficients turn into plain-English reasons ("Visits down 60% vs the
month before"). It is trained on the club's own history with snapshots taken
in the past and labelled by what happened next. Accuracy is measured on the
most recent snapshot, which the model never saw during training (a time
split, so no look-ahead). With too little history, fixed expert weights are
used instead, with the same reasons.
"""

import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingPlayer, CheckIn, ChurnScore, Club, Membership, User
from app.timeutil import club_now

HORIZON_DAYS = 45  # "will they have left 45 days from now?"
TRAIN_SNAPSHOTS = (120, 105, 90, 75)  # days before today
TEST_SNAPSHOT = HORIZON_DAYS  # most recent snapshot whose outcome is known
HIGH, MEDIUM = 0.4, 0.15

FEATURES = [
    "visits_30",
    "visit_trend",  # log ratio of last 30 days vs the 30 before (negative = slowing)
    "days_since_visit",
    "booking_trend",
    "cancel_rate",
    "no_show_rate",
    "days_to_end",
    "auto_renew_off",
    "no_membership",
    "lesson_share",
    "matches_60",
    "partner_lost",
    "short_tenure",
]

# Used when there isn't enough history to train (signs match what the model learns).
EXPERT_WEIGHTS = {
    "visits_30": -0.5,
    "visit_trend": -0.9,
    "days_since_visit": 0.9,
    "booking_trend": -0.4,
    "cancel_rate": 0.4,
    "no_show_rate": 0.3,
    "days_to_end": -0.5,
    "auto_renew_off": 0.8,
    "no_membership": 0.3,
    "lesson_share": -0.3,
    "matches_60": -0.2,
    "partner_lost": 0.5,
    "short_tenure": 0.2,
}


@dataclass
class History:
    """Everything needed to compute features at any point in time, loaded once."""

    members: dict[int, User]
    visits: dict[int, list[datetime]] = field(default_factory=lambda: defaultdict(list))
    bookings: dict[int, list[tuple[datetime, str, str, int]]] = field(
        default_factory=lambda: defaultdict(list)
    )  # (start, status, type, booking_id)
    players: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))
    memberships: dict[int, list[Membership]] = field(default_factory=lambda: defaultdict(list))


def load_history(db: Session, club: Club) -> History:
    members = {
        u.id: u
        for u in db.scalars(select(User).where(User.club_id == club.id, User.role == "member"))
    }
    h = History(members=members)
    ids = list(members)
    if not ids:
        return h
    for user_id, at in db.execute(
        select(CheckIn.user_id, CheckIn.created_at).where(CheckIn.club_id == club.id)
    ):
        h.visits[user_id].append(at)
    for booking_id, user_id, start, status, kind in db.execute(
        select(Booking.id, BookingPlayer.user_id, Booking.start_at, Booking.status, Booking.type)
        .join(BookingPlayer, BookingPlayer.booking_id == Booking.id)
        .where(Booking.club_id == club.id)
    ):
        h.bookings[user_id].append((start, status, kind, booking_id))
        h.players[booking_id].append(user_id)
    for m in db.scalars(select(Membership).where(Membership.user_id.in_(ids))):
        h.memberships[m.user_id].append(m)
    return h


def _membership_on(h: History, user_id: int, day: date) -> Membership | None:
    for m in h.memberships.get(user_id, []):
        if m.start_date <= day <= m.end_date and m.status != "cancelled":
            return m
    return None


def features_at(h: History, user_id: int, at: datetime) -> dict:
    """Features for one member using only data from before `at`."""
    visits = [v for v in h.visits.get(user_id, []) if v < at]
    v30 = sum(1 for v in visits if v >= at - timedelta(days=30))
    v_prev = sum(1 for v in visits if at - timedelta(days=60) <= v < at - timedelta(days=30))
    last = max(visits) if visits else None
    user = h.members[user_id]
    tenure = (at - user.created_at).days if user.created_at else 365
    days_since = (at - last).days if last else min(tenure, 120)

    bookings = [b for b in h.bookings.get(user_id, []) if b[0] < at]
    b30 = [b for b in bookings if b[0] >= at - timedelta(days=30)]
    b_prev = [b for b in bookings if at - timedelta(days=60) <= b[0] < at - timedelta(days=30)]
    b60 = [b for b in bookings if b[0] >= at - timedelta(days=60)]
    b90 = [b for b in bookings if b[0] >= at - timedelta(days=90) and b[1] != "cancelled"]
    cancels = sum(1 for b in b60 if b[1] == "cancelled")
    no_shows = sum(1 for b in b60 if b[1] == "no_show")

    m = _membership_on(h, user_id, at.date())
    days_to_end = (m.end_date - at.date()).days if m else 0
    renews = bool(m and m.auto_renew)

    # Regular partners: played together 3+ times in the 30-120 days before `at`.
    partner_counts: Counter = Counter()
    for start, status, _, bid in bookings:
        if at - timedelta(days=120) <= start < at - timedelta(days=30) and status != "cancelled":
            for other in h.players.get(bid, []):
                if other != user_id:
                    partner_counts[other] += 1
    regulars = [p for p, n in partner_counts.items() if n >= 3]
    lost = [
        p
        for p in regulars
        if not any(at - timedelta(days=30) <= v < at for v in h.visits.get(p, []))
    ]

    return {
        "visits_30": v30,
        "visits_prev_30": v_prev,
        "visit_trend": math.log((v30 + 1) / (v_prev + 1)),
        "days_since_visit": min(days_since, 120),
        "booking_trend": math.log((len(b30) + 1) / (len(b_prev) + 1)),
        "bookings_30": len(b30),
        "bookings_prev_30": len(b_prev),
        "cancel_rate": cancels / len(b60) if b60 else 0.0,
        "cancels_60": cancels,
        "bookings_60": len(b60),
        "no_show_rate": no_shows / len(b60) if b60 else 0.0,
        "no_shows_60": no_shows,
        "days_to_end": max(0, min(days_to_end, 60)) if m else 0,
        "membership_end": m.end_date.isoformat() if m else None,
        "plan_id": m.plan_id if m else None,
        "auto_renew_off": float(bool(m) and not renews),
        "no_membership": float(m is None),
        "lesson_share": (
            sum(1 for b in b90 if b[2] in ("lesson", "clinic")) / len(b90) if b90 else 0.0
        ),
        "matches_60": sum(1 for b in b60 if b[2] == "match" and b[1] != "cancelled"),
        "partner_lost": float(bool(lost)),
        "lost_partner_id": lost[0] if lost else None,
        "short_tenure": float(tenure < 60),
        "tenure_days": tenure,
    }


def was_active(h: History, user_id: int, at: datetime) -> bool:
    visits = h.visits.get(user_id, [])
    recent = any(at - timedelta(days=30) <= v < at for v in visits)
    return recent or _membership_on(h, user_id, at.date()) is not None


def churned_by(h: History, user_id: int, at: datetime) -> bool:
    """Left = no membership covering that day and no visit in the 21 days before it."""
    if _membership_on(h, user_id, at.date()) is not None:
        return False
    visits = h.visits.get(user_id, [])
    return not any(at - timedelta(days=21) <= v < at for v in visits)


def dataset(h: History, now: datetime, days_ago: int) -> tuple[list[int], np.ndarray, np.ndarray]:
    at = now - timedelta(days=days_ago)
    outcome = at + timedelta(days=HORIZON_DAYS)
    ids, X, y = [], [], []
    for uid, user in h.members.items():
        if user.created_at and user.created_at >= at:
            continue
        if not was_active(h, uid, at):
            continue
        f = features_at(h, uid, at)
        ids.append(uid)
        X.append([f[k] for k in FEATURES])
        y.append(int(churned_by(h, uid, outcome)))
    return ids, np.array(X, dtype=float), np.array(y)


@dataclass
class ChurnModel:
    kind: str  # "logistic regression" | "expert weights"
    mean: np.ndarray
    std: np.ndarray
    coef: np.ndarray
    intercept: float
    metrics: dict
    trained_at: float

    def contributions(self, x: np.ndarray) -> np.ndarray:
        return self.coef * (x - self.mean) / self.std

    def score(self, x: np.ndarray) -> float:
        z = float(self.contributions(x).sum() + self.intercept)
        return 1 / (1 + math.exp(-z))


def train(h: History, now: datetime) -> ChurnModel:
    parts = [dataset(h, now, d) for d in TRAIN_SNAPSHOTS]
    X = np.vstack([p[1] for p in parts if len(p[1])]) if any(len(p[1]) for p in parts) else None
    y = np.concatenate([p[2] for p in parts]) if X is not None else None
    _, X_test, y_test = dataset(h, now, TEST_SNAPSHOT)

    if X is None or len(X) < 60 or len(set(y)) < 2 or y.sum() < 8:
        mean = X.mean(axis=0) if X is not None and len(X) else np.zeros(len(FEATURES))
        std = X.std(axis=0) if X is not None and len(X) else np.ones(len(FEATURES))
        std[std == 0] = 1
        coef = np.array([EXPERT_WEIGHTS[k] for k in FEATURES])
        model = ChurnModel("expert weights", mean, std, coef, -1.5, {}, time.time())
    else:
        mean, std = X.mean(axis=0), X.std(axis=0)
        std[std == 0] = 1
        clf = LogisticRegression(C=0.3, max_iter=1000)
        clf.fit((X - mean) / std, y)
        model = ChurnModel(
            "logistic regression",
            mean,
            std,
            clf.coef_[0],
            float(clf.intercept_[0]),
            {"training_rows": int(len(X)), "training_churn_rate": round(float(y.mean()), 3)},
            time.time(),
        )

    if len(X_test) and len(set(y_test)) == 2:
        probs = np.array([model.score(x) for x in X_test])
        flagged = probs >= HIGH
        model.metrics.update(
            {
                "test_rows": int(len(X_test)),
                "test_churn_rate": round(float(y_test.mean()), 3),
                "auc": round(float(roc_auc_score(y_test, probs)), 3),
                "precision_high": round(
                    float(precision_score(y_test, flagged, zero_division=0)), 3
                ),
                "recall_high": round(float(recall_score(y_test, flagged, zero_division=0)), 3),
                "flagged_high": int(flagged.sum()),
            }
        )
    return model


# --- Reasons ----------------------------------------------------------------


def _reason(key: str, f: dict, names: dict[int, str]) -> str | None:
    if key in ("visit_trend", "visits_30"):
        a, b = f["visits_prev_30"], f["visits_30"]
        if a > b:
            return f"Visits down {round((a - b) / a * 100)}% vs the month before ({a} → {b})"
        if b == 0:
            return "No visits in the last 30 days"
        return None
    if key == "days_since_visit":
        return f"No visit in {f['days_since_visit']} days" if f["days_since_visit"] >= 10 else None
    if key == "booking_trend":
        a, b = f["bookings_prev_30"], f["bookings_30"]
        return f"Booking less: {a} → {b} bookings a month" if a > b else None
    if key == "cancel_rate":
        n = f["cancels_60"]
        return f"Cancelled {n} of {f['bookings_60']} recent bookings" if n >= 2 else None
    if key == "no_show_rate":
        n = f["no_shows_60"]
        return f"{n} no-show{'s' if n > 1 else ''} in the last 2 months" if n else None
    if key == "days_to_end":
        if f["membership_end"] and f["days_to_end"] <= 30:
            tail = ", auto-renew is off" if f["auto_renew_off"] else ""
            return f"Membership ends in {f['days_to_end']} days{tail}"
        return None
    if key == "auto_renew_off":
        return "Switched off auto-renew" if f["auto_renew_off"] else None
    if key == "no_membership":
        return "No active membership (pays per booking)" if f["no_membership"] else None
    if key == "partner_lost":
        if f["partner_lost"]:
            name = names.get(f["lost_partner_id"], "A regular partner")
            return f"Regular partner {name} stopped playing"
        return None
    if key == "lesson_share":
        return "Not taking lessons or clinics" if f["lesson_share"] == 0 else None
    if key == "matches_60":
        return "Hasn't played a match in 2 months" if f["matches_60"] == 0 else None
    if key == "short_tenure":
        return (
            f"Joined {f['tenure_days']} days ago, still building a habit"
            if f["short_tenure"]
            else None
        )
    return None


def explain(model: ChurnModel, f: dict, names: dict[int, str], limit: int = 3) -> list[dict]:
    x = np.array([f[k] for k in FEATURES], dtype=float)
    contrib = model.contributions(x)
    order = np.argsort(-contrib)
    out, seen = [], set()
    for i in order:
        if contrib[i] <= 0.05 or len(out) >= limit:
            break
        key = FEATURES[i]
        text = _reason(key, f, names)
        # visit_trend and visits_30 describe the same thing; show it once
        group = "visits" if key in ("visit_trend", "visits_30") else key
        if text and group not in seen:
            seen.add(group)
            out.append({"key": key, "text": text, "weight": round(float(contrib[i]), 2)})
    return out


def band(score: float) -> str:
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


_models: dict[int, ChurnModel] = {}


def get_model(db: Session, club: Club, refresh: bool = False) -> ChurnModel:
    model = _models.get(club.id)
    if refresh or model is None or time.time() - model.trained_at > 6 * 3600:
        now = club_now(club.timezone)
        model = train(load_history(db, club), now)
        _models[club.id] = model
    return model


def score_club(db: Session, club: Club, refresh_model: bool = True) -> dict:
    """Score every current member and replace the club's churn scores."""
    now = club_now(club.timezone)
    h = load_history(db, club)
    model = train(h, now) if refresh_model else get_model(db, club)
    _models[club.id] = model
    names = {uid: u.full_name for uid, u in h.members.items()}
    db.execute(delete(ChurnScore).where(ChurnScore.club_id == club.id))
    counts = Counter()
    for uid, user in h.members.items():
        if not user.is_active or not was_active(h, uid, now):
            continue  # already gone; nothing left to predict
        f = features_at(h, uid, now)
        x = np.array([f[k] for k in FEATURES], dtype=float)
        s = model.score(x)
        b = band(s)
        counts[b] += 1
        db.add(
            ChurnScore(
                club_id=club.id,
                user_id=uid,
                score=round(s, 3),
                band=b,
                reasons=explain(model, f, names),
                features={k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()},
            )
        )
    db.commit()
    return {"scored": sum(counts.values()), **counts, "model": model.kind, **model.metrics}


def clear_cache() -> None:
    _models.clear()
