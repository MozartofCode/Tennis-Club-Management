from tests.conftest import auth


def test_owner_signup_creates_club(client, owner):
    assert owner["user"]["role"] == "owner"
    assert owner["user"]["club_id"] is not None
    me = client.get("/api/auth/me", headers=auth(owner["token"]))
    assert me.json()["email"] == "owner@club.test"


def test_member_signup_and_login(client, member):
    assert member["user"]["role"] == "member"
    r = client.post(
        "/api/auth/login", json={"email": "MEMBER@club.test", "password": "password123"}
    )
    assert r.status_code == 200


def test_wrong_password_rejected(client, member):
    r = client.post("/api/auth/login", json={"email": "member@club.test", "password": "nope1234"})
    assert r.status_code == 401


def test_duplicate_email_rejected(client, owner):
    r = client.post(
        "/api/auth/register",
        json={"email": "owner@club.test", "password": "password123", "full_name": "X"},
    )
    assert r.status_code == 409


def test_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
