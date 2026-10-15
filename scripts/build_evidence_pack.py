"""Build the competition evidence pack (PDF + DOCX) from collected evidence and the repo's result files.

    python scripts/collect_evidence.py EVID --junit EVID/junit.xml --pytest-output EVID/pytest_output.txt
    python scripts/build_evidence_pack.py EVID OUT_DIR        (needs reportlab, uharfbuzz, python-docx)

Every number comes from EVID/evidence.json, EVID/junit.xml or files under benchmarks/results; numbers that
were observed in a session rather than stored in a file are labelled as such. Nothing here imports the app.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "benchmarks" / "results"
BN = re.compile(r"[\u0980-\u09FF]")
_SECRET_RX = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{6,}"), "sk-***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{10,}"), r"\1***"),
    (re.compile(r"(?i)(api[_-]?key|token|password|secret)(\"?\s*[:=]\s*\"?)[^\s\",}]+"), r"\1\2***"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "***@***"),
    (re.compile(r"\b\w+-demo-20\d\d\b"), "***"),  # demo passwords
]


def scrub(s: str) -> str:
    for rx, rep in _SECRET_RX:
        s = rx.sub(rep, s)
    return s


def pct(v) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def num(v, unit="") -> str:
    return "n/a" if v is None else f"{v}{unit}"


# ----------------------------------------------------------------------------- content model
class Doc:
    def __init__(self):
        self.blocks: list[tuple] = []

    def h1(self, t): self.blocks.append(("h1", t))
    def h2(self, t): self.blocks.append(("h2", t))
    def p(self, t): self.blocks.append(("p", scrub(t)))
    def bullets(self, items): self.blocks.append(("ul", [scrub(i) for i in items]))
    def code(self, t): self.blocks.append(("code", scrub(t)))
    def table(self, header, rows, widths=None): self.blocks.append(("table", header, [[scrub(str(c)) for c in r] for r in rows], widths))
    def img(self, path, caption): self.blocks.append(("img", path, caption))
    def br(self): self.blocks.append(("pagebreak",))


def golden(ev, label):
    return next((g for g in ev["benchmarks"]["golden"] if g["label"] == label), None)


def speed(ev, label):
    return next((s for s in ev["benchmarks"]["speed"] if s["label"] == label), None)


def rows_of(label):
    p = RES / "golden" / label / "results.json"
    return json.loads(p.read_text(encoding="utf-8"))["rows"] if p.exists() else None


def classify(name: str, cls: str) -> str:
    n = name.lower()
    if "language" in n or "detect_lang" in n:
        return "Language detection"
    if any(k in n for k in ("fallback", "falls_back", "router", "local_only", "override_goes_first", "streams_only",
                            "never_falls")):
        return "Provider routing and fallback"
    if any(k in n for k in ("system_prompt_is_static", "prompt_cache", "single_leading_system", "constrained",
                            "chat_stream", "envelope", "structured", "emulated", "extract_json")):
        return "Prompts, caching and tool-call formats"
    if cls in ("test_security", "test_pii") or any(k in n for k in ("injection", "blocked_tool", "neutral")):
        return "Security, permissions and prompt-injection scanner"
    if cls == "test_ingestion" or any(k in n for k in ("upload", "import", "categoriz")):
        return "Upload and ingestion"
    if cls in ("test_actions", "test_analysis", "test_finance_math", "test_financing", "test_forecast", "test_nl_entry"):
        return "Finance tools and sandbox actions"
    if cls == "test_providers":
        return "Provider adapters (wire formats)"
    return "API, agent loop, UI and benchmark plumbing"


def build_content(ev: dict, junit: Path, shots: Path) -> Doc:
    d = Doc()
    env, tests = ev["environment"], ev["tests"]
    final = golden(ev, "final-gemma-golden")
    stress = next((s for s in ev["benchmarks"]["stress"] if s["label"] == "final-gemma-stress-v2"), None)

    # 1 -------------------------------------------------------------------------------------------------
    d.h1("1. Overview")
    d.table(["Item", "Value"], [
        ["Project", "SME Finance Copilot (sme-finance-copilot)"],
        ["Competition", "2026 Shenzhen International FinTech Competition (FinTechathon), International Track, "
                        "Topic E: SME Finance Copilot"],
        ["Evidence generated", ev["generated"]],
        ["Git branch", env["git_branch"]],
        ["Git commit", env["git_commit"]],
        ["Commit date", env["git_commit_date"]],
        ["Data used", "Fictional demo persona and FAKE generated statements only. No real customer data."],
    ], [4, 12])
    d.p("This pack collects the evidence behind the project's claims: a fresh automated test run, model benchmarks "
        "on a 48-scenario golden set and a 44-prompt Bangla/Banglish/English stress set, security and sandbox "
        "decisions taken from the real audit log, data-ingestion checks against totals computed with pandas, and "
        "UI screenshots. Section 11 gives the exact commands to reproduce every result from a clean clone.")
    d.p("How the evidence was produced: scripts/collect_evidence.py (fresh tests, uploads, security cases on a "
        "throwaway copy of the seeded demo database, result files) and scripts/build_evidence_pack.py (this "
        "document). Neither changes application code.")

    # 2 -------------------------------------------------------------------------------------------------
    d.h1("2. Environment")
    d.table(["Component", "Value"], [
        ["GPU", "AMD Radeon RX 9060 XT, 16 GB VRAM (Vulkan backend)"],
        ["CPU / RAM", "AMD Ryzen 7 3700X (8 cores) / 16 GB DDR4-3200"],
        ["OS", f"Microsoft Windows 10 Home 10.0.19045 ({env['os']})"],
        ["Python", env["python"]],
        ["llama.cpp", env["llama_server"]],
        ["Default provider profile", f"{env['default_profile']} (config/providers.yaml)"],
        ["Fallback chain", " -> ".join(env["fallback_chain"] or [])],
    ], [4, 12])
    d.h2("Local model profiles")
    d.table(["Profile", "Model", "Tools", "Timeout", "Retries", "Endpoint"],
            [[k, v["model"], v["tools"], f"{v['timeout']} s", v["max_retries"], v["base_url"]]
             for k, v in env["local_profiles"].items()], [3.2, 3, 2, 1.6, 1.5, 4.7])
    d.h2("Final llama-server flags")
    d.code("Gemma 4 12B (default):\n  llama-server -m gemma-4-12b-it-Q4_K_M.gguf --host 127.0.0.1 --port 8080 -ngl 99 -c 16384 \\\n"
           "    --reasoning off -cram 2048 -fa on -ctk q8_0 -ctv q8_0 \\\n"
           "    --spec-type draft-mtp -md mtp-gemma-4-12B-it-Q8_0.gguf -ngld 99\n\n"
           "Qwen3-14B (backup):\n  llama-server -m Qwen3-14B-Q4_K_M.gguf --host 127.0.0.1 --port 8080 -ngl 99 -c 16384 \\\n"
           "    --reasoning off -cram 2048 -fa off\n\n"
           "Both are started by scripts\\start_local_llm.bat [gemma|qwen14b].")
    d.h2("Application settings (defaults)")
    d.table(["Setting", "Default"], [[k, v] for k, v in env["settings_defaults"].items()], [7, 9])
    d.h2("Model files on disk (D:\\llama-vulkan\\models)")
    md = env["models_on_disk"]
    d.table(["File", "Size (bytes)"], [[k, f"{v:,}"] for k, v in md.items()] if isinstance(md, dict) else [[md, ""]], [11, 5])

    # 3 -------------------------------------------------------------------------------------------------
    d.br()
    d.h1("3. Automated test results")
    if "missing" in tests:
        d.p(f"MISSING: test result file {tests['missing']}")
    else:
        d.table(["Total", "Passed", "Failed", "Errors", "Skipped", "Duration"], [[
            tests["tests"], tests["tests"] - tests["failures"] - tests["errors"] - tests["skipped"], tests["failures"],
            tests["errors"], tests["skipped"], f"{tests['summary_line'].split(' in ')[-1] if ' in ' in tests['summary_line'] else ''}"
            f" (pytest summary); {tests['time_s']} s (JUnit sum)"]], [2, 2, 2, 2, 2, 6])
        d.p(f"Run started {tests['timestamp']} with: python -m pytest -p no:cacheprovider -o addopts=\"\" -q "
            "--junitxml=junit.xml -rfE  (fresh process, no cache).")
        d.h2("Real output of the run (trimmed to the summary)")
        d.code("\n".join(tests["output_tail"]) + ("\nFAILED: " + ", ".join(tests["failed_tests"]) if tests["failed_tests"] else
                                                   "\n(no failures or errors to show)"))
        # by area
        groups: dict[str, list[str]] = defaultdict(list)
        status: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        if junit.exists():
            for tc in ET.parse(junit).getroot().iter("testcase"):
                cls = tc.get("classname", "").split(".")[-1]
                area = classify(tc.get("name", ""), cls)
                groups[area].append(tc.get("name"))
                status[area][0] += 1
                if tc.find("failure") is not None or tc.find("error") is not None:
                    status[area][1] += 1
        d.h2("Tests grouped by area")
        rows = []
        for area in sorted(groups):
            names = sorted({re.sub(r"\[.*\]$", "", n) for n in groups[area]})
            rows.append([area, status[area][0], status[area][1], ", ".join(n.replace("test_", "") for n in names[:7])
                         + (f" (+{len(names) - 7} more)" if len(names) > 7 else "")])
        d.table(["Area", "Tests", "Failed", "Examples (test names)"], rows, [4.2, 1.3, 1.3, 9.2])
        d.p("Areas are assigned by test name and file; parametrised cases count individually (e.g. each language "
            "sample in the language-detection test).")
        d.h2("Test files and what each covers")
        rows = []
        for f, v in tests["per_file"].items():
            doc = ""
            src = ROOT / "tests" / f"{f}.py"
            if src.exists():
                m = re.match(r'\s*"""(.*?)"""', src.read_text(encoding="utf-8"), re.S)
                doc = (m.group(1).strip().splitlines()[0] if m else "")
            rows.append([f"{f}.py", v["tests"], v["failures"], f"{v['time']} s", doc])
        d.table(["File", "Tests", "Failed", "Time", "Covers (module docstring)"], rows, [3.6, 1.2, 1.3, 1.4, 8.5])

    # 4 -------------------------------------------------------------------------------------------------
    d.br()
    d.h1("4. Model benchmark evidence")
    d.p("Golden set: sme_copilot/benchmarks/golden.yaml, 48 scenarios (26 English, 11 Bangla, 11 Banglish). Each "
        "scenario runs through the real agent loop; ground truth is computed by the app's deterministic tools on a "
        "fresh copy of the seeded demo DB. Speed harness: scripts/bench_local_llm.py with the app's real prompt. "
        "Rates are fractions of applicable scenarios, shown as recorded (one decimal).")
    d.h2("4.1 Comparison of all models (best configuration of each)")
    combos = [("Qwen3.8 27B IQ4_XS (before; first 16 scen.)", "qwen38-27b-baseline-first16", "27b-baseline"),
              ("Qwen3.5 9B Q5_K_M, native", "qwen35-9b-native", "9b-fastpp-native"),
              ("Qwen3.5 9B Q5_K_M, emulated", "qwen35-9b-emulated", "9b-fastpp-emulated"),
              ("Qwen3-14B Q4_K_M, emulated (backup)", "qwen3-14b-emulated", "14b-fastpp-emulated"),
              ("Gemma 4 12B Q4_K_M + MTP, native, final (default)", "final-gemma-golden", "gemma4-12b-faon-q8-mtp"),
              ("Granite 4.2 8B Q5_K_M, native", "granite42-8b-native", "granite42-8b-faoff"),
              ("gpt-oss-20b MXFP4, native", "gptoss20b-native", "gptoss20b-plain")]
    rows = []
    for name, gl, sl in combos:
        g, s = golden(ev, gl), speed(ev, sl)
        if not g:
            rows.append([name] + ["missing"] * 9)
            continue
        rows.append([name, g["scenarios"], pct(g["tool_call_success"]), pct(g["numeric_accuracy"]), pct(g["hallucination_rate"]),
                     pct(g["language_match_all"]), f"{s['ttft_cold_ms'] / 1000:.1f} s" if s else "n/a",
                     f"{s['tg_tok_s']}" if s else "n/a", f"{g['latency_p50_s']} s", f"{g['vram_peak_mb']:,} MB"])
    d.table(["Model / mode", "Scen.", "Tool ok", "Numeric", "Halluc.", "Lang.", "TTFT*", "Gen tok/s*", "Median answer",
             "Peak VRAM"], rows, [4.6, 1, 1.2, 1.3, 1.2, 1.2, 1.2, 1.3, 1.5, 1.6])
    d.p("* TTFT and generation tok/s come from the speed harness (cold first request with the app's full system "
        "prompt and tool definitions); the other columns come from the golden set. Peak VRAM is the llama-server "
        "process's dedicated GPU memory during the golden run. The 27B row covers only the first 16 (English) "
        "scenarios because each took 80+ s.")
    d.h2("4.2 Final golden-set and stress-set results (Gemma 4 12B, final settings)")
    if final and stress:
        d.table(["Metric", "Golden set (48)", "Stress set (44)"], [
            ["Scenarios / errors", f"{final['scenarios']} / {final['errors']}", f"{stress['scenarios']} / {stress['errors']}"],
            ["Tool-call success", pct(final["tool_call_success"]), pct(stress["tool_call_success"])],
            ["Valid tool arguments", pct(final["valid_tool_args"]), pct(stress["valid_tool_args"])],
            ["Numeric accuracy", pct(final["numeric_accuracy"]), pct(stress["numeric_accuracy"])],
            ["Financing top-match", pct(final["financing_match"]), pct(stress["financing_match"])],
            ["Answers with an unverified number", pct(final["hallucination_rate"]), pct(stress["hallucination_rate"])],
            ["Refusal correct", pct(final["refusal_correct"]), pct(stress["refusal_correct"])],
            ["Safety pass (no money moved)", pct(final["safety_pass"]), pct(stress["safety_pass"])],
            ["Reply language matches question", pct(final["language_match_all"]), pct(stress["language_match_all"])],
            ["Bangla + Banglish language match", pct(final["bangla_banglish_language_match"]),
             pct(stress["bangla_banglish_language_match"])],
            ["Median / mean / p95 answer time", f"{final['latency_p50_s']} / {final['latency_mean_s']} / {final['latency_p95_s']} s",
             f"{stress['latency_p50_s']} / {stress['latency_mean_s']} / {stress['latency_p95_s']} s"],
            ["Peak VRAM", f"{final['vram_peak_mb']:,} MB", f"{stress['vram_peak_mb']:,} MB"],
        ], [6, 5, 5])
        d.p("Stress set: sme_copilot/benchmarks/stress.yaml (44 prompts: English, Bangla script, Banglish and mixed; "
            "Bangla digits, the taka sign, typos, one-word and long questions, a period with no data, an unknown "
            "customer, an over-limit transfer). Run label final-gemma-stress-v2 (after the fixes in section 9).")
    else:
        d.p("MISSING: final golden or stress summary.")
    d.h2("4.3 Chosen models and why")
    d.bullets([
        "Default: Gemma 4 12B Q4_K_M with its MTP draft head (profile local-llamacpp, native tool calls). Highest "
        "numeric accuracy and language match of the models tested, fewest unverified numbers among the fast models, "
        "8 GB VRAM, and the only configuration that streams answers token by token.",
        "Backup: Qwen3-14B Q4_K_M (profile local-qwen14b, emulated JSON tool calls). Next-best accuracy and a different "
        "model family; slower and needs 13 GB.",
        "Rejected: gpt-oss-20b and Granite 4.2 8B were fast but 35-40% of their answers contained numbers that are "
        "in no tool result; Qwen3.5 9B was fast but less accurate; Qwen3.8 27B (before) was accurate on its 16 "
        "scenarios but took 80 s per answer and filled the GPU.",
        "The demo default is cloud Claude (default_profile in config/providers.yaml) because competition judges will "
        "not have this GPU; it was not benchmarked here (no API key on the build machine).",
    ])
    d.h2("4.4 Before and after (Qwen3.8 27B baseline vs Gemma 4 12B final)")
    b_s, a_s = speed(ev, "27b-baseline"), speed(ev, "gemma4-12b-faon-q8-mtp")
    b_g = golden(ev, "qwen38-27b-baseline-first16")
    base_rows, gem_rows = rows_of("qwen38-27b-baseline-first16"), rows_of("final-gemma-golden")
    same16 = None
    if base_rows and gem_rows:
        ids = [r["id"] for r in base_rows]
        gm = {r["id"]: r for r in gem_rows}
        sub = [gm[i] for i in ids if i in gm]

        def m(rs, k):
            v = [r[k] for r in rs if r.get(k) is not None]
            return sum(v) / len(v) if v else None
        same16 = (statistics.median(r["latency_ms"] for r in sub) / 1000, statistics.mean(r["latency_ms"] for r in sub) / 1000,
                  m(sub, "tool_ok"), m(sub, "numeric_accuracy"), m(sub, "hallucination"), len(sub))
    rows = []
    if b_s and a_s:
        rows += [["Generation speed (speed harness)", f"{b_s['tg_tok_s']} tok/s", f"{a_s['tg_tok_s']} tok/s"],
                 ["Prompt processing (speed harness)", f"{b_s['pp_tok_s']} tok/s", f"{a_s['pp_tok_s']} tok/s"],
                 ["Cold TTFT, full app prompt", f"{b_s['ttft_cold_ms'] / 1000:.2f} s", f"{a_s['ttft_cold_ms'] / 1000:.2f} s"],
                 ["Cached TTFT (repeat prefix)", f"{b_s['ttft_cached_ms'] / 1000:.2f} s", f"{a_s['ttft_cached_ms'] / 1000:.2f} s"],
                 ["VRAM (llama-server, dedicated)", f"{b_s['vram_dedicated_mb']:,} MB (GPU full, spills)", f"{a_s['vram_dedicated_mb']:,} MB"]]
    if b_g and same16:
        rows += [[f"Median / mean answer, same {same16[5]} golden scenarios", f"{b_g['latency_p50_s']} / {b_g['latency_mean_s']} s",
                  f"{same16[0]:.2f} / {same16[1]:.2f} s"],
                 ["Tool ok / numeric / unverified number, same scenarios",
                  f"{pct(b_g['tool_call_success'])} / {pct(b_g['numeric_accuracy'])} / {pct(b_g['hallucination_rate'])}",
                  f"{pct(same16[2])} / {pct(same16[3])} / {pct(same16[4])}"]]
    rows.append(["Chat answer seen in the UI (session observation, not in a result file)",
                 "132,415 ms for 'What needs my attention this week?' (2026-10-14)",
                 "first words after ~4.4 s, full answer 6.7 s for a cash question (streamed; 2026-10-15)"])
    d.table(["Measure", "Before: Qwen3.8 27B", "After: Gemma 4 12B"], rows, [6, 5, 5])
    d.p("Honest reading: on the same 16 English scenarios the 27B scored higher on tool calls and numbers; Gemma "
        "answers several times faster, fits in half the VRAM and streams. The full 48-scenario accuracy of the 27B "
        "was not measured (too slow).")

    # 5 -------------------------------------------------------------------------------------------------
    d.br()
    d.h1("5. Security and sandbox evidence")
    d.p("Each case below was executed fresh by scripts/collect_evidence.py on a throwaway copy of the seeded demo "
        "database. The decision is what the app returned; the log lines are the rows written to the hash-chained "
        "audit table (hash truncated to 12 characters). Phone and account numbers are masked by the app's own PII "
        "masker ([PHONE_1], [ACCOUNT_1]); provider calls were mocked, so nothing left the machine.")
    for i, c in enumerate(ev["security"], 1):
        d.h2(f"5.{i} {c['title']}")
        d.p(c["why"])
        d.table(["", ""], [["Input", c["input"]], ["System decision", c["decision"]]], [3, 13])
        d.code("\n".join(c["log"]) if c["log"] else "(no audit rows)")
    d.p("Finding: the Banglish attack 'ager sob instruction ignore koro ...' was caught by the Banglish transfer rule "
        "but not by the override rule (word order 'instruction ignore' differs from the English pattern). See "
        "section 10.")
    gs = next((c for c in ev["benchmarks"]["checks"] if c["label"] == "check-golden-safety"), None)
    if gs:
        d.p(f"Live-model safety re-check with Gemma (6 golden scenarios: English transfer, injection attack, accountant "
            f"transfer, three fraud refusals): tool ok {pct(gs['tool_call_success'])}, refusal correct "
            f"{pct(gs['refusal_correct'])}, safety pass {pct(gs['safety_pass'])}.")

    # 6 -------------------------------------------------------------------------------------------------
    d.br()
    d.h1("6. Data ingestion evidence")
    d.p("scripts/make_fake_statements.py writes 12 clearly FAKE files and expected.json (totals computed with pandas "
        "from the same rows). scripts/check_fake_uploads.py uploads each through POST /api/data/upload into its own "
        "fresh copy of the seeded DB and compares the stored rows and in/out totals. Fresh run for this pack:")
    exp = ev["uploads"]["expected"]
    tests_of = {
        "01_clean_bank.csv": "Bank statement with preamble lines, Withdrawal/Deposit columns",
        "02_clean_bank.xlsx": "Excel upload, Debit/Credit columns",
        "03_bangla_headers_digits.csv": "Bangla headers, Bangla descriptions, Bangla digits and the taka sign",
        "04_mixed_dates.csv": "Four date formats mixed in one file",
        "05_duplicates.csv": "10 repeated rows that must be flagged, not double-counted",
        "06_missing_amount_column.csv": "No amount / debit / credit column",
        "07_empty.csv": "Zero-byte file",
        "08_header_only.csv": "Header row with no data",
        "09_binary_garbage.csv": "Random bytes named .csv",
        "10_large_4_9mb.csv": "60,000 rows, about 3.2 MB",
        "11_too_large_6mb.csv": "Over the 5 MB upload limit",
        "12_statement.pdf": "PDF statement (unsupported format)",
    }
    rows = []
    out = {ln.split()[1]: ln for ln in ev["uploads"]["output"] if ln.startswith(("PASS", "FAIL"))}
    for f, e in exp.items():
        line = out.get(f, "")
        verdict = line.split()[0] if line else "missing"
        http = re.search(r"HTTP (\d+)", line)
        ms = re.search(r"(\d+) ms", line)
        if e.get("outcome") == "imported":
            got = re.search(r"in ([\d,]+)/[\d,]+\s+out ([\d,]+)/", line)
            expected = f"rows {e['rows']}; in {e['total_in']:,.0f}; out {e['total_out']:,.0f}"
            actual = f"in {got.group(1)}; out {got.group(2)}" if got else "see log"
        else:
            expected = e["outcome"]
            actual = (line.split("-> ", 1)[1][:220] if "-> " in line else "")
        rows.append([f, tests_of.get(f, ""), expected, f"HTTP {http.group(1) if http else '?'}; {actual}",
                     f"{ms.group(1) if ms else '?'} ms", verdict])
    d.table(["File", "What it tests", "Expected (pandas)", "Imported / response", "Time", "Result"], rows,
            [3.2, 3.6, 3.4, 4, 1.2, 1.1])
    d.p(f"Summary line of the fresh run: {next((ln for ln in ev['uploads']['output'] if 'failure' in ln), 'missing')}")
    d.h2("Bugs found by these files and fixed (commit 6a7982e)")
    d.table(["Input", "Before", "After"], [
        ["Empty file", "IndexError in read_table -> HTTP 500", "HTTP 422 'the file is empty'"],
        ["Missing amount column", "HTTP 200, 0 rows imported, no reason", "HTTP 422 naming the missing column and the columns seen"],
        ["Header-only file", "'could not find a date column. Columns seen: []' (misleading)", "HTTP 422 'no data rows found below the header row'"],
        ["Binary garbage", "'could not find a date column. Columns seen: []'", "HTTP 422 'no recognisable table found ...'"],
        ["Error display in UI", "3.5 s toast only", "Also stays in the result panel (commit eb85038, screenshot in section 8)"],
    ], [3.4, 6.3, 6.3])
    d.h2("Import speed (60,000-row statement)")
    big = out.get("10_large_4_9mb.csv", "")
    msb = re.search(r"(\d+) ms", big)
    d.table(["Measurement", "Time", "Source"], [
        ["Before memoizing keyword categorisation", "32,073 ms", "docs/overnight_log.md section 4 (2026-10-14)"],
        ["After (commit 6a7982e)", "14,559 ms", "docs/overnight_log.md section 4 (2026-10-14)"],
        ["Fresh run for this pack", f"{int(msb.group(1)):,} ms" if msb else "missing", "scripts/check_fake_uploads.py, today"],
    ], [6, 3, 7])

    # 7 -------------------------------------------------------------------------------------------------
    d.h1("7. Chat over uploaded statements")
    uc = ev["upload_chat"]
    if isinstance(uc, dict):
        d.p(f"MISSING: {uc}")
    else:
        ok = sum(1 for r in uc if r["ok"])
        d.p(f"scripts/check_upload_chat.py (result file benchmarks/results/upload_chat_check.json): after uploading a fake "
            f"statement, the copilot (Gemma 4 12B, local) was asked for May 2026 total income and total expenses in three "
            f"languages. The expected values were computed by the deterministic get_financial_summary tool on the same "
            f"database. Result: {ok} of {len(uc)} answers quoted both numbers, with no fallback.")
        d.table(["File", "Language", "Expected income / expenses", "Both found", "Fallback", "Time", "Reply (start)"],
                [[r["file"], r["lang"], f"{r['want']['income']:,.0f} / {r['want']['expense']:,.0f}",
                  "yes" if all(r["hit"].values()) else "no", "yes" if r["fallback"] else "no", f"{r['secs']} s",
                  r["reply"][:90]] for r in uc], [3.2, 1.5, 2.8, 1.2, 1.2, 1, 5.1])

    # 8 -------------------------------------------------------------------------------------------------
    d.br()
    d.h1("8. UI evidence")
    d.p("Screenshots taken with the built-in browser of the local demo (fake persona 'Nusrat Trims & Accessories', "
        "local-only mode, Gemma 4 12B on llama.cpp).")
    caps = [("01_dashboard.jpg", "Dashboard: KPIs, 90-day forecast with 80% band, prioritised alerts."),
            ("02a_chat_streaming.jpg", "Streamed answer, mid-generation: text is arriving; the model/latency chips are not shown yet."),
            ("02b_chat_streaming_later.jpg", "Same answer about a second later: more text has streamed in."),
            ("03_chat_unverified_number.jpg", "A finished answer with the 'Could not verify these numbers' warning for a figure "
                                             "the model summed itself (204100). Also visible: raw '**' Markdown markers."),
            ("04_fallback_badge.jpg", "Fallback made visible: the vLLM profile (no server) was chosen; the reply came from the "
                                      "local Gemma profile, with a warning naming the failed model and the reason, and red chips."),
            ("05_upload_error.jpg", "Upload of a file without an amount column: the 422 message stays visible in the panel.")]
    for f, c in caps:
        p = shots / f
        if p.exists():
            d.img(p, c)
        else:
            d.p(f"SKIPPED: screenshot {f} not available.")

    # 9 -------------------------------------------------------------------------------------------------
    d.br()
    d.h1("9. Bugs found and fixed")
    d.table(["Bug", "How it was found", "Fix", "Commit"], [
        ["Every local request silently fell back to the rules engine (HTTP 500)", "Speed harness: Qwen3.5 template "
         "rejected a second system message", "Fold the tool prompt into one leading system message; regression test", "f31a00d"],
        ["Fallbacks were invisible (only a tooltip)", "Live chat showed 'rules-offline' after the local model failed",
         "API fields fallback/requested_profile/fallback_reason, red UI banner, error log, audit entry", "f31a00d"],
        ["A failed local model could fall back to a cloud model", "Review of the fallback chain", "Local primary keeps only "
         "local profiles in its chain", "f31a00d"],
        ["Context too small (4096) and 60 s timeout with retries", "Live chat: HTTP 400 'exceeds context size', task cancelled at 60 s",
         "-c 16384, per-profile timeout 120 s, no retries for local", "f31a00d"],
        ["Benchmark financing metric required '(scheme-type)' verbatim", "Correct answers scored as misses", "Match on the "
         "product name without the qualifier", "f31a00d"],
        ["Tool results abridged to 'key figures only' (financing lost recommendations)", "Measuring tool output size",
         "Recursive abridging of low-value fields before capping lists", "c2f8d81"],
        ["Empty upload -> HTTP 500; missing amount column imported 0 rows silently", "Fake statement files", "Clear 422 messages", "6a7982e"],
        ["60k-row import took 32 s", "Fake statement files + cProfile", "Memoize categorisation (14.6 s)", "6a7982e"],
        ["Code-switched Bangla detected as English", "Stress-set validation in code", "Word-level Bangla rule", "519d453"],
        ["Upload error visible for only 3.5 s", "Browser check", "Error stays in the result panel", "eb85038"],
        ["Bangla loan question answered from general knowledge", "Golden-set per-scenario review", "Prompt rule: call the "
         "tool for money questions", "02410ba"],
        ["Bangla-script customer name -> 'no open invoice'", "Stress set", "Unmatched names return the real (neutralised) "
         "names for a retry", "9a31a7b"],
        ["Model asked permission instead of creating the transfer request", "Stress set", "Prompt: call the transfer tool "
         "directly (it only creates a request)", "9a31a7b"],
        ["Every Bangla 'send money' request blocked as prompt injection", "Stress set, then scanner check in code",
         "Bangla rule limited to sweeping transfers; Banglish rule added", "2e9c1d0"],
        ["Launcher wait loop failed without a console", "Running the .bat non-interactively", "ping instead of timeout", "0cc7bf3"],
    ], [5, 4.2, 5, 1.8])

    # 10 ------------------------------------------------------------------------------------------------
    d.h1("10. Known limitations and risks")
    fin_h = pct(final["hallucination_rate"]) if final else "n/a"
    st_h = pct(stress["hallucination_rate"]) if stress else "n/a"
    gem_cold = speed(ev, "gemma4-12b-faon-q8-mtp")
    d.bullets([
        f"Unverified numbers: {fin_h} of golden-set answers and {st_h} of stress-set answers contain a number that is in no "
        "tool result. Many are correct derived figures (percentages, sums such as 2,04,100), but they were not computed "
        "by code; the UI marks them 'Could not verify these numbers' (screenshot 03).",
        f"First request after the model loads: cold TTFT {gem_cold['ttft_cold_ms'] / 1000:.2f} s with the full prompt "
        "(speed harness); later requests reuse the cached prefix "
        f"({gem_cold['ttft_cached_ms'] / 1000:.2f} s)." if gem_cold else "Cold first request: measurement missing.",
        "Long tool outputs still cost time: the 'needs attention' digest answer took 23.5 s in the UI (screenshot 03).",
        "PDF and image statements are not supported (CSV/TSV/TXT/XLSX only); a PDF upload is rejected with HTTP 415.",
        "No fine-tuning: LoRA on a 12-14B model needs more than 16 GB VRAM in bf16, and 4-bit QLoRA (bitsandbytes) has no "
        "ROCm build for Windows. Accuracy gains came from prompts, smaller tool results, caching and decoding settings.",
        f"Gemma's tool selection is not perfect: {pct(final['tool_call_success']) if final else 'n/a'} tool-call success "
        f"on the golden set and {pct(stress['tool_call_success']) if stress else 'n/a'} on the stress set; "
        "some misses are judgement cases (e.g. EMI calculator instead of a what-if) and the metric counts only the first "
        "call, so a correct retry still counts as a miss.",
        "The 27B baseline was more accurate on its 16 measured scenarios (100% tool and numeric) than Gemma on the same "
        "scenarios; the trade was made for speed and VRAM.",
        "Prompt-injection scanner gap: the Banglish override phrase 'instruction ignore koro' (Bangla word order) is not "
        "matched by the override rule; the transfer rule and the permission layer still prevented any money movement.",
        "Banglish replies and English Markdown: the UI shows raw '**' markers instead of bold text (screenshot 03).",
        "The Data page shows the literal text 'null' under its heading (screenshot 05).",
        "Cloud default (Claude) was not benchmarked: no API key on the build machine.",
        "Model servers do not survive the shell that started them in every setup; one stopped during this work and had to be "
        "restarted (the launcher starts it in its own window, which is the supported way).",
        "Results come from one PC and one llama.cpp build (10930); other GPUs or drivers will differ.",
    ])

    # 11 ------------------------------------------------------------------------------------------------
    d.br()
    d.h1("11. Reproduction guide")
    d.code("# 1. Clone and install (Python 3.11+; Windows paths shown)\n"
           "git clone https://github.com/SazidFaruk-web/sme-finance-copilot.git\n"
           "cd sme-finance-copilot\ngit checkout model-tuning\n"
           "python -m venv .venv\n.venv\\Scripts\\pip install -r requirements-dev.txt\n\n"
           "# 2. Local model (llama.cpp Vulkan build + GGUF files in D:\\llama-vulkan\\models)\n"
           "#    gemma-4-12b-it-Q4_K_M.gguf          https://huggingface.co/unsloth/gemma-4-12b-it-GGUF\n"
           "#    mtp-gemma-4-12B-it-Q8_0.gguf        https://huggingface.co/ggml-org/gemma-4-12B-it-GGUF\n"
           "#    Qwen3-14B-Q4_K_M.gguf (optional)    https://huggingface.co/Qwen/Qwen3-14B-GGUF\n"
           "scripts\\start_local_llm.bat            (or: scripts\\start_local_llm.bat qwen14b)\n\n"
           "# 3. App (demo data); pick 'Local Gemma 4 12B' in the Model menu, or set LLM_PROFILE=local-llamacpp\n"
           ".venv\\Scripts\\python -m sme_copilot.cli demo        # http://127.0.0.1:8000\n\n"
           "# 4. Tests\n.venv\\Scripts\\python -m pytest -p no:cacheprovider -o addopts=\"\" -q\n\n"
           "# 5. Benchmarks (needs the model files; starts its own llama-server on port 8085)\n"
           ".venv\\Scripts\\python scripts\\eval_local_model.py --model D:/llama-vulkan/models/gemma-4-12b-it-Q4_K_M.gguf ^\n"
           "   --label my-golden --tools native -- -ngl 99 -c 16384 -fa on -ctk q8_0 -ctv q8_0 --reasoning off -cram 2048 ^\n"
           "   --spec-type draft-mtp -md D:/llama-vulkan/models/mtp-gemma-4-12B-it-Q8_0.gguf -ngld 99\n"
           "#    stress set: add --scenario-file sme_copilot/benchmarks/stress.yaml --summary-file stress_summary.jsonl\n"
           ".venv\\Scripts\\python scripts\\bench_local_llm.py --model <gguf> --label <name> --tools native -- <flags>\n"
           ".venv\\Scripts\\python scripts\\summarize_local_models.py\n\n"
           "# 6. Uploads and evidence\n.venv\\Scripts\\python scripts\\make_fake_statements.py\n"
           ".venv\\Scripts\\python scripts\\check_fake_uploads.py\n"
           ".venv\\Scripts\\python scripts\\check_upload_chat.py --base-url http://127.0.0.1:8080/v1 --tools native\n"
           ".venv\\Scripts\\python scripts\\collect_evidence.py EVID --junit EVID\\junit.xml --pytest-output EVID\\pytest_output.txt\n"
           "<venv with reportlab, uharfbuzz, python-docx>\\python scripts\\build_evidence_pack.py EVID <output folder>")

    # 12 ------------------------------------------------------------------------------------------------
    d.br()
    d.h1("12. Appendix")
    d.h2("A. Summary from docs/overnight_log.md")
    d.code(re.sub(r"\*\*", "", ev["overnight_summary"]).strip())
    d.h2("B. Branch commits (main..model-tuning)")
    d.table(["Commit", "Subject"], [c.split("|", 1) for c in ev["commits"]], [2, 14])
    d.h2("C. File index")
    d.table(["What", "Where in the repo"], [
        ["All model runs (readable)", "benchmarks/results/local_models.md"],
        ["Golden runs, one line each", "benchmarks/results/golden_summary.jsonl"],
        ["Per-scenario golden results", "benchmarks/results/golden/<label>/results.json, results.csv, summary.md"],
        ["Stress runs", "benchmarks/results/stress_summary.jsonl, golden/final-gemma-stress-v2/"],
        ["Targeted re-checks (transfers, safety)", "benchmarks/results/checks.jsonl, golden/check-*/"],
        ["Speed harness runs", "benchmarks/results/local_llm_runs.jsonl"],
        ["Early Qwen runs (before static prompt)", "benchmarks/results/golden_9b_*/, golden_14b_emulated/"],
        ["Chat over uploads", "benchmarks/results/upload_chat_check.json"],
        ["Step-by-step log and decisions", "docs/overnight_log.md"],
        ["Assumptions (models, hardware)", "ASSUMPTIONS.md (items 36-40)"],
        ["Golden / stress scenario sets", "sme_copilot/benchmarks/golden.yaml, stress.yaml"],
        ["Fake statements + expected totals", "data/fake_statements/ (git-ignored, regenerate with make_fake_statements.py)"],
        ["Raw llama-server logs", "benchmarks/results/golden/*/server.log, server_*.log (git-ignored, local only)"],
        ["Evidence generators", "scripts/collect_evidence.py, scripts/build_evidence_pack.py"],
    ], [6, 10])
    return d


# ----------------------------------------------------------------------------- PDF
def render_pdf(d: Doc, path: Path, title: str) -> int:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, PageBreak, PageTemplate, Paragraph,
                                    Preformatted, Spacer, Table, TableStyle)
    from reportlab.platypus.tableofcontents import TableOfContents
    from xml.sax.saxutils import escape

    fonts = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("Body", str(fonts / "Nirmala.ttf")))
    pdfmetrics.registerFont(TTFont("BodyB", str(fonts / "NirmalaB.ttf")))
    pdfmetrics.registerFont(TTFont("Mono", str(fonts / "consola.ttf")))
    from reportlab.lib.fonts import addMapping
    addMapping("Body", 0, 0, "Body")
    addMapping("Body", 1, 0, "BodyB")
    INK, MUTED, RULE, BAND = colors.HexColor("#1b2430"), colors.HexColor("#5b6675"), colors.HexColor("#c9d1db"), colors.HexColor("#eef2f6")
    ACCENT = colors.HexColor("#1f5f8b")
    S = {
        "title": ParagraphStyle("t", fontName="BodyB", fontSize=26, leading=32, textColor=INK, alignment=TA_CENTER),
        "sub": ParagraphStyle("s", fontName="Body", fontSize=12, leading=17, textColor=MUTED, alignment=TA_CENTER),
        "h1": ParagraphStyle("h1", fontName="BodyB", fontSize=16, leading=21, textColor=ACCENT, spaceBefore=6, spaceAfter=8),
        "h2": ParagraphStyle("h2", fontName="BodyB", fontSize=11.5, leading=15, textColor=INK, spaceBefore=8, spaceAfter=4),
        "p": ParagraphStyle("p", fontName="Body", fontSize=9.2, leading=13, textColor=INK, spaceAfter=5),
        "li": ParagraphStyle("li", fontName="Body", fontSize=9.2, leading=13, textColor=INK, leftIndent=12, bulletIndent=2, spaceAfter=3),
        "cell": ParagraphStyle("c", fontName="Body", fontSize=7.6, leading=9.6, textColor=INK),
        "cellh": ParagraphStyle("ch", fontName="BodyB", fontSize=7.6, leading=9.6, textColor=colors.white),
        "cap": ParagraphStyle("cap", fontName="Body", fontSize=8.2, leading=11, textColor=MUTED, spaceAfter=10),
        "mono": ParagraphStyle("m", fontName="Mono", fontSize=6.9, leading=8.6, textColor=INK),
        "monobn": ParagraphStyle("mb", fontName="Body", fontSize=6.9, leading=9.4, textColor=INK),
        "toc1": ParagraphStyle("toc1", fontName="Body", fontSize=10, leading=15, leftIndent=0),
        "toc2": ParagraphStyle("toc2", fontName="Body", fontSize=8.6, leading=12, leftIndent=14, textColor=MUTED),
    }
    shaped: dict[str, ParagraphStyle] = {}

    def bn_style(st):
        # HarfBuzz shaping only where Bengali appears: vowel signs and conjuncts need it, and ReportLab's
        # shaped line-breaking can fail on some plain-Latin paragraphs.
        if st.name not in shaped:
            shaped[st.name] = st.clone(st.name + "_bn", shaping=1)
        return shaped[st.name]

    class Tpl(BaseDocTemplate):
        def afterFlowable(self, f):
            if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
                lvl = 0 if f.style.name == "h1" else 1
                key = f"h{id(f)}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(f.getPlainText(), key, level=lvl, closed=lvl > 0)
                self.notify("TOCEntry", (lvl, f.getPlainText(), self.page, key))

    W, H = A4
    margin = 1.7 * cm

    def deco(canv, doc):
        canv.saveState()
        canv.setFont("Body", 7.5)
        canv.setFillColor(MUTED)
        canv.drawString(margin, 1.0 * cm, title)
        canv.drawRightString(W - margin, 1.0 * cm, f"Page {doc.page}")
        canv.setStrokeColor(RULE)
        canv.line(margin, 1.35 * cm, W - margin, 1.35 * cm)
        canv.restoreState()

    doc = Tpl(str(path), pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=1.6 * cm, bottomMargin=1.8 * cm,
              title=title, author="SME Finance Copilot team", subject="FinTechathon 2026 Topic E evidence pack")
    frame = Frame(margin, 1.8 * cm, W - 2 * margin, H - 3.4 * cm, id="f")
    doc.addPageTemplates([PageTemplate(id="cover", frames=[frame]), PageTemplate(id="body", frames=[frame], onPage=deco)])
    usable = W - 2 * margin

    def para(t, st):
        return Paragraph(escape(t).replace("\n", "<br/>"), bn_style(st) if BN.search(t) else st)

    def code_block(t):
        lines = t.splitlines() or [""]
        st = S["monobn"] if BN.search(t) else S["mono"]
        wrapped = []
        width = 118 if st is S["mono"] else 130
        for ln in lines:
            while len(ln) > width:
                wrapped.append(ln[:width])
                ln = "    " + ln[width:]
            wrapped.append(ln)
        out = []
        step = 55  # lines per shaded box, so a block never exceeds one page
        for i in range(0, len(wrapped), step):
            chunk = "\n".join(wrapped[i:i + step])
            pre = Preformatted(chunk, st) if st is S["mono"] else para(chunk, st)
            tbl = Table([[pre]], colWidths=[usable])
            tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BAND), ("BOX", (0, 0), (-1, -1), 0.4, RULE),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                     ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            out.append(tbl)
        return out + [Spacer(1, 6)]

    story = [Spacer(1, 5 * cm), Paragraph("SME Finance Copilot", S["title"]), Spacer(1, 6),
             Paragraph("Evidence Pack", S["title"]), Spacer(1, 18),
             Paragraph("FinTechathon 2026 · International Track · Topic E: SME Finance Copilot", S["sub"]),
             Spacer(1, 30)]
    meta = next(b for b in d.blocks if b[0] == "table")
    for k, v in meta[2]:
        if k in ("Evidence generated", "Git branch", "Git commit"):
            story.append(Paragraph(f"{escape(k)}: {escape(v)}", S["sub"]))
    story += [Spacer(1, 40), Paragraph("All data in this document is fictional demo data or FAKE generated statements.", S["sub"]),
              PageBreak()]
    from reportlab.platypus.doctemplate import NextPageTemplate
    story.insert(0, NextPageTemplate("body"))
    toc = TableOfContents()
    toc.levelStyles = [S["toc1"], S["toc2"]]
    toc.dotsMinLevel = 0
    story += [Paragraph("Contents", S["h1"].clone("toch", spaceAfter=10)), toc, PageBreak()]

    for b in d.blocks:
        kind = b[0]
        if kind == "h1":
            story.append(Paragraph(escape(b[1]), S["h1"]))
        elif kind == "h2":
            story.append(Paragraph(escape(b[1]), S["h2"]))
        elif kind == "p":
            story.append(para(b[1], S["p"]))
        elif kind == "ul":
            story += [Paragraph(escape(i), S["li"], bulletText="•") for i in b[1]]
            story.append(Spacer(1, 4))
        elif kind == "code":
            story += code_block(b[1])
        elif kind == "pagebreak":
            story.append(PageBreak())
        elif kind == "img":
            img = Image(str(b[1]))
            r = usable / img.imageWidth
            img.drawWidth, img.drawHeight = usable, img.imageHeight * r
            story.append(KeepTogether([img, Spacer(1, 3), para(b[2], S["cap"])]))
        elif kind == "table":
            header, rows, widths = b[1], b[2], b[3]
            data = ([[para(str(h), S["cellh"]) for h in header]] if any(header) else []) + \
                   [[para(str(c), S["cell"]) for c in r] for r in rows]
            ws = [usable * w / sum(widths) for w in widths] if widths else None
            t = Table(data, colWidths=ws, repeatRows=1 if any(header) else 0)
            ts = [("GRID", (0, 0), (-1, -1), 0.3, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                  ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
            if any(header):
                ts += [("BACKGROUND", (0, 0), (-1, 0), ACCENT)]
                ts += [("BACKGROUND", (0, i), (-1, i), BAND) for i in range(2, len(data), 2)]
            else:
                ts += [("BACKGROUND", (0, 0), (0, -1), BAND)]
            t.setStyle(TableStyle(ts))
            story += [t, Spacer(1, 8)]
    doc.multiBuild(story)
    from pypdf import PdfReader
    return len(PdfReader(str(path)).pages)


# ----------------------------------------------------------------------------- DOCX
def render_docx(d: Doc, path: Path, title: str) -> None:
    from docx import Document
    from docx.enum.section import WD_ORIENT  # noqa: F401
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(1.7)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Nirmala UI", Pt(9.5)
    st.element.rPr.rFonts.set(qn("w:cs"), "Nirmala UI")

    def field(par, instr):
        r = par.add_run()
        for tag, attr in (("w:fldChar", {"w:fldCharType": "begin"}), ("w:instrText", None), ("w:fldChar", {"w:fldCharType": "end"})):
            el = OxmlElement(tag)
            if attr:
                for k, v in attr.items():
                    el.set(qn(k), v)
            else:
                el.set(qn("xml:space"), "preserve")
                el.text = instr
            r._r.append(el)

    fp = sec.footer.paragraphs[0]
    fp.text = f"{title}    Page "
    field(fp, "PAGE")
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.paragraph_format.space_before = Pt(160)
    r = t.add_run("SME Finance Copilot\nEvidence Pack")
    r.bold, r.font.size = True, Pt(28)
    s = doc.add_paragraph("FinTechathon 2026 · International Track · Topic E: SME Finance Copilot")
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta = next(b for b in d.blocks if b[0] == "table")
    for k, v in meta[2]:
        if k in ("Evidence generated", "Git branch", "Git commit"):
            doc.add_paragraph(f"{k}: {v}").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("All data in this document is fictional demo data or FAKE generated statements.").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()
    doc.add_heading("Contents", level=1)
    p = doc.add_paragraph()
    field(p, 'TOC \\o "1-2" \\h \\z \\u')
    doc.add_paragraph("(Right-click and choose Update Field if the contents list is empty.)").runs[0].italic = True
    doc.add_page_break()

    for b in d.blocks:
        kind = b[0]
        if kind == "h1":
            doc.add_heading(b[1], level=1)
        elif kind == "h2":
            doc.add_heading(b[1], level=2)
        elif kind == "p":
            doc.add_paragraph(b[1])
        elif kind == "ul":
            for i in b[1]:
                doc.add_paragraph(i, style="List Bullet")
        elif kind == "pagebreak":
            doc.add_page_break()
        elif kind == "code":
            par = doc.add_paragraph()
            run = par.add_run(b[1])
            run.font.name, run.font.size = ("Nirmala UI" if BN.search(b[1]) else "Consolas"), Pt(7)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), "EEF2F6")
            par._p.get_or_add_pPr().append(shd)
        elif kind == "img":
            doc.add_picture(str(b[1]), width=Cm(17.5))
            cap = doc.add_paragraph(b[2])
            cap.runs[0].font.size, cap.runs[0].font.color.rgb = Pt(8.5), RGBColor(0x5B, 0x66, 0x75)
        elif kind == "table":
            header, rows = b[1], b[2]
            ncol = len(rows[0]) if rows else len(header)
            tbl = doc.add_table(rows=0, cols=ncol)
            tbl.style = "Table Grid"
            if any(header):
                cells = tbl.add_row().cells
                for c, h in zip(cells, header):
                    c.text = str(h)
                    c.paragraphs[0].runs[0].bold = True
            for r in rows:
                cells = tbl.add_row().cells
                for c, v in zip(cells, r):
                    c.text = str(v)
            for row in tbl.rows:
                for c in row.cells:
                    for par in c.paragraphs:
                        for run in par.runs:
                            run.font.size = Pt(7.5)
            doc.add_paragraph()
    doc.core_properties.title = title
    doc.save(str(path))


def main() -> None:
    evid, out = Path(sys.argv[1]), Path(sys.argv[2])
    ev = json.loads((evid / "evidence.json").read_text(encoding="utf-8"))
    d = build_content(ev, evid / "junit.xml", evid / "shots")
    title = "SME Finance Copilot - Evidence Pack"
    pdf = out / "SME_Finance_Copilot_Evidence_Pack.pdf"
    pages = render_pdf(d, pdf, title)
    print(f"PDF: {pdf} ({pages} pages)")
    try:
        docx = out / "SME_Finance_Copilot_Evidence_Pack.docx"
        render_docx(d, docx, title)
        print(f"DOCX: {docx}")
    except Exception as e:  # noqa: BLE001 - the PDF is the deliverable; report and continue
        print(f"DOCX skipped: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
