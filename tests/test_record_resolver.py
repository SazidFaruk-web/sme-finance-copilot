"""Resolver / fast-path / queue tests (no LLM). Slow end-to-end cases run against the real model: pytest -m slow."""
from __future__ import annotations

import pytest

from sme_copilot.tools import record_resolver as rr
from sme_copilot.tools.record_resolver import fast_path, read_record, resolve_record


def ex(**kw):
    base = {"type": "sale", "item": None, "quantity": None, "unit_price": None, "total_stated": None,
            "counterparty": None, "category": "sales", "payment_method": "unknown"}
    return {**base, **kw}


def test_unit_price_times_quantity():
    r = resolve_record(ex(item="gamcha", quantity=6, unit_price=100))
    assert r["signed_amount"] == 600 and not r["needs_confirm"] and "6 gamcha x 100 = 600" in r["preview"]


def test_large_quantity():
    assert resolve_record(ex(item="lungi", quantity=200, unit_price=120))["signed_amount"] == 24000


def test_sale_return_is_negative_and_contra_revenue():
    r = resolve_record(ex(type="sale_return", item="shirt", quantity=2, total_stated=1500, category="sales_returns"))
    assert r["signed_amount"] == -1500 and r["direction"] == "out" and r["category"] == "sales_returns"
    assert not r["needs_confirm"]


def test_rent_expense():
    r = resolve_record(ex(type="expense", category="rent", total_stated=10000))
    assert r["signed_amount"] == -10000 and r["category"] == "rent"


def test_single_amount_uses_total():
    r = resolve_record(ex(total_stated=750))
    assert r["amount"] == 750 and not r["needs_confirm"]


def test_amount_none_needs_confirm():
    r = resolve_record(ex(item="x"))
    assert r["needs_confirm"] and r["signed_amount"] is None


def test_supplier_return_positive():
    r = resolve_record(ex(type="purchase_return", category="purchases", total_stated=4500))
    assert r["signed_amount"] == 4500 and r["direction"] == "in" and r["category"] == "purchase_returns"


def test_total_mismatch_prefers_total_and_confirms():
    r = resolve_record(ex(quantity=6, unit_price=100, total_stated=700))
    assert r["amount"] == 700 and r["needs_confirm"]


@pytest.mark.parametrize("kw", [dict(total_stated=2_000_000), dict(total_stated=-5), dict(total_stated=100, quantity=0),
                                dict(type="expense", category="other", total_stated=100)])
def test_confirm_triggers(kw):
    assert resolve_record(ex(**kw))["needs_confirm"]


def test_fast_path_patterns():
    assert fast_path("sold 12 shirts for 6000 taka") | {} == fast_path("sold 12 shirts for 6000 taka")
    e = fast_path("6 ta gamcha bikri korci protitar dam 100 taka kore")
    assert (e["quantity"], e["unit_price"], e["total_stated"]) == (6, 100, None)
    e = fast_path("200 Lungi bikri korsi prottektar dam chilo 120 taka kore")
    assert resolve_record(e)["signed_amount"] == 24000
    e = fast_path("6 ta gamcha bikri korci 600 taka")
    assert (e["unit_price"], e["total_stated"]) == (None, 600)
    e = fast_path("dokan vara 10000 taka dilam")
    assert e["category"] == "rent" and resolve_record(e)["signed_amount"] == -10000


@pytest.mark.parametrize("text", ["2 ta jama ferot diye gese 1500 taka", "supplier ke ferot dilam 4500 taka",
                                  "hello"])
def test_fast_path_skips_returns(text):
    assert fast_path(text) is None


def test_llm_cache_and_failure(monkeypatch):
    rr.clear_cache()
    calls = []

    def fake(text):
        calls.append(text)
        return ex(type="sale_return", quantity=2, total_stated=1500, category="sales_returns")

    monkeypatch.setattr(rr, "_llm_extract", fake)
    t = "2 ta jama ferot diye gese 1500 taka"
    assert read_record(t)[1] == "llm" and read_record("  2 TA jama ferot diye gese 1500 taka ")[1] == "cache"
    assert len(calls) == 1

    rr.clear_cache()
    n = {"c": 0}

    def flaky(text):
        n["c"] += 1
        if n["c"] == 1:
            raise ValueError("boom")
        return ex(total_stated=5)

    monkeypatch.setattr(rr, "_llm_extract", flaky)
    assert read_record("something odd 5")[1] == "llm" and n["c"] == 2  # retry once
    rr.clear_cache()
    monkeypatch.setattr(rr, "_llm_extract", lambda t: (_ for _ in ()).throw(ValueError("x")))
    assert read_record("unreadable zzz") == (None, "failed")


def test_add_transaction_end_to_end(seeded, monkeypatch):
    from sme_copilot.agent.tools_analysis import AddTxnArgs, add_transaction
    from tests.conftest import make_ctx
    ctx = make_ctx(seeded)
    r = add_transaction(ctx, AddTxnArgs(text="6 ta gamcha bikri korci protitar dam 100 taka kore"))
    assert r.recorded and r.entry["amount"] == 600 and r.entry["direction"] == "in"
    monkeypatch.setattr(rr, "_llm_extract", lambda t: ex(type="sale_return", quantity=2, total_stated=1500,
                                                         category="sales_returns"))
    rr.clear_cache()
    r = add_transaction(ctx, AddTxnArgs(text="2 ta jama ferot diye gese 1500 taka"))
    assert r.recorded and r.entry["amount"] == 1500 and r.entry["direction"] == "out"
    assert r.entry["category"] == "sales_returns"
    monkeypatch.setattr(rr, "_llm_extract", lambda t: ex(type="expense", category="other", total_stated=90))
    rr.clear_cache()
    r = add_transaction(ctx, AddTxnArgs(text="kichu ekta 90 taka"))
    assert not r.recorded and r.needs_confirm and r.preview
    assert add_transaction(ctx, AddTxnArgs(text="kichu ekta 90 taka", confirmed=True)).recorded


@pytest.mark.slow
@pytest.mark.parametrize("text,signed", [
    ("6 ta gamcha bikri korci protitar dam 100 taka kore", 600),
    ("200 Lungi bikri korsi prottektar dam chilo 120 taka kore", 24000),
    ("2 ta jama ferot diye gese 1500 taka", -1500),
    ("supplier ke 3 ta thaan ferot dilam 4500 taka", 4500),
    ("১০ টা পাঞ্জাবি কিনলাম প্রতিটা ৫০০ টাকা", -5000),
])
def test_real_model(text, signed):
    rr.clear_cache()
    extracted, _ = read_record(text)
    assert extracted is not None, "model unreachable"
    assert resolve_record(extracted)["signed_amount"] == signed
