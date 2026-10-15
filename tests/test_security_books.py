"""Security checks for the bookkeeping features: confirmations + step-up (1), sessions/CSRF (3),
cross-business isolation (4), input/export hardening (5)."""
import io
from datetime import date

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


def _audit_actions(client, h, n=30):
    return [e["action"] for e in client.get(f"/api/audit?limit={n}", headers=h).json()]


def _invoice(client, h, amount, **kw):
    body = {"counterparty": "Nadia Garments", "lines": [{"description": "Zippers", "rate": amount}], "send": True, **kw}
    return client.post("/api/books/invoices", json=body, headers=h).json()


# ----------------------------------------------------------------------------- 1. high-risk actions
def test_reminder_button_only_proposes_then_click_executes(client, seeded):
    from sme_copilot.models import Reminder
    h = login(client)
    out = client.post("/api/tools/create_payment_reminder", json={"args": {"counterparty": "Karim"}}, headers=h).json()
    assert out["status"] == "pending_confirmation"
    d = out["data"]
    assert d["recipient"] == "Karim Knit Composite" and d["amount"] == 120_000 and "INV-201" in d["preview"]
    assert seeded["db"].query(Reminder).count() == 0
    r = client.post(f"/api/actions/{out['pending_action_id']}/confirm", json={}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert seeded["db"].query(Reminder).count() == 1
    assert client.post(f"/api/actions/{out['pending_action_id']}/confirm", json={}, headers=h).status_code == 409


def test_cancel_and_reject_are_audited(client):
    h = login(client)
    out = client.post("/api/tools/generate_loan_report", json={"args": {}}, headers=h).json()
    assert out["status"] == "pending_confirmation" and "loan-readiness PDF" in out["data"]["summary"]
    assert client.post(f"/api/actions/{out['pending_action_id']}/reject", headers=h).status_code == 200
    client.post("/api/actions/cancelled", json={"action": "record_invoice_payment", "summary": "5000 from X"}, headers=h)
    acts = _audit_actions(client, h)
    assert "generate_loan_report" in acts and "cancelled:record_invoice_payment" in acts


def test_money_confirmation_is_owner_only_and_needs_step_up(client):
    h, ha = login(client), login(client, "accountant", "acct-pass-123")
    out = client.post("/api/tools/sandbox_transfer", json={"args": {"recipient_name": "Dhaka Zipper House",
                                                                    "amount": 60_000}}, headers=h).json()
    pid = out["pending_action_id"]
    assert client.post(f"/api/actions/{pid}/confirm", json={"confirm_amount": 60_000}, headers=ha).status_code == 403
    r = client.post(f"/api/actions/{pid}/confirm", json={"confirm_amount": 60_000}, headers=h)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "step_up_required"
    r = client.post(f"/api/actions/{pid}/confirm", json={"confirm_amount": 60_000, "password": "nope-nope"}, headers=h)
    assert r.status_code == 403
    r = client.post(f"/api/actions/{pid}/confirm", json={"confirm_amount": 60_000, "password": "owner-pass-123"},
                    headers=h)
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert "step_up_failed" in _audit_actions(client, h)


def test_record_payment_owner_only_with_step_up_above_threshold(client):
    h, ha = login(client), login(client, "accountant", "acct-pass-123")
    inv = _invoice(client, h, 80_000)
    url = f"/api/books/invoices/{inv['id']}/payments"
    assert client.post(url, json={"amount": 1000}, headers=ha).status_code == 403  # owner only
    assert client.post(url, json={"amount": 1000}, headers=h).status_code == 200  # small: no password
    r = client.post(url, json={"amount": 60_000}, headers=h)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "step_up_required"
    r = client.post(url, json={"amount": 60_000, "password": "owner-pass-123"}, headers=h)
    assert r.status_code == 200 and r.json()["outstanding"] == 19_000
    ev = next(e for e in client.get("/api/audit?limit=5", headers=h).json() if e["action"] == "record_invoice_payment")
    assert "password" not in ev["inputs"]


def test_large_delete_needs_step_up(client):
    h = login(client)
    big = client.get("/api/data/transactions?q=sold&limit=1", headers=h).json()["rows"][0]
    assert big["amount"] >= 50_000
    r = client.delete(f"/api/books/transactions/{big['id']}", headers=h)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "step_up_required"
    r = client.request("DELETE", f"/api/books/transactions/{big['id']}", json={"password": "owner-pass-123"},
                       headers=h)
    assert r.status_code == 200


def test_daily_reminder_limit(client, monkeypatch):
    from sme_copilot.config import reset_settings_cache
    monkeypatch.setenv("REMINDER_DAILY_LIMIT", "1")
    reset_settings_cache()
    h = login(client)
    first = client.post("/api/tools/create_payment_reminder", json={"args": {"counterparty": "Karim"}}, headers=h)
    client.post(f"/api/actions/{first.json()['pending_action_id']}/confirm", json={}, headers=h)
    second = client.post("/api/tools/create_payment_reminder", json={"args": {"counterparty": "Karim"}}, headers=h)
    assert second.status_code == 403 and "Daily limit" in str(second.json()["detail"])


# ----------------------------------------------------------------------------- 3. auth & sessions
def test_login_sets_httponly_samesite_cookie_and_csrf(client):
    r = client.post("/api/auth/login", json={"username": "owner", "password": "owner-pass-123"})
    cookies = r.headers.get_list("set-cookie")
    sess = next(c for c in cookies if c.startswith("smec_session="))
    csrf = next(c for c in cookies if c.startswith("smec_csrf="))
    assert "HttpOnly" in sess and "samesite=strict" in sess.lower() and "HttpOnly" not in csrf
    assert client.get("/api/auth/me").status_code == 200  # cookie alone is enough to read
    body = {"action": "x", "summary": ""}
    assert client.post("/api/actions/cancelled", json=body).status_code == 403  # write without CSRF header
    assert client.post("/api/actions/cancelled", json=body, headers={"X-CSRF-Token": "forged"}).status_code == 403
    ok = client.post("/api/actions/cancelled", json=body, headers={"X-CSRF-Token": r.json()["csrf"]})
    assert ok.status_code == 200


def test_logout_invalidates_session_and_cookie(client):
    r = client.post("/api/auth/login", json={"username": "owner", "password": "owner-pass-123"})
    tok, csrf = r.json()["token"], r.json()["csrf"]
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_passwords_hashed_and_lockout(client, seeded):
    assert seeded["owner"].password_hash.startswith("$2b$")
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "viewer", "password": "wrong-password"})
    r = client.post("/api/auth/login", json={"username": "viewer", "password": "viewer-pass-123"})
    assert r.status_code == 401 and "locked" in r.json()["detail"]


