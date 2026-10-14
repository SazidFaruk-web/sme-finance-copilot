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


def cmd_seed(reset: bool, as_of: str | None) -> dict:
    from sme_copilot.config import get_settings
    from sme_copilot.db import SessionLocal, init_db, reset_engine
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
        res = load(db, _as_of(as_of))
    print(json.dumps(res, indent=1, default=str))
    print("\nDemo logins: nusrat (owner), rafiq (accountant), mitu (viewer). Passwords: see .env.example "
          "(DEMO_*_PASSWORD).")
    return res


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; we print ৳ and Bangla
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="sme_copilot", description="SME Finance Copilot CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the web app")
    s.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    s.add_argument("--reload", action="store_true")
    sub.add_parser("models", help="list provider profiles and availability")
    sd = sub.add_parser("seed", help="load demo data")
    sd.add_argument("--reset", action="store_true", help="delete the local SQLite DB first")
    sd.add_argument("--as-of", default=None, help="pretend today is YYYY-MM-DD")
    dm = sub.add_parser("demo", help="reset + seed + serve")
    dm.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    dm.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    sub.add_parser("digest", help="refresh alerts and print digests")
    sub.add_parser("verify-audit", help="verify the audit hash chain")
    b = sub.add_parser("bench", help="run the model benchmark")
    b.add_argument("--profiles", default="rules-offline", help="comma-separated provider profiles")
    b.add_argument("--limit", type=int, default=0, help="only the first N scenarios")
    b.add_argument("--out", default="benchmarks/results")
    ev = sub.add_parser("evidence", help="scripted end-to-end demo + execution evidence export")
    ev.add_argument("--out", default="docs/evidence")
    ft = sub.add_parser("export-finetune", help="export interaction log to a fine-tuning dataset")
    ft.add_argument("--out", default="data/finetune")
    ft.add_argument("--include-unrated", action="store_true")

    args = parser.parse_args(argv)
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
        cmd_seed(args.reset, args.as_of)
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
        return run_cli(args.profiles.split(","), limit=args.limit, out_dir=args.out)
    elif args.cmd == "evidence":
        from sme_copilot.demo.evidence import run_evidence
        return run_evidence(args.out)
    elif args.cmd == "export-finetune":
        from sme_copilot.telemetry.export import export_cli
        return export_cli(args.out, include_unrated=args.include_unrated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
