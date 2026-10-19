"""After uploading a fake statement, ask the AI Assistant about it and check its numbers against code.

For each statement: upload it into a fresh copy of the seeded DB through the API, ask the chat endpoint
(English, Bangla and Banglish) for that month's income and expenses, then compute the truth with the
deterministic `get_financial_summary` tool on the same DB and check the reply quotes those numbers.
Also checks the dashboard API answers and that no reply is a silent fallback.

    python scripts/check_upload_chat.py --base-url http://127.0.0.1:8085/v1 [--profile-extra JSON]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

QUESTIONS = {
    "en": "What were my total income and total expenses in {month_en}?",
    "bn": "{month_bn} মাসে আমার মোট আয় আর মোট খরচ কত ছিল?",
    "banglish": "{month_bl} mashe amar mot ay ar mot khoroch koto chilo?",
}
MONTH = ("2026-05", "May 2026", "মে ২০২৬", "May 2026")
FILES = ["01_clean_bank.csv", "03_bangla_headers_digits.csv", "04_mixed_dates.csv"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--tools", default="emulated")
    ap.add_argument("--profile-extra", default="{}")
    ap.add_argument("--src", default=str(ROOT / "data" / "fake_statements"))
    a = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config" / "providers.yaml").read_text(encoding="utf-8"))
    cfg["profiles"]["local-llamacpp"].update({"base_url": a.base_url, "tools": a.tools, "timeout": 180,
                                              "max_retries": 0, **json.loads(a.profile_extra)})
    tmp = Path(tempfile.mkdtemp(prefix="upchat-"))
    (tmp / "providers.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    os.environ.update({"APP_ENV": "test", "DATA_DIR": str(tmp), "PROVIDERS_FILE": str(tmp / "providers.yaml"),
                       "LLM_PROFILE": "local-llamacpp", "LOCAL_ONLY_MODE": "true", "AS_OF_DATE": "2026-10-14",
                       "RATE_LIMIT_PER_MINUTE": "100000", "LOGIN_RATE_LIMIT_PER_MINUTE": "100000"})
    from fastapi.testclient import TestClient

    from sme_copilot.agent.executor import execute
    from sme_copilot.agent.grounding import extract_numbers
    from sme_copilot.api.deps import tool_context
    from sme_copilot.api.main import create_app
    from sme_copilot.benchmarks.runner import number_in_reply
    from sme_copilot.config import reset_settings_cache
    from sme_copilot.db import SessionLocal, init_db, reset_engine
    from sme_copilot.demo.seed import load
    from sme_copilot.models import User

    template = tmp / "template.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{template.as_posix()}"
    reset_settings_cache()
    reset_engine()
    init_db()
    with SessionLocal() as s:
        load(s, date(2026, 10, 14), write=False)
    reset_engine()
    results, failures = [], 0
    src = Path(a.src)
    with TestClient(create_app()) as c:
        for i, name in enumerate(FILES):
            db = tmp / f"run_{i}.db"
            shutil.copy(template, db)
            os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
            reset_settings_cache()
            reset_engine()
            h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={
                "username": "nusrat", "password": os.environ.get("DEMO_OWNER_PASSWORD", "owner-demo-2026")}).json()["token"]}
            up = c.post("/api/data/upload", files={"file": (name, (src / name).read_bytes())}, headers=h)
            assert up.status_code == 200, up.text
            dash = c.get("/api/dashboard", headers=h)
            with SessionLocal() as s:
                u = s.query(User).filter_by(username="nusrat").one()
                truth = execute(tool_context(s, u), "get_financial_summary", {"period": MONTH[0]}).data
            want = {"income": float(truth["total_income"]), "expense": float(truth["total_expense"])}
            for lang, q in QUESTIONS.items():
                text = q.format(month_en=MONTH[1], month_bn=MONTH[2], month_bl=MONTH[3])
                t0 = time.perf_counter()
                d = c.post("/api/chat", json={"message": text}, headers=h).json()
                secs = time.perf_counter() - t0
                nums = extract_numbers(d.get("reply", ""))
                hit = {k: number_in_reply(v, nums) for k, v in want.items()}
                ok = all(hit.values()) and not d.get("fallback") and d.get("profile") == "local-llamacpp"
                failures += not ok
                results.append({"file": name, "lang": lang, "ok": ok, "secs": round(secs, 1), "want": want, "hit": hit,
                                "fallback": d.get("fallback"), "fallback_reason": d.get("fallback_reason"),
                                "language": d.get("language"), "tools": [t["tool"] for t in d.get("tool_calls", [])],
                                "dashboard_status": dash.status_code, "reply": d.get("reply", "")[:300]})
                print(("PASS" if ok else "FAIL"), name, lang, f"{secs:.1f}s", hit, "fallback" if d.get("fallback") else "",
                      "|", d.get("reply", "")[:140].replace("\n", " "))
    reset_engine()
    out = ROOT / "benchmarks" / "results" / "upload_chat_check.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{failures} failure(s) of {len(results)}; wrote {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
