from tests.conftest import auth, future_slot


def test_owner_configures_club(client, owner, club_setup):
    h = auth(owner["token"])
    r = client.patch("/api/club", json={"base_price": 50, "open_hour": 6}, headers=h)
    assert r.status_code == 200 and r.json()["base_price"] == 50
    assert len(client.get("/api/club/courts", headers=h).json()) == 2
    bad = client.patch("/api/club", json={"open_hour": 22, "close_hour": 8}, headers=h)
    assert bad.status_code == 400


def test_member_cannot_change_club(client, member):
    r = client.patch("/api/club", json={"base_price": 1}, headers=auth(member["token"]))
    assert r.status_code == 403


def test_book_conflict_and_cancel(client, owner, member, club_setup):
    court = club_setup["courts"][0]["id"]
    h = auth(member["token"])
    slot = future_slot()
    r = client.post("/api/bookings", json={"court_id": court, "start_at": slot}, headers=h)
    assert r.status_code == 200, r.text
    booking = r.json()
    assert booking["price"] == 40  # default base price, no membership

    # Same court & time is taken
    owner_h = auth(owner["token"])
    clash = client.post(
        "/api/bookings",
        json={"court_id": court, "start_at": slot, "member_id": member["user"]["id"]},
        headers=owner_h,
    )
    assert clash.status_code == 409

    mine = client.get("/api/me/bookings", headers=h).json()
    assert [b["id"] for b in mine] == [booking["id"]]

    r = client.post(f"/api/bookings/{booking['id']}/cancel", headers=h)
    assert r.json()["status"] == "cancelled"
    # Slot is free again
    r = client.post("/api/bookings", json={"court_id": court, "start_at": slot}, headers=h)
    assert r.status_code == 200


def test_membership_discount_applies(client, owner, member, club_setup):
    client.post(
        f"/api/members/{member['user']['id']}/membership",
        json={"plan_id": club_setup["plan"]["id"]},
        headers=auth(owner["token"]),
    )
    r = client.post(
        "/api/bookings",
        json={"court_id": club_setup["courts"][0]["id"], "start_at": future_slot(10)},
        headers=auth(member["token"]),
    )
    body = r.json()
    assert body["price"] == 32
    assert body["price_breakdown"][0]["label"] == "Gold member"


def test_member_cannot_see_others(client, owner, member, club_setup):
    h = auth(member["token"])
    assert client.get("/api/members", headers=h).status_code == 403
    assert client.get("/api/bookings?day=2026-01-01", headers=h).status_code == 403


def test_qr_check_in(client, owner, member, club_setup):
    qr = client.get("/api/me/qr", headers=auth(member["token"])).json()
    owner_h = auth(owner["token"])
    r = client.post("/api/checkin/scan", json={"token": qr["token"]}, headers=owner_h)
    assert r.status_code == 200
    assert r.json()["status"] == "no_booking"
    again = client.post("/api/checkin/scan", json={"token": qr["token"]}, headers=owner_h)
    assert again.json()["status"] == "already"
    assert len(client.get("/api/checkin", headers=owner_h).json()) == 1
    bad = client.post("/api/checkin/scan", json={"token": "nope"}, headers=owner_h)
    assert bad.status_code == 404
    # Members can't run the kiosk
    assert (
        client.post(
            "/api/checkin/scan", json={"token": qr["token"]}, headers=auth(member["token"])
        ).status_code
        == 403
    )


def test_csv_import(client, owner, club_setup):
    csv = "Name,Email,Level,Plan\nAna Ivanovic,ana@x.io,4.0,Gold\nNo Email,,3\nBob,bob@x.io,abc,\n"
    r = client.post(
        "/api/members/import",
        files={"file": ("members.csv", csv, "text/csv")},
        headers=auth(owner["token"]),
    )
    assert r.json()["created"] == 2
    assert len(r.json()["skipped"]) == 1
    rows = client.get("/api/members", headers=auth(owner["token"])).json()
    ana = next(m for m in rows if m["email"] == "ana@x.io")
    assert ana["plan"] == "Gold" and ana["membership_status"] == "active"


def test_coach_account_and_lesson(client, owner, member, club_setup):
    oh = auth(owner["token"])
    r = client.post(
        "/api/club/coaches",
        json={"full_name": "Carla Coach", "email": "carla@x.io", "hourly_rate": 60},
        headers=oh,
    )
    temp = r.json()["temporary_password"]
    coach_id = client.get("/api/club/coaches", headers=oh).json()[0]["id"]
    r = client.post(
        "/api/bookings",
        json={
            "court_id": club_setup["courts"][1]["id"],
            "start_at": future_slot(9),
            "coach_id": coach_id,
        },
        headers=auth(member["token"]),
    )
    assert r.json()["type"] == "lesson" and r.json()["price"] == 100
    login = client.post("/api/auth/login", json={"email": "carla@x.io", "password": temp}).json()
    sched = client.get("/api/coach/schedule", headers=auth(login["token"])).json()
    assert len(sched) == 1
    students = client.get("/api/coach/students", headers=auth(login["token"])).json()
    assert students[0]["full_name"] == "Max Member"


def test_availability_grid(client, member, club_setup):
    day = future_slot()[:10]
    r = client.get(f"/api/availability?day={day}", headers=auth(member["token"])).json()
    assert len(r["courts"]) == 2
    assert len(r["cells"]) == 2 * len(r["hours"])
    assert all(c["status"] == "free" for c in r["cells"])
