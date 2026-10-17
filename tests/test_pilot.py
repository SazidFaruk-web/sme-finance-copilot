from datetime import date, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from tests.test_api import client, login  # noqa: F401 fixtures
from sme_copilot.models import Alert, Business, Invoice, Transaction
from sme_copilot.pilot.calculations import loan, stock
from sme_copilot.pilot.models import GuidedCase, NotificationDelivery, NotificationPreference, ReminderJob, SourceCheck


def post(client, h, path, body):
    response = client.post("/api/pilot/" + path, headers=h, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def start(client, h, kind, **answers):
    case = post(client, h, "cases", {"kind": kind, "language": "en", "request_key": str(uuid4())})
    while case["next_question"]:
        q = case["next_question"]
        assert q["id"] in answers, q
        case = post(client, h, f"cases/{case['id']}/answer", {"version": case["version"], "question_id": q["id"], "value": answers[q["id"]]})
    return case


def confirm(client, h, case, action="save"):
    preview = post(client, h, f"cases/{case['id']}/preview", {"version": case["version"], "action": action})
    payload = {"version": preview["version"], "token": preview["preview"]["token"]}
    result = post(client, h, f"cases/{case['id']}/confirm", payload)
    return result, payload


def sale(**kw):
    return dict(record_type="sale", date="2026-10-14", amount="১,২০০", description="Daily sales", settled="yes", channel="cash", **kw)


def test_record_idempotency_and_stale_preview(client, seeded, db):
    h = login(client)
    c = start(client, h, "record", **sale())
    p = post(client, h, f"cases/{c['id']}/preview", {"version": c["version"], "action": "save"})
    row = Transaction(business_id=seeded["business"].id, txn_date=date(2026, 10, 14), amount=5, direction="out", category="rent")
    db.add(row); db.commit()
    bad = client.post(f"/api/pilot/cases/{c['id']}/confirm", headers=h, json={"version": p["version"], "token": p["preview"]["token"]})
    assert bad.status_code == 409 and bad.json()["detail"]["code"] == "records_changed"
    c = client.get(f"/api/pilot/cases/{c['id']}", headers=h).json()
    done, payload = confirm(client, h, c)
    again = post(client, h, f"cases/{c['id']}/confirm", payload)
    assert done["result"]["effects"] == again["result"]["effects"]
    rows = list(db.scalars(select(Transaction).where(Transaction.reference == f"CASE-{c['id']}")))
    assert len(rows) == 1 and rows[0].amount == 1200


def test_credit_transfer_and_repayment_are_distinct(client, seeded, db):
    h = login(client)
    args = sale(); args.update(settled="no", party="Corner shop", due_date="2026-10-20"); args.pop("channel")
    credit = start(client, h, "record", **args)
    saved, _ = confirm(client, h, credit)
    assert "transaction_ids" not in saved["result"]["effects"]
    assert db.get(Invoice, saved["result"]["effects"]["invoice_id"]).amount_paid == 0
    for kind, extra in [("transfer", {"to_channel": "bank"}), ("repay", {"interest": 100})]:
        c = start(client, h, "record", record_type=kind, date="2026-10-14", amount=1000, description=kind, channel="cash", **extra)
        saved, _ = confirm(client, h, c)
        rows = list(db.scalars(select(Transaction).where(Transaction.reference == f"CASE-{c['id']}")))
        assert len(rows) == 2
        if kind == "transfer":
            assert sum(float(r.amount) * (1 if r.direction == "in" else -1) for r in rows) == 0
            assert all(r.category == "internal_transfer" for r in rows)
        else:
            assert {r.category: float(r.amount) for r in rows} == {"loan_repayment": 900, "loan_interest": 100}


def test_partial_credit_entry_records_only_cash_paid(client, db):
    h = login(client)
    args = sale(); args.update(settled="partial", paid_now=200, party="Corner shop", due_date="2026-10-25")
    c = start(client, h, "record", **args); done, _ = confirm(client, h, c)
    inv = db.get(Invoice, done["result"]["effects"]["invoice_id"])
    assert inv.amount == 1200 and inv.amount_paid == 200 and inv.status == "partial"
    rows = list(db.scalars(select(Transaction).where(Transaction.reference == f"CASE-{c['id']}")))
    assert len(rows) == 1 and rows[0].amount == 200


def test_answer_revision_invalidates_preview_and_old_version(client):
    h = login(client); c = start(client, h, "record", **sale())
    p = post(client, h, f"cases/{c['id']}/preview", {"version": c["version"], "action": "save"})
    updated = post(client, h, f"cases/{c['id']}/answer", {"version": p["version"], "question_id": "amount", "value": 300})
    assert updated["preview"] == {} and updated["result"]["metrics"]["amount"] == 300
    r = client.post(f"/api/pilot/cases/{c['id']}/confirm", headers=h, json={"version": p["version"], "token": p["preview"]["token"]})
    assert r.status_code == 409
    assert client.post(f"/api/pilot/cases/{c['id']}/answer", headers=h, json={"version": p["version"], "question_id": "amount", "value": 500}).status_code == 409


def test_check_creates_correction_task_and_unknown_does_not_write(client, db):
    h = login(client)
    c = start(client, h, "record", record_type="check", date="2026-10-14", cash=1, note=None)
    done, _ = confirm(client, h, c)
    assert done["result"]["status"] == "check_records" and done["result"]["effects"]["alert_id"]
    bad = sale(); bad["amount"] = None
    c = start(client, h, "record", **bad)
    assert client.post(f"/api/pilot/cases/{c['id']}/preview", headers=h, json={"version": c["version"], "action": "save"}).status_code == 422


def test_collection_partial_payment_document_and_reminder_stop(client, seeded, db):
    h = login(client)
    inv = db.scalar(select(Invoice).where(Invoice.status == "open"))
    inv.amount_paid = 5000; inv.status = "partial"; db.commit()
    c = start(client, h, "collect", invoice_id=str(inv.id), disputed="no", promised_date=None, review_date="2026-10-17")
    done, _ = confirm(client, h, c, "draft")
    assert done["result"]["metrics"]["outstanding"] == float(inv.amount) - 5000
    assert done["documents"][0]["stage"] == "prepared"
    from sme_copilot.pilot.worker import due_jobs
    inv.status = "paid"; inv.amount_paid = inv.amount; db.commit()
    due_jobs(db, date(2026, 10, 17)); db.commit()
    job = db.scalar(select(ReminderJob).where(ReminderJob.case_id == c["id"]))
    assert not job.active


def loan_answers():
    return dict(lender="Actual written quote", quote_source="Written quote dated 2026-10-14", principal=10000, fees=200,
        schedule=[{"date": "2026-10-21", "amount": 2000}, {"date": "2027-10-21", "amount": 9500}],
        quote_complete="yes", cash=50000, purchase=5000, income=20000, slow_income=10000,
        expenses=3000, household=2000, existing_debt=500, other_schedule=[], reserve=10000, cash_timing="daily",
        facts_complete="yes", security="No pledge in quote", review_date="2026-10-20")


def test_full_loan_term_unknowns_and_last_balloon(client):
    a = loan_answers()
    result = loan(a, date(2026, 10, 14))
    assert result["end_date"] == "2027-10-21" and result["metrics"]["total_repaid"] == 11500
    assert result["metrics"]["net_received"] == 9800
    for key in ("fees", "existing_debt", "expenses", "cash", "household", "schedule"):
        assert loan({**a, key: None}, date(2026, 10, 14))["status"] == "need_information"
    tight = {**a, "schedule": [{"date": "2027-10-21", "amount": 1000000}]}
    assert loan(tight, date(2026, 10, 14))["status"] == "tight"
    h = login(client); c = start(client, h, "loan", **a); done, _ = confirm(client, h, c)
    assert done["result"]["human_review"] == "pending"


def test_seasonal_loan_missing_calendar_and_delayed_receipts():
    a = {**loan_answers(), "cash_timing": "uneven"}
    assert loan(a, date(2026, 10, 14))["status"] == "need_information"
    a["income_schedule"] = [{"date": "2027-01-01", "amount": 120000}]
    result = loan(a, date(2026, 10, 14))
    assert result["usual"]["minimum"] <= a["cash"] + a["principal"] - a["fees"] - a["purchase"]
    assert result["slow"]["minimum"] <= result["usual"]["minimum"]


def test_legacy_illustrative_guidance_blocked_for_pilot(client, monkeypatch, seeded):
    from sme_copilot.config import get_settings
    from sme_copilot.forecasting.alerts import compliance_due_dates
    monkeypatch.setattr(get_settings(), "allow_illustrative_guidance", False)
    h = login(client)
    for tool in ("match_financing", "get_financing_catalog", "loan_readiness_score", "compliance_info"):
        r = client.post(f"/api/tools/{tool}", headers=h, json={"args": {}})
        assert r.status_code == 403 and r.json()["detail"]["status"] == "blocked", r.text
    assert compliance_due_dates(seeded["business"], date(2026, 11, 25)) == []


def test_stock_test_and_follow_up(client):
    h = login(client)
    a = dict(product="Soap", quantity=20, unit_cost=50, delivery=100, price=75, selling_cost=5,
             expected=15, evidence="Five customer requests", risk="Some may stay unsold", collection_days=0,
             cash=10000, reserve=5000, review_date="2026-11-15")
    c = start(client, h, "stock", **a); saved, _ = confirm(client, h, c, "small")
    assert saved["result"]["test_quantity"] == 10 and saved["result"]["test_budget"] == 600
    result = post(client, h, f"cases/{c['id']}/outcome", {"units_sold": 7, "money_received": 525})
    assert result["result"]["outcome"]["units_sold"] == 7
    c = start(client, h, "stock", **{**a, "cash": 5100})
    r = client.post(f"/api/pilot/cases/{c['id']}/preview", headers=h, json={"version": c["version"], "action": "small"})
    assert r.status_code == 422


def test_shortfall_and_paperwork_handoff(client):
    h = login(client)
    c = start(client, h, "shortfall", purpose="Supplier", amount=20000, due_date="2026-10-25", cash=12000,
              essentials=5000, collections=7000, existing_debt=1000, reserve=2000, review_date="2026-10-20")
    done, _ = confirm(client, h, c, "supplier")
    assert done["result"]["metrics"]["gap_now"] == 16000
    c = start(client, h, "paperwork", topic="trade", authority="dscc", activity="General shop", registered="yes",
              period="2026-27", documents="Previous licence", deadline="2026-11-01", deadline_source="Licence page 1",
              request="Please advise the renewal process.")
    done, _ = confirm(client, h, c, "draft"); d = done["documents"][0]
    assert "guidance" in d["body"] and d["stage"] == "prepared"
    assert client.patch(f"/api/pilot/documents/{d['id']}", headers=h, json={"stage": "accepted", "reference": "receipt"}).status_code == 422
    for stage in ("submitted", "accepted"):
        r = client.patch(f"/api/pilot/documents/{d['id']}", headers=h, json={"stage": stage, "reference": "REF-1"})
        assert r.status_code == 200
    assert client.get("/api/pilot/documents", headers=h).json()[0]["stage"] == "accepted"


def test_tenant_role_input_validation_and_privacy(client, seeded, db):
    h = login(client); c = start(client, h, "record", **sale())
    hview = login(client, "viewer", "viewer-pass-123")
    assert client.post("/api/pilot/cases", headers=hview, json={"kind": "record", "request_key": str(uuid4())}).status_code == 403
    h = login(client)
    from sme_copilot.security.auth import create_user
    other = Business(name="Other"); db.add(other); db.flush(); create_user(db, other.id, "other", "other-pass-123", "owner", "Other"); db.commit()
    other_h = login(client, "other", "other-pass-123")
    assert client.get(f"/api/pilot/cases/{c['id']}", headers=other_h).status_code == 404
    h = login(client)
    r = client.post(f"/api/pilot/cases/{c['id']}/answer", headers=h, json={"version": c["version"], "question_id": "amount", "value": "NaN"})
    assert r.status_code == 422
    data = client.get("/api/privacy/export", headers=h).json()
    assert len(data["guided_cases"]) == 1
    saved, _ = confirm(client, h, c)
    r = client.post("/api/privacy/delete", headers=h, json={"password": "owner-pass-123", "confirm": "DELETE MY DATA"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert not list(db.scalars(select(GuidedCase).where(GuidedCase.business_id == seeded["business"].id)))


def test_sms_opt_in_daily_deduplication_retry_and_no_sensitive_content(client, db, seeded, monkeypatch):
    from sme_copilot.config import get_settings
    from sme_copilot.pilot.worker import tick
    monkeypatch.setattr(get_settings(), "pilot_sms_enabled", True)
    h = login(client)
    assert client.put("/api/pilot/notifications", headers=h, json={"phone": "01711111111", "consent": True, "send_hour": 18}).status_code == 200
    c = start(client, h, "record", record_type="check", date="2026-10-14", cash=1, note=None)
    confirm(client, h, c)
    class Provider:
        calls = []
        def send(self, phone, text, reference):
            self.calls.append((phone, text, reference))
            return ("retry", "", "connection_failed") if len(self.calls) == 1 else ("accepted", "ref-1", "")
    provider = Provider()
    now = datetime(2026, 10, 14, 12, 0)
    tick(db, now, provider); assert not provider.calls  # unverified number
    pref = db.get(NotificationPreference, seeded["owner"].id); pref.verified = True; db.commit()
    tick(db, now, provider); tick(db, now + timedelta(minutes=1), provider)
    assert len(provider.calls) == 1
    tick(db, now + timedelta(minutes=6), provider); tick(db, now + timedelta(minutes=7), provider)
    assert len(provider.calls) == 2 and provider.calls[0][2] == provider.calls[1][2]
    delivery = db.scalar(select(NotificationDelivery)); assert delivery.status == "accepted"
    assert "1,200" not in provider.calls[0][1] and "Nusrat" not in provider.calls[0][1]
    assert len(list(db.scalars(select(NotificationDelivery)))) == 1


def test_changed_sources_never_auto_verify(db, monkeypatch):
    from sme_copilot.pilot import knowledge
    specs = {"sources": [{"id": "test", "url": "https://example.gov.bd/rule", "reviewed_by": "Local reviewer",
        "reviewed_on": "2026-10-14", "effective_from": "2026-10-01", "valid_until": "2026-10-21"}]}
    monkeypatch.setattr(knowledge, "load_yaml", lambda _: specs)
    day = datetime(2026, 10, 14)
    knowledge.check_sources(db, day, httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text="first"))))
    knowledge.check_sources(db, day + timedelta(days=1), httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text="changed"))))
    assert knowledge.sources(db, date(2026, 10, 15))[0]["status"] == "changed"
    assert knowledge.sources(db, date(2026, 11, 1))[0]["status"] != "reviewed"


