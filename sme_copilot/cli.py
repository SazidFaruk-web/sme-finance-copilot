"""Command-line entry point: ``python -m sme_copilot.cli <command>``."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sme_copilot", description="SME Finance Copilot CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")

    sub.add_parser("models", help="list provider profiles and availability")

    args = parser.parse_args(argv)
    if args.cmd == "serve":
        import uvicorn
        uvicorn.run("sme_copilot.api.main:app", host=args.host, port=args.port, reload=args.reload)
    elif args.cmd == "models":
        from sme_copilot.llm_providers import get_registry
        reg = get_registry()
        print(f"default: {reg.default_profile}")
        for p in reg.list_profiles():
            flag = "OK " if p.available else "-- "
            print(f"  {flag}{p.name:22} {p.adapter:18} {p.model:32} {'external' if p.external else 'local'}"
                  f"  {p.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
