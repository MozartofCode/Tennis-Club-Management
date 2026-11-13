"""Time helpers. Bookings use club-local naive datetimes; audit columns use naive UTC."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# Availability blocks members pick from: (first start hour, last start hour)
BLOCKS = {"morning": (6, 11), "afternoon": (12, 16), "evening": (17, 21)}


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def club_now(timezone: str) -> datetime:
    """Current wall-clock time at the club, as a naive datetime."""
    return datetime.now(ZoneInfo(timezone)).replace(tzinfo=None, second=0, microsecond=0)


def block_for_hour(hour: int) -> str | None:
    for name, (start, end) in BLOCKS.items():
        if start <= hour <= end:
            return name
    return None


def availability_key(dt: datetime) -> str | None:
    block = block_for_hour(dt.hour)
    return f"{DAY_KEYS[dt.weekday()]}:{block}" if block else None
