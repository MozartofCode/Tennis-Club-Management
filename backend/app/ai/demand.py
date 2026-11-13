"""Court demand forecasting.

Predicts what share of a club's courts will be booked at a given date and
hour. A small gradient-boosted model learns from recent booking history; the
strongest input is a lagged "same weekday and hour over the previous four
weeks" average, so the model never sees the day it is predicting. With too
little history it falls back to that average directly.
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, Club, Court

TRAIN_WEEKS = 12
LAG_WEEKS = 4
MIN_TRAIN_ROWS = 200
CACHE_SECONDS = 6 * 3600


@dataclass
class DemandModel:
    club_id: int
    hours: list[int]
    courts: int
    history: dict[tuple[date, int], float]  # (day, hour) -> utilization
    model: GradientBoostingRegressor | None
    trained_at: float
    mae: float | None = None  # on the most recent two weeks, held out
    rows: int = 0

    def lag_avg(self, day: date, hour: int) -> float | None:
        vals = [
            self.history[(day - timedelta(weeks=w), hour)]
            for w in range(1, LAG_WEEKS + 1)
            if (day - timedelta(weeks=w), hour) in self.history
        ]
        if not vals:
            # Further out than the lag window: use the most recent same-weekday weeks.
            vals = [
                u
                for (d, h), u in self.history.items()
                if h == hour and d.weekday() == day.weekday()
            ][-LAG_WEEKS:]
        return float(np.mean(vals)) if vals else None

    def features(self, day: date, hour: int, peak: set[tuple[bool, int]]) -> list[float]:
        weekend = day.weekday() >= 5
        lag = self.lag_avg(day, hour)
        return [
            day.weekday(),
            hour,
            float(weekend),
            float((weekend, hour) in peak),
            lag if lag is not None else 0.3,
            day.month,
        ]

    def predict(self, day: date, hour: int, peak: set[tuple[bool, int]]) -> float:
        if self.model is None:
            lag = self.lag_avg(day, hour)
            return (
                lag if lag is not None else (0.6 if ((day.weekday() >= 5, hour) in peak) else 0.25)
            )
        x = np.array([self.features(day, hour, peak)])
        return float(np.clip(self.model.predict(x)[0], 0, 1))


_cache: dict[int, DemandModel] = {}


def peak_set(club: Club) -> set[tuple[bool, int]]:
    peaks = club.peak_hours or {}
    return {(False, h) for h in peaks.get("weekday", [])} | {
        (True, h) for h in peaks.get("weekend", [])
    }


def utilization_history(db: Session, club: Club, since: date, until: date) -> dict:
    courts = db.scalar(
        select(func.count()).select_from(Court).where(Court.club_id == club.id, Court.is_active)
    )
    if not courts:
        return {}
    rows = db.execute(
        select(Booking.start_at).where(
            Booking.club_id == club.id,
            Booking.status.in_(("booked", "completed", "no_show")),
            Booking.start_at >= datetime.combine(since, datetime.min.time()),
            Booking.start_at < datetime.combine(until, datetime.min.time()),
        )
    ).scalars()
    counts: dict[tuple[date, int], int] = defaultdict(int)
    for start in rows:
        counts[(start.date(), start.hour)] += 1
    out = {}
    day = since
    while day < until:
        for hour in range(club.open_hour, club.close_hour):
            out[(day, hour)] = min(1.0, counts.get((day, hour), 0) / courts)
        day += timedelta(days=1)
    return out


def train(db: Session, club: Club, today: date) -> DemandModel:
    hours = list(range(club.open_hour, club.close_hour))
    courts = db.scalar(
        select(func.count()).select_from(Court).where(Court.club_id == club.id, Court.is_active)
    )
    since = today - timedelta(weeks=TRAIN_WEEKS + LAG_WEEKS)
    history = utilization_history(db, club, since, today)
    first_booking = db.scalar(select(func.min(Booking.start_at)).where(Booking.club_id == club.id))
    if first_booking:
        history = {k: v for k, v in history.items() if k[0] >= first_booking.date()}
    dm = DemandModel(club.id, hours, courts or 0, history, None, time.time())
    peak = peak_set(club)

    train_start = today - timedelta(weeks=TRAIN_WEEKS)
    keys = sorted(k for k in history if k[0] >= train_start and dm.lag_avg(*k) is not None)
    dm.rows = len(keys)
    if len(keys) < MIN_TRAIN_ROWS:
        return dm
    X = np.array([dm.features(d, h, peak) for d, h in keys])
    y = np.array([history[k] for k in keys])

    # Hold out the last two weeks to report accuracy, then refit on everything.
    cutoff = today - timedelta(weeks=2)
    split = np.array([d >= cutoff for d, _ in keys])
    params = dict(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=0)
    if split.any() and (~split).sum() >= MIN_TRAIN_ROWS // 2:
        holdout = GradientBoostingRegressor(**params).fit(X[~split], y[~split])
        dm.mae = float(np.mean(np.abs(holdout.predict(X[split]) - y[split])))
    dm.model = GradientBoostingRegressor(**params).fit(X, y)
    return dm


def get_model(db: Session, club: Club, today: date, refresh: bool = False) -> DemandModel:
    dm = _cache.get(club.id)
    if refresh or dm is None or time.time() - dm.trained_at > CACHE_SECONDS:
        dm = train(db, club, today)
        _cache[club.id] = dm
    return dm


def clear_cache() -> None:
    _cache.clear()
