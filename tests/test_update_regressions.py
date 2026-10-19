"""Regressions from the October 19 model, setup, recording and Home updates."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from tests.test_api import client, login  # noqa: F401 fixture
from sme_copilot.agent.executor import ToolOutcome
from sme_copilot.agent.orchestrator import AgentResult, _enforce_honesty
from sme_copilot.config import get_settings
from sme_copilot.home_insight import candidates
from sme_copilot.models import Invoice, Transaction
from sme_copilot.tools.nl_entry import money_amount, parse_entry


def test_shipped_shared_profile_and_private_offline_fallback(client, monkeypatch):
    from sme_copilot.llm_providers import registry
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_profile", "shared-llm")
    monkeypatch.setattr(settings, "llm_shared_only", True)
    monkeypatch.setattr(settings, "local_only_mode", True)
    reg = registry.ProviderRegistry(settings=settings, transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    monkeypatch.setattr(registry, "_registry", reg)
    example = Path(".env.example").read_text(encoding="utf-8")
    assert "LLM_PROFILE=shared-llm" in example and reg.info("shared-llm").available
    assert all(not reg.info(p).external for p in registry.ModelRouter(reg).chain())
    h = login(client)
    models = client.get("/api/models", headers=h).json()
    response = client.post("/api/chat", headers=h, json={"message": "Who owes me money?", "profile": models["default"]})
    assert response.status_code == 200, response.text
    assert response.json()["profile"] == "rules-offline" and response.json()["fallback"]


@pytest.mark.parametrize("text", [
    "Received 1000 from Rahman on 19 October 2026",
    "Received 1000 from Rahman on October 19, 2026",
    "Received 1000 from Rahman on 19/10/2026",
    "Received 1000 from Rahman on 2026-10-19",
    "Received ১,০০০ from Rahman on ১৯ October ২০২৬",
    "Received 1000 from Rahman phone 01712345678",
])
def test_payment_amount_ignores_dates_and_phone_numbers(text):
    assert money_amount(text) == 1000


def test_named_date_preserves_the_explicit_year():
    entry = parse_entry("Received 1000 on 19 October 2025", date(2026, 10, 20))
    assert entry.amount == 1000 and entry.txn_date == "2025-10-19"


def test_credit_payment_saves_actual_amount_date_and_outstanding(client, seeded, db):
    h = login(client)
    original = db.scalar(select(Invoice).where(Invoice.kind == "receivable", Invoice.status == "open").order_by(Invoice.due_date))
    before = float(original.amount_paid)
    response = client.post("/api/data/entry", headers=h, json={
        "text": f"Received 1000 from {original.counterparty} on 1 October 2026", "confirmed": True})
    assert response.status_code == 200, response.text
    out = response.json()["data"]
    assert out["recorded"] and out["credit"]["amount"] == 1000
    db.expire_all()
    assert float(db.get(Invoice, original.id).amount_paid) == before + 1000
    txn = db.get(Transaction, out["transaction_id"])
    assert float(txn.amount) == 1000 and txn.txn_date == date(2026, 10, 1)


def test_ambiguous_payment_never_changes_cash_or_customer_dues(client, db):
    h = login(client)
    count = db.query(Transaction).count()
    response = client.post("/api/data/entry", headers=h, json={
        "text": "Received 1000 taka from Karim Knit Composite, remaining balance 2000 taka", "confirmed": True})
    assert response.status_code == 200, response.text
    out = response.json()["data"]
    assert not out["recorded"] and out["manual_form"] and "amount" in out["missing"]
    assert db.query(Transaction).count() == count


@pytest.mark.parametrize("helper", ["setup", "prices"])
def test_direct_external_helpers_mask_pii(helper, monkeypatch):
    from sme_copilot.business_profile import _ask_model as setup
    from sme_copilot.market.watch import _ask_model as prices
    monkeypatch.setattr(get_settings(), "mask_pii", True)
    personal = "Call 01712345678 or owner@example.com; TIN 123456789012"
    class Provider:
        external, supports_json_mode = True, True
        def chat(self, messages, **kwargs):
            self.prompt = "\n".join(m.content for m in messages)
            return SimpleNamespace(content='{"business_type":"retail","summary":"shop [PHONE_1]","items":["Sugar","Rice"],"price_items":["Sugar","Rice"],"reason":"shop"}')
    provider = Provider()
    if helper == "setup":
        result = setup(provider, "Shop", personal, "", ["Sugar", "Rice"])
        assert result["summary"] == "shop 01712345678"  # restored only on this computer
    else:
        prices(provider, "Shop", "retail", personal, ["Sugar", "Rice"])
    for raw in ("01712345678", "owner@example.com", "123456789012"):
        assert raw not in provider.prompt
    assert "[PHONE_1]" in provider.prompt


@pytest.mark.parametrize("external,mask", [(False, True), (True, False)])
def test_direct_helper_preserves_local_or_explicitly_unmasked_input(external, mask, monkeypatch):
    from sme_copilot.security.pii import chat_with_pii
    from sme_copilot.llm_providers.base import Message
    monkeypatch.setattr(get_settings(), "mask_pii", mask)
    class Provider:
        def chat(self, messages):
            assert messages[0].content == "01712345678"
            return SimpleNamespace(content="ok")
    provider = Provider(); provider.external = external
    assert chat_with_pii(provider, [Message("user", "01712345678")]).content == "ok"


@pytest.mark.parametrize("tool,status,data,reply,blocked", [
    ("add_transaction", "ok", {"recorded": True}, "I have sent the payment reminder.", True),
    ("add_transaction", "ok", {"recorded": True}, "I have prepared a reminder.", True),
    ("create_payment_reminder", "pending_confirmation", {}, "I have sent the reminder.", True),
    ("create_payment_reminder", "pending_confirmation", {}, "I have scheduled the reminder.", True),
    ("create_payment_reminder", "pending_confirmation", {}, "I have prepared a reminder; please confirm it.", False),
    ("sandbox_transfer", "pending_confirmation", {}, "I've prepared this request but NOTHING has been sent yet: transfer in the sandbox. Please confirm.", False),
    ("create_payment_reminder", "ok", {"reminder_id": 1}, "The reminder has been sent.", True),
    ("create_payment_reminder", "ok", {"reminder_id": 1}, "The reminder has been scheduled.", False),
    ("add_transaction", "ok", {"recorded": False, "needs_confirm": True}, "I have saved your record.", True),
    ("add_transaction", "ok", {"recorded": True}, "I have saved your record.", False),
    ("generate_loan_report", "ok", {"report_id": 1}, "I have created the report.", False),
    ("generate_loan_report", "pending_confirmation", {}, "The report is saved.", True),
    ("draft_invoice_followup", "ok", {"draft_id": 1}, "I have drafted a letter.", False),
    ("pay_supplier_invoice", "ok", {"transfer_id": 1}, "I have paid the supplier.", True),
    ("pay_supplier_invoice", "ok", {"transfer_id": 1}, "I have paid the supplier in the sandbox.", False),
])
def test_claims_require_the_matching_action_and_completion_state(tool, status, data, reply, blocked):
    result = AgentResult(request_id="regression", reply=reply, language="en")
    _enforce_honesty(result, [ToolOutcome(tool, status, 1, {}, data=data)])
    assert bool(result.blocked_claim) is blocked


def test_sales_note_excludes_loans_transfers_and_capital_but_includes_refunds(db, business):
    for when, amount, direction, category in [
        (date(2026, 9, 1), 10000, "in", "sales"),
        (date(2026, 10, 1), 10000, "in", "sales"),
        (date(2026, 10, 2), 1000000, "in", "loan_received"),
        (date(2026, 10, 2), 20000, "in", "internal_transfer"),
        (date(2026, 10, 2), 50000, "in", "owner_capital"),
    ]:
        db.add(Transaction(business_id=business.id, txn_date=when, amount=amount, direction=direction, category=category))
    db.commit()
    assert not [x for x in candidates(db, business.id, date(2026, 10, 19)) if x["key"].startswith("sales_")]
    db.add(Transaction(business_id=business.id, txn_date=date(2026, 10, 3), amount=4000, direction="out", category="sales_returns"))
    db.commit()
    drop = next(x for x in candidates(db, business.id, date(2026, 10, 19)) if x["key"] == "sales_down")
    assert drop["params"] == {"pct": 40, "now": 6000, "before": 10000}
