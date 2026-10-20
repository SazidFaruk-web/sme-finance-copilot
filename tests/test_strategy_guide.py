from uuid import uuid4

import pytest

from tests.test_api import client, login  # noqa: F401
from tests.test_pilot import post, confirm
from sme_copilot.pilot.question_model import parse_choice


@pytest.mark.parametrize('content', ['{"id":"storage_setup"}', '```json\n{"id":"storage_setup"}\n```', 'storage_setup'])
def test_local_model_markdown_fenced_choices_are_accepted(content):
    assert parse_choice(content, ["storage_setup", "priority"]) == "storage_setup"


@pytest.mark.parametrize('content', ['{"id":"buy_now"}', '["priority"]', '{"id": 1}', 'Choose priority because it is best', '```json\n{"id":"priority"}\n``` then buy now'])
def test_model_routing_remains_bounded(content):
    assert parse_choice(content, ["storage_setup", "priority"]) is None


def test_strategy_model_switch_is_independent_of_other_workflow_ordering(monkeypatch):
    from types import SimpleNamespace
    from sme_copilot.pilot import question_model
    from sme_copilot.llm_providers import registry
    monkeypatch.setattr(question_model, "get_settings", lambda: SimpleNamespace(pilot_question_model=False, strategy_question_model=True))
    fake = SimpleNamespace(default_profile="local", config={"profiles": {"local": {}}},
                           info=lambda name: SimpleNamespace(external=False, adapter="openai_compatible"))
    monkeypatch.setattr(registry, "get_registry", lambda: fake)
    provider = SimpleNamespace(chat=lambda *args, **kwargs: SimpleNamespace(content='```json\n{"id":"storage_setup"}\n```'))
    monkeypatch.setattr(registry, "ProviderRegistry", lambda **kwargs: SimpleNamespace(get=lambda name: provider))
    assert question_model.select_id({"purpose": "strategy_followup"}, ["storage_setup"]) == "storage_setup"
    assert question_model.select_id({"goal": "loan"}, ["storage_setup"]) is None


def begin(client, h, plan="seasonal"):
    return post(client, h, "cases", {"kind": "strategy", "plan_type": plan, "request_key": str(uuid4())})


def answer(client, h, case, key, value):
    return post(client, h, f"cases/{case['id']}/answer", {"version": case["version"], "question_id": key, "value": value})


def finish(client, h, case, **changes):
    values = dict(item="Mango pulp (kg)", drivers=["availability"], stage="exploring",
                  storage_setup="no", priority="money", demand_signal="guess", review_date="2026-10-22") | changes
    count = 0
    while case["next_question"]:
        key = case["next_question"]["id"]
        case = answer(client, h, case, key, values[key]); count += 1
    return case, count


def test_short_flow_uses_choices_and_stops_before_financial_questionnaire(client):
    h = login(client); c, count = finish(client, h, begin(client, h))
    assert count == 5
    assert c["result"]["status"] == "strategy_start"
    assert c["result"]["preliminary"] and not c["result"]["metrics"]
    assert c["can_deepen"] and not c["checkpoint_due"]
    assert c["result"]["regulatory_status"] == "needs_review"
    assert "storage" in c["result"]["reason"]["en"]
    done, _ = confirm(client, h, c)
    assert done["result"]["preliminary"] and done["result"]["effects"]["alert_id"]


def test_llm_receives_actual_choice_answers_and_routing_is_stable(client, monkeypatch):
    calls = []
    def select(payload, allowed):
        calls.append((payload, allowed)); return "priority"
    monkeypatch.setattr("sme_copilot.pilot.question_model.select_id", select)
    h = login(client); c = begin(client, h)
    for key, value in dict(item="Private supplier name not for model", drivers=["lower_cost", "availability"], stage="quote").items():
        c = answer(client, h, c, key, value)
    assert c["next_question"]["id"] == "priority"
    assert c["next_question"]["selected_by"] == "model"
    assert len(calls) == 1
    assert calls[0][0]["answers"]["drivers"] == ["lower_cost", "availability"]
    assert "Private supplier" not in str(calls)
    for _ in range(2):
        refreshed = client.get(f"/api/pilot/cases/{c['id']}", headers=h).json()
        assert refreshed["next_question"]["id"] == "priority"
    assert len(calls) == 1


