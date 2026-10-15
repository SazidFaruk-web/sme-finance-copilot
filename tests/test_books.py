"""Bookkeeping basics: parties (baki ledger)."""
import pytest
from fastapi.testclient import TestClient

from sme_copilot.api.main import create_app
from tests.test_api import login


@pytest.fixture
def client(seeded):
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        yield c


def test_customer_balances(client):
    h = login(client)
    d = client.get("/api/books/parties?kind=customer", headers=h).json()
    karim = next(p for p in d["rows"] if p["name"] == "Karim Knit Composite")
    assert karim["balance"] == 200_000 and karim["overdue"] == 120_000 and karim["invoices"] == 2
    rahman = next(p for p in d["rows"] if p["name"] == "Rahman Fashion")
    assert rahman["balance"] == 0
    assert d["total_balance"] == 200_000 and d["rows"][0]["name"] == "Karim Knit Composite"


def test_party_ledger_running_balance(client):
    h = login(client, "viewer", "viewer-pass-123")  # read-only roles can see balances
    d = client.get("/api/books/parties/ledger", params={"name": "rahman fashion"}, headers=h).json()
    assert [x["type"] for x in d["lines"]] == ["invoice", "payment"]
    assert d["lines"][0]["balance"] == 45_000 and d["balance"] == 0
    assert client.get("/api/books/parties/ledger", params={"name": "nobody"}, headers=h).status_code == 404


def test_parties_require_auth(client):
    assert client.get("/api/books/parties").status_code == 401


def _new_invoice(client, h, **kw):
    body = {"counterparty": "Nadia Garments", "lines": [{"description": "Zippers", "quantity": 100, "rate": 12},
                                                          {"description": "Buttons", "quantity": 200, "rate": 4}]}
    body.update(kw)
    r = client.post("/api/books/invoices", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_invoice_draft_send_and_statuses(client):
    h = login(client)
    inv = _new_invoice(client, h)
    assert inv["status"] == "draft" and inv["amount"] == 2000 and inv["invoice_no"].startswith("INV-")
    assert inv["due_date"] == "2026-11-13"  # 30 days after the pinned as-of date
    # drafts do not count as money owed and cannot take payments
    assert client.post(f"/api/books/invoices/{inv['id']}/payments", json={"amount": 100}, headers=h).status_code == 409
    assert client.post(f"/api/books/invoices/{inv['id']}/send", headers=h).json()["status"] == "sent"
    assert client.post(f"/api/books/invoices/{inv['id']}/send", headers=h).status_code == 409
    statuses = {i["invoice_no"]: i["status"] for i in client.get("/api/books/invoices", headers=h).json()}
    assert statuses["INV-201"] == "overdue" and statuses["INV-202"] == "paid" and statuses["INV-203"] == "sent"
    late = _new_invoice(client, h, issue_date="2026-09-01", due_date="2026-09-15", send=True)
    assert late["status"] == "overdue" and late["days_overdue"] == 29
    dup = client.post("/api/books/invoices", json={"counterparty": "X", "invoice_no": "INV-201",
                                                   "lines": [{"description": "a", "rate": 1}]}, headers=h)
    assert dup.status_code == 409


def test_partial_then_full_payment(client):
    h = login(client)
    inv = _new_invoice(client, h, send=True)
    r = client.post(f"/api/books/invoices/{inv['id']}/payments", json={"amount": 500, "channel": "bkash"}, headers=h)
    assert r.json()["status"] == "partial" and r.json()["outstanding"] == 1500
    assert client.post(f"/api/books/invoices/{inv['id']}/payments", json={"amount": 2000}, headers=h).status_code == 422
    r = client.post(f"/api/books/invoices/{inv['id']}/payments", json={"amount": 1500}, headers=h).json()
    assert r["status"] == "paid" and r["paid_date"] == "2026-10-14"
    assert client.post(f"/api/books/invoices/{inv['id']}/payments", json={"amount": 1}, headers=h).status_code == 409
    # payments became cash-in transactions and show in the party ledger
    txns = client.get(f"/api/data/transactions?ids={r['transaction_id']}", headers=h).json()["rows"]
    assert txns[0]["direction"] == "in" and txns[0]["category"] == "sales" and txns[0]["amount"] == 1500
    led = client.get("/api/books/parties/ledger", params={"name": "Nadia Garments"}, headers=h).json()
    assert [x["type"] for x in led["lines"]] == ["invoice", "payment", "payment"] and led["balance"] == 0
    detail = client.get(f"/api/books/invoices/{inv['id']}", headers=h).json()
    assert len(detail["lines"]) == 2 and [p["amount"] for p in detail["payments"]] == [500, 1500]
    actions = [e["action"] for e in client.get("/api/audit?limit=20", headers=h).json()]
    assert actions.count("record_invoice_payment") == 2 and "create_invoice" in actions


def test_supplier_bill_payment_is_cash_out(client):
    h = login(client)
    bill = _new_invoice(client, h, kind="payable", counterparty="Dhaka Zipper House", send=True)
    assert bill["invoice_no"].startswith("BILL-")
    r = client.post(f"/api/books/invoices/{bill['id']}/payments", json={"amount": 2000}, headers=h).json()
    t = client.get(f"/api/data/transactions?ids={r['transaction_id']}", headers=h).json()["rows"][0]
    assert t["direction"] == "out" and r["status"] == "paid"
    sup = client.get("/api/books/parties?kind=supplier", headers=h).json()
    assert any(p["name"] == "Dhaka Zipper House" and p["balance"] == 0 for p in sup["rows"])


def test_invoice_pdf_and_permissions(client):
    h = login(client)
    inv = _new_invoice(client, h, counterparty="<b>Evil & Co</b>", notes="Thanks <3")
    r = client.get(f"/api/books/invoices/{inv['id']}/pdf", headers=h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    hv = login(client, "viewer", "viewer-pass-123")
    assert client.post("/api/books/invoices", json={"counterparty": "X", "lines": [{"description": "a", "rate": 1}]},
                       headers=hv).status_code == 403
    assert client.post(f"/api/books/invoices/{inv['id']}/payments", json={"amount": 1}, headers=hv).status_code == 403
    assert client.get("/api/books/invoices/999999", headers=h).status_code == 404
