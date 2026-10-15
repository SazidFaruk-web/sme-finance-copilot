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
