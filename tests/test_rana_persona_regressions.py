"""Regressions found by the two-month "Rana Electric & Hardware" persona test (scripts/seed_rana_persona.py, 2026-10-19)."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from sme_copilot.agent.intent_rules import RuleIntentEngine, c_aging, c_stock, detect_period, Fmt
from sme_copilot.agent.tools_analysis import AddTxnArgs, add_transaction
from sme_copilot.api.main import create_app
from sme_copilot.llm_providers.base import ToolSpec
from sme_copilot.models import Item
from sme_copilot.tools.analysis import profitability
from sme_copilot.tools.categorize import categorize
from sme_copilot.tools.nl_entry import parse_entry
from sme_copilot.tools.quality import TxnKey, find_duplicates
from tests.conftest import make_ctx, make_txn_df

# ----------------------------------------------------------------------------- 1. categoriser


@pytest.mark.parametrize("text,category", [
    ("Taken home for family expenses", "owner_drawings"),
    ("Sent to parents in Cumilla (bKash)", "owner_drawings"),
    ("Children school fees", "owner_drawings"),
    ("CHQ to Chawkbazar Tools Import - part payment CTI-3308", "inventory"),
    ("CHQ to Bright Light Wholesale - Stock purchase - 200 12W LED bulb", "inventory"),
    ("CHQ to Haji Abdul Karim (landlord) - shop rent", "rent"),  # a specific keyword still beats "chq"
    ("Loan processing fee TL/NWB/2026/0512", "loan_interest"),
    ("Market committee monthly fee", "misc_expense"),
    ("Mobile recharge", "misc_expense"),
    ("Account maintenance fee and SMS charge", "mobile_fees"),
    ("DPDC electricity bill (paid by bKash)", "utilities"),
])
def test_rana_narrations_categorised(text, category):
    assert categorize(text, "out").category == category


def test_bought_with_quantity_and_amount_is_stock_purchase():
    e = parse_entry("bought 200 switch board from bright light 17000 cash", date(2026, 10, 19))
    assert (e.direction, e.category, e.amount, e.quantity) == ("out", "inventory", 17000, 200)
    assert parse_entry("bought lunch 300", date(2026, 10, 19)).category == "food_entertainment"


def test_drawings_no_longer_make_a_false_operating_loss():
    rows = [(1, "2026-10-02", 200_000, "in", "sales"), (2, "2026-10-03", 120_000, "out", "inventory")]
    for i, text in enumerate(["Taken home for family expenses", "Sent to parents in Cumilla (bKash)",
                              "Children school fees"], start=3):
        rows.append((i, "2026-10-05", 15_000, "out", categorize(text, "out").category))
    p = profitability(make_txn_df(rows), date(2026, 10, 1), date(2026, 10, 31))
    assert p.operating_profit == 80_000
    assert p.excluded["owner_drawings_and_transfers"] == 45_000


# ----------------------------------------------------------------------------- 2. chat routing (rules-offline)
TOOLS = [ToolSpec(n, "", {}) for n in ("draft_invoice_followup", "get_profitability", "get_financial_summary",
                                        "get_stock", "get_aging", "forecast_cash_flow", "match_financing")]
CTX = {"language": "en", "today": "2026-10-19", "business": "Rana Electric & Hardware", "number_style": "lakh"}


def _plan(text, **ctx):
    return RuleIntentEngine().plan(text, TOOLS, {**CTX, **ctx})


def test_bank_letter_is_not_a_customer_reminder():
    out = _plan("write a letter to my bank manager asking for a loan of 2 lakh")
    assert isinstance(out, str), out
    assert "৳2,00,000" in out and "Rana Electric & Hardware" in out and "Branch Manager" in out
    calls = _plan("write a letter to Kamal Electrician about his unpaid bill")
    assert calls[0].name == "draft_invoice_followup"  # customer letters still go to the follow-up tool


@pytest.mark.parametrize("text,period", [
    ("How much profit did I make in September?", "2026-09"),
    ("profit in october", "2026-10"),
    ("profit in december", "2025-12"),          # a future month means last year's
    ("sep 2025 er lav koto", "2025-09"),
    ("সেপ্টেম্বর মাসে লাভ কত?", "2026-09"),
    ("profit last 3 months", "last_3_months"),  # unchanged
    ("may I see my profit?", "last_3_months"),  # "may" is not a month here
])
def test_named_month_period(text, period):
    assert detect_period(text.lower(), "last_3_months", date(2026, 10, 19)) == period


def test_profit_in_september_asks_for_september():
    [call] = _plan("How much profit did I make in September?")
    assert call.name == "get_profitability" and call.arguments == {"period": "2026-09"}


@pytest.mark.parametrize("text", ["which items are running low?", "what is out of stock", "kon mal shesh hoye geche?"])
def test_low_stock_question_reads_stock(text):
    [call] = _plan(text)
    assert call.name == "get_stock"


@pytest.mark.parametrize("text", ["kotodin dhore Kamal electrician taka dey nai?", "who has not paid me?",
                                  "Kamal er taka deyni koto din?"])
def test_unpaid_questions_go_to_receivables_not_forecast(text):
    [call] = _plan(text, language="banglish")
    assert call.name == "get_aging" and call.arguments["kind"] == "receivable"
    assert call.arguments["counterparty"] == text


# ----------------------------------------------------------------------------- 3. overdue answer


def _aging(n_customers):
    cps = [{"counterparty": f"Customer {i}", "outstanding": 1000.0 * (i + 1), "overdue": 1000.0 * (i + 1),
            "max_days_past_due": 10, "invoices": 1} for i in range(n_customers)]
    return {"kind": "receivable", "total_outstanding": 10_000.0, "overdue_total": 9_000.0, "overdue_count": n_customers + 1,
            "buckets": {"90+": 0.0}, "by_counterparty": cps, "items": []}


def test_overdue_answer_counts_customers_and_says_how_many_more():
    text = c_aging(_aging(4), Fmt("en", "lakh"))
    assert "5 bills from 4 customers" in text and text.count("Customer ") == 3 and "and 1 more" in text
    assert "Customer 3 ৳4,000" in text  # biggest overdue first
    assert "more" not in c_aging(_aging(3), Fmt("en", "lakh"))


def test_aging_for_one_customer_says_since_when():
    r = {**_aging(1), "counterparty_filter": "Kamal Electrician", "total_outstanding": 6810.0,
         "items": [{"invoice_no": "RE-0005", "due_date": "2026-09-22", "days_past_due": 27, "outstanding": 6810.0}]}
    assert c_aging(r, Fmt("banglish", "lakh")) == ("Kamal Electrician er kache pawna ৳6,810 (1 ta bill). Sobcheye puron "
                                                     "bill RE-0005, due chilo 22 Sep 2026: 27 din age.")


def test_stock_answer_lists_low_items():
    r = {"item_count": 5, "restock_cost": 12_000.0, "items": [
        {"name": "MCB circuit breaker 32A", "unit": "pcs", "qty": 0, "reorder_level": 20, "days_left": None, "status": "out"},
        {"name": "Switch socket board", "unit": "pcs", "qty": 52, "reorder_level": 120, "days_left": 2.9, "status": "low"}]}
    text = c_stock(r, Fmt("en", "lakh"))
    assert "2 items running low or out" in text and "MCB circuit breaker 32A: out of stock" in text
    assert "52 pcs left" in text and "৳12,000" in text


# ----------------------------------------------------------------------------- 2/5. through the tools and API


@pytest.fixture
def client(seeded):
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        yield c


def _login(client):
    r = client.post("/api/auth/login", json={"username": "owner", "password": "owner-pass-123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_chat_answers_one_customer_and_low_stock(seeded, client):
    db, b = seeded["db"], seeded["business"]
    db.add(Item(business_id=b.id, name="MCB circuit breaker 32A", aliases=["mcb"], unit="pcs", opening_qty=0,
                reorder_level=20, cost_price=380))
    db.commit()
    h = _login(client)
    r = client.post("/api/chat", json={"message": "kotodin dhore Karim Knit taka dey nai?", "language": "banglish"},
                    headers=h).json()
    assert r["tool_calls"][0]["tool"] == "get_aging"
    assert r["reply"].startswith("Karim Knit Composite er kache pawna") and "INV-201" in r["reply"]
    r = client.post("/api/chat", json={"message": "which items are running low?"}, headers=h).json()
    assert r["tool_calls"][0]["tool"] == "get_stock" and "MCB circuit breaker 32A: out of stock" in r["reply"]


def test_sale_with_no_stock_warns_before_saving(seeded):
    db, b = seeded["db"], seeded["business"]
    db.add(Item(business_id=b.id, name="MCB circuit breaker 32A", aliases=["mcb"], unit="pcs", opening_qty=0,
                reorder_level=20, cost_price=380))
    db.flush()
    ctx = make_ctx(seeded)
    r = add_transaction(ctx, AddTxnArgs(text="sold 3 MCB 1560 cash"))
    assert not r.recorded and r.needs_confirm and r.reason == "not enough stock"
    assert "0 pcs of MCB circuit breaker 32A" in r.preview
    ok = add_transaction(ctx, AddTxnArgs(text="sold 3 MCB 1560 cash", confirmed=True))
    assert ok.recorded and ok.entry["amount"] == 1560 and ok.stock["linked"]


def test_customer_payment_preview_has_direction_and_offers_the_open_bill(client):
    h = _login(client)
    p = client.post("/api/data/entry/preview", json={"text": "Karim Knit 20000 dilo bank e"}, headers=h).json()
    assert p["direction"] == "in" and p["category"] == "sales" and p["counterparty"] == "Karim Knit Composite"
    assert p["credit"]["bills"][0] == "INV-201" and "Link it to" in p["preview"] and "INV-201" in p["preview"]
    saved = client.post("/api/data/entry", json={"text": "Karim Knit 20000 dilo bank e"}, headers=h).json()["data"]
    assert saved["needs_confirm"] and saved["entry"]["direction"] == "in" and saved["credit"]["kind"] == "payment"


# ----------------------------------------------------------------------------- 6. statement vs hand-recorded payment


def test_statement_credit_naming_the_invoice_is_a_duplicate_of_the_recorded_payment():
    recorded = TxnKey(427, date(2026, 9, 26), 46150.0, "in", "Payment for RE-0002", "RE-0002", "Al-Amin Construction",
                      "sales", "invoice_payment")
    bank = TxnKey(None, date(2026, 9, 26), 46150.0, "in", "NPSB credit from AL-AMIN CONSTRUCTION ref RE-0002", "", "",
                  "sales", "csv:statement.csv")
    late = TxnKey(None, date(2026, 9, 28), 46150.0, "in", "BEFTN inward AL-AMIN CONSTRUCTION", "", "", "sales",
                  "csv:statement.csv")
    other = TxnKey(None, date(2026, 9, 26), 46150.0, "in", "NPSB credit from GREEN VIEW APARTMENTS", "", "", "sales",
                   "csv:statement.csv")
    assert "RE-0002" in find_duplicates([bank], [recorded])[0][1]
    assert "Al-Amin Construction" in find_duplicates([late], [recorded])[0][1]  # names the customer, 2 days later
    assert find_duplicates([other], [recorded]) == {}
    # Two imports of the same customer and amount are not matched by name alone (separate real payments)
    imported = TxnKey(9, date(2026, 9, 26), 46150.0, "in", "NPSB credit", "", "Al-Amin Construction", "sales", "csv:a.csv")
    assert find_duplicates([late], [imported]) == {}


def test_bank_import_flags_hand_recorded_invoice_payment(seeded, client):
    h = _login(client)
    inv = next(i for i in client.get("/api/books/invoices", headers=h).json() if i["invoice_no"] == "INV-201")
    r = client.post(f"/api/books/invoices/{inv['id']}/payments", json={"amount": 120000, "paid_on": "2026-10-01",
                                                                         "channel": "bank", "password": "owner-pass-123"}, headers=h)
    assert r.status_code == 200, r.text
    csv = "Date,Narration,Withdrawal,Deposit\n01/10/2026,NPSB credit from KARIM KNIT COMPOSITE ref INV-201,,120000\n"
    rep = client.post("/api/data/paste", json={"text": csv, "doc_type": "bank"}, headers=h).json()
    assert rep["imported"] == 0 and len(rep["duplicates"]) == 1 and "INV-201" in rep["duplicates"][0]["reason"]
