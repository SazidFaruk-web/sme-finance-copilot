"""Run the golden benchmark against one local GGUF model under llama-server.

Starts llama-server with the given flags on a private port, points a temporary copy of the
`local-llamacpp` profile at it (tool mode and request extras overridable), runs the 48-scenario golden
set through the real agent loop, samples the server's peak GPU memory, and writes:

    benchmarks/results/golden/<label>/{results.csv,results.json,summary.md,...}
    benchmarks/results/golden_summary.jsonl   (one line per run)

    python scripts/eval_local_model.py --model D:/m/x.gguf --label x-emulated --tools emulated -- -ngl 99 -c 16384
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_local_llm import GpuSampler  # noqa: E402

PROFILE = "local-llamacpp"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="D:/llama-vulkan/llama-server.exe")
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--tools", choices=["native", "emulated"], default="emulated")
    ap.add_argument("--port", type=int, default=8085)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="", help="comma-separated scenario ids to run (default: all)")
    ap.add_argument("--profile-extra", default="{}", help="JSON merged into the profile (e.g. request extras)")
    ap.add_argument("server_args", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    extra_args = [x for x in a.server_args if x != "--"]

    cfg = yaml.safe_load((ROOT / "config" / "providers.yaml").read_text(encoding="utf-8"))
    prof = cfg["profiles"][PROFILE]
    prof.update({"base_url": f"http://127.0.0.1:{a.port}/v1", "tools": a.tools, "timeout": 180, "max_retries": 0,
                 "label": a.label})
    prof.update(json.loads(a.profile_extra))
    tmp_cfg = Path(tempfile.mkdtemp(prefix="evalcfg-")) / "providers.yaml"
    tmp_cfg.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    os.environ.update({"PROVIDERS_FILE": str(tmp_cfg), "LLM_PROFILE": PROFILE, "LOCAL_ONLY_MODE": "true"})

    out_dir = ROOT / "benchmarks" / "results" / "golden" / a.label
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [a.server, "-m", a.model, "--host", "127.0.0.1", "--port", str(a.port), *extra_args]
    t0 = time.perf_counter()
    with open(out_dir / "server.log", "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        sampler = GpuSampler(proc.pid)
        sampler.start()
        try:
            while True:
                if proc.poll() is not None:
                    raise SystemExit(f"llama-server exited early (code {proc.returncode}); see {out_dir / 'server.log'}")
                try:
                    if httpx.get(f"http://127.0.0.1:{a.port}/health", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.perf_counter() - t0 > 900:
                    raise SystemExit("llama-server not healthy after 900 s")
                time.sleep(0.5)
            load_s = time.perf_counter() - t0

            from sme_copilot.config import reset_settings_cache
            reset_settings_cache()
            from sme_copilot.benchmarks.runner import load_golden, run_benchmark, write_outputs
            scen = load_golden()
            if a.ids:
                wanted = set(a.ids.split(","))
                scen = [s for s in scen if s["id"] in wanted]
            t1 = time.perf_counter()
            rows, summary = run_benchmark([PROFILE], limit=a.limit, scenarios=scen)
            wall = time.perf_counter() - t1
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
            sampler.stop()

    if not rows:
        raise SystemExit("no rows: profile unavailable?")
    write_outputs(rows, summary, out_dir)
    s = summary[0]
    lat = [r["latency_ms"] for r in rows if r.get("latency_ms")]
    rec = {
        "time": datetime.now().isoformat(timespec="seconds"), "label": a.label, "model": Path(a.model).name,
        "tools": a.tools, "flags": " ".join(extra_args), "profile_extra": json.loads(a.profile_extra),
        "scenarios": len(rows), "errors": s["errors"], "load_s": round(load_s, 1), "wall_s": round(wall, 1),
        "vram_peak_mb": round(sampler.peak_ded), "ttft_ms": s["ttft_ms"], "tokens_per_sec": s["tokens_per_sec"],
        "latency_mean_s": round(statistics.mean(lat) / 1000, 2) if lat else None,
        "latency_p50_s": round(s["latency_p50_ms"] / 1000, 2) if s["latency_p50_ms"] else None,
        "latency_p95_s": round(s["latency_p95_ms"] / 1000, 2) if s["latency_p95_ms"] else None,
        **{k: s[k] for k in ("tool_call_success", "valid_tool_args", "numeric_accuracy", "financing_match",
                             "hallucination_rate", "refusal_correct", "safety_pass", "language_match_all",
                             "bangla_banglish_language_match", "fallback_used")},
    }
    with open(ROOT / "benchmarks" / "results" / "golden_summary.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
