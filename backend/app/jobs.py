"""Background jobs: waitlist sweeps every minute, churn scoring nightly."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Club

log = logging.getLogger("courtiq.jobs")
_scheduler: BackgroundScheduler | None = None


def waitlist_sweep() -> None:
    from app.ai import waitlist

    with SessionLocal() as db:
        for club in db.scalars(select(Club)).all():
            try:
                result = waitlist.sweep(db, club)
                if result["expired"] or result["offered"]:
                    log.info("Waitlist sweep club=%s %s", club.id, result)
            except Exception:  # keep the scheduler alive
                db.rollback()
                log.exception("Waitlist sweep failed for club %s", club.id)


def start() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(waitlist_sweep, "interval", minutes=1, id="waitlist", coalesce=True)
    _scheduler.start()


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
