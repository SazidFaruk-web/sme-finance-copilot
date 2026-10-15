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


Q3 = "period=custom&start=2026-07-01&end=2026-09-30"


def test_profit_and_loss_report(client):
    h = login(client)
    r = client.get(f"/api/books/reports/pnl?{Q3}", headers=h).json()
    lines = dict(r["rows"])
    assert lines["Sales (revenue)"] == 900_000 and lines["Gross profit"] == 450_000
    assert lines["  Salary"] == -135_000 and lines["Operating profit"] == 180_000
    assert "50.0%" in r["notes"][0]


def test_cash_flow_report_ties_out(client):
    h = login(client)
    rows = dict(client.get(f"/api/books/reports/cashflow?{Q3}", headers=h).json()["rows"])
    assert rows["Opening cash"] + rows["Net cash flow"] == rows["Closing cash"] == 380_000
    assert rows["Money in"] == 900_000 and rows["Money out"] == -720_000


def test_aging_report_buckets(client):
    h = login(client)
    r = client.get("/api/books/reports/aging", headers=h).json()
    assert r["header"][1:5] == ["Not yet due", "0-30 days", "31-60 days", "61+ days"]
    assert r["rows"][0] == ["Karim Knit Composite", 80_000, 0, 120_000, 0, 200_000]
    assert client.get("/api/books/reports/aging?party=payable", headers=h).json()["rows"] == [["Total", 0, 0, 0, 0, 0]]


def test_report_periods_and_validation(client):
    h = login(client)
    assert client.get("/api/books/reports/pnl?period=month", headers=h).json()["start"] == "2026-10-01"
    assert client.get("/api/books/reports/pnl?period=quarter", headers=h).json()["start"] == "2026-10-01"
    assert client.get("/api/books/reports/pnl?period=year", headers=h).json()["start"] == "2026-01-01"
    assert client.get("/api/books/reports/pnl?period=last_month", headers=h).json()["end"] == "2026-09-30"
    assert client.get("/api/books/reports/pnl?period=custom", headers=h).status_code == 422
    assert client.get("/api/books/reports/pnl?period=bogus", headers=h).status_code == 422
    assert client.get("/api/books/reports/balance", headers=h).status_code == 422