# ----------------------------------------------------------------------------- 4. cross-business isolation
@pytest.fixture
def other(seeded):
    """A second business with its own data; the first business's users must never reach it."""
    from sme_copilot.models import (Business, DeletedTransaction, Invoice, Item, Obligation, RecurringInvoice,
                                    Transaction)
    from sme_copilot.security.auth import create_user
    db = seeded["db"]
    b = Business(name="Other Shop", opening_cash_balance=0)
    db.add(b)
    db.flush()
    create_user(db, b.id, "other", "other-pass-123", "owner")
    inv = Invoice(business_id=b.id, kind="receivable", invoice_no="OTH-1", counterparty="Secret Client", amount=5000,
                  issue_date=date(2026, 10, 1), due_date=date(2026, 10, 30), status="open")
    t = Transaction(business_id=b.id, txn_date=date(2026, 10, 2), amount=777, direction="in", category="sales",
                    description="secret sale", source="manual")
    it = Item(business_id=b.id, name="Secret Item")
    ob = Obligation(business_id=b.id, name="Secret rent", category="rent", amount=1, next_due=date(2026, 10, 1))
    ri = RecurringInvoice(business_id=b.id, counterparty="Secret Client", amount=1, next_issue=date(2026, 10, 1))
    db.add_all([inv, t, it, ob, ri])
    db.flush()
    tr = DeletedTransaction(business_id=b.id, original_id=999, data={"txn_date": "2026-10-01", "amount": 1,
                                                                      "direction": "in"})
    db.add(tr)
    db.commit()
    return {"invoice": inv.id, "txn": t.id, "item": it.id, "obligation": ob.id, "recurring_invoice": ri.id,
            "trash": tr.id}


