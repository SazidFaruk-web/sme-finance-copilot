"""FastAPI application factory."""
from __future__ import annotations

import logging
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
    yield


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
    for mod in ("routes_insights", "routes_actions"):
        try:
            m = __import__(f"sme_copilot.api.{mod}", fromlist=["router"])
            app.include_router(m.router)
        except ModuleNotFoundError as e:
            if e.name != f"sme_copilot.api.{mod}":
                raise

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

    return app


app = create_app()
