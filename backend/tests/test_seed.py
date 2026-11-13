from app.db import SessionLocal
from scripts.seed import DEMO_PASSWORD, seed
from tests.conftest import auth


def test_seed_builds_a_usable_demo_club(client):
    with SessionLocal() as db:
        stats = seed(db)
    assert stats["members"] == 250
    assert stats["bookings"] > 3000
    assert stats["turned_away_at_peak"] > 0  # peak demand exceeds supply

    r = client.post(
        "/api/auth/login", json={"email": "owner@courtiq.demo", "password": DEMO_PASSWORD}
    )
    h = auth(r.json()["token"])
    members = client.get("/api/members", headers=h).json()
    assert len(members) == 250
    statuses = {m["membership_status"] for m in members}
    assert {"active", "expired", "none"} <= statuses


def test_analytics_summarises_the_club(client):
    with SessionLocal() as db:
        seed(db)
    r = client.post(
        "/api/auth/login", json={"email": "owner@courtiq.demo", "password": DEMO_PASSWORD}
    )
    data = client.get("/api/analytics", headers=auth(r.json()["token"])).json()
    assert len(data["weekly"]) == 12
    assert data["last_30"]["bookings"] > 100
    peak = [h for h in data["by_hour"] if h["weekday_peak"]]
    off = [h for h in data["by_hour"] if not h["weekday_peak"]]
    assert max(h["weekday"] for h in peak) > max(h["weekday"] for h in off) * 0.9
    assert data["members"]["total"] == 250
