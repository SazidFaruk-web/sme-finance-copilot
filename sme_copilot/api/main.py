"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI

from sme_copilot import __version__
from sme_copilot.llm_providers import get_registry


def create_app() -> FastAPI:
    app = FastAPI(title="SME Finance Copilot", version=__version__)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/models")
    def models() -> dict:
        reg = get_registry()
        return {"default": reg.default_profile,
                "profiles": [p.__dict__ for p in reg.list_profiles()]}

    return app


app = create_app()
