"""Shared pytest setup: isolate every test session in a temp data dir with a fixed key."""
from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="smecopilot-test-")
os.environ["APP_ENV"] = "test"
os.environ["DATA_DIR"] = _TMP
os.environ["LLM_PROFILE"] = "rules-offline"
os.environ["LOCAL_ONLY_MODE"] = "false"
# Test-only Fernet key (not a secret; generated for this repository's tests).
os.environ["FIELD_ENCRYPTION_KEY"] = "q2Vt0b2dJ3m8u0cA8n7f1yV3oZx9lS5eT4rW6pQ1hKs="
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "100000"
for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
          "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"):
    os.environ.pop(k, None)


import pandas as pd  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Fresh SQLite database per test."""
    from sme_copilot.config import reset_settings_cache
    from sme_copilot.db import SessionLocal, init_db, reset_engine

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    reset_settings_cache()
    reset_engine()
    init_db()
    s = SessionLocal()
    yield s
    s.close()
    reset_engine()
    reset_settings_cache()


@pytest.fixture
def business(db):
    from datetime import date

    from sme_copilot.models import Business
    b = Business(name="Test Trims", sector="accessories", established_on=date(2022, 1, 1),
                 opening_cash_balance=100_000, opening_balance_date=date(2025, 12, 31),
                 has_trade_license=True, has_tin=True)
    db.add(b)
    db.commit()
    return b


def make_txn_df(rows):
    """rows: (id, 'YYYY-MM-DD', amount, direction, category[, counterparty])"""
    recs = []
    for r in rows:
        recs.append({"id": r[0], "date": pd.Timestamp(r[1]), "amount": float(r[2]), "direction": r[3],
                     "category": r[4], "counterparty": r[5] if len(r) > 5 else "", "description": "",
                     "channel": "cash", "source": "test", "source_row": r[0] + 1, "batch_id": None,
                     "is_anomaly": False, "flags": []})
    return pd.DataFrame(recs)
