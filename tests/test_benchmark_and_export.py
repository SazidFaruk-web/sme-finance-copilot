"""Benchmark harness, golden set integrity, tool-output compaction, fine-tune export."""
import json

from sme_copilot.agent.executor import compact_json
from sme_copilot.agent.toolkit import REGISTRY, load_all_tools
from sme_copilot.benchmarks.runner import dig, language_ok, load_golden, number_in_reply, run_benchmark, summarize, write_outputs
from sme_copilot.telemetry.export import build, export


def test_golden_set_is_large_multilingual_and_references_real_tools():
    load_all_tools()
    g = load_golden()
    assert len(g) >= 40 and len({s["id"] for s in g}) == len(g)
    langs = {s["lang"] for s in g}
    assert langs == {"en", "bn", "banglish"}
    assert sum(1 for s in g if s["lang"] == "bn") >= 8 and sum(1 for s in g if s["lang"] == "banglish") >= 8
    for s in g:
        for t in s.get("expect_tools", []):
            assert t in REGISTRY, (s["id"], t)
        if s.get("truth"):
            assert s["truth"]["tool"] in REGISTRY and REGISTRY[s["truth"]["tool"]].tier == 0
    assert any(s.get("expect_refusal") for s in g) and any(s.get("expect_no_execution") for s in g)


def test_metric_helpers():
    assert dig({"a": [{"b": 5}]}, "a.0.b") == 5
    assert number_in_reply(123456, [123000]) and not number_in_reply(123456, [100000])
    assert number_in_reply(1_234_567, [12.35])  # written as "12.35 lakh"
    assert language_ok("গত মাসে আপনার লাভ ৳৫০,০০০", "bn") and not language_ok("Your profit is ৳50,000", "bn")
    assert language_ok("Apnar lav ekhon ৳50,000", "banglish") and language_ok("Your profit is ৳50,000", "en")


def test_benchmark_runs_offline_and_writes_outputs(tmp_path):
    rows, summary = run_benchmark(["rules-offline", "claude-sonnet"], limit=6)
    assert len(rows) == 6 and summary[0]["profile"] == "rules-offline"  # unavailable cloud profile skipped
    assert summary[0]["tool_call_success"] == 1.0 and summary[0]["numeric_accuracy"] == 1.0
    assert all(r["fallback_used"] == 0 for r in rows)
    paths = write_outputs(rows, summary, tmp_path)
    assert paths["chart"].stat().st_size > 5_000
    assert "| rules-offline |" in paths["summary_md"].read_text(encoding="utf-8")


def test_compact_json_always_valid_and_keeps_counts():
    big = {"status": "ok", "result": {"recommendations": [{"name": f"p{i}", "documents": ["x" * 400] * 10,
                                                            "reasons": ["r" * 200] * 4} for i in range(30)],
                                      "rejected": [], "trace": {"formula": "f", "steps": [{"x": "y" * 500}] * 50}}}
    text = compact_json(big, budget=6000)
    d = json.loads(text)
    assert len(text) <= 6000 and d["result"]["recommendations_total"] == 30


def test_finetune_export(tmp_path):
    log = tmp_path / "interactions.jsonl"
    recs = [
        {"type": "interaction", "id": "a", "user": "gato mash e lav koto?", "reply": "Lav ৳50,000", "language": "banglish",
         "tool_results": [{"tool": "get_profitability", "arguments": {"period": "last_month"}, "output": "{\"status\": \"ok\"}"}],
         "ungrounded_numbers": [], "error": ""},
        {"type": "interaction", "id": "b", "user": "q2", "reply": "bad", "tool_results": [], "ungrounded_numbers": [], "error": ""},
        {"type": "interaction", "id": "c", "user": "q3", "reply": "meh", "tool_results": [], "ungrounded_numbers": [], "error": ""},
        {"type": "interaction", "id": "d", "user": "q4", "reply": "x 999", "tool_results": [], "ungrounded_numbers": [999], "error": ""},
        {"type": "feedback", "id": "a", "rating": "up"},
        {"type": "feedback", "id": "b", "rating": "down", "correction": "better"},
        {"type": "feedback", "id": "c", "rating": "down", "correction": None},
    ]
    log.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
    sft, prefs, stats = build(include_unrated=True, path=log)
    assert stats["kept_up"] == 1 and stats["kept_corrected"] == 1 and stats["excluded_down_no_correction"] == 1
    assert stats["excluded_error_or_ungrounded"] == 1
    a = next(x for x in sft if x["meta"]["id"] == "a")["messages"]
    assert [m["role"] for m in a] == ["system", "user", "assistant", "tool", "assistant"]
    assert a[2]["tool_calls"][0]["function"]["name"] == "get_profitability"
    assert prefs == [{"prompt": "q2", "chosen": "better", "rejected": "bad", "meta": prefs[0]["meta"]}]
    st = export(tmp_path / "out", include_unrated=False, path=log)
    assert (tmp_path / "out" / "sft_openai.jsonl").read_text(encoding="utf-8").count("\n") == 2 and st["excluded_unrated"] == 1
