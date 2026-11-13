from datetime import datetime, timedelta

from app.ai import matchmaking
from app.db import SessionLocal
from app.models import Match, User
from scripts.seed import DEMO_PASSWORD, seed
from tests.conftest import auth


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    return auth(r.json()["token"]), r.json()["user"]


def test_suggestions_are_level_matched_with_bookable_quiet_slots(client):
    with SessionLocal() as db:
        seed(db)
    h, me = login(client, "member@courtiq.demo")
    sugg = client.get("/api/matches/suggestions", headers=h).json()
    assert len(sugg) == 5
    assert all(abs(s["skill_level"] - me["skill_level"]) <= 1.0 for s in sugg)
    assert sugg == sorted(sugg, key=lambda s: -s["score"])
    assert all(s["reasons"] for s in sugg)
    slots = [slot for s in sugg for slot in s["slots"]]
    assert slots and all(slot["per_person"] == round(slot["price"] / 2, 2) for slot in slots)


def test_invite_accept_books_court_and_result_updates_ratings(client):
    with SessionLocal() as db:
        seed(db)
    h, me = login(client, "member@courtiq.demo")
    s = client.get("/api/matches/suggestions", headers=h).json()[0]
    slot = s["slots"][0]
    inv = client.post(
        "/api/matches",
        json={
            "opponent_id": s["user_id"],
            "start_at": slot["start_at"],
            "court_id": slot["court_id"],
        },
        headers=h,
    )
    assert inv.status_code == 200, inv.text
    match_id = inv.json()["id"]
    dup = client.post(
        "/api/matches",
        json={"opponent_id": s["user_id"], "start_at": slot["start_at"]},
        headers=h,
    )
    assert dup.status_code == 409

    with SessionLocal() as db:
        opp_email = db.get(User, s["user_id"]).email
    oh, _ = login(client, opp_email)
    assert client.get("/api/matches/mine", headers=oh).json()["incoming"][0]["id"] == match_id
    # The inviter can't accept their own invite
    assert client.post(f"/api/matches/{match_id}/accept", headers=h).status_code == 403
    accepted = client.post(f"/api/matches/{match_id}/accept", headers=oh).json()
    assert accepted["status"] == "accepted" and accepted["booking_id"]
    mine = client.get("/api/me/bookings", headers=h).json()
    booked = next(b for b in mine if b["id"] == accepted["booking_id"])
    assert booked["type"] == "match" and len(booked["players"]) == 2

    # Too early to report
    early = client.post(f"/api/matches/{match_id}/result", json={"winner_id": me["id"]}, headers=h)
    assert early.status_code == 400
    with SessionLocal() as db:
        m = db.get(Match, match_id)
        m.proposed_start = datetime.now() - timedelta(days=1)
        before = db.get(User, me["id"]).rating
        db.commit()
    r = client.post(
        f"/api/matches/{match_id}/result",
        json={"winner_id": me["id"], "score_text": "6-4 6-3"},
        headers=h,
    )
    assert r.json()["status"] == "completed"
    with SessionLocal() as db:
        assert db.get(User, me["id"]).rating > before


def test_league_pairs_each_player_once(client):
    with SessionLocal() as db:
        seed(db)
    h, _ = login(client, "owner@courtiq.demo")
    created = client.post("/api/league/run", headers=h).json()
    assert len(created) >= 5
    players = [p for m in created for p in (m["requester_id"], m["opponent_id"])]
    assert len(players) == len(set(players))
    assert client.post("/api/league/run", headers=h).json() == []  # already paired this week


def test_clinic_suggestions_target_quiet_hours(client):
    with SessionLocal() as db:
        seed(db)
    h, _ = login(client, "owner@courtiq.demo")
    sugg = client.get("/api/clinics/suggestions", headers=h).json()
    assert sugg and all(s["demand"] <= 0.3 and s["member_count"] >= 4 for s in sugg)
    coach = client.get("/api/club/coaches", headers=h).json()[0]
    s = sugg[0]
    clinic = client.post(
        "/api/clinics",
        json={
            "court_id": s["court_id"],
            "start_at": s["start_at"],
            "coach_id": coach["id"],
            "title": "Level-up clinic",
            "invite_ids": [m["id"] for m in s["members"]],
        },
        headers=h,
    ).json()
    mh, _ = login(client, "member@courtiq.demo")
    joined = client.post(f"/api/clinics/{clinic['id']}/join", headers=mh)
    assert joined.status_code == 200 and len(joined.json()["players"]) == 1


def test_elo_expected_score():
    assert matchmaking.expected(1500, 1500) == 0.5
    assert matchmaking.expected(1700, 1500) > 0.7
