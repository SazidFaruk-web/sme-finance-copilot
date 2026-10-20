"""Add missing stock history to the isolated browser fixture, never the app DB."""
import os
import sys
from pathlib import Path
from datetime import date

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
runtime = root / "data" / "ui-review" / "runtime"
os.environ.update(APP_ENV="demo", DATA_DIR=str(runtime), DATABASE_URL=f"sqlite:///{runtime.as_posix()}/review.db",
                  LLM_PROFILE="rules-offline", LLM_SHARED_ONLY="false")
from sqlalchemy import select
from sme_copilot.db import SessionLocal
from sme_copilot.models import User
from sme_copilot.demo.trade_book import seed_stock

with SessionLocal() as db:
    owner = db.scalar(select(User).where(User.username == "tanvir"))
    if not owner:
        raise RuntimeError("Start tests/browser/server.py first")
    seed_stock(db, owner.business_id, "electronics", date(2026, 10, 17))
    db.commit()
