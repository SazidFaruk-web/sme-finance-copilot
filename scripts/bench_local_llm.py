"""Benchmark a GGUF model under llama-server with the app's real prompt.

Starts llama-server with the given flags, sends the copilot's actual system prompt + tool definitions,
and records load time, time to first token, prompt-processing and generation speed, prompt-cache reuse
and peak GPU memory (dedicated vs shared, from Windows GPU counters, so VRAM spill is visible).

    python scripts/bench_local_llm.py --model D:/models/x.gguf --label x-q5 -- -c 16384 -fa on -ctk q8_0 -ctv q8_0

Appends one JSON line per run to benchmarks/results/local_llm_runs.jsonl.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sme_copilot.agent.prompts import build_system_prompt, build_user_turn  # noqa: E402
from sme_copilot.agent.toolkit import specs_for  # noqa: E402
from sme_copilot.llm_providers.base import Message  # noqa: E402
from sme_copilot.llm_providers.openai_provider import to_openai_messages, to_openai_tools  # noqa: E402
from sme_copilot.llm_providers.structured import tool_prompt  # noqa: E402

QUESTIONS = ["What needs my attention this week?", "How much do customers owe me and how much of it is overdue?"]


def gpu_mem_mb(pid: int) -> tuple[float, float]:
    """(dedicated, shared) GPU memory used by one process, MB. Windows only."""
    ps = (f"(Get-Counter '\\GPU Process Memory(pid_{pid}_*)\\Dedicated Usage',"
          f"'\\GPU Process Memory(pid_{pid}_*)\\Shared Usage' -ErrorAction SilentlyContinue)"
          ".CounterSamples | ForEach-Object { $_.Path + '|' + $_.CookedValue }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0.0, 0.0
    ded = sha = 0.0
    for line in out.splitlines():
        path, _, val = line.rpartition("|")
        try:
            v = float(val) / 2**20
        except ValueError:
            continue
        if path.endswith("dedicated usage"):
            ded += v
        elif path.endswith("shared usage"):
            sha += v
    return ded, sha


class GpuSampler(threading.Thread):
    def __init__(self, pid: int) -> None:
        super().__init__(daemon=True)
        self.pid = pid
        self.peak_ded = self.peak_shared = 0.0
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            d, s = gpu_mem_mb(self.pid)
            self.peak_ded, self.peak_shared = max(self.peak_ded, d), max(self.peak_shared, s)
            self._stop.wait(1.0)

    def stop(self) -> None:
        self._stop.set()


def app_messages(question: str, tools_mode: str) -> tuple[list[dict], list[dict] | None]:
    system = build_system_prompt()
    turn = build_user_turn(question, language="en", business_name="Nusrat Fashion Accessories", sector="garments",
                           today=date(2026, 10, 14), style="lakh", user_role="owner")
    specs = specs_for(None)
    msgs = [Message("system", system), Message("user", turn)]
    if tools_mode == "emulated":
        return to_openai_messages([Message("system", f"{system}\n\n{tool_prompt(specs)}"), msgs[1]]), None
    return to_openai_messages(msgs), to_openai_tools(specs)


def stream_request(base: str, question: str, tools_mode: str, max_tokens: int) -> dict:
    messages, tools = app_messages(question, tools_mode)
    payload = {"messages": messages, "temperature": 0.0, "max_tokens": max_tokens, "stream": True,
               "cache_prompt": True}
    if tools:
        payload["tools"] = tools
    t0 = time.perf_counter()
    first_any = first_content = None
    timings: dict = {}
    content, reasoning, tool_args = [], [], []
    with httpx.Client(timeout=600) as c, c.stream("POST", f"{base}/v1/chat/completions", json=payload) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            evt = json.loads(body)
            timings = evt.get("timings") or timings
            for ch in evt.get("choices") or []:
                d = ch.get("delta") or {}
                now = time.perf_counter()
                piece = d.get("content") or ""
                rpiece = d.get("reasoning_content") or ""
                tpiece = "".join((tc.get("function") or {}).get("arguments") or "" for tc in d.get("tool_calls") or [])
                tname = "".join((tc.get("function") or {}).get("name") or "" for tc in d.get("tool_calls") or [])
                if (piece or rpiece or tpiece or tname) and first_any is None:
                    first_any = now
                if (piece or tpiece or tname) and first_content is None:
                    first_content = now
                content.append(piece)
                reasoning.append(rpiece)
                tool_args.append(tname + tpiece)
    total = time.perf_counter() - t0
    return {
        "question": question,
        "ttft_ms": round(((first_any or t0) - t0) * 1000),
        "ttft_answer_ms": round(((first_content or t0) - t0) * 1000),
        "total_ms": round(total * 1000),
        "prompt_tokens": timings.get("prompt_n"),
        "cached_tokens": timings.get("cache_n"),
        "pp_tok_s": round(timings.get("prompt_per_second") or 0, 1),
        "gen_tokens": timings.get("predicted_n"),
        "tg_tok_s": round(timings.get("predicted_per_second") or 0, 2),
        "reasoning_chars": len("".join(reasoning)),
        "output": ("".join(tool_args) or "".join(content))[:300],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="D:/llama-vulkan/llama-server.exe")
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--tools", choices=["native", "emulated"], default="native")
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "local_llm_runs.jsonl"))
    ap.add_argument("server_args", nargs=argparse.REMAINDER, help="extra llama-server flags after --")
    a = ap.parse_args()
    extra = [x for x in a.server_args if x != "--"]

    base = f"http://127.0.0.1:{a.port}"
    cmd = [a.server, "-m", a.model, "--host", "127.0.0.1", "--port", str(a.port), *extra]
    t0 = time.perf_counter()
    log_path = Path(a.out).with_name(f"server_{a.label}.log")
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        sampler = GpuSampler(proc.pid)
        sampler.start()
        try:
            while True:
                if proc.poll() is not None:
                    raise SystemExit(f"llama-server exited early (code {proc.returncode}); see {log_path}")
                try:
                    if httpx.get(f"{base}/health", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.perf_counter() - t0 > 600:
                    raise SystemExit("llama-server did not become healthy in 600s")
                time.sleep(0.5)
            load_s = time.perf_counter() - t0
            runs = []
            for q in QUESTIONS:
                runs.append(stream_request(base, q, a.tools, a.max_tokens))
            runs.append({**stream_request(base, QUESTIONS[0], a.tools, a.max_tokens), "repeat": True})
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
            sampler.stop()

    cold = runs[0]
    rec = {
        "date": date.today().isoformat(), "label": a.label, "model": Path(a.model).name, "tools": a.tools,
        "flags": " ".join(extra), "load_s": round(load_s, 1),
        "vram_dedicated_mb": round(sampler.peak_ded), "shared_mem_mb": round(sampler.peak_shared),
        "prompt_tokens": cold["prompt_tokens"], "pp_tok_s": cold["pp_tok_s"],
        "tg_tok_s": round(sum(r["tg_tok_s"] for r in runs) / len(runs), 2),
        "ttft_cold_ms": cold["ttft_answer_ms"], "ttft_cached_ms": runs[-1]["ttft_answer_ms"],
        "cached_tokens_repeat": runs[-1]["cached_tokens"],
        "total_ms_cold": cold["total_ms"], "reasoning_chars": cold["reasoning_chars"], "runs": runs,
    }
    with open(a.out, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k != "runs"}, indent=1))
    for r in runs:
        print("  ->", r["question"][:40], "|", r["output"][:160].replace("\n", " "))


if __name__ == "__main__":
    main()