def test_report_exports(client):
    h = login(client)
    r = client.get(f"/api/books/reports/pnl?{Q3}&fmt=csv", headers=h)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    assert "Operating profit,180000.0" in r.text and "attachment" in r.headers["content-disposition"]
    r = client.get(f"/api/books/reports/cashflow?{Q3}&fmt=pdf", headers=h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    actions = [e["action"] for e in client.get("/api/audit?limit=10", headers=h).json()]
    assert actions.count("export_report") == 2


def test_transaction_search_and_filters(client):
    h = login(client)
    get = lambda qs: client.get(f"/api/data/transactions?limit=500&{qs}", headers=h).json()["rows"]  # noqa: E731
    rent = get("q=RENT")
    assert len(rent) == 3 and all("rent" in r["description"].lower() for r in rent)
    assert {r["counterparty"] for r in get("q=karim")} == {"Karim Knit"}
    aug = get("start=2026-08-01&end=2026-08-31")
    assert len(aug) == 5 and all(r["date"].startswith("2026-08") for r in aug)
    assert all(r["direction"] == "in" for r in get("direction=in")) and len(get("direction=in")) == 3
    assert get("q=karim&direction=out") == []


def test_edit_transaction_fields_audited(client):
    h = login(client)
    row = client.get("/api/data/transactions?q=courier&limit=1", headers=h).json()["rows"][0]
    r = client.patch(f"/api/data/transactions/{row['id']}", json={"amount": 16000, "txn_date": "2026-09-16",
                                                                   "description": "Courier (fixed)"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 16000 and r.json()["date"] == "2026-09-16"
    ev = next(e for e in client.get("/api/audit?limit=5", headers=h).json() if e["action"] == "edit_transaction")
    assert ev["inputs"]["before"]["amount"] == 15000 and ev["inputs"]["after"]["amount"] == 16000
    assert client.patch(f"/api/data/transactions/{row['id']}", json={"amount": -5}, headers=h).status_code == 422


def test_delete_any_transaction_and_undo(client):
    h = login(client)
    row = client.get("/api/data/transactions?q=rent&limit=1", headers=h).json()["rows"][0]
    assert row["source"] != "manual"  # imported rows can be deleted too (into the trash)
    d = client.delete(f"/api/books/transactions/{row['id']}", headers=h).json()
    assert client.get(f"/api/data/transactions?ids={row['id']}", headers=h).json()["rows"] == []
    r = client.post(f"/api/books/transactions/restore/{d['trash_id']}", headers=h).json()
    back = client.get(f"/api/data/transactions?ids={r['restored']}", headers=h).json()["rows"][0]
    assert {k: back[k] for k in ("date", "amount", "category", "description", "source_row")} == \
        {k: row[k] for k in ("date", "amount", "category", "description", "source_row")}
    assert client.post(f"/api/books/transactions/restore/{d['trash_id']}", headers=h).status_code == 404
    actions = [e["action"] for e in client.get("/api/audit?limit=5", headers=h).json()]
    assert "delete_transaction" in actions and "restore_transaction" in actions


def test_delete_undo_restores_stock(client):
    h = login(client)
    item = client.post("/api/items", json={"name": "Zipper", "opening_qty": 100}, headers=h).json()
    e = client.post("/api/data/entry", json={"text": "sold 10 zipper for 500 taka cash", "confirmed": True},
                    headers=h).json()["data"]
    qty = lambda: next(i["qty"] for i in client.get("/api/stock", headers=h).json()["items"] if i["id"] == item["id"])  # noqa: E731
    assert qty() == 90
    d = client.delete(f"/api/books/transactions/{e['transaction_id']}", headers=h).json()
    assert qty() == 100
    client.post(f"/api/books/transactions/restore/{d['trash_id']}", headers=h)
    assert qty() == 90


def test_invoice_payment_rows_are_protected(client):
    h = login(client)
    inv = _new_invoice(client, h, send=True)
    p = client.post(f"/api/books/invoices/{inv['id']}/payments", json={"amount": 100}, headers=h).json()
    tid = p["transaction_id"]
    assert client.delete(f"/api/books/transactions/{tid}", headers=h).status_code == 409
    assert client.patch(f"/api/data/transactions/{tid}", json={"amount": 5}, headers=h).status_code == 409
    assert client.patch(f"/api/data/transactions/{tid}", json={"description": "note"}, headers=h).status_code == 200
    hv = login(client, "viewer", "viewer-pass-123")
    assert client.delete(f"/api/books/transactions/{tid}", headers=hv).status_code == 403


def test_recurring_expense_posts_and_advances(client):
    h = login(client)
    r = client.post("/api/books/recurring", json={"name": "Shop rent", "category": "rent", "amount": 30000,
                                                  "next_due": "2026-09-01"}, headers=h).json()
    assert r["type"] == "expense"
    lst = client.get("/api/books/recurring", headers=h).json()
    assert lst["due_count"] == 1
    out = client.post("/api/books/recurring/post-due", headers=h).json()
    assert out["transactions"] == 2  # September and October were both due
    rows = client.get(f"/api/data/transactions?ids={','.join(map(str, out['transaction_ids']))}", headers=h).json()
    assert sorted(x["date"] for x in rows["rows"]) == ["2026-09-01", "2026-10-01"]
    assert all(x["category"] == "rent" and x["direction"] == "out" for x in rows["rows"])
    nxt = next(x for x in client.get("/api/books/recurring", headers=h).json()["rows"] if x["id"] == r["id"])
    assert nxt["next_due"] == "2026-11-01" and not nxt["due_now"]
    assert client.post("/api/books/recurring/post-due", headers=h).json()["transactions"] == 0  # idempotent


def test_recurring_invoice_creates_drafts(client):
    h = login(client)
    r = client.post("/api/books/recurring", json={"type": "invoice", "name": "Tenant Rahim", "description": "Room rent",
                                                  "amount": 8000, "frequency": "monthly", "next_due": "2026-10-05",
                                                  "due_days": 7}, headers=h).json()
    out = client.post("/api/books/recurring/post-due", headers=h).json()
    assert out["invoices"] == 1
    inv = client.get(f"/api/books/invoices/{out['invoice_ids'][0]}", headers=h).json()
    assert inv["status"] == "draft" and inv["amount"] == 8000 and inv["due_date"] == "2026-10-12"
    assert inv["lines"][0]["description"] == "Room rent"
    client.post(f"/api/books/recurring/invoice/{r['id']}/stop", headers=h)
    assert not next(x for x in client.get("/api/books/recurring", headers=h).json()["rows"]
                    if x["type"] == "invoice")["active"]


def test_recurring_validation_and_audit(client):
    h = login(client)
    bad = {"name": "x", "category": "sales", "amount": 1, "next_due": "2026-10-01"}
    assert client.post("/api/books/recurring", json=bad, headers=h).status_code == 422
    assert client.post("/api/books/recurring/expense/9999/stop", headers=h).status_code == 404
    hv = login(client, "viewer", "viewer-pass-123")
    assert client.post("/api/books/recurring/post-due", headers=hv).status_code == 403
    client.post("/api/books/recurring/post-due", headers=h)
    assert "post_recurring" in [e["action"] for e in client.get("/api/audit?limit=5", headers=h).json()]


def test_advance_keeps_day_of_month():
    from datetime import date

    from sme_copilot.api.routes_books import advance
    assert advance(date(2026, 1, 31), "monthly", 31) == date(2026, 2, 28)
    assert advance(date(2026, 2, 28), "monthly", 31) == date(2026, 3, 31)
    assert advance(date(2026, 11, 15), "quarterly", 15) == date(2027, 2, 15)
    assert advance(date(2026, 3, 1), "once", 1) is None


def test_dashboard_additions(client):
    h = login(client)
    d = client.get("/api/dashboard", headers=h).json()
    assert "profit_this_month" in d["kpis"] and d["kpi_traces"]["profit_this_month"]["steps"]
    assert d["receivables_aging"] == {"not_due": 80_000, "0-30": 0, "31-60": 120_000, "61+": 0}
    assert isinstance(d["expense_this_month"], list)
    client.post("/api/books/recurring", json={"name": "Rent", "category": "rent", "amount": 30000,
                                              "next_due": "2026-10-01"}, headers=h)
    client.post("/api/books/recurring/post-due", headers=h)
    d = client.get("/api/dashboard", headers=h).json()
    assert d["kpis"]["profit_this_month"] == -30_000
    assert d["expense_this_month"][0]["category"] == "rent" and d["expense_this_month"][0]["amount"] == 30_000