def test_cross_business_access_is_refused_everywhere(client, other):
    h = login(client)
    o = other
    assert client.get(f"/api/books/invoices/{o['invoice']}", headers=h).status_code == 404
    assert client.get(f"/api/books/invoices/{o['invoice']}/pdf", headers=h).status_code == 404
    assert client.post(f"/api/books/invoices/{o['invoice']}/send", headers=h).status_code == 404
    assert client.post(f"/api/books/invoices/{o['invoice']}/payments", json={"amount": 1}, headers=h).status_code == 404
    assert client.delete(f"/api/books/transactions/{o['txn']}", headers=h).status_code == 404
    assert client.patch(f"/api/data/transactions/{o['txn']}", json={"amount": 1}, headers=h).status_code == 404
    assert client.post(f"/api/books/transactions/restore/{o['trash']}", headers=h).status_code == 404
    assert client.post(f"/api/books/recurring/expense/{o['obligation']}/stop", headers=h).status_code == 404
    assert client.post(f"/api/books/recurring/invoice/{o['recurring_invoice']}/stop", headers=h).status_code == 404
    assert client.post("/api/stock/adjust", json={"item_id": o["item"], "qty_change": 5}, headers=h).status_code == 404
    mine = client.get("/api/data/transactions?limit=1", headers=h).json()["rows"][0]["id"]
    assert client.post("/api/stock/link", json={"transaction_id": mine, "item_id": o["item"], "quantity": 1},
                       headers=h).status_code == 404
    assert client.post("/api/stock/link", json={"transaction_id": o["txn"], "item_id": o["item"]},
                       headers=h).status_code == 404
    # lists, ledgers and reports never include the other business's rows
    blob = "".join(client.get(u, headers=h).text for u in (
        "/api/books/invoices", "/api/books/parties", "/api/books/parties?kind=supplier", "/api/books/recurring",
        "/api/stock", "/api/data/transactions?limit=500&q=secret", "/api/books/reports/aging",
        "/api/books/reports/pnl?period=year", "/api/books/reports/cashflow?period=year"))
    assert "Secret" not in blob and "secret" not in blob and "OTH-1" not in blob
    assert client.get("/api/books/parties/ledger", params={"name": "Secret Client"}, headers=h).status_code == 404
    # and the other owner sees only their own data
    ho = login(client, "other", "other-pass-123")
    assert [i["invoice_no"] for i in client.get("/api/books/invoices", headers=ho).json()] == ["OTH-1"]


def test_new_routes_require_login(client):
    for method, url in [("get", "/api/books/invoices"), ("post", "/api/books/invoices"), ("get", "/api/books/parties"),
                        ("get", "/api/books/reports/pnl"), ("get", "/api/books/recurring"),
                        ("post", "/api/books/recurring/post-due"), ("delete", "/api/books/transactions/1"),
                        ("post", "/api/books/transactions/restore/1"), ("get", "/api/stock"),
                        ("post", "/api/actions/cancelled")]:
        assert getattr(client, method)(url).status_code == 401, url


# ----------------------------------------------------------------------------- 5. input & export hardening
def test_input_limits(client):
    h = login(client)
    long = {"counterparty": "x" * 201, "lines": [{"description": "a", "rate": 1}]}
    assert client.post("/api/books/invoices", json=long, headers=h).status_code == 422
    many = {"counterparty": "X", "lines": [{"description": "a", "rate": 1}] * 51}
    assert client.post("/api/books/invoices", json=many, headers=h).status_code == 422
    huge = {"counterparty": "X", "lines": [{"description": "a", "rate": 1e11}]}
    assert client.post("/api/books/invoices", json=huge, headers=h).status_code == 422
    assert client.post("/api/books/recurring", json={"name": "r", "amount": -5, "next_due": "2026-10-01"},
                       headers=h).status_code == 422
    assert client.post("/api/data/entry", json={"text": "x" * 301}, headers=h).status_code == 422


def test_upload_type_and_size_limits(client):
    h = login(client)
    r = client.post("/api/data/upload", files={"file": ("evil.exe", b"MZ", "application/octet-stream")}, headers=h)
    assert r.status_code == 415
    big = b"Date,Amount\n" + b"01/01/2026,1\n" * 500_000
    r = client.post("/api/data/upload", files={"file": ("big.csv", big, "text/csv")}, headers=h)
    assert r.status_code == 413


def test_csv_and_excel_exports_neutralise_formulas(client):
    h = login(client)
    _invoice(client, h, 1000, counterparty="=HYPERLINK(\"http://evil\")")
    csv_text = client.get("/api/books/reports/aging?fmt=csv", headers=h).text
    assert "'=HYPERLINK" in csv_text and "\n=HYPERLINK" not in csv_text
    client.post("/api/items", json={"name": "=1+2"}, headers=h)
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(client.get("/api/stock/export", headers=h).content))
    names = [c.value for c in wb.active["A"]]
    assert "'=1+2" in names and "=1+2" not in names


def test_pdf_filename_is_sanitised(client):
    h = login(client)
    inv = _invoice(client, h, 1000, invoice_no='../../etc/"x\r\nSet-Cookie: a=b')
    r = client.get(f"/api/books/invoices/{inv['id']}/pdf", headers=h)
    disp = r.headers["content-disposition"]
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    fname = disp.split('filename="', 1)[1][:-1]
    assert fname.startswith("invoice_") and all(c.isalnum() or c in "-_." for c in fname)


def test_recent_activity_panel_is_scoped_and_minimal(client, other):
    hv = login(client, "viewer", "viewer-pass-123")
    rows = client.get("/api/privacy/recent", headers=hv).json()
    assert 0 < len(rows) <= 5 and set(rows[0]) == {"ts", "actor", "action", "confirmation"}
    assert all(r["actor"] != "other" for r in rows)
