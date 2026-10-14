"""Upload every fake statement through the HTTP API and compare what was stored with expected.json.

    python scripts/make_fake_statements.py && python scripts/check_fake_uploads.py [dir]

Runs against a throwaway copy of the seeded demo database (never the real one).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "fake_statements"
    expected = json.loads((src / "expected.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="fakeup-"))
    os.environ.update({"APP_ENV": "test", "DATA_DIR": str(tmp), "DATABASE_URL": f"sqlite:///{(tmp / 'c.db').as_posix()}",
                       "LLM_PROFILE": "rules-offline", "RATE_LIMIT_PER_MINUTE": "100000",
                       "LOGIN_RATE_LIMIT_PER_MINUTE": "100000", "AS_OF_DATE": "2026-10-14"})
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from sme_copilot.api.main import create_app
    from sme_copilot.config import reset_settings_cache
    from sme_copilot.db import SessionLocal, init_db, reset_engine
    from sme_copilot.demo.seed import load
    from sme_copilot.models import Transaction
    from datetime import date

    reset_settings_cache()
    template = tmp / "template.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{template.as_posix()}"
    reset_settings_cache()
    reset_engine()
    init_db()
    with SessionLocal() as s:
        load(s, date(2026, 10, 14), write=False)
    reset_engine()
    failures = 0
    with TestClient(create_app()) as c:
        for i, (name, exp) in enumerate(expected.items()):
            # Each file goes into its own copy of the seeded DB, so cross-file de-duplication cannot interfere.
            db = tmp / f"run_{i}.db"
            shutil.copy(template, db)
            os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
            reset_settings_cache()
            reset_engine()
            tok = c.post("/api/auth/login", json={"username": "nusrat", "password": os.environ.get(
                "DEMO_OWNER_PASSWORD", "owner-demo-2026")}).json()["token"]
            h = {"Authorization": f"Bearer {tok}"}
            path = src / name
            t0 = time.perf_counter()
            r = c.post("/api/data/upload", files={"file": (name, path.read_bytes())}, headers=h)
            ms = (time.perf_counter() - t0) * 1000
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
            line = f"{name:30s} HTTP {r.status_code} {ms:7.0f} ms"
            ok = True
            if exp.get("outcome") == "imported":
                if r.status_code != 200:
                    ok = False
                    line += f"  expected import, got {str(body)[:160]}"
                else:
                    with SessionLocal() as s:
                        q = lambda d: s.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(  # noqa: E731
                            Transaction.batch_id == body["batch_id"], Transaction.direction == d,
                            Transaction.is_duplicate.is_(False)))
                        n = s.scalar(select(func.count()).where(Transaction.batch_id == body["batch_id"],
                                                                Transaction.is_duplicate.is_(False)))
                        got_in, got_out = round(float(q("in")), 2), round(float(q("out")), 2)
                    ok = (n == exp["rows"] and abs(got_in - exp["total_in"]) < 0.01 and abs(got_out - exp["total_out"]) < 0.01)
                    line += (f"  rows {n}/{exp['rows']}  in {got_in:,.0f}/{exp['total_in']:,.0f}"
                             f"  out {got_out:,.0f}/{exp['total_out']:,.0f}  dup={body.get('duplicates')} err={body.get('errors')}")
            else:
                detail = body.get("detail") if isinstance(body, dict) else body
                clear = r.status_code in (400, 413, 415, 422) and isinstance(detail, str) and len(detail) > 5
                if r.status_code == 200 and isinstance(body, dict) and body.get("imported", 0) == 0:
                    clear = bool(body.get("message") or body.get("warnings") or body.get("error_messages"))
                ok = clear
                line += f"  -> {str(detail if detail is not None else body)[:140]}"
            failures += not ok
            print(("PASS " if ok else "FAIL ") + line)
    reset_engine()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
