"""Stock: matching, movement signs, linking from records, reversal, status maths, API scoping (no LLM)."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from sme_copilot.agent.tools_analysis import AddTxnArgs, add_transaction
from sme_copilot.api.main import create_app
from sme_copilot.models import Business, Item, StockMovement, Transaction
from sme_copilot.security.auth import create_user
from sme_copilot.tools import stock as S
from tests.conftest import make_ctx
from tests.test_api import login

TODAY = date(2026, 10, 14)


def new_item(db, biz, name="gamcha", **kw):
    it = Item(business_id=biz.id, name=name, aliases=kw.pop("aliases", []), opening_qty=kw.pop("opening_qty", 100),
              reorder_level=kw.pop("reorder_level", 10), cost_price=kw.pop("cost_price", 50), **kw)
    db.add(it)
    db.flush()
    return it


def qty(db, biz, name="gamcha"):
    return next(r["qty"] for r in S.stock_rows(db, biz.id, TODAY) if r["name"] == name)


def test_match_item_hit_and_miss(seeded):
    db, b = seeded["db"], seeded["business"]
    it = new_item(db, b, "Gamcha", aliases=["gamchha"])
    new_item(db, b, "Lungi")
    assert S.match_item(db, b.id, "gamcha").id == it.id          # exact, case-insensitive
    assert S.match_item(db, b.id, "gamchha").id == it.id         # alias
    assert S.match_item(db, b.id, "gamchaa").id == it.id         # fuzzy >= 85
    assert S.match_item(db, b.id, "shirt") is None               # miss
    assert S.match_item(db, b.id, "") is None and S.match_item(db, b.id, None) is None


def test_match_item_other_business_invisible(seeded):
    db, b = seeded["db"], seeded["business"]
    other = Business(name="Other", sector="x", established_on=date(2020, 1, 1))
    db.add(other)
    db.flush()
    new_item(db, other, "gamcha")
    assert S.match_item(db, b.id, "gamcha") is None


@pytest.mark.parametrize("rtype,sign", [("sale", -1), ("sale_return", 1), ("purchase", 1), ("purchase_return", -1)])
def test_movement_signs(seeded, rtype, sign):
    db, b = seeded["db"], seeded["business"]
    new_item(db, b)
    res = S.link_transaction(db, b.id, 999, rtype, "gamcha", 6)
    assert res["linked"]
    assert db.scalar(select(StockMovement.qty_change)) == sign * 6


def test_sale_and_return_through_add_transaction(seeded):
    db, b = seeded["db"], seeded["business"]
    new_item(db, b)
    ctx = make_ctx(seeded)
    r = add_transaction(ctx, AddTxnArgs(text="6 ta gamcha bikri korci protitar dam 100 taka kore"))
    assert r.recorded and r.stock["linked"] and qty(db, b) == 94
    # sale_return via a mocked extraction (no LLM)
    from sme_copilot.tools import record_resolver as rr
    rr.clear_cache()
    rr._cache[rr.normalize("2 ta gamcha ferot diye gese 1500 taka")] = {
        "type": "sale_return", "item": "gamcha", "quantity": 2, "unit_price": None, "total_stated": 1500,
        "counterparty": None, "category": "sales_returns", "payment_method": "unknown"}
    r2 = add_transaction(ctx, AddTxnArgs(text="2 ta gamcha ferot diye gese 1500 taka"))
    assert r2.recorded and r2.stock["linked"] and qty(db, b) == 96
    rr.clear_cache()


def test_no_match_saves_and_asks(seeded):
    db, b = seeded["db"], seeded["business"]
    new_item(db, b, "lungi")
    r = add_transaction(make_ctx(seeded), AddTxnArgs(text="6 ta gamcha bikri korci protitar dam 100 taka kore"))
    assert r.recorded and r.transaction_id
    assert r.stock["ask_item"] and not r.stock["linked"] and r.stock["items"][0]["name"] == "lungi"
    assert db.scalar(select(StockMovement)) is None            # never guessed


def test_no_quantity_asks(seeded):
    db, b = seeded["db"], seeded["business"]
    new_item(db, b)
    res = S.link_transaction(db, b.id, 1, "sale", "gamcha", None)
    assert res["ask_item"] and not res["linked"]


def test_reversal_on_delete_and_edit(seeded):
    db, b = seeded["db"], seeded["business"]
    new_item(db, b)
    r = add_transaction(make_ctx(seeded), AddTxnArgs(text="6 ta gamcha bikri korci protitar dam 100 taka kore"))
    t = db.get(Transaction, r.transaction_id)
    assert qty(db, b) == 94
    # edit: category flipped to a customer return -> stock goes back up by 6 (sign flips)
    t.direction, t.category = "out", "sales_returns"
    S.relink_after_edit(db, t)
    assert qty(db, b) == 106
    S.reverse_for_transaction(db, t.id)                          # delete
    assert qty(db, b) == 100
    S.reverse_for_transaction(db, t.id)                          # idempotent
    assert qty(db, b) == 100
    assert db.scalars(select(StockMovement)).all().__len__() >= 4  # append-only history kept


@pytest.mark.parametrize("q,reorder,sold,status,days", [
    (0, 5, 0, "out", None), (-3, 5, 0, "out", None),
    (5, 5, 0, "low", None),                    # at reorder level
    (6, 5, 0, "ok", None),                     # no sales -> days_left null, not low
    (70, 5, 300, "low", 7.0),                  # exactly 7 days left
    (71, 5, 300, "ok", 7.1),
])
def test_status_and_days_left(seeded, q, reorder, sold, status, days):
    db, b = seeded["db"], seeded["business"]
    it = new_item(db, b, opening_qty=q + sold, reorder_level=reorder)
    if sold:
        S.add_movement(db, it, -sold, "sale")
    row = S.stock_rows(db, b.id, TODAY)[0]
    assert row["status"] == status and row["days_left"] == days


def test_restock_cost(seeded):
    db, b = seeded["db"], seeded["business"]
    new_item(db, b, "a", opening_qty=2, reorder_level=10, cost_price=5)    # (20-2)*5 = 90
    new_item(db, b, "b", opening_qty=50, reorder_level=10, cost_price=5)   # ok -> excluded
    assert S.restock_cost(S.stock_rows(db, b.id, TODAY)) == 90


def test_stock_alerts(seeded):
    from sme_copilot.forecasting.alerts import refresh_alerts
    db, b = seeded["db"], seeded["business"]
    new_item(db, b, "zip", opening_qty=0, reorder_level=10, cost_price=10_000_000)
    kinds = {a.kind: a for a in refresh_alerts(db, b, TODAY)}
    assert "out of stock" in kinds["stock_out"].title and "stock_cash" in kinds


def test_api_scoping_and_owner_only(seeded):
    db = seeded["db"]
    other = Business(name="Other Co", sector="x", established_on=date(2020, 1, 1))
    db.add(other)
    db.flush()
    create_user(db, other.id, "otherowner", "other-pass-1234", "owner", "O")
    foreign = new_item(db, other, "foreign")
    db.commit()
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        owner = login(c)
        acct = login(c, "accountant", "acct-pass-123")
        assert c.post("/api/items", json={"name": "gamcha", "opening_qty": 10}, headers=owner).status_code == 200
        assert c.post("/api/items", json={"name": "Gamcha"}, headers=owner).status_code == 409
        assert c.post("/api/items", json={"name": "x"}, headers=acct).status_code == 403
        assert c.post("/api/stock/adjust", json={"item_id": foreign.id, "qty_change": 5}, headers=owner).status_code == 404
        assert c.post("/api/stock/adjust", json={"item_id": foreign.id, "qty_change": 5}, headers=acct).status_code == 403
        rows = c.get("/api/stock", headers=owner).json()["items"]
        assert [r["name"] for r in rows] == ["gamcha"]            # foreign item invisible
        mine = rows[0]["id"]
        assert c.post("/api/stock/adjust", json={"item_id": mine, "qty_change": -4}, headers=owner).json()["qty"] == 6
        ex = c.get("/api/stock/export", headers=acct)
        assert ex.status_code == 200 and ex.content[:2] == b"PK"
        t = db.scalar(select(Transaction).where(Transaction.business_id == seeded["business"].id).limit(1))
        assert c.post("/api/stock/link", json={"transaction_id": t.id, "item_id": foreign.id, "quantity": 1},
                      headers=owner).status_code == 404


def test_create_item_keeps_the_quantity_typed_and_records_the_month_sold(seeded):
    """The Add item form asks for what is on the shelf; a month already sold must not come off that count."""
    db = seeded["db"]
    db.commit()
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        owner = login(c)
        assert c.post("/api/items", json={"name": "gamcha", "opening_qty": 40, "cost_price": 120,
                                          "sold_this_month": 15}, headers=owner).status_code == 200
        row = next(r for r in c.get("/api/stock", headers=owner).json()["items"] if r["name"] == "gamcha")
        assert row["qty"] == 40                      # the shelf count the owner typed, not 40 - 15
        assert row["sold_30d"] == 15                 # the month's sales are a movement, so days-left works
        assert row["days_left"] == 80.0              # 40 / (15 / 30)
        assert row["cost_price"] == 120
        # Nothing sold is just as valid: no movement, no sales rate.
        assert c.post("/api/items", json={"name": "lungi", "opening_qty": 5}, headers=owner).status_code == 200
        lungi = next(r for r in c.get("/api/stock", headers=owner).json()["items"] if r["name"] == "lungi")
        assert (lungi["qty"], lungi["sold_30d"], lungi["days_left"]) == (5, 0, None)


def test_delete_item_removes_its_stock_history_but_no_money_records(seeded):
    """Removing an item is owner-only, scoped to the business, and never touches the ledger."""
    db, b = seeded["db"], seeded["business"]
    it = new_item(db, b, "gamcha")
    S.add_movement(db, it, -6, "sale")
    item_id = it.id  # kept as a plain value: the row is gone before the final checks
    other = Business(name="Other Co", sector="x", established_on=date(2020, 1, 1))
    db.add(other)
    db.flush()
    create_user(db, other.id, "otherowner", "other-pass-1234", "owner", "O")
    foreign_id = new_item(db, other, "foreign").id
    db.commit()
    txns_before = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.business_id == b.id))
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        owner, acct = login(c), login(c, "accountant", "acct-pass-123")
        assert c.delete(f"/api/items/{item_id}", headers=acct).status_code == 403       # owner-only
        assert c.delete(f"/api/items/{foreign_id}", headers=owner).status_code == 404   # another business
        assert c.delete(f"/api/items/{item_id}", headers=owner).json() == {"deleted": item_id, "name": "gamcha"}
        assert c.delete(f"/api/items/{item_id}", headers=owner).status_code == 404      # already gone
        assert [r["name"] for r in c.get("/api/stock", headers=owner).json()["items"]] == []
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.item_id == item_id)) == 0
    assert db.scalar(select(func.count()).select_from(Transaction).where(Transaction.business_id == b.id)) == txns_before
