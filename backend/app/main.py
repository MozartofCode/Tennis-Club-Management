"""FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import jobs
from app.api import (
    auth,
    bookings,
    checkin,
    club,
    coach,
    matches,
    me,
    members,
    pricing,
    retention,
    waitlist,
)
from app.config import get_settings
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if get_settings().jobs_enabled:
        jobs.start()
    yield
    jobs.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CourtIQ API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        auth.router,
        club.router,
        members.router,
        bookings.router,
        checkin.router,
        me.router,
        coach.router,
        pricing.router,
        waitlist.router,
        retention.router,
        matches.router,
    ):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"ok": True, "ai": settings.llm_enabled}

    return app


app = create_app()
