"""Demo seed produces the intended story; static UI is served with a strict CSP."""
from datetime import date

from fastapi.testclient import TestClient

from sme_copilot.api.main import create_app
from sme_copilot.demo.seed import generate, load
from sme_copilot.forecasting.forecast import forecast
from sme_copilot.models import Business, Invoice, Transaction
from sme_copilot.tools import repo

AS_OF = date(2026, 10, 14)


def test_generate_is_deterministic():
    a, b = generate(AS_OF), generate(AS_OF)
    assert a.files == b.files and a.opening_balance == b.opening_balance
    assert set(a.files) >= {"sales_ledger.csv", "bank_statement.csv", "bkash_statement.csv", "customer_invoices.csv",
                            "supplier_bills.csv", "expenses_ledger.csv", "quick_entries.txt"}


def test_seed_story(db):
    res = load(db, AS_OF, write=False)
    imp = res["imports"]
    assert imp["bank_statement.csv"]["duplicates"] == 1 and imp["expenses_ledger.csv"]["duplicates"] == 0
    assert imp["expenses_ledger.csv"]["anomalies"] >= 1
    assert imp["bkash_statement.csv"]["injection_flags"] == 1 and imp["bkash_statement.csv"]["errors"] == 1
    b = db.query(Business).one()
    txns, inv = repo.load_transactions(db, b.id, end=AS_OF), repo.load_invoices(db, b.id)
    fc = forecast(txns, inv, repo.load_obligations(db, b.id), b, AS_OF, 90)
    assert 100_000 < fc.start_balance < 300_000            # tight but positive today
    assert fc.first_below_threshold_date is not None        # a cash dip is coming -> alerts, financing story
    assert db.query(Invoice).filter_by(kind="payable", status="open").count() == 3
    overdue = [i for i in db.query(Invoice).filter_by(kind="receivable", status="open") if i.due_date < AS_OF]
    assert any(i.counterparty == "Karim Knit Composite" for i in overdue)
    assert db.query(Transaction).filter(Transaction.flags.contains("injection_suspect")).count() == 1


def test_frontend_served_with_csp(db):
    with TestClient(create_app()) as c:
        r = c.get("/")
        assert r.status_code == 200 and "app.js" in r.text
        assert "script-src 'self'" in r.headers["Content-Security-Policy"]
        js = c.get("/static/app.js").text
        assert ".innerHTML" not in js and ".insertAdjacentHTML" not in js  # dynamic text uses textContent