def test_backup_restores_guided_data_without_overwrite(client, db, tmp_path):
    import sqlite3
    from scripts.backup_pilot import backup
    h = login(client); c = start(client, h, "record", **sale()); confirm(client, h, c)
    path = backup(tmp_path / "owner-backup.db")
    with sqlite3.connect(path) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert restored.execute("SELECT COUNT(*) FROM guided_cases").fetchone()[0] == 1
    with pytest.raises(ValueError):
        backup(path)


def test_document_attachment_validation_and_encryption(client, db):
    from sme_copilot.pilot.models import CaseDocument
    from sqlalchemy import text
    h = login(client); c = start(client, h, "record", **sale())
    url = f"/api/pilot/cases/{c['id']}/attachments"
    preview = post(client, h, f"cases/{c['id']}/preview", {"version": c["version"], "action": "save"})
    assert client.post(url, headers=h, files={"file": ("evil.html", b"<script>alert(1)</script>", "application/pdf")}).status_code == 422
    raw = b"%PDF-1.4\nprivate-owner-document"
    response = client.post(url, headers=h, files={"file": ("quote.pdf", raw, "application/pdf")})
    assert response.status_code == 200
    doc_id = response.json()["id"]
    stored = db.execute(text("SELECT content FROM case_documents WHERE id=:id"), {"id": doc_id}).scalar()
    assert "private-owner" not in stored and not stored.startswith("JVBER")
    assert client.get(f"/api/pilot/documents/{doc_id}/download", headers=h).content == raw
    assert client.post(f"/api/pilot/cases/{c['id']}/confirm", headers=h, json={"version": preview["version"], "token": preview["preview"]["token"]}).status_code == 409


