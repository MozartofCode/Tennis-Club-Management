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
