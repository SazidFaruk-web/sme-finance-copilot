"""Goal roadmaps: reading the owner's sentence, pricing it, and the month-by-month plan.

Nothing here contacts a model or the network; the reviewed wording and the offline price catalog
are what a deployment without either must fall back to.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from sme_copilot.roadmap import engine, narrative, prices
from sme_copilot.roadmap.facts import Facts, MonthFact
from sme_copilot.roadmap.goal import read_amount, read_horizon, read_rules, strip_price_words

from tests.test_api import client, login  # noqa: F401 fixtures


# ----------------------------------------------------------------------- reading the sentence
@pytest.mark.parametrize("text,expected", [
    ("i want to buy a Big oven that costs around 2.5 lakhs of taka", 250_000),
    ("another place of my own that costs around 20 lakhs taka", 2_000_000),
    ("দাম প্রায় ৮০ হাজার টাকা", 80_000),
    ("delivery van, about 5,50,000", 550_000),
    ("budget 45k", 45_000),
    ("৳1,20,000 freezer", 120_000),
    ("a 60 litre gas oven", None),          # a capacity is not a price
    ("two deck oven", None),
])
def test_read_amount(text, expected):
    assert read_amount(text) == expected


@pytest.mark.parametrize("text,months", [
    ("delivery van within 2 years", 24),
    ("in 6 months", 6),
    ("আগামী বছর", 12),
    ("a commercial oven", None),
])
def test_read_horizon(text, months):
    assert read_horizon(text) == months


def test_item_wording_drops_the_price_clause():
    assert strip_price_words("i want to buy a Big oven that costs around 2.5 lakhs of taka") == "Big oven"
    # A sentence that is only a price keeps its words rather than becoming empty.
    assert strip_price_words("around 2.5 lakh") != ""


def test_read_rules_without_a_model():
    goal = read_rules("i want to add a small chicken grilling machine")
    assert goal.item == "small chicken grilling machine"
    assert goal.category == "equipment"
    assert goal.amount is None and goal.amount_from == "unknown"


# ----------------------------------------------------------------------- prices
def test_catalog_price_is_a_dated_range_not_a_quote():
    estimate = prices.catalog_price("commercial oven")
    assert estimate is not None
    assert estimate.source == "catalog"
    assert estimate.low < estimate.amount < estimate.high
    assert estimate.reviewed and estimate.note["en"]


def test_owner_price_always_wins():
    estimate = prices.estimate("commercial oven", amount=180_000)
    assert estimate.source == "owner" and estimate.amount == 180_000


def test_unknown_item_has_no_invented_price():
    estimate = prices.estimate("a thing nobody sells")
    assert estimate.source == "unknown" and estimate.amount is None


def test_online_lookup_is_refused_in_local_only_mode(monkeypatch):
    from sme_copilot.config import reset_settings_cache
    monkeypatch.setenv("GOAL_PRICE_LOOKUP", "true")
    monkeypatch.setenv("LOCAL_ONLY_MODE", "true")
    reset_settings_cache()
    try:
        assert prices.lookup_available() is False
        assert prices.web_price("commercial oven") is None
    finally:
        reset_settings_cache()


def test_trimmed_average_needs_several_figures():
    assert prices._trimmed_average([100_000.0, 120_000.0]) is None
    amount, low, high = prices._trimmed_average([90_000.0, 100_000.0, 110_000.0, 120_000.0, 900_000.0])
    assert 100_000 <= amount <= 120_000  # the outlier is trimmed away
    assert low <= amount <= high


# ----------------------------------------------------------------------- the engine
def make_facts(*, surplus=18_000.0, spare=74_000.0, months=7, season=True) -> Facts:
    f = Facts(today="2026-10-20", months_of_history=months, record_count=1500, cash_now=160_000.0,
              monthly_in=92_000.0, monthly_out=74_000.0, monthly_surplus=surplus,
              best_month_surplus=surplus * 2, worst_month_surplus=-1500.0, reserve=74_000.0,
              spare_cash=spare, owed_to_you=22_700.0, bills_to_pay=11_400.0, committed_monthly=11_800.0,
              season_known=season, confidence="good")
    if season:
        pattern = {3: 1.46, 4: 1.12, 5: 1.26, 6: 0.71, 7: 0.63, 8: 0.92, 9: 0.91}
        for month, index in pattern.items():
            f.months.append(MonthFact(month=f"2026-{month:02d}", money_in=92_000 * index, money_out=74_000.0,
                                      surplus=surplus, index=index,
                                      label="peak" if index >= 1.2 else "low" if index <= 0.8 else "normal"))
    return f


def plan_for(amount, **kw):
    goal = read_rules("a commercial oven")
    price = prices.estimate(goal.item, amount=amount)
    return engine.build(goal, price, make_facts(**kw.pop("facts", {})), **kw)


def test_affordable_today_is_a_quick_win():
    plan = plan_for(30_000)
    assert plan.strategy == "quick_win" and plan.template == "quick-win"
    assert plan.months_needed == 0 and plan.feasible
    assert plan.from_cash_now == 30_000


def test_only_half_of_spare_cash_is_committed_up_front():
    plan = plan_for(250_000)
    assert plan.from_cash_now == pytest.approx(37_000, abs=1)   # half of 74,000 spare
    assert plan.from_cash_now < make_facts().spare_cash


def test_monthly_amount_leaves_a_margin_under_the_recorded_surplus():
    plan = plan_for(250_000)
    assert 0 < plan.monthly_amount <= make_facts().monthly_surplus * engine.SAFETY_SHARE
    assert plan.monthly_amount % engine.ROUND_TO == 0


def test_busy_months_are_asked_for_more_than_quiet_ones():
    plan = plan_for(250_000)
    by_season = {m.season: m.amount for m in plan.month_plan}
    assert by_season["peak"] > by_season["normal"] > by_season["low"]
    # The whole schedule still adds up to exactly what is needed.
    assert plan.month_plan[-1].cumulative == pytest.approx(250_000 - plan.from_cash_now, abs=1)


def test_no_recorded_surplus_cannot_produce_a_savings_plan():
    plan = plan_for(250_000, facts={"surplus": 0.0, "spare": 0.0})
    assert plan.feasible is False and plan.template == "gap-review"
    assert "no_surplus" in plan.reasons and plan.monthly_amount == 0


def test_a_price_we_do_not_know_produces_no_dates():
    goal = read_rules("something unusual")
    plan = engine.build(goal, prices.estimate("something unusual"), make_facts())
    assert plan.feasible is False and plan.buy_month is None and "no_price" in plan.reasons


def test_a_goal_far_beyond_the_records_is_not_dressed_up_as_a_loan():
    plan = plan_for(2_000_000)
    assert plan.feasible is False and plan.template == "gap-review"
    assert plan.strategy == "out_of_reach"
    # The saving steps stop at a review date instead of running for years.
    assert [p.kind for p in plan.phases][-1] == "review"


def test_a_deadline_the_savings_cannot_meet_offers_a_split_not_a_promise():
    plan = plan_for(250_000, horizon_months=6)
    assert plan.strategy == "save_then_borrow" and plan.template == "split-rail"
    assert plan.to_borrow > 0 and plan.repay_months
    assert plan.repay_months <= engine.MAX_REPAY_MONTHS
    assert "quote_before_borrowing" in plan.watchouts


def test_repayment_longer_than_the_limit_is_refused():
    # A small surplus cannot service the shortfall on a large goal in any sensible time.
    plan = plan_for(2_000_000, horizon_months=12, facts={"surplus": 4_000.0, "spare": 5_000.0})
    assert plan.feasible is False
    assert plan.strategy == "out_of_reach"


def test_every_template_id_is_one_the_front_end_knows():
    for amount in (30_000, 60_000, 90_000, 150_000, 250_000, 2_000_000):
        for horizon in (None, 6, 12, 24):
            plan = plan_for(amount, horizon_months=horizon)
            assert plan.template in engine.TEMPLATES, (amount, horizon, plan.template)


def test_mostly_funded_goals_use_the_gauge():
    # Half the spare cash already covers most of the price, and more than two months remain.
    plan = plan_for(68_000, facts={"spare": 70_000.0})
    assert plan.from_cash_now >= plan.target * 0.5 and plan.months_needed > 2
    assert plan.template == "runway-gauge"


def test_a_two_month_plan_stays_two_plain_steps():
    plan = plan_for(60_000, facts={"spare": 70_000.0})
    assert plan.months_needed == 2 and plan.template == "two-step"


def test_illustrative_finance_is_absent_unless_asked_for():
    assert plan_for(250_000, horizon_months=6).illustrative_finance is None
    shown = plan_for(250_000, horizon_months=6, illustrative=True).illustrative_finance
    assert shown and shown["illustrative"] is True and shown["monthly_low"] < shown["monthly_high"]


# ----------------------------------------------------------------------- the wording
def test_reviewed_wording_covers_every_step_in_every_language():
    goal = read_rules("a commercial oven")
    plan = plan_for(250_000)
    for language in ("en", "bn", "zh"):
        words = narrative.written_by_rules(plan, goal, language)
        assert words["written_by"] == "rules" and words["headline"] and words["subtitle"]
        assert len(words["phases"]) == len(plan.phases)
        assert all(p["title"] and p["summary"] and p["actions"] for p in words["phases"])


def test_model_prose_containing_a_figure_is_rejected():
    assert narrative._clean("Save steadily each month", narrative.MAX_SUMMARY)
    assert narrative._clean("Save 13,500 each month", narrative.MAX_SUMMARY) is None
    assert narrative._clean("মাসে ১৩৫০০ টাকা রাখুন", narrative.MAX_SUMMARY) is None
    assert narrative._clean("<b>Save</b>", narrative.MAX_SUMMARY) is None
    assert narrative._clean("x" * 500, narrative.MAX_SUMMARY) is None


def test_the_model_is_never_shown_an_amount():
    goal = read_rules("a commercial oven")
    plan = plan_for(250_000)
    shape = narrative._shape(plan, goal, make_facts())
    import json

    text = json.dumps(shape)
    for figure in (str(int(plan.target)), str(int(plan.monthly_amount)), str(int(plan.from_cash_now))):
        assert figure not in text


def test_write_falls_back_to_reviewed_wording_with_no_model():
    goal = read_rules("a commercial oven")
    plan = plan_for(250_000)
    assert narrative.write(plan, goal, make_facts(), use_model=False)["written_by"] == "rules"


# ----------------------------------------------------------------------- the API
def post_goal(client, h, text, **extra):
    body = {"text": text, "request_key": str(uuid4()), "language": "en", **extra}
    response = client.post("/api/strategy/goals", headers=h, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_goal_context_reports_what_the_planner_knows(client, seeded):
    h = login(client)
    data = client.get("/api/strategy/goal-context", headers=h).json()
    assert "monthly_surplus" in data["facts"] and "cash_now" in data["facts"]
    assert data["price_lookup_available"] is False  # off unless an operator turns it on


def test_create_read_and_adjust_a_goal(client, seeded):
    h = login(client)
    created = post_goal(client, h, "i want to buy a commercial oven, about 2.5 lakh")
    assert created["goal"]["item"]
    assert created["price"]["amount"] == 250_000 and created["price"]["source"] == "owner"
    assert created["plan"]["template"] in engine.TEMPLATES
    assert created["narrative"]["headline"]

    listed = client.get("/api/strategy/goals", headers=h).json()
    assert [row["id"] for row in listed] == [created["id"]]

    changed = client.patch(f"/api/strategy/goals/{created['id']}", headers=h,
                           json={"amount": 120_000}).json()
    assert changed["price"]["amount"] == 120_000
    assert changed["plan"]["months_needed"] <= created["plan"]["months_needed"]


def test_creating_a_goal_twice_with_one_key_returns_the_same_plan(client, seeded):
    h = login(client)
    key = str(uuid4())
    first = client.post("/api/strategy/goals", headers=h,
                        json={"text": "a deep freezer", "request_key": key, "language": "en"}).json()
    second = client.post("/api/strategy/goals", headers=h,
                         json={"text": "a deep freezer", "request_key": key, "language": "en"}).json()
    assert first["id"] == second["id"]


def test_goals_are_scoped_to_one_business(client, seeded, db):
    from sme_copilot.models import Business
    from sme_copilot.security.auth import create_user

    h = login(client)
    mine = post_goal(client, h, "a deep freezer")
    other = Business(name="Someone Else", sector="retail")
    db.add(other)
    db.flush()
    create_user(db, other.id, "stranger", "stranger-pass-123", "owner", "Stranger")
    db.commit()
    theirs = login(client, "stranger", "stranger-pass-123")
    assert client.get(f"/api/strategy/goals/{mine['id']}", headers=theirs).status_code == 404
    assert client.get("/api/strategy/goals", headers=theirs).json() == []


def test_a_viewer_cannot_create_or_delete_a_goal(client, seeded):
    owner = login(client)
    created = post_goal(client, owner, "a deep freezer")
    viewer = login(client, "viewer", "viewer-pass-123")
    assert client.post("/api/strategy/goals", headers=viewer,
                       json={"text": "a van", "request_key": str(uuid4()), "language": "en"}).status_code == 403
    assert client.delete(f"/api/strategy/goals/{created['id']}", headers=viewer).status_code == 403
    # Reading a plan the owner made is allowed.
    assert client.get(f"/api/strategy/goals/{created['id']}", headers=viewer).status_code == 200


def test_online_lookup_is_refused_when_the_operator_has_not_enabled_it(client, seeded):
    h = login(client)
    created = post_goal(client, h, "a deep freezer")
    response = client.patch(f"/api/strategy/goals/{created['id']}", headers=h, json={"search_price": True})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "lookup_unavailable"


def test_a_plan_goes_stale_when_the_records_move_on(client, seeded, db):
    from sme_copilot.models import Transaction

    h = login(client)
    created = post_goal(client, h, "a deep freezer")
    assert created["stale"] is False
    db.add(Transaction(business_id=seeded["business"].id, txn_date=date(2026, 10, 13), amount=50_000,
                       direction="in", category="sales", description="A large order"))
    db.commit()
    assert client.get(f"/api/strategy/goals/{created['id']}", headers=h).json()["stale"] is True


def test_deleting_a_goal_leaves_the_records_alone(client, seeded, db):
    from sme_copilot.models import Transaction

    h = login(client)
    created = post_goal(client, h, "a deep freezer")
    before = db.query(Transaction).count()
    assert client.delete(f"/api/strategy/goals/{created['id']}", headers=h).status_code == 200
    assert client.get(f"/api/strategy/goals/{created['id']}", headers=h).status_code == 404
    assert db.query(Transaction).count() == before


def test_wording_is_reused_while_the_plan_keeps_its_shape(client, seeded, monkeypatch):
    """Changing a price must not pay the cost of another local model run."""
    h = login(client)
    created = post_goal(client, h, "a commercial oven, about 2.5 lakh")
    shape = created["narrative"]["shape"]
    assert shape

    calls = []
    original = narrative.write

    def counted(*a, **kw):
        calls.append(1)
        return original(*a, **kw)

    monkeypatch.setattr(narrative, "write", counted)
    # A price nudge that leaves the same steps in the same seasons reuses the wording.
    same = client.patch(f"/api/strategy/goals/{created['id']}", headers=h, json={"amount": 249_000}).json()
    assert same["narrative"]["shape"] == shape and not calls
    # A price that changes the shape of the plan is written afresh.
    different = client.patch(f"/api/strategy/goals/{created['id']}", headers=h, json={"amount": 20_000}).json()
    assert different["narrative"]["shape"] != shape and calls
