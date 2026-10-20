from datetime import date

import pytest
from sqlalchemy import select

from tests.test_api import client, login  # noqa: F401
from tests.test_pilot import post, confirm
from sme_copilot.models import Business, Transaction
from sme_copilot.pilot.models import CaseDocument, ReminderJob
from sme_copilot.pilot.strategy import assess, strategy_questions, ideas


def start(client, h, kind, **answers):
    """Keep regression coverage of existing detailed comparisons."""
    from uuid import uuid4
    c = post(client, h, "cases", {"kind": kind, "strategy_mode": "detailed", "request_key": str(uuid4())})
    while c["next_question"]:
        key = c["next_question"]["id"]
        c = post(client, h, f"cases/{c['id']}/answer", {"version": c["version"], "question_id": key, "value": answers[key]})
    return c


def stock_answers(**changes):
    return dict(plan_type="seasonal", item="Frozen mango pulp, kg", evidence="Recorded winter orders",
                buy_date="2026-10-25", months=4, quantity=100, unit_cost=50, quote_source="Supplier quote 17 Oct",
                setup=100, later_price=100, later_source="Owner estimate based on previous invoices",
                monthly_use=30, existing_stock=0, capacity=110, safe_months=6, loss_percent=10,
                monthly_storage=100, finance_cost=100, cash=50000, commitments=10000, reserve=5000,
                storage_plan="Supplier cold-chain protocol; power backup to verify", rule_notes=None,
                review_date="2026-10-22") | changes


def equipment_answers(**changes):
    base = stock_answers(plan_type="equipment")
    for key in ("later_price", "later_source", "monthly_use", "existing_stock", "capacity",
                "safe_months", "loss_percent", "monthly_storage", "finance_cost"):
        base.pop(key)
    return base | dict(item="Freezer", quantity=2, unit_cost=20000, months=12, cash=500000,
                       needed_capacity=700, current_capacity=300, added_capacity=200,
                       extra_receipts=10000, extra_costs=4000, slow_receipts=5000,
                       capacity_check="200 litres each; backup and floor space checked") | changes


def test_storage_full_cost_and_lower_demand():
    r = assess(stock_answers(), date(2026, 10, 17))
    assert r["metrics"]["needed_now"] == 5100
    assert r["metrics"]["running_cost"] == 500
    assert r["metrics"]["plan_benefit"] == 3400
    assert r["metrics"]["slow_benefit"] == 400
    assert r["metrics"]["protected_money_left"] == 29400
    assert r["status"] == "strategy_review"
    assert r["regulatory_status"] == "needs_review"
    assert r["review_required"]


@pytest.mark.parametrize("change", [
    {"capacity": 99}, {"safe_months": 3}, {"monthly_storage": 2000},
    {"existing_stock": 120}, {"loss_percent": 100}, {"cash": 17000},
])
def test_cheap_stock_does_not_override_constraints(change):
    assert assess(stock_answers(**change), date(2026, 10, 17))["status"] == "strategy_rethink"


@pytest.mark.parametrize("field", ["cash", "commitments", "unit_cost", "loss_percent", "evidence", "safe_months"])
def test_unknown_is_not_zero(field):
    r = assess(stock_answers(**{field: None}), date(2026, 10, 17))
    assert r["status"] == "need_information" and not r["metrics"]


def test_existing_stock_consumed_first_and_no_invented_resale_value():
    r = assess(stock_answers(existing_stock=70), date(2026, 10, 17))
    assert r["metrics"]["plan_benefit"] == -600
    assert r["metrics"]["slow_benefit"] == -5600
    assert r["metrics"]["unused_units"] == 40


def test_equipment_full_purchase_cost_and_all_running_costs():
    r = assess(equipment_answers(), date(2026, 10, 17))
    assert r["metrics"]["plan_benefit"] == 31900
    assert r["metrics"]["slow_benefit"] == -28100
    assert r["status"] == "strategy_rethink"
    assert r["metrics"]["payback_months"] == 6.68
    assert r["metrics"]["equipment_units_needed"] == 2
    assert assess(equipment_answers(quantity=1.5), date(2026, 10, 17))["status"] == "need_information"


def test_equipment_checks_current_capacity_before_expansion():
    r = assess(equipment_answers(current_capacity=800, slow_receipts=10000), date(2026, 10, 17))
    assert r["status"] == "strategy_rethink"
    assert r["metrics"]["equipment_units_needed"] == 0


def test_business_context_and_model_failure_have_honest_fallback(monkeypatch):
    monkeypatch.setattr("sme_copilot.pilot.question_model.select_id", lambda *args: None)
    b = Business(name="Juice corner", sector="food", prefs={"about": "Mango juice"})
    r = ideas(b)
    assert r["source"] == "rules" and r["ideas"][0]["id"] == "seasonal"
    assert len(r["ideas"]) == 3


