"""Guided Home: complete evidence, persistent reminders, and novice-friendly offline help."""
from datetime import date

from fastapi.testclient import TestClient

from sme_copilot.api.main import create_app
from sme_copilot.models import Alert, Transaction
from sme_copilot.agent.intent_rules import c_digest, Fmt
from sme_copilot.agent.orchestrator import Agent
from tests.conftest import make_ctx
import pytest


def test_dashboard_keeps_reminders_beyond_the_alert_preview(seeded, monkeypatch):
    monkeypatch.setenv("AS_OF_DATE", "2026-10-14")
    from sme_copilot.config import reset_settings_cache
    reset_settings_cache()
    db, b = seeded["db"], seeded["business"]
    for i in range(15):
        db.add(Alert(business_id=b.id, kind="review", severity="critical", title=f"Review {i}",
                     status="open", created_by="user", dedupe_key=f"review-test-{i}"))
    db.add(Alert(business_id=b.id, kind="custom", severity="info", title="Check supplier order", due_date=date(2026, 11, 1),
                 status="scheduled", created_by="user", dedupe_key="personal-test"))
    db.add(Transaction(business_id=b.id, txn_date=date(2026, 10, 14), amount=123, direction="in", is_duplicate=True))
    db.add(Transaction(business_id=b.id, txn_date=date(2027, 1, 1), amount=456, direction="in"))
    db.commit()
    with TestClient(create_app()) as client:
        login = client.post("/api/auth/login", json={"username": "owner", "password": "owner-pass-123"})
        h = {"Authorization": f"Bearer {login.json()['token']}"}
        d = client.get("/api/dashboard", headers=h).json()
        assert len(d["alerts"]) == 12
        assert len(d["guidance_alerts"]) > 15
        assert any(a["title"] == "Check supplier order" for a in d["reminders"])
        expected = db.query(Transaction).filter(Transaction.business_id == b.id, Transaction.is_duplicate.is_(False),
                                                Transaction.txn_date <= date(2026, 10, 14)).count()
        assert d["record_count"] == expected
        # Loading again preserves the same reminder; no browser-local-only state.
        assert client.get("/api/dashboard", headers=h).json()["reminders"] == d["reminders"]


@pytest.mark.parametrize("q,tool", [
    ("What should I focus on today?", "get_digest"),
    ("আজ কোন কাজে মনোযোগ দেব?", "get_digest"),
    ("Can I cover the bills coming up?", "forecast_cash_flow"),
    ("সামনের বিল দেওয়ার মতো টাকা আছে?", "forecast_cash_flow"),
    ("কোন ক্রেতার কাছে টাকা পাব?", "get_aging"),
])
def test_home_questions_work_without_a_model(seeded, q, tool):
    r = Agent().run(make_ctx(seeded), q)
    assert r.tool_calls and r.tool_calls[0]["tool"] == tool, r.tool_calls
    assert r.tool_calls[0]["status"] == "ok"
    assert r.ungrounded_numbers == []


def test_offline_digest_limits_decisions_and_explains_how():
    data = {"as_of": "2026-10-14", "kpis": {"cash_balance": 50000}, "alerts": [
        {"kind": "overdue_invoice", "title": "Customer A owes money"},
        {"kind": "payable_due", "title": "Unrelated supplier bill"},
    ]}
    text = c_digest(data, Fmt("en", "lakh"))
    assert "Customer A" in text and "Unrelated supplier bill" not in text
    assert "Bills & invoices" in text and "sandbox outbox" in text
    assert "live bank balance" in text
