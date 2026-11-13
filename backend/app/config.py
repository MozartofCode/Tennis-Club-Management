"""Application settings, loaded from environment variables / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "backend" / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        extra="ignore",
    )

    # SQLite locally; in production use the Supabase Postgres connection string.
    database_url: str = f"sqlite:///{DATA_DIR / 'courtiq.db'}"

    # Auth: the API issues its own JWTs (works the same on SQLite and Supabase Postgres).
    jwt_secret: str = "dev-only-secret-change-me-in-production-please"
    jwt_ttl_hours: int = 24 * 14

    # AI (optional): without a key the offer writer uses templates.
    anthropic_api_key: str | None = None
    offer_model: str = "claude-sonnet-5-5"

    # Email (optional): without a key, emails are logged instead of sent.
    resend_api_key: str | None = None
    email_from: str = "CourtIQ <noreply@courtiq.app>"

    # Background jobs (hold expiry, nightly churn scoring). Off in tests.
    jobs_enabled: bool = True

    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
