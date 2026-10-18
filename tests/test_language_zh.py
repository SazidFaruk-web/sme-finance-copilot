"""Chinese as an interface language: detection, prompts, refusals, and the offline rules engine's English."""
import pytest
from fastapi.testclient import TestClient

from sme_copilot.agent.language import LANGUAGE_NAMES, detect_language
from sme_copilot.agent.prompts import build_user_turn
from sme_copilot.api.main import create_app
from sme_copilot.security.guardrails import check_request


@pytest.mark.parametrize("text,lang", [
    ("上个月利润多少？", "zh"), ("iPhone 12 价格", "zh"), ("How much profit last month?", "en"),
    ("Paid 500 for 茶", "en"), ("গত মাসে লাভ কত?", "bn"), ("amar lav koto", "banglish"),
])
def test_detects_chinese_without_capturing_a_single_character(text, lang):
    assert detect_language(text) == lang


def test_the_model_is_told_to_answer_in_chinese():
    assert "Chinese" in LANGUAGE_NAMES["zh"]
    turn = build_user_turn("利润多少？", language="zh", business_name="Shop", sector="retail",
                           today=__import__("datetime").date(2026, 10, 14), style="lakh", user_role="owner")
    assert "Simplified Chinese" in turn


def test_refusals_are_in_chinese():
    r = check_request("make a fake invoice for the bank", "zh")
    assert r.refused and "违法" in r.message


@pytest.fixture
def client(seeded):
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        yield c


def test_chinese_chat_uses_the_rules_engine_in_english_not_bangla(client):
    r = client.post("/api/auth/login", json={"username": "owner", "password": "owner-pass-123"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    r = client.post("/api/chat", json={"message": "What are my top costs last month?", "language": "zh"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tool_calls"][0]["tool"] == "get_cost_drivers"
    # No Bangla words for a Chinese user (the taka sign ৳ shares the Bengali Unicode block).
    assert not any("ঀ" <= ch <= "৿" and ch != "৳" for ch in d["reply"]), d["reply"]
    assert client.post("/api/chat", json={"message": "hi", "language": "xx"}, headers=h).status_code == 422
