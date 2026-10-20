"""Scanning: a code finds its item and its price, an unknown code stays unknown, and codes never collide."""
from __future__ import annotations

from fastapi.testclient import TestClient

from sme_copilot.api.main import create_app
from sme_copilot.demo import trade_book as T
from sme_copilot.models import Business
from tests.test_api import login


def test_check_digit_is_a_real_ean13():
    assert T._ean13("400638133393") == "4006381333931"      # the textbook example
    assert all(len(T._ean13(f"2{n:011d}")) == 13 for n in range(5))


def test_scan_finds_the_item_and_its_price(seeded):
    db, b = seeded["db"], seeded["business"]
    from datetime import date
    T.seed_stock(db, b.id, "food", date(2026, 10, 14))
    codes = T.seed_barcodes(db, b.id)
    assert codes and len({c.code for c in codes}) == len(codes)   # one per item, none repeated
    db.commit()
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        owner, acct = login(c), login(c, "accountant", "acct-pass-123")
        rows = {r["name"]: r for r in c.get("/api/stock", headers=owner).json()["items"]}
        fry = rows["Chicken fry"]
        assert fry["barcodes"], "the stock list carries the code so it can be printed or shown"

        hit = c.get("/api/stock/barcode", params={"code": fry["barcodes"][0]}, headers=owner).json()
        assert hit["found"] is True
        assert hit["item"]["name"] == "Chicken fry" and hit["item"]["price"] == 120
        assert hit["item"]["qty"] == fry["qty"]                   # what is left, so the seller can see it

        miss = c.get("/api/stock/barcode", params={"code": "0000000000000"}, headers=owner).json()
        assert miss["found"] is False and miss["item"] is None    # never matched to something close

        other = rows["Samosa"]["id"]
        assert c.post("/api/stock/barcode", json={"code": "2999999999999", "item_id": other},
                      headers=acct).status_code == 403            # owner only
        assert c.post("/api/stock/barcode", json={"code": "2999999999999", "item_id": other},
                      headers=owner).status_code == 200
        assert c.get("/api/stock/barcode", params={"code": "2999999999999"},
                     headers=owner).json()["item"]["name"] == "Samosa"
        clash = c.post("/api/stock/barcode", json={"code": "2999999999999", "item_id": fry["id"]}, headers=owner)
        assert clash.status_code == 409 and "Samosa" in clash.json()["detail"]


def test_codes_do_not_leak_between_businesses(seeded):
    from datetime import date
    db, b = seeded["db"], seeded["business"]
    T.seed_stock(db, b.id, "food", date(2026, 10, 14))
    mine = T.seed_barcodes(db, b.id)[0].code
    other = Business(name="Other Co", sector="x", established_on=date(2020, 1, 1))
    db.add(other)
    db.flush()
    T.seed_stock(db, other.id, "food", date(2026, 10, 14))
    db.commit()
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        owner = login(c)
        assert c.get("/api/stock/barcode", params={"code": mine}, headers=owner).json()["found"] is True
        theirs = [bc.code for bc in T.seed_barcodes(db, other.id)]
        for code in theirs:
            assert c.get("/api/stock/barcode", params={"code": code}, headers=owner).json()["found"] is False