def test_equipment_and_storage_followups_change_with_owner_responses(client, monkeypatch):
    monkeypatch.setattr("sme_copilot.pilot.question_model.select_id", lambda *args: None)
    h = login(client)
    equipment, _ = finish(client, h, begin(client, h, "equipment"), drivers=["growth"], item="Freezer")
    assert equipment["answers"]["_strategy_followup"] == "demand_signal"
    assert "Test demand" in equipment["result"]["reason"]["en"]
    bulk, _ = finish(client, h, begin(client, h, "bulk"), drivers=["lower_cost"])
    assert bulk["answers"]["_strategy_followup"] == "priority"
    assert "bill money" in bulk["result"]["reason"]["en"]


def test_model_cannot_invent_question_or_financial_answers(client, monkeypatch):
    monkeypatch.setattr("sme_copilot.pilot.question_model.select_id", lambda *args: "buy_now_without_checks")
    h = login(client); c, _ = finish(client, h, begin(client, h))
    assert c["answers"]["_strategy_question_source"] == "rules"
    assert "unit_cost" not in c["answers"]
    r = client.post(f"/api/pilot/cases/{c['id']}/answer", headers=h,
                    json={"version": c["version"], "question_id": "_strategy_depth", "value": "costs"})
    assert r.status_code == 422


@pytest.mark.parametrize("value", [[], ["made_up"], ["lower_cost", "lower_cost"], "lower_cost", [True]])
def test_multi_select_values_are_validated(client, value):
    h = login(client); c = answer(client, h, begin(client, h), "item", "Sugar (kg)")
    r = client.post(f"/api/pilot/cases/{c['id']}/answer", headers=h,
                    json={"version": c["version"], "question_id": "drivers", "value": value})
    assert r.status_code == 422


def test_unknown_answers_and_no_reminder_can_save_direction_without_inventing_amounts(client):
    h = login(client); c, count = finish(client, h, begin(client, h), item=None, drivers=None, stage=None, storage_setup=None, review_date=None)
    done, _ = confirm(client, h, c)
    assert count <= 5 and not done["result"]["metrics"]
    assert "alert_id" not in done["result"]["effects"]


def test_exact_costs_are_opt_in_and_simplifying_keeps_saved_answers(client):
    h = login(client); c, _ = finish(client, h, begin(client, h))
    deep = post(client, h, f"cases/{c['id']}/control", {"version": c["version"], "action": "deepen"})
    assert deep["next_question"] and not deep["result"].get("metrics")
    deep = answer(client, h, deep, "quantity", 50)
    simple = post(client, h, f"cases/{c['id']}/control", {"version": deep["version"], "action": "simplify"})
    assert simple["result"]["preliminary"] and simple["answers"]["quantity"] == 50
    deep = post(client, h, f"cases/{c['id']}/control", {"version": simple["version"], "action": "deepen"})
    assert deep["answers"]["quantity"] == 50
    changed = answer(client, h, deep, "item", "Sugar (kg)")
    assert "quantity" not in changed["answers"]
    assert changed["preview"] == {}


def test_legacy_detailed_case_can_move_to_short_guide_without_losing_values(client):
    h = login(client)
    c = post(client, h, "cases", {"kind": "strategy", "plan_type": "bulk", "strategy_mode": "detailed", "request_key": str(uuid4())})
    c = answer(client, h, c, "quantity", 40)
    c = post(client, h, f"cases/{c['id']}/control", {"version": c["version"], "action": "simplify"})
    c, _ = finish(client, h, c, item="Sugar (kg)", drivers=["lower_cost"])
    # Changing the item deliberately discards quotes/quantities for a different purchase.
    assert c["result"]["preliminary"]


def test_answer_edits_invalidate_preview_and_revisit_relevant_followup(client):
    h = login(client); c, _ = finish(client, h, begin(client, h, "bulk"), drivers=["lower_cost"])
    p = post(client, h, f"cases/{c['id']}/preview", {"version": c["version"], "action": "save"})
    changed = answer(client, h, p, "drivers", ["availability"])
    assert changed["preview"] == {} and "priority" not in changed["answers"]
    assert changed["next_question"]["id"] == "storage_setup"
    r = client.post(f"/api/pilot/cases/{c['id']}/confirm", headers=h,
                    json={"version": p["version"], "token": p["preview"]["token"]})
    assert r.status_code == 409
