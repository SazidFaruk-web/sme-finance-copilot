"""FastAPI application factory."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sme_copilot import __version__
from sme_copilot.config import ROOT_DIR, get_settings
from sme_copilot.db import init_db
from sme_copilot.security.http import RateLimitMiddleware, SecurityHeadersMiddleware

FRONTEND_DIR = ROOT_DIR / "frontend"
log = logging.getLogger("sme_copilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.app_env == "production" and not s.field_encryption_key:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be set in production")
    init_db()
    stop = threading.Event()
    if s.digest_scheduler:
        threading.Thread(target=_digest_loop, args=(stop,), daemon=True, name="digest-scheduler").start()
    yield
    stop.set()


def _digest_loop(stop: threading.Event, interval_s: int = 3600) -> None:
    """Proactive alerts: refresh every business's alerts hourly so the digest is ready when the owner opens
    the app (or call `python -m sme_copilot.cli digest` from cron)."""
    from sme_copilot.api.deps import as_of_today
    from sme_copilot.db import SessionLocal
    from sme_copilot.forecasting.alerts import refresh_alerts
    from sme_copilot.models import Business
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                for b in db.query(Business).all():
                    refresh_alerts(db, b, as_of_today())
                db.commit()
        except Exception:  # noqa: BLE001 - background job must never crash the app
            log.exception("digest scheduler run failed")
        stop.wait(interval_s)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="SME Finance Copilot", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs" if s.app_env != "production" else None, redoc_url=None)

    app.add_middleware(RateLimitMiddleware, get_limits=lambda: (get_settings().rate_limit_per_minute,
                                                                get_settings().login_rate_limit_per_minute))
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])

    from . import routes_core, routes_data
    app.include_router(routes_core.router)
    app.include_router(routes_data.router)
    for mod in ("routes_insights", "routes_actions", "routes_stock"):
        try:
            m = __import__(f"sme_copilot.api.{mod}", fromlist=["router"])
            app.include_router(m.router)
        except ModuleNotFoundError as e:
            if e.name != f"sme_copilot.api.{mod}":
                raise

    @app.get("/api/health")
    def health() -> dict:
        st = get_settings()
        out = {"status": "ok", "version": __version__, "env": st.app_env, "local_only_mode": st.local_only_mode}
        if st.app_env == "demo":  # demo deployments only: show the seeded demo logins on the login screen
            import os
            out["demo_users"] = [
                {"username": "nusrat", "role": "owner", "password": os.environ.get("DEMO_OWNER_PASSWORD", "owner-demo-2026")},
                {"username": "rafiq", "role": "accountant",
                 "password": os.environ.get("DEMO_ACCOUNTANT_PASSWORD", "accountant-demo-2026")},
                {"username": "mitu", "role": "viewer", "password": os.environ.get("DEMO_VIEWER_PASSWORD", "viewer-demo-2026")},
            ]
        return out

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()
