from datetime import datetime, timedelta

from app.ai.pricing import Adjustment, PricingContext, demand_adjustment, price_slot
from app.models import Club, Court


class FixedModel:
    def __init__(self, value: float):
        self.value = value

    def predict(self, day, hour, peak):
        return self.value


def make_ctx(demand: float, mode="on", fills=None, now=None, discount=None, **club_kw):
    settings = dict(
        name="T",
        base_price=40,
        min_price=25,
        max_price=60,
        max_surge_pct=35,
        max_discount_pct=30,
        pricing_mode=mode,
        open_hour=7,
        close_hour=22,
    )
    club = Club(**(settings | club_kw))
    return PricingContext(
        club=club,
        now=now or datetime(2026, 1, 5, 8, 0),
        model=FixedModel(demand),
        peak=set(),
        courts=4,
        fills=fills or {},
        discount=discount,
    )


COURT = Court(id=1, name="C1")
SLOT = datetime(2026, 1, 7, 18, 0)


def test_busy_hour_surcharges_up_to_the_limit():
    q = price_slot(make_ctx(0.99), COURT, SLOT)
    assert q.price == 54  # +35%
    assert q.adjustments[0].label.startswith("Busy hour")


def test_quiet_hour_discounts():
    q = price_slot(make_ctx(0.05), COURT, SLOT)
    assert q.price == 28  # -30%
    assert q.adjustments[0].pct == -30


def test_middling_demand_keeps_standard_price():
    assert price_slot(make_ctx(0.45), COURT, SLOT).price == 40


def test_actual_fill_overrides_a_low_forecast():
    fills = {(SLOT.date(), SLOT.hour): 4}  # every court already booked
    assert price_slot(make_ctx(0.1, fills=fills), COURT, SLOT).price == 54


def test_owner_price_range_always_wins():
    q = price_slot(make_ctx(0.99, max_price=45), COURT, SLOT)
    assert q.price == 45
    assert any("price range" in a.label for a in q.adjustments)


def test_last_minute_deal_respects_discount_cap():
    now = SLOT - timedelta(hours=2)
    q = price_slot(make_ctx(0.05, now=now), COURT, SLOT)
    assert q.price == 28  # -30% quiet + -10% last minute, capped at -30%
    assert any(a.label == "Capped by your limits" for a in q.adjustments)


def test_suggest_mode_charges_standard_but_shows_suggestion():
    q = price_slot(make_ctx(0.99, mode="suggest"), COURT, SLOT)
    assert q.price == 40 and q.suggested == 54
    assert q.adjustments == [] and q.dynamic


def test_member_discount_stacks_after_dynamic_price():
    disc = Adjustment("Plus member", -15)
    q = price_slot(make_ctx(0.99, discount=disc), COURT, SLOT)
    assert q.price == round(54 * 0.85, 2)


def test_demand_adjustment_is_monotonic():
    club = Club(max_surge_pct=35, max_discount_pct=30)
    pcts = []
    for d in [i / 20 for i in range(21)]:
        a = demand_adjustment(d, club)
        pcts.append(a.pct if a else 0)
    assert pcts == sorted(pcts)
