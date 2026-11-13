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


def test_imported_member_claims_profile_by_signing_up(client, owner):
    from tests.conftest import auth as h

    client.post(
        "/api/members",
        json={"full_name": "Imported Ivy", "email": "ivy@x.io"},
        headers=h(owner["token"]),
    )
    r = client.post(
        "/api/auth/register",
        json={"email": "ivy@x.io", "password": "newpass123", "full_name": "Ivy"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["full_name"] == "Imported Ivy"  # same profile, not a new one
    again = client.post(
        "/api/auth/register",
        json={"email": "ivy@x.io", "password": "other1234", "full_name": "Ivy"},
    )
    assert again.status_code == 409  # can't be claimed twice


def test_staff_reset_password(client, owner, member):
    from tests.conftest import auth as h

    r = client.post(
        f"/api/members/{member['user']['id']}/reset-password", headers=h(owner["token"])
    )
    temp = r.json()["temporary_password"]
    login = client.post("/api/auth/login", json={"email": "member@club.test", "password": temp})
    assert login.status_code == 200


def test_staff_cannot_touch_another_clubs_data(client, owner, member, club_setup):
    from tests.conftest import auth as h
    from tests.conftest import future_slot

    other = client.post(
        "/api/auth/register-owner",
        json={
            "email": "rival@club.test",
            "password": "password123",
            "full_name": "Rival",
            "club_name": "Rival Club",
        },
    ).json()
    rh = h(other["token"])
    mid = member["user"]["id"]
    assert client.get(f"/api/members/{mid}", headers=rh).status_code == 404
    assert client.post(f"/api/members/{mid}/reset-password", headers=rh).status_code == 404
    b = client.post(
        "/api/bookings",
        json={"court_id": club_setup["courts"][0]["id"], "start_at": future_slot()},
        headers=h(member["token"]),
    ).json()
    assert client.post(f"/api/bookings/{b['id']}/cancel", headers=rh).status_code == 404
    slot = future_slot(9)
    entry = client.post(
        "/api/waitlist",
        json={"date": slot[:10], "start_hour": 9, "end_hour": 9},
        headers=h(member["token"]),
    ).json()["entry"]
    assert client.delete(f"/api/waitlist/{entry['id']}", headers=rh).status_code == 404
