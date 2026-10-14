"""HTTP API: auth, chat, SSE, tools, upload, audit, headers, rate limiting."""
import json

import pytest
from fastapi.testclient import TestClient

from sme_copilot.api.main import create_app
from tests.conftest import SMALL_LEDGER


@pytest.fixture
def client(seeded):
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        yield c


def login(client, user="owner", pw="owner-pass-123"):
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_requires_auth(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "owner", "password": "nope"})
    assert r.status_code == 401 and "invalid" in r.json()["detail"]


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_chat_roundtrip_and_conversation(client):
    h = login(client)
    r = client.post("/api/chat", json={"message": "What are my top costs last month?"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tool_calls"][0]["tool"] == "get_cost_drivers" and d["profile"] == "rules-offline"
    assert d["traces"] and d["conversation_id"]
    r2 = client.post("/api/chat", json={"message": "gato mash e lav koto?", "conversation_id": d["conversation_id"]},
                     headers=h)
    assert r2.json()["language"] == "banglish"


def test_chat_unknown_profile_rejected(client):
    h = login(client)
    r = client.post("/api/chat", json={"message": "hi", "profile": "gpt-99"}, headers=h)
    assert r.status_code == 400


def test_chat_profile_override_falls_back_when_key_missing(client):
    h = login(client)
    r = client.post("/api/chat", json={"message": "summary last 3 months", "profile": "claude-sonnet"}, headers=h)
    d = r.json()
    assert d["profile"] == "rules-offline"
    assert d["attempts"][0]["profile"] == "claude-sonnet" and "missing env var" in d["attempts"][0]["error"]


def test_chat_stream_sse(client):
    h = login(client)
    with client.stream("POST", "/api/chat/stream", json={"message": "break even?"}, headers=h) as r:
        body = "".join(r.iter_text())
    assert "event: tool" in body and "event: delta" in body and "event: done" in body
    done = [ln for ln in body.split("\n\n") if ln.startswith("event: done")][0]
    payload = json.loads(done.split("data: ", 1)[1])
    assert payload["tool_calls"][0]["tool"] == "get_break_even"


def test_tools_endpoint_uses_permission_pipeline(client):
    h_view = login(client, "viewer", "viewer-pass-123")
    r = client.post("/api/tools/get_profitability", json={"args": {"period": "last_3_months"}}, headers=h_view)
    assert r.status_code == 200 and r.json()["data"]["gross_margin_pct"] == 50.0
    r = client.post("/api/tools/add_transaction", json={"args": {"text": "paid rent 5000"}}, headers=h_view)
    assert r.status_code == 403
    r = client.post("/api/tools/execute_real_bank_transfer", json={"args": {}}, headers=login(client))
    assert r.status_code == 403 and r.json()["detail"]["status"] == "blocked"
    assert client.post("/api/tools/nope", json={"args": {}}, headers=h_view).status_code == 404
    tools = client.get("/api/tools", headers=h_view).json()
    assert any(t["name"] == "get_aging" and t["tier"] == 0 for t in tools)


def test_upload_and_transactions(client):
    h = login(client, "accountant", "acct-pass-123")
    extra = SMALL_LEDGER.replace("2026", "2025")
    r = client.post("/api/data/upload", files={"file": ("old.csv", extra.encode(), "text/csv")},
                    data={"doc_type": "auto"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 15
    r = client.post("/api/data/upload", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, headers=h)
    assert r.status_code == 415
    rows = client.get("/api/data/transactions?limit=5", headers=h).json()["rows"]
    assert len(rows) == 5 and {"source_row", "flags", "account"} <= set(rows[0])
    h_view = login(client, "viewer", "viewer-pass-123")
    r = client.post("/api/data/paste", json={"text": "Date,Amount\n01/01/2026,5"}, headers=h_view)
    assert r.status_code == 403


def test_entry_preview_and_record(client):
    h = login(client)
    p = client.post("/api/data/entry/preview", json={"text": "dokan bhara 15k dilam bkash e"}, headers=h).json()
    assert p["amount"] == 15000 and p["category"] == "rent"
    r = client.post("/api/data/entry", json={"text": "dokan bhara 15k dilam bkash e"}, headers=h)
    assert r.json()["data"]["recorded"] is True


def test_patch_category_is_audited(client):
    h = login(client)
    tid = client.get("/api/data/transactions?limit=1", headers=h).json()["rows"][0]["id"]
    r = client.patch(f"/api/data/transactions/{tid}", json={"category": "marketing"}, headers=h)
    assert r.status_code == 200 and r.json()["categorized_by"] == "user"
    log = client.get("/api/audit?event_type=operation", headers=h).json()
    assert any(e["action"] == "edit_transaction" for e in log)
    assert client.get("/api/audit/verify", headers=h).json()["ok"] is True


def test_viewer_cannot_read_audit(client):
    assert client.get("/api/audit", headers=login(client, "viewer", "viewer-pass-123")).status_code == 403


def test_feedback(client, tmp_path):
    h = login(client)
    d = client.post("/api/chat", json={"message": "break even?"}, headers=h).json()
    r = client.post("/api/feedback", json={"interaction_id": d["interaction_id"], "rating": "down",
                                           "correction": "Call me on 01711111111 instead"}, headers=h)
    assert r.status_code == 200
    from sme_copilot.telemetry.interactions import read_all
    inter, fb = read_all()
    assert d["interaction_id"] in inter and fb[d["interaction_id"]]["rating"] == "down"
    assert "01711111111" not in fb[d["interaction_id"]]["correction"]


def test_login_rate_limit(client, monkeypatch):
    from sme_copilot.config import reset_settings_cache
    monkeypatch.setenv("LOGIN_RATE_LIMIT_PER_MINUTE", "3")
    reset_settings_cache()
    codes = [client.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3] == 429


def test_dashboard_payload(client):
    h = login(client, "viewer", "viewer-pass-123")
    d = client.get("/api/dashboard", headers=h).json()
    assert d["kpis"]["cash_balance"] == 380_000 and d["kpis"]["gross_margin_3m"] == 50.0
    assert len(d["forecast"]["series"]) == 90 and {"low", "high", "balance"} <= set(d["forecast"]["series"][0])
    assert d["expense_breakdown"][0]["category"] == "inventory"
    assert any(a["kind"] == "overdue_invoice" for a in d["alerts"])
    assert d["kpi_traces"]["margins"]["steps"]


def test_whatif_and_alert_actions(client):
    h = login(client)
    r = client.post("/api/whatif", json={"scenarios": [{"kind": "revenue_change", "pct": -30}]}, headers=h)
    assert r.status_code == 200 and r.json()["end_balance_change"] < 0
    bad = client.post("/api/whatif", json={"scenarios": [{"kind": "loan"}]}, headers=h)
    assert bad.status_code == 422
    alerts = client.get("/api/alerts", headers=h).json()
    aid = alerts[0]["id"]
    assert client.post(f"/api/alerts/{aid}/dismissed", headers=h).json()["status"] == "dismissed"
    h_view = login(client, "viewer", "viewer-pass-123")
    assert client.post(f"/api/alerts/{aid}/acknowledged", headers=h_view).status_code == 403


def test_settings_toggle_number_style(client):
    h = login(client)
    assert client.patch("/api/settings", json={"number_style": "intl"}, headers=h).json()["number_style"] == "intl"
    d = client.post("/api/chat", json={"message": "summary last 3 months"}, headers=h).json()
    assert "৳900,000" in d["reply"]
