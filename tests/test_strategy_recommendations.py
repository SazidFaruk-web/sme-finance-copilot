from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from tests.test_api import client, login  # noqa: F401
from tests.test_pilot import post, confirm
from sme_copilot.models import Item, StockMovement, Transaction, Invoice, InvoiceLine, InvoicePayment, Business
from sme_copilot.pilot.models import GuidedCase
from sme_copilot.pilot.strategy_recommendations import candidates, load_history, recommendations, _rankings

TODAY = date(2026, 10, 14)


@pytest.fixture(autouse=True)
def reset_rankings():
    _rankings.clear()


def item(db, business, name="Sugar", opening=0, threshold=0):
    row = Item(business_id=business.id, name=name, unit="kg", opening_qty=opening, reorder_level=threshold)
    db.add(row); db.flush(); return row


def move(db, product, back, quantity, reason="sale", transaction=None):
    row = StockMovement(item_id=product.id, qty_change=-quantity if reason == "sale" else quantity,
                        reason=reason, transaction_id=transaction,
                        created_at=datetime.combine(TODAY - timedelta(days=back), datetime.min.time()))
    db.add(row); db.flush(); return row


def repeated(db, business):
    product = item(db, business)
    for back in (5, 20, 40, 60): move(db, product, back, 10, "purchase")
    db.commit(); return product


def growing(db, business):
    product = item(db, business, "Mango juice", opening=500)
    for n in range(8):
        move(db, product, n + 1, 20)
        move(db, product, n + 31, 10)
    db.commit(); return product


def test_repeated_purchases_produce_specific_bulk_idea_with_evidence(db, business):
    product = repeated(db, business)
    result = recommendations(db, business, TODAY)
    idea = next(x for x in result["suggestions"] if x["id"] == f"bulk-{product.id}")
    assert "Sugar" in idea["title"]["en"]
    assert idea["evidence"][0]["value"] == 4
    assert idea["basis"] == "records"
    assert "quote" in idea["checks"]["en"] and "storage" in idea["checks"]["en"]


def test_stock_shortage_and_excess_do_not_both_push_larger_purchases(db, business):
    low = item(db, business, "Low stock", opening=60, threshold=10)
    move(db, low, 1, 55)
    high = item(db, business, "Too much stock", opening=1000)
    for n in range(5): move(db, high, n + 1, 10)
    db.commit()
    _, rows = candidates(db, business, TODAY)
    assert next(x for x in rows if x["id"] == f"restock-{low.id}")["evidence"][0]["value"] == 5
    assert next(x for x in rows if x["id"] == f"wait-{high.id}")["signal"] == "overstock"
    assert not any(x["id"] == f"bulk-{high.id}" for x in rows)


def test_growth_can_prompt_capacity_check_but_not_equipment_purchase_approval(db, business):
    product = growing(db, business)
    _, rows = candidates(db, business, TODAY)
    equipment = next(x for x in rows if x["signal"] == "equipment")
    assert [e["value"] for e in equipment["evidence"]] == [160, 80]
    assert "capacity" in equipment["checks"]["en"] and "alone" in equipment["checks"]["en"]
    assert equipment["item"] == product.name and equipment["supporting_records"]


def test_equipment_idea_keeps_product_evidence_but_asks_which_machine(client, seeded, db):
    h = login(client); product = growing(db, seeded["business"])
    c = post(client, h, "cases", {"kind": "strategy", "suggestion_id": f"equipment-{product.id}", "request_key": str(uuid4())})
    assert c["answers"]["_strategy_suggestion"]["item"] == product.name
    assert "item" not in c["answers"]  # A growing product is not an equipment quote.
    assert c["next_question"]["id"] == "item"


def test_sparse_sales_do_not_establish_growth(db, business):
    product = item(db, business, opening=1000)
    move(db, product, 1, 100); move(db, product, 40, 1); db.commit()
    assert not any(x["signal"] == "equipment" for x in candidates(db, business, TODAY)[1])


def test_linked_movements_use_transaction_date_and_exclude_bad_links(db, business):
    product = item(db, business, opening=100)
    def transaction(back, duplicate=False, bid=None, category="sales"):
        t = Transaction(business_id=bid or business.id, txn_date=TODAY - timedelta(days=back), amount=100,
                        direction="in", category=category, item=product.name, quantity=5, is_duplicate=duplicate)
        db.add(t); db.flush(); return t
    good = transaction(40)
    # Uploaded today, but belongs in the earlier 30-day window.
    move(db, product, -1, 5, transaction=good.id)
    for t in [transaction(-1), transaction(1, duplicate=True), transaction(1, category="loan_received")]:
        move(db, product, 1, 100, transaction=t.id)
    other = Business(name="Other"); db.add(other); db.flush()
    move(db, product, 1, 100, transaction=transaction(1, bid=other.id).id)
    db.commit()
    history = load_history(db, business, TODAY)
    assert len(history["events"][product.id]) == 1
    assert history["events"][product.id][0][0] == TODAY - timedelta(days=40)


def test_cash_entries_and_invoice_payments_do_not_duplicate_stock_quantities(db, business):
    product = item(db, business, opening=100)
    t = Transaction(business_id=business.id, txn_date=TODAY, direction="in", category="sales", amount=50, item=product.name, quantity=10)
    db.add(t); db.flush(); move(db, product, 0, 10, transaction=t.id)
    inv = Invoice(business_id=business.id, kind="receivable", counterparty="Customer", amount=50, amount_paid=50,
                  issue_date=TODAY, due_date=TODAY, status="paid")
    db.add(inv); db.flush(); db.add(InvoiceLine(invoice_id=inv.id, description=product.name, quantity=10, rate=5))
    db.add(InvoicePayment(business_id=business.id, invoice_id=inv.id, amount=50, paid_on=TODAY, channel="cash", transaction_id=t.id))
    db.commit()
    assert sum(r[2] for r in load_history(db, business, TODAY)["events"][product.id]) == 10


