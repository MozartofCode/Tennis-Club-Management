import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JOBS_ENABLED"] = "false"
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    from app.ai import churn, demand

    demand.clear_cache()
    churn.clear_cache()
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def owner(client):
    r = client.post(
        "/api/auth/register-owner",
        json={
            "email": "owner@club.test",
            "password": "password123",
            "full_name": "Olive Owner",
            "club_name": "Test Club",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def member(client, owner):
    r = client.post(
        "/api/auth/register",
        json={
            "email": "member@club.test",
            "password": "password123",
            "full_name": "Max Member",
            "club_id": owner["user"]["club_id"],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def club_setup(client, owner):
    """Two courts, one plan, open 7-22."""
    h = auth(owner["token"])
    c1 = client.post("/api/club/courts", json={"name": "Court 1"}, headers=h).json()
    c2 = client.post("/api/club/courts", json={"name": "Court 2", "indoor": True}, headers=h).json()
    plan = client.post(
        "/api/club/plans",
        json={"name": "Gold", "monthly_price": 120, "court_discount_pct": 20, "priority": 2},
        headers=h,
    ).json()
    return {"courts": [c1, c2], "plan": plan}


def future_slot(hour: int = 18, days: int = 2) -> str:
    from datetime import date, timedelta

    return f"{(date.today() + timedelta(days=days)).isoformat()}T{hour:02d}:00:00"


def make_member(client, owner, email: str, name: str = "Extra Member") -> dict:
    r = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": name,
            "club_id": owner["user"]["club_id"],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()
