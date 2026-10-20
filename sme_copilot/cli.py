"""Command-line entry point: ``python -m sme_copilot.cli <command>``.

  serve              run the web app
  models             list provider profiles and whether they are usable
  seed [--reset]     load the demo persona (Nusrat Trims & Accessories)
  demo               reset + seed + serve (one-command demo, works offline)
  digest             refresh alerts and print the digest for every business
  verify-audit       verify the audit hash chain
  bench              run the model benchmark (see sme_copilot/benchmarks)
  evidence           run the scripted end-to-end demo and export execution evidence
  export-finetune    export the interaction log as a fine-tuning dataset
  warmup             prime the local model with the agent prompt so the first chat answer is fast
  market [--setup]   show the Home price drawer data; --setup downloads the public prices and the
                     forecast model once (an explicit operator step, allowed even in LOCAL_ONLY_MODE)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date


def _as_of(arg: str | None) -> date:
    from sme_copilot.api.deps import as_of_today
    return date.fromisoformat(arg) if arg else as_of_today()


def cmd_seed(reset: bool, as_of: str | None, story: bool = False) -> dict:
    from sme_copilot.config import get_settings
    from sme_copilot.db import SessionLocal, init_db, reset_engine
    from sme_copilot.demo.personas import load_personas
    from sme_copilot.demo.seed import load

    s = get_settings()
    db_path = s.data_dir / "copilot.db"
    if reset and not s.database_url:
        reset_engine()
        for suffix in ("", "-wal", "-shm"):
            p = db_path.with_name(db_path.name + suffix)
            if p.exists():
                p.unlink()
        for f in (s.reports_dir.glob("*.pdf") if s.reports_dir.exists() else []):
            f.unlink()
    init_db()
    with SessionLocal() as db:
        from sme_copilot.models import Business
        if db.query(Business).count() and not reset:
            print("Database already has data; use --reset to recreate the demo.")
            return {}
        # Default: the four test owners shown on the login screen. --story: the scripted Nusrat business used by
        # the demo video, the evidence run and the benchmarks (its logins are not listed on the login screen).
        res = load(db, _as_of(as_of)) if story else load_personas(db, _as_of(as_of))
    print(json.dumps(res, indent=1, default=str))
    print("\nDemo logins: " + ("nusrat (owner), rafiq (accountant), mitu (viewer)" if story else "tanvir, shirin, rokeya, rafi")
          + ". Passwords: see .env.example (DEMO_*_PASSWORD).")
    return res


def cmd_market(setup: bool, district: str, business_type: str) -> int:
    from sme_copilot.market import forecast, prices, service
    if setup:
        try:
            print("prices:", "downloaded" if prices.refresh(force=True, explicit=True) else "unchanged")
        except Exception as e:
            print(f"prices: download failed ({e}); the bundled snapshot stays in use")
        name = forecast.download_model()
        print("forecast model:", name or "unavailable (install requirements-forecast.txt); statistical estimate in use")
    engine = forecast.forecaster(wait=True)
    r = service.overview(district, business_type, _as_of(None))
    print(f"{r['district']} / {r['business_type']}: engine {engine.name}, data to {r['latest_observation']} "
          f"({r['source']['origin']}), forecast for {r['target_month']}")
    for item in r["items"]:
        print("  " + service.summary_line(item))
    return 0


def cmd_warmup(profile: str | None) -> int:
    """Send the agent's real system prompt + tool list to a local model once. llama-server keeps that
    prefix in its prompt cache, so the user's first question only processes its own few tokens."""
    import time

    from sme_copilot.agent.prompts import build_system_prompt
    from sme_copilot.agent.toolkit import specs_for
    from sme_copilot.llm_providers import get_registry, get_router
    from sme_copilot.llm_providers.base import Message, ProviderError

    reg = get_registry()
    name = profile or reg.default_profile
    info = reg.info(name)
    if info.external:
        print(f"{name} is a cloud model; nothing to warm up.")
        return 0
    if not info.available:
        print(f"{name} is not available: {info.reason}")
        return 1
    messages = [Message("system", build_system_prompt()), Message("user", "hi")]
    start = time.perf_counter()
    try:
        get_router().chat(messages, override=name, tools=specs_for(), max_tokens=8, fallback=False)
    except ProviderError as e:
        print(f"warm-up failed: {e}")
        return 1
    print(f"{name} warmed up in {time.perf_counter() - start:.1f} s")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; we print ৳ and Bangla
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="sme_copilot", description="Ascent Copilot CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the web app")
    s.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    s.add_argument("--reload", action="store_true")
    sub.add_parser("models", help="list provider profiles and availability")
    sd = sub.add_parser("seed", help="load demo data")
    sd.add_argument("--reset", action="store_true", help="delete the local SQLite DB first")
    sd.add_argument("--as-of", default=None, help="pretend today is YYYY-MM-DD")
    sd.add_argument("--story", action="store_true", help="load the scripted Nusrat demo business instead of the four test owners")
    dm = sub.add_parser("demo", help="reset + seed + serve")
    dm.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    dm.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    sub.add_parser("digest", help="refresh alerts and print digests")
    sub.add_parser("verify-audit", help="verify the audit hash chain")
    b = sub.add_parser("bench", help="run the model benchmark")
    b.add_argument("--profiles", default="rules-offline", help="comma-separated provider profiles")
    b.add_argument("--limit", type=int, default=0, help="only the first N scenarios")
    b.add_argument("--out", default="benchmarks/results")
    b.add_argument("--judge", default=None, help="optional provider profile used as LLM judge for fluency")
    ev = sub.add_parser("evidence", help="scripted end-to-end demo + execution evidence export")
    ev.add_argument("--out", default="docs/evidence")
    ft = sub.add_parser("export-finetune", help="export interaction log to a fine-tuning dataset")
    ft.add_argument("--out", default="data/finetune")
    ft.add_argument("--include-unrated", action="store_true")
    wu = sub.add_parser("warmup", help="prime the local model so the first chat answer is fast")
    wu.add_argument("--profile", default=None, help="provider profile (default: LLM_PROFILE / default_profile)")
    mk = sub.add_parser("market", help="show market prices and forecasts for the Home price drawer")
    mk.add_argument("--setup", action="store_true", help="download the latest prices and the forecast model now")
    mk.add_argument("--district", default="Dhaka")
    mk.add_argument("--type", default="retail", help="business type, e.g. retail, restaurant_food")

    args = parser.parse_args(argv)
    if args.cmd == "market":
        return cmd_market(args.setup, args.district, args.type)
    if args.cmd == "serve":
        import uvicorn
        uvicorn.run("sme_copilot.api.main:app", host=args.host, port=args.port, reload=args.reload)
    elif args.cmd == "models":
        from sme_copilot.llm_providers import get_registry
        reg = get_registry()
        print(f"default: {reg.default_profile}  (routing {'on' if reg.routing.get('enabled') else 'off'})")
        for p in reg.list_profiles():
            flag = "OK " if p.available else "-- "
            print(f"  {flag}{p.name:22} {p.adapter:18} {p.model:32} {'external' if p.external else 'local'}  {p.reason}")
    elif args.cmd == "seed":
        cmd_seed(args.reset, args.as_of, args.story)
    elif args.cmd == "demo":
        cmd_seed(True, None)
        import uvicorn
        print(f"\nOpen http://{args.host}:{args.port}  (login: nusrat)")
        uvicorn.run("sme_copilot.api.main:app", host=args.host, port=args.port)
    elif args.cmd == "digest":
        from sme_copilot.db import SessionLocal, init_db
        from sme_copilot.forecasting.digest import build_digest
        from sme_copilot.models import Business
        init_db()
        with SessionLocal() as db:
            for biz in db.query(Business).all():
                d = build_digest(db, biz, _as_of(None))
                db.commit()
                print(f"[{biz.name}] {d.headline}")
                for a in d.alerts:
                    print(f"  - [{a['severity']}] {a['title']}")
    elif args.cmd == "verify-audit":
        from sme_copilot.db import SessionLocal, init_db
        from sme_copilot.security.audit import verify_chain
        init_db()
        with SessionLocal() as db:
            res = verify_chain(db)
        print(json.dumps(res, indent=1))
        return 0 if res["ok"] else 2
    elif args.cmd == "bench":
        from sme_copilot.benchmarks.runner import run_cli
        return run_cli(args.profiles.split(","), limit=args.limit, out_dir=args.out, judge=args.judge)
    elif args.cmd == "evidence":
        from sme_copilot.demo.evidence import run_evidence
        return run_evidence(args.out)
    elif args.cmd == "export-finetune":
        from sme_copilot.telemetry.export import export_cli
        return export_cli(args.out, include_unrated=args.include_unrated)
    elif args.cmd == "warmup":
        return cmd_warmup(args.profile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
