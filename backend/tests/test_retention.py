from app.ai import offers
from app.db import SessionLocal
from scripts.seed import DEMO_PASSWORD, seed
from tests.conftest import auth


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    return auth(r.json()["token"])


def test_churn_board_scores_and_explains(client):
    with SessionLocal() as db:
        seed(db)
    h = login(client, "owner@courtiq.demo")
    board = client.get("/api/churn", headers=h).json()
    assert board["model"]["kind"] == "logistic regression"
    assert board["model"]["auc"] > 0.7  # time-split holdout
    high = [r for r in board["rows"] if r["band"] == "high"]
    assert high and all(r["reasons"] for r in high)
    assert board["rows"] == sorted(board["rows"], key=lambda r: -r["score"])
    # members can't see it
    assert client.get("/api/churn", headers=login(client, "member@courtiq.demo")).status_code == 403


def test_offer_draft_approve_send_redeem(client):
    with SessionLocal() as db:
        seed(db)
    h = login(client, "owner@courtiq.demo")
    created = client.post("/api/offers/generate", json={"limit": 5}, headers=h).json()["created"]
    assert created == 5
    drafts = client.get("/api/offers?status=draft", headers=h).json()
    assert all(d["written_by"] == "template" for d in drafts)  # no API key in tests
    d = drafts[0]
    edited = client.patch(
        f"/api/offers/{d['id']}", json={"message": "Edited by the owner"}, headers=h
    ).json()
    assert edited["message"] == "Edited by the owner"
    sent = client.post(f"/api/offers/{d['id']}/send", headers=h).json()
    assert sent["status"] == "sent"
    # Cooldown: generating again doesn't duplicate offers for the same members
    client.post("/api/offers/generate", json={"limit": 50}, headers=h)
    ids = [o["user_id"] for o in client.get("/api/offers", headers=h).json()]
    assert len(ids) == len(set(ids))

    # The member sees and claims it
    with SessionLocal() as db:
        from app.models import User

        email = db.get(User, d["user_id"]).email
    mh = login(client, email)
    mine = client.get("/api/me/offers", headers=mh).json()
    assert mine[0]["id"] == d["id"]
    assert client.post(f"/api/me/offers/{d['id']}/redeem", headers=mh).json()["status"] == (
        "redeemed"
    )


def test_offer_rules():
    class S:
        band = "high"
        features = {}

        def __init__(self, keys):
            self.reasons = [{"key": k} for k in keys]

    assert offers.plan_for(S(["auto_renew_off"]), {}).kind == "renewal_discount"
    assert offers.plan_for(S(["partner_lost", "visit_trend"]), {}).kind == "match_intro"
    assert offers.plan_for(S(["visit_trend"]), {}).kind == "free_session"
    assert offers.plan_for(None, {"visits_30": 8, "lesson_share": 0}).kind == "lesson_upsell"
    assert offers.plan_for(None, {"visits_30": 1, "lesson_share": 0}) is None


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text, stop="end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop


def _writer(monkeypatch, text, stop="end_turn"):
    from app.config import get_settings
    from app.models import Club, User

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    calls = {}

    class FakeMessages:
        def create(self, **kw):
            calls.update(kw)
            return _Resp(text, stop)

    class FakeClient:
        def __init__(self, **kw):
            self.beta = type("B", (), {"messages": FakeMessages()})()

    monkeypatch.setattr(offers.anthropic, "Anthropic", FakeClient)
    club, user = Club(name="Riverside"), User(full_name="Ana Silva", skill_level=3.5)
    return offers.write_message(club, user, offers.PLANS["renewal"], ["Membership ends"], []), calls


def test_claude_message_is_used_when_valid(monkeypatch):
    (title, msg, by), calls = _writer(
        monkeypatch, '{"title": "Stay with us, Ana", "message": "Renew now and get 15% off."}'
    )
    assert by == "claude" and title == "Stay with us, Ana"
    assert calls["output_config"]["format"]["type"] == "json_schema"
    assert calls["fallbacks"] == "default"


def test_claude_message_falls_back_when_offer_missing_or_refused(monkeypatch):
    (_, _, by), _ = _writer(monkeypatch, '{"title": "Hi", "message": "Come back soon!"}')
    assert by == "template"  # the 15% offer wasn't stated
    (_, _, by), _ = _writer(monkeypatch, "", stop="refusal")
    assert by == "template"
