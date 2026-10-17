"""Isolated UI review server. Never writes demo source files or the real app database."""
import os
import sys
from pathlib import Path
from datetime import date

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
runtime = root / 'data' / 'ui-review' / 'runtime'
runtime.mkdir(parents=True, exist_ok=True)
os.environ.update(APP_ENV='demo', DATA_DIR=str(runtime), DATABASE_URL=f'sqlite:///{runtime.as_posix()}/review.db',
                  AS_OF_DATE='2026-10-17', LLM_PROFILE='rules-offline', LLM_SHARED_ONLY='false',
                  RATE_LIMIT_PER_MINUTE='100000', LOGIN_RATE_LIMIT_PER_MINUTE='100000', DIGEST_SCHEDULER='false')
from sme_copilot.db import init_db, SessionLocal
from sme_copilot.models import Business
from sme_copilot.demo.seed import load
init_db()
with SessionLocal() as db:
    if not db.query(Business).count():
        load(db, date(2026, 10, 17), write=False)
        db.commit()
import uvicorn
uvicorn.run('sme_copilot.api.main:app', host='127.0.0.1', port=8002, log_level='warning')
