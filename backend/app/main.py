"""FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import jobs
from app.api import (
    analytics,
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
from app.config import REPO_ROOT, get_settings
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if get_settings().jobs_enabled:
        jobs.start()
    yield
    jobs.stop()


DEV_SECRET = "dev-only-secret-change-me-in-production-please"


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.environment == "production" and settings.jwt_secret == DEV_SECRET:
        raise RuntimeError("Set JWT_SECRET to a long random value before running in production")
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
        analytics.router,
    ):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"ok": True, "ai": settings.llm_enabled}

    # In production one container serves the built web app too (see Dockerfile).
    dist = REPO_ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            file = (dist / path).resolve()
            if path and file.is_file() and dist.resolve() in file.parents:
                return FileResponse(file)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
