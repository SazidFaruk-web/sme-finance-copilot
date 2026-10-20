"""Named customers and suppliers: matching, the owner's answer winning, and what a quick entry files."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from sme_copilot.api.main import create_app
from sme_copilot.models import Invoice, Party
from sme_copilot.tools import parties as P
from tests.test_api import login

TODAY = date(2026, 10, 14)


def new_party(db, biz, name="Saif Telecom (PK)", kind="customer", **kw):
    p = Party(business_id=biz.id, kind=kind, name=name, aliases=kw.pop("aliases", []), **kw)
    db.add(p)
    db.flush()
    return p


def new_invoice(db, biz, counterparty, amount=1000, kind="receivable", days_ago=10, paid=0.0):
    i = Invoice(business_id=biz.id, kind=kind, invoice_no=f"T-{counterparty[:4]}-{days_ago}", counterparty=counterparty,
                amount=amount, amount_paid=paid, issue_date=TODAY - timedelta(days=days_ago),
                due_date=TODAY - timedelta(days=days_ago - 30), status="open")
    db.add(i)
    db.flush()
    return i


def test_match_is_exact_alias_or_a_suggestion_but_never_a_guess(seeded):
    db, b = seeded["db"], seeded["business"]
    saif = new_party(db, b, "Saif Telecom (PK)", aliases=["Saif PK"])
    new_party(db, b, "Nasrin Electronics")

    assert P.match(db, b.id, "customer", "saif telecom (pk)")["exact"] is True      # same name, any case
    assert P.match(db, b.id, "customer", "Saif PK")["exact"] is True                # a confirmed spelling
    close = P.match(db, b.id, "customer", "Saif Telecom PK")                        # a typo away
    assert close["exact"] is False and close["party"].id == saif.id and close["score"] >= 85
    assert P.match(db, b.id, "customer", "Rahman Brothers") is None                 # nobody close
    assert P.match(db, b.id, "customer", "") is None
    assert P.match(db, b.id, "supplier", "Saif Telecom (PK)") is None               # wrong side of the book


def test_a_confirmed_answer_outlives_later_matching(seeded):
    """The owner's own link is locked: a name that matches someone else must not move the invoice."""
    db, b = seeded["db"], seeded["business"]
    saif = new_party(db, b, "Saif Telecom (PK)")
    nasrin = new_party(db, b, "Nasrin Electronics")
    inv = new_invoice(db, b, "Nasrin Electronics", amount=5000)

    assert P.resolve(db, b.id, "customer")[inv.id] == nasrin.id      # by name alone it is Nasrin's
    P.link(db, inv.id, saif.id, locked=True)                         # the owner says it is really Saif's
    assert P.resolve(db, b.id, "customer")[inv.id] == saif.id
    P.remember_alias(db, saif, "Nasrin Electronics")
    assert P.resolve(db, b.id, "customer")[inv.id] == saif.id        # still Saif's, not re-matched away
    assert P.detail(db, b.id, saif, TODAY)["invoices"] == 1
    assert P.detail(db, b.id, nasrin, TODAY)["invoices"] == 0


def test_rows_count_real_money_and_keep_names_only_on_invoices_visible(seeded):
    db, b = seeded["db"], seeded["business"]
    saif = new_party(db, b, "Saif Telecom (PK)")
    new_invoice(db, b, "Saif Telecom (PK)", amount=8000, days_ago=40, paid=3000)
    new_invoice(db, b, "Saif Telecom (PK)", amount=2000, days_ago=10)
    new_invoice(db, b, "Walk-in Shop", amount=500, days_ago=5)      # never named by the owner

    rows = {r["name"]: r for r in P.rows(db, b.id, "customer", TODAY)}
    mine = rows["Saif Telecom (PK)"]
    assert mine["named"] is True and mine["id"] == saif.id
    assert (mine["invoices"], mine["invoiced"], mine["paid"], mine["balance"]) == (2, 10000.0, 3000.0, 7000.0)
    assert mine["overdue"] == 5000.0                                 # only the one past its due date
    assert mine["every_days"] == 30.0 and mine["regular"] is True
    assert rows["Walk-in Shop"]["named"] is False                    # shown, but not on the owner's list