def test_sms_unknown_is_never_blindly_retried_and_optout_stops_it(client, db, seeded, monkeypatch):
    from sme_copilot.config import get_settings
    from sme_copilot.pilot.worker import tick
    monkeypatch.setattr(get_settings(), "pilot_sms_enabled", True)
    h = login(client)
    client.put("/api/pilot/notifications", headers=h, json={"phone": "01711111111", "consent": True})
    pref = db.get(NotificationPreference, seeded["owner"].id); pref.verified = True; db.commit()
    c = start(client, h, "record", record_type="check", date="2026-10-14", cash=1, note=None); confirm(client, h, c)
    class Provider:
        calls = 0
        def send(self, *args):
            self.calls += 1
            return "unknown", "", "read_timeout"
    provider = Provider(); now = datetime(2026, 10, 14, 12)
    tick(db, now, provider); tick(db, now + timedelta(minutes=20), provider)
    assert provider.calls == 1
    client.put("/api/pilot/notifications", headers=h, json={"phone": "01711111111", "consent": False})
    db.expire_all(); tick(db, now + timedelta(minutes=30), provider)
    assert provider.calls == 1


def test_model_cannot_choose_unapproved_question(monkeypatch):
    from sme_copilot.pilot import question_model
    pending = [{"id": "cash", "label": {"en": "Cash", "bn": "টাকা"}, "type": "money"}]
    monkeypatch.setattr(question_model, "select_id", lambda *args: "execute_payment")
    assert question_model.next_question("loan", {"principal": 100}, pending)["id"] == "cash"
