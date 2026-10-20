"""Shared pytest setup: isolate every test session in a temp data dir with a fixed key."""
from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="smecopilot-test-")
os.environ["APP_ENV"] = "test"
os.environ["DATA_DIR"] = _TMP
os.environ["LLM_PROFILE"] = "rules-offline"
os.environ["STRATEGY_QUESTION_MODEL"] = "false"  # tests never contact a real model
os.environ["LLM_SHARED_ONLY"] = "false"
os.environ["LOCAL_ONLY_MODE"] = "false"
# Test-only Fernet key (not a secret; generated for this repository's tests).
os.environ["FIELD_ENCRYPTION_KEY"] = "q2Vt0b2dJ3m8u0cA8n7f1yV3oZx9lS5eT4rW6pQ1hKs="
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["ALLOW_ILLUSTRATIVE_GUIDANCE"] = "true"  # legacy calculator fixtures, never real-owner guidance
os.environ["APP_LANGUAGES"] = "en,bn,zh"  # the language tests need Bangla and Chinese; the app default is English only
os.environ["MARKET_REFRESH"] = "false"  # tests use the bundled price snapshot, never the network
os.environ["MARKET_FORECAST_MODEL"] = ""  # statistical estimate; the model has its own opt-in test
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


SMALL_LEDGER = "Date,Description,Amount,Type,Party\n" + "\n".join(
    line for m in ("07", "08", "09") for line in (
        f"10/{m}/2026,Sold zippers and buttons,300000,income,Karim Knit",
        f"11/{m}/2026,Bought zippers from wholesaler,150000,expense,Islampur Traders",
        f"01/{m}/2026,Shop rent,30000,expense,",
        f"28/{m}/2026,Staff salary,45000,expense,",
        f"15/{m}/2026,Courier and van delivery,15000,expense,",
    )) + "\n"

SMALL_INVOICES = """Invoice No,Customer,Amount,Invoice Date,Due Date,Paid Date,Phone
INV-201,Karim Knit Composite,120000,01/08/2026,31/08/2026,,01711111111
INV-202,Rahman Fashion,45000,15/08/2026,14/09/2026,20/09/2026,01722222222
INV-203,Karim Knit Composite,80000,01/10/2026,31/10/2026,,
"""


@pytest.fixture
def seeded(db, monkeypatch):
    """Business + owner/accountant/viewer + 3 months of data; 'today' pinned to 2026-10-14."""
    from datetime import date

    from sme_copilot.config import reset_settings_cache
    from sme_copilot.models import Business, SandboxAccount
    from sme_copilot.security.auth import create_user
    from sme_copilot.tools.ingestion import import_file

    monkeypatch.setenv("AS_OF_DATE", "2026-10-14")
    reset_settings_cache()
    b = Business(name="Test Trims", sector="accessories", established_on=date(2022, 1, 1),
                 opening_cash_balance=200_000, opening_balance_date=date(2026, 6, 30),
                 has_trade_license=True, has_tin=True, collateral_value=500_000)
    db.add(b)
    db.flush()
    owner = create_user(db, b.id, "owner", "owner-pass-123", "owner", "Nusrat")
    acct = create_user(db, b.id, "accountant", "acct-pass-123", "accountant", "Rafiq")
    viewer = create_user(db, b.id, "viewer", "viewer-pass-123", "viewer", "Mitu")
    db.add(SandboxAccount(business_id=b.id, balance=300_000, account_no="9990001112223"))
    import_file(db, b.id, SMALL_LEDGER.encode(), "ledger.csv")
    import_file(db, b.id, SMALL_INVOICES.encode(), "invoices.csv")
    db.commit()
    return {"business": b, "owner": owner, "accountant": acct, "viewer": viewer, "db": db}


def make_ctx(seeded, role="owner"):
    from datetime import date

    from sme_copilot.agent.toolkit import ToolContext
    return ToolContext(session=seeded["db"], business=seeded["business"], user=seeded[role],
                       as_of=date(2026, 10, 14), request_id="test")