def test_party_api_add_edit_lookup_and_remove(seeded):
    db, b = seeded["db"], seeded["business"]
    new_invoice(db, b, "Saif Telecom (PK)", amount=4000)
    db.commit()
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        owner, acct = login(c), login(c, "accountant", "acct-pass-123")
        assert c.post("/api/parties", json={"kind": "customer", "name": "x"}, headers=acct).status_code == 403

        made = c.post("/api/parties", json={"kind": "customer", "name": "Saif Telecom (PK)",
                                            "phone": "01911234569", "email": "saif@example.com"}, headers=owner)
        assert made.status_code == 200
        pid = made.json()["id"]
        assert made.json()["invoices"] == 1 and made.json()["balance"] == 4000.0   # picks up the invoice at once
        assert c.post("/api/parties", json={"kind": "customer", "name": "saif telecom (pk)"},
                      headers=owner).status_code == 409                            # already on the list

        look = c.get("/api/parties/match/lookup", params={"kind": "customer", "name": "Saif Telecom PK"},
                     headers=owner).json()
        assert look["exact"] is False and look["suggestion"]["id"] == pid          # close: only ever a suggestion

        assert c.patch(f"/api/parties/{pid}", json={"note": "Pays by bKash"}, headers=owner).json()["note"] == "Pays by bKash"
        assert c.get(f"/api/parties/{pid}", headers=owner).json()["phone"] == "01911234569"
        assert c.delete(f"/api/parties/{pid}", headers=owner).json()["name"] == "Saif Telecom (PK)"
        assert c.get(f"/api/parties/{pid}", headers=owner).status_code == 404
        rows = c.get("/api/parties", params={"kind": "customer"}, headers=owner).json()["rows"]
        assert [r["named"] for r in rows if r["name"] == "Saif Telecom (PK)"] == [False]  # invoice kept, card gone


def test_quick_entry_asks_before_filing_under_a_close_name_then_files_it(seeded):
    """'Sold 10 biriyani to Saif' must not assume Saif Telecom (PK); once confirmed it files and invoices."""
    db, b = seeded["db"], seeded["business"]
    new_party(db, b, "Saif Telecom (PK)")
    db.commit()
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        owner = login(c)
        text = "sold 10 biriyani to Saif Telecom PK for 2500 taka cash"

        asked = c.post("/api/data/entry", json={"text": text}, headers=owner).json()["data"]
        assert asked["recorded"] is False and asked["needs_confirm"] is True
        assert asked["party"]["name"] == "Saif Telecom (PK)"            # a question, not an assumption

        pid = asked["party"]["id"]
        done = c.post("/api/data/entry", json={"text": text, "party_id": pid}, headers=owner).json()["data"]
        assert done["recorded"] is True
        assert done["party"]["name"] == "Saif Telecom (PK)" and done["party"]["invoice_no"]

        d = c.get(f"/api/parties/{pid}", headers=owner).json()
        assert d["invoices"] == 1 and d["invoiced"] == 2500.0 and d["balance"] == 0.0   # paid at the counter
        assert "saif telecom pk" in [a.lower() for a in d["aliases"]]    # the spelling is remembered


def test_quick_entry_left_as_written_when_the_owner_says_no(seeded):
    db, b = seeded["db"], seeded["business"]
    new_party(db, b, "Saif Telecom (PK)")
    db.commit()
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        owner = login(c)
        out = c.post("/api/data/entry", json={"text": "sold 10 biriyani to Saif Telecom PK for 2500 taka cash",
                                              "party_declined": True}, headers=owner).json()["data"]
        assert out["recorded"] is True and out["party"] is None
        rows = c.get("/api/parties", params={"kind": "customer"}, headers=owner).json()["rows"]
        assert next(r for r in rows if r["name"] == "Saif Telecom (PK)")["invoices"] == 0


def test_a_shortened_name_is_offered_not_missed(seeded):
    """Owners write "shanto" for Shanto Chicken; character similarity alone scores that 60 and misses it."""
    db, b = seeded["db"], seeded["business"]
    shanto = new_party(db, b, "Shanto Chicken", kind="supplier")
    new_party(db, b, "Bondor Bazar Chicken House", kind="supplier")

    hit = P.match(db, b.id, "supplier", "shanto")
    assert hit is not None and hit["party"].id == shanto.id and hit["exact"] is False
    assert P.match(db, b.id, "supplier", "chicken") is None      # fits both names, so it stays a question
    assert P.match(db, b.id, "supplier", "sh") is None           # too short to mean anything


def test_buying_from_a_supplier_asks_then_files_the_bill(seeded):
    """A purchase names a supplier, so the question and the bill belong on the supplier side of the book."""
    db, b = seeded["db"], seeded["business"]
    new_party(db, b, "Shanto Chicken", kind="supplier")
    db.commit()
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        owner = login(c)
        text = "bought chicken from shanto 5000 taka"   # the rules parser reads this with no model installed

        asked = c.post("/api/data/entry", json={"text": text, "confirmed": True}, headers=owner).json()["data"]
        assert asked["recorded"] is False and asked["needs_confirm"] is True
        assert asked["party"]["name"] == "Shanto Chicken" and asked["party"]["kind"] == "supplier"

        pid = asked["party"]["id"]
        done = c.post("/api/data/entry", json={"text": text, "confirmed": True, "party_id": pid},
                      headers=owner).json()["data"]
        assert done["recorded"] is True and done["party"]["invoice_no"].startswith("BILL")

        d = c.get(f"/api/parties/{pid}", headers=owner).json()
        assert d["invoices"] == 1 and d["invoiced"] == 5000.0
        assert "shanto" in [a.lower() for a in d["aliases"]]      # the short name is learned
