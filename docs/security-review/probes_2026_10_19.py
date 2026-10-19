"""Bounded vulnerability reproductions. Use isolated pytest fixtures, never live owner data.

Run: python -m pytest -p tests.conftest docs/security-review/probes_2026_10_19.py -o addopts= -q
These assert the observed vulnerable behavior; they are audit evidence, not acceptance tests.
"""
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from sme_copilot.api.main import create_app
from sme_copilot.models import Business, Invoice, InvoicePayment, PendingAction, SandboxTransfer, Transaction
from sme_copilot.security.auth import create_user, hash_password, verify_password


def login(client, username="owner", password="owner-pass-123"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def bill(db, bid):
    row = Invoice(business_id=bid, kind="receivable", invoice_no="AUDIT-1", counterparty="Audit Customer",
                  amount=100000, amount_paid=0, issue_date=date(2026, 10, 1), due_date=date(2026, 10, 10), status="open")
    db.add(row); db.commit()
    return row


def test_payment_role_and_step_up_bypassed_by_quick_entry(seeded):
    db = seeded["db"]
    inv = bill(db, seeded["business"].id)
    with TestClient(create_app()) as c:
        headers = login(c, "accountant", "acct-pass-123")
        denied = c.post(f"/api/books/invoices/{inv.id}/payments", json={"amount": 60000}, headers=headers)
        assert denied.status_code == 403, denied.text
        owner = login(c)
        denied = c.post(f"/api/books/invoices/{inv.id}/payments", json={"amount": 60000}, headers=owner)
        assert denied.status_code == 403, denied.text
        response = c.post("/api/data/entry", json={"text": "Received 60000 from Audit Customer", "confirmed": True}, headers=headers)
        assert response.status_code == 200 and response.json()["data"]["recorded"], response.text
        db.expire_all()
        assert float(db.get(Invoice, inv.id).amount_paid) == 60000


def test_undo_bypasses_password_and_invoice_protection(seeded):
    db = seeded["db"]
    inv = bill(db, seeded["business"].id)
    with TestClient(create_app()) as c:
        headers = login(c)
        payment = c.post(f"/api/books/invoices/{inv.id}/payments", headers=headers,
                         json={"amount": 60000, "password": "owner-pass-123"})
        assert payment.status_code == 200, payment.text
        tid = payment.json()["transaction_id"]
        protected = c.delete(f"/api/books/transactions/{tid}", headers=headers)
        assert protected.status_code == 409
        bypass = c.delete(f"/api/data/transactions/{tid}", headers=headers)
        assert bypass.status_code == 200, bypass.text
        db.expire_all()
        assert db.get(Transaction, tid) is None
        assert float(db.get(Invoice, inv.id).amount_paid) == 60000
        assert db.scalar(select(InvoicePayment).where(InvoicePayment.transaction_id == tid)) is not None
        ordinary = Transaction(id=tid + 1, business_id=inv.business_id, txn_date=date(2026, 10, 10), amount=60000,
                               direction="out", category="rent", source="manual")
        db.add(ordinary); db.commit()
        assert c.delete(f"/api/books/transactions/{ordinary.id}", headers=headers).status_code == 403
        assert c.delete(f"/api/data/transactions/{ordinary.id}", headers=headers).status_code == 200


def test_viewer_can_reject_owner_payment(seeded):
    with TestClient(create_app()) as c:
        owner = login(c)
        action = c.post("/api/tools/sandbox_transfer", json={"args": {"recipient_name": "Audit Supplier", "amount": 1000}}, headers=owner)
        pid = action.json()["pending_action_id"]
        viewer = login(c, "viewer", "viewer-pass-123")
        response = c.post(f"/api/actions/{pid}/reject", headers=viewer)
        assert response.status_code == 200, response.text
        seeded["db"].expire_all()
        assert seeded["db"].get(PendingAction, pid).status == "rejected"


def test_password_suffix_is_ignored():
    prefix = "A" * 72
    hashed = hash_password(prefix + "real-secret-suffix")
    assert verify_password(prefix + "wrong-suffix", hashed)
    bangla_prefix = "ক" * 24
    assert verify_password(bangla_prefix + "wrong", hash_password(bangla_prefix + "real"))


def test_cross_business_feedback_changes_training_answer(seeded, monkeypatch, tmp_path):
    from sme_copilot.telemetry import interactions, export
    monkeypatch.setattr(interactions, "_path", lambda: tmp_path / "interactions.jsonl")
    db = seeded["db"]
    other = Business(name="Other audit business")
    db.add(other); db.flush()
    create_user(db, other.id, "other-auditor", "audit-pass-123", "viewer")
    db.commit()
    with TestClient(create_app()) as c:
        headers = login(c)
        reply = c.post("/api/chat", headers=headers, json={"message": "How much cash do I have?", "profile": "rules-offline"})
        assert reply.status_code == 200, reply.text
        iid = reply.json()["interaction_id"]
        other_headers = login(c, "other-auditor", "audit-pass-123")
        response = c.post("/api/feedback", headers=other_headers,
                          json={"interaction_id": iid, "rating": "down", "correction": "UNTRUSTED AUDIT ANSWER"})
        assert response.status_code == 200, response.text
        sft, _, _ = export.build(path=tmp_path / "interactions.jsonl")
        assert any(item["messages"][-1]["content"] == "UNTRUSTED AUDIT ANSWER" for item in sft)


def test_nonfinite_confirmation_bypasses_amount_retyping(seeded):
    with TestClient(create_app()) as c:
        headers = login(c)
        response = c.post("/api/tools/sandbox_transfer", headers=headers,
                          json={"args": {"recipient_name": "Audit Supplier", "amount": 1000}})
        pid = response.json()["pending_action_id"]
        result = c.post(f"/api/actions/{pid}/confirm", headers=headers, json={"confirm_amount": "NaN"})
        assert result.status_code == 200 and result.json()["status"] == "ok", result.text


def test_overlapping_confirmations_can_execute_twice(seeded):
    from sme_copilot.agent.executor import execute, confirm_pending
    from sme_copilot.api.deps import tool_context
    from sme_copilot.db import SessionLocal
    from sme_copilot.models import User
    from tests.conftest import make_ctx
    pid = execute(make_ctx(seeded), "sandbox_transfer", {"recipient_name": "Audit Supplier", "amount": 1000}).pending_action_id
    # Both requests read pending before either completes: a valid concurrent-request interleaving.
    with SessionLocal() as first, SessionLocal() as second:
        pa1 = first.get(PendingAction, pid)
        pa2 = second.get(PendingAction, pid)
        assert pa1.status == pa2.status == "pending"
        ctx1 = tool_context(first, first.get(User, seeded["owner"].id))
        ctx2 = tool_context(second, second.get(User, seeded["owner"].id))
        assert confirm_pending(ctx1, pid, confirm_amount=1000).status == "ok"
        assert confirm_pending(ctx2, pid, confirm_amount=1000).status == "ok"
    seeded["db"].expire_all()
    assert len(seeded["db"].scalars(select(SandboxTransfer).where(SandboxTransfer.pending_action_id == pid)).all()) == 2
