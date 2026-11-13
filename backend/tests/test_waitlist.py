from datetime import timedelta

from app.db import SessionLocal
from app.models import WaitlistEntry
from app.timeutil import club_now
from tests.conftest import auth, future_slot, make_member


def fill_hour(client, owner, club_setup, slot):
    """Book every court at `slot` with two different members."""
    for i, court in enumerate(club_setup["courts"]):
        m = make_member(client, owner, f"filler{i}@x.io", f"Filler {i}")
        r = client.post(
            "/api/bookings",
            json={"court_id": court["id"], "start_at": slot},
            headers=auth(m["token"]),
        )
        assert r.status_code == 200
        yield m, r.json()


def test_freed_slot_is_offered_held_and_accepted(client, owner, member, club_setup):
    slot = future_slot(18)
    fillers = list(fill_hour(client, owner, club_setup, slot))
    h = auth(member["token"])
    join = client.post(
        "/api/waitlist", json={"date": slot[:10], "start_hour": 18, "end_hour": 18}, headers=h
    )
    assert join.status_code == 200, join.text
    assert join.json()["position"] == 1
    entry_id = join.json()["entry"]["id"]

    # A filler cancels: the slot goes on hold for the waiting member.
    filler, booking = fillers[0]
    client.post(f"/api/bookings/{booking['id']}/cancel", headers=auth(filler["token"]))
    mine = client.get("/api/waitlist/mine", headers=h).json()
    assert mine[0]["status"] == "offered"
    assert mine[0]["offer_court_name"] == booking["court_name"]
    notes = client.get("/api/me/notifications", headers=h).json()
    assert notes[0]["kind"] == "waitlist_offer"

    # Nobody else can grab the held slot.
    other = make_member(client, owner, "sneaky@x.io")
    grab = client.post(
        "/api/bookings",
        json={"court_id": booking["court_id"], "start_at": slot},
        headers=auth(other["token"]),
    )
    assert grab.status_code == 409

    accepted = client.post(f"/api/waitlist/{entry_id}/accept", headers=h)
    assert accepted.status_code == 200
    assert accepted.json()["source"] == "waitlist"
    queue = client.get("/api/waitlist", headers=auth(owner["token"])).json()
    assert queue["filled_30d"] == 1


def test_higher_tier_goes_first_and_expired_offer_moves_on(client, owner, member, club_setup):
    slot = future_slot(19)
    fillers = list(fill_hour(client, owner, club_setup, slot))
    oh = auth(owner["token"])
    premium = make_member(client, owner, "vip@x.io", "Vip Member")
    client.post(
        f"/api/members/{premium['user']['id']}/membership",
        json={"plan_id": club_setup["plan"]["id"]},
        headers=oh,
    )
    body = {"date": slot[:10], "start_hour": 19, "end_hour": 19}
    client.post("/api/waitlist", json=body, headers=auth(member["token"]))
    client.post("/api/waitlist", json=body, headers=auth(premium["token"]))

    filler, booking = fillers[1]
    client.post(f"/api/bookings/{booking['id']}/cancel", headers=auth(filler["token"]))
    vip = client.get("/api/waitlist/mine", headers=auth(premium["token"])).json()[0]
    assert vip["status"] == "offered"
    assert any("Gold member" in r for r in vip["priority_reasons"])

    # Let the hold run out, then sweep: the next member gets it.
    with SessionLocal() as db:
        e = db.get(WaitlistEntry, vip["id"])
        e.offer_expires_at = club_now("America/New_York") - timedelta(minutes=1)
        db.commit()
        from app.ai import waitlist
        from app.models import Club

        waitlist.sweep(db, db.get(Club, owner["user"]["club_id"]))
    mine = client.get("/api/waitlist/mine", headers=auth(member["token"])).json()
    assert mine[0]["status"] == "offered"


def test_decline_passes_it_on(client, owner, member, club_setup):
    slot = future_slot(20)
    fillers = list(fill_hour(client, owner, club_setup, slot))
    second = make_member(client, owner, "second@x.io")
    body = {"date": slot[:10], "start_hour": 20, "end_hour": 20}
    first_id = client.post("/api/waitlist", json=body, headers=auth(member["token"])).json()[
        "entry"
    ]["id"]
    client.post("/api/waitlist", json=body, headers=auth(second["token"]))
    filler, booking = fillers[0]
    client.post(f"/api/bookings/{booking['id']}/cancel", headers=auth(filler["token"]))
    client.post(f"/api/waitlist/{first_id}/decline", headers=auth(member["token"]))
    mine = client.get("/api/waitlist/mine", headers=auth(second["token"])).json()
    assert mine[0]["status"] == "offered"


def test_join_validates_and_suggests_alternatives(client, member, club_setup):
    h = auth(member["token"])
    past = client.post(
        "/api/waitlist", json={"date": "2020-01-01", "start_hour": 9, "end_hour": 9}, headers=h
    )
    assert past.status_code == 400
    slot = future_slot(10)
    r = client.post(
        "/api/waitlist", json={"date": slot[:10], "start_hour": 10, "end_hour": 11}, headers=h
    )
    assert r.json()["alternatives"]
    dup = client.post(
        "/api/waitlist", json={"date": slot[:10], "start_hour": 11, "end_hour": 11}, headers=h
    )
    assert dup.status_code == 409
