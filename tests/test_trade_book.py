"""Demo books: a kitchen gets food names and food stock, and the stock history explains today's numbers."""
from __future__ import annotations

from datetime import date

from sme_copilot.demo import trade_book as T
from sme_copilot.models import Party
from sme_copilot.tools import stock as S

TODAY = date(2026, 10, 14)


def test_each_business_gets_the_book_that_matches_what_it_sells():
    assert T.pick_book("Rokeya's Kitchen", "homemade food sold through Facebook") == "food"
    assert T.pick_book("Ruhamas Cake") == "food"
    assert T.pick_book("Tanvir Mobile Corner", "mobile phone accessories shop") == "electronics"
    assert T.pick_book("Boighor Book Corner", "bookshop near Rajshahi University") == "books"
    assert T.pick_book("Rafi Fashion") == "clothing"
    assert T.pick_book("Something Unknown Ltd") == T.DEFAULT_BOOK      # never leaves a business empty


def test_a_kitchen_is_seeded_with_food_not_phone_accessories(seeded):
    db, b = seeded["db"], seeded["business"]
    for kind in ("customer", "supplier"):
        T.seed_parties(db, b.id, kind, "food")
    names = {p.name for p in db.query(Party).filter(Party.business_id == b.id)}
    assert "Bondor Bazar Chicken House" in names and "Saif Ahmed" in names
    assert not any("Shenzhen" in n or "Power Bank" in n for n in names)
    for kind in ("customer", "supplier"):
        assert len([p for p in db.query(Party).filter(Party.business_id == b.id, Party.kind == kind)]) == T.TARGET


def test_seeded_stock_has_history_behind_its_numbers(seeded):
    db, b = seeded["db"], seeded["business"]
    T.seed_stock(db, b.id, "food", TODAY)
    rows = {r["name"]: r for r in S.stock_rows(db, b.id, TODAY)}
    fry = rows["Chicken fry"]
    assert fry["unit"] == "piece"
    assert fry["sold_30d"] > 0 and fry["qty"] > 0          # counted from movements, not written in
    assert fry["days_left"] is not None                    # a sales rate exists, so days-left can be worked out
    assert fry["status"] in ("ok", "low")
    assert all(r["sold_30d"] > 0 for r in rows.values())   # every seeded item has a month of sales behind it


def test_seeding_twice_adds_nothing_and_keeps_names_with_activity(seeded):
    db, b = seeded["db"], seeded["business"]
    T.seed_parties(db, b.id, "customer", "food")
    assert T.seed_parties(db, b.id, "customer", "food") == []    # already there, nothing duplicated
    assert T.seed_stock(db, b.id, "food", TODAY) and T.seed_stock(db, b.id, "food", TODAY) == []