def test_credit_invoice_lines_can_supply_missing_product_history(db, business):
    product = item(db, business)
    inv = Invoice(business_id=business.id, kind="receivable", counterparty="Customer", amount=100, amount_paid=0,
                  issue_date=TODAY, due_date=TODAY + timedelta(days=7), status="open")
    db.add(inv); db.flush(); db.add(InvoiceLine(invoice_id=inv.id, description=product.name, quantity=20, rate=5)); db.commit()
    event = load_history(db, business, TODAY)["events"][product.id][0]
    assert event[2] == 20 and event[3] == "invoice"


def test_reversals_do_not_count_as_purchase_days_or_growth(db, business):
    product = item(db, business)
    for back in (1, 8, 15):
        move(db, product, back, 10, "purchase")
        move(db, product, back, -10, "reversal:purchase")
    db.commit()
    assert not any(x["signal"] == "bulk" for x in candidates(db, business, TODAY)[1])


def test_seasonal_label_requires_two_years_and_does_not_invent_a_price_forecast(db, business):
    product = item(db, business, opening=10000)
    for year in (2024, 2025):
        for month in range(1, 7):
            for day in (1, 10, 20):
                db.add(StockMovement(item_id=product.id, qty_change=-(50 if month == 5 else 10), reason="sale",
                                     created_at=datetime(year, month, day)))
    db.commit()
    idea = next(x for x in candidates(db, business, TODAY)[1] if x["signal"] == "seasonal")
    assert "May" in idea["reason"]["en"] and "2024" in idea["reason"]["en"]
    assert "quote" in idea["checks"]["en"]
    assert "price" not in idea["reason"]["en"]


def test_new_juice_owner_gets_type_based_storage_idea_without_fabricated_history(db, business):
    business.sector = "Juice shop"; db.commit()
    idea = recommendations(db, business, TODAY)["suggestions"][0]
    assert idea["id"] == "seasonal-fruit" and idea["basis"] == "business_type"
    assert not idea["evidence"] and "safe" in idea["checks"]["en"]


def test_empty_business_gets_honest_recording_step(db, business):
    idea = recommendations(db, business, TODAY)["suggestions"][0]
    assert idea["basis"] == "missing_history" and idea["href"] == "#data"


def test_ai_cannot_prioritize_investment_ahead_of_cash_risk(db, business, monkeypatch):
    product = growing(db, business); repeated(db, business)
    db.add(Invoice(business_id=business.id, kind="payable", counterparty="Supplier", amount=200000, amount_paid=0,
                   issue_date=TODAY, due_date=TODAY + timedelta(days=2), status="open")); db.commit()
    monkeypatch.setattr("sme_copilot.pilot.question_model.select_id", lambda *args: f"equipment-{product.id}")
    result = recommendations(db, business, TODAY)
    assert result["suggestions"][0]["id"] == "protect-cash"
    assert len(result["suggestions"]) <= 3


def test_suggestions_are_read_only_scoped_and_open_a_prepared_short_case(client, seeded, db):
    h = login(client); product = repeated(db, seeded["business"])
    before = db.scalar(select(func.count()).select_from(GuidedCase))
    payload = client.get("/api/pilot/strategy", headers=h).json()
    assert db.scalar(select(func.count()).select_from(GuidedCase)) == before
    assert any(x["item"] == product.name for x in payload["suggestions"])
    c = post(client, h, "cases", {"kind": "strategy", "suggestion_id": f"bulk-{product.id}", "request_key": str(uuid4())})
    assert c["answers"]["item"] == product.name
    assert c["next_question"]["id"] == "drivers"  # no repeated item question
    assert c["answers"]["_strategy_suggestion"]["evidence"][0]["value"] == 4
    assert client.get("/api/pilot/strategy", headers=h).json()["suggestions"][0]["case_id"] == c["id"]
    other = Business(name="Other shop"); db.add(other); db.flush()
    outside = repeated(db, other)
    response = client.post("/api/pilot/cases", headers=h, json={"kind": "strategy", "suggestion_id": f"bulk-{outside.id}", "request_key": str(uuid4())})
    assert response.status_code == 409


def test_changed_stock_invalidates_suggestion_and_action_preview(client, seeded, db):
    h = login(client); product = repeated(db, seeded["business"])
    c = post(client, h, "cases", {"kind": "strategy", "suggestion_id": f"bulk-{product.id}", "request_key": str(uuid4())})
    for key, value in {"drivers": ["lower_cost"], "stage": "exploring", "priority": "supplier", "review_date": "2026-10-22"}.items():
        c = post(client, h, f"cases/{c['id']}/answer", {"version": c["version"], "question_id": key, "value": value})
    p = post(client, h, f"cases/{c['id']}/preview", {"version": c["version"], "action": "save"})
    move(db, product, 0, 100, "purchase"); db.commit()
    assert client.get(f"/api/pilot/cases/{c['id']}", headers=h).json()["suggestion_stale"]
    response = client.post(f"/api/pilot/cases/{c['id']}/confirm", headers=h, json={"version": p["version"], "token": p["preview"]["token"]})
    assert response.status_code == 409
    response = client.post(f"/api/pilot/cases/{c['id']}/preview", headers=h, json={"version": p["version"], "action": "save"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "suggestion_changed"