def test_plan_persistence_scope_permissions_and_single_confirmation(client, db):
    h = login(client)
    c = start(client, h, "strategy", **stock_answers())
    done, payload = confirm(client, h, c)
    assert done["result"]["human_review"] == "pending"
    assert done["result"]["regulatory_status"] == "needs_review"
    again = post(client, h, f"cases/{c['id']}/confirm", payload)
    assert again["result"]["effects"] == done["result"]["effects"]
    assert len(list(db.scalars(select(CaseDocument).where(CaseDocument.case_id == c["id"])))) == 1
    job = db.scalar(select(ReminderJob).where(ReminderJob.case_id == c["id"]))
    assert job.kind == "review"
    assert not list(db.scalars(select(Transaction).where(Transaction.reference == f"CASE-{c['id']}")))
    # Use the seeded business through the case instead of relying on its name or ID.
    from sme_copilot.pilot.models import GuidedCase
    b = db.get(Business, db.get(GuidedCase, c["id"]).business_id)
    b.sector = "Changed business activity"; db.commit()
    assert client.get(f"/api/pilot/cases/{c['id']}", headers=h).json()["stale"]


def test_branch_edits_drop_irrelevant_answers_and_invalidate_preview(client):
    h = login(client); c = start(client, h, "strategy", **stock_answers())
    p = post(client, h, f"cases/{c['id']}/preview", {"version": c["version"], "action": "save"})
    changed = post(client, h, f"cases/{c['id']}/answer",
                   {"version": p["version"], "question_id": "plan_type", "value": "equipment"})
    assert "loss_percent" not in changed["answers"]
    assert not changed["preview"]
    assert client.post(f"/api/pilot/cases/{c['id']}/confirm", headers=h,
                       json={"version": p["version"], "token": p["preview"]["token"]}).status_code == 409


@pytest.mark.parametrize("value", ["NaN", "Infinity", -1, 101])
def test_invalid_loss_percentage_rejected(client, value):
    h = login(client)
    c = post(client, h, "cases", {"kind": "strategy", "plan_type": "bulk", "strategy_mode": "detailed", "request_key": "strategy-invalid"})
    assert client.post(f"/api/pilot/cases/{c['id']}/answer", headers=h,
                       json={"version": c["version"], "question_id": "loss_percent", "value": value}).status_code == 422


def test_unknown_and_expired_date_cannot_be_saved_as_complete_plan(client):
    h = login(client); c = start(client, h, "strategy", **stock_answers(commitments=None))
    assert c["result"]["status"] == "need_information"
    r = client.post(f"/api/pilot/cases/{c['id']}/preview", headers=h, json={"version": c["version"], "action": "save"})
    assert r.status_code == 422
    # An incomplete owner can still save a follow-up without a positive recommendation.
    done, _ = confirm(client, h, c, "wait")
    assert done["result"]["status"] == "need_information"


def test_viewer_cannot_start_strategy(client):
    h = login(client, "viewer", "viewer-pass-123")
    assert client.post("/api/pilot/cases", headers=h,
                       json={"kind": "strategy", "request_key": "viewer-strategy"}).status_code == 403


def test_other_business_cannot_read_or_answer_a_plan(client, db):
    from sme_copilot.security.auth import create_user
    h = login(client); c = start(client, h, "strategy", **stock_answers())
    other = Business(name="Other shop"); db.add(other); db.flush()
    create_user(db, other.id, "other-owner", "other-pass-123", "owner", "Other")
    db.commit()
    outsider = login(client, "other-owner", "other-pass-123")
    assert client.get(f"/api/pilot/cases/{c['id']}", headers=outsider).status_code == 404
    assert client.post(f"/api/pilot/cases/{c['id']}/answer", headers=outsider,
                       json={"version": c["version"], "question_id": "cash", "value": 1}).status_code == 404


def test_review_reminder_does_not_trigger_sms(client, db):
    from sme_copilot.pilot.worker import due_jobs
    h = login(client); c = start(client, h, "strategy", **stock_answers())
    done, _ = confirm(client, h, c)
    job = db.scalar(select(ReminderJob).where(ReminderJob.case_id == c["id"]))
    assert job.id not in due_jobs(db, date(2026, 10, 22)).get(job.business_id, [])


def test_unsure_owner_can_save_a_followup_without_picking_a_plan(client):
    h = login(client)
    c = start(client, h, "strategy", plan_type=None, review_date="2026-10-22")
    assert c["result"]["status"] == "need_information"
    done, _ = confirm(client, h, c, "wait")
    assert done["result"]["effects"]["alert_id"]
    assert not done["result"]["metrics"]
