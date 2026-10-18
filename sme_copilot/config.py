"""Application settings.

Secrets come only from environment variables (or a local .env file that is git-ignored).
Non-secret, structured configuration (provider profiles, routing rules, catalogs) lives in
YAML files under ``config/``.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"  # dev | demo | test | production
    data_dir: Path = ROOT_DIR / "data"
    database_url: str = ""  # default derived from data_dir

    # --- Security -------------------------------------------------------------------
    field_encryption_key: str = ""  # Fernet key; required in production
    session_ttl_minutes: int = 240
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    rate_limit_per_minute: int = 120
    login_rate_limit_per_minute: int = 10
    mask_pii: bool = True  # mask PII before any external LLM call
    local_only_mode: bool = False  # refuse every provider marked external: true

    # --- Sandbox money limits (BDT) ----------------------------------------------------
    sandbox_per_txn_limit: float = 200_000
    sandbox_daily_cap: float = 500_000
    step_up_amount: float = 50_000  # payments/deletes at or above this need the password again
    reminder_daily_limit: int = 20  # reminders queued per business per day
    cookie_secure: bool = False  # set COOKIE_SECURE=true behind HTTPS
    allow_signup: bool = True  # ALLOW_SIGNUP=false: only existing accounts can log in
    confirmation_ttl_minutes: int = 10

    # --- LLM ------------------------------------------------------------------------
    providers_file: Path = CONFIG_DIR / "providers.yaml"
    llm_profile: str = ""  # overrides default_profile from providers.yaml
    llm_shared_only: bool = False  # all users use the server's default profile; rules remain an offline fallback
    shared_llm_base_url: str = "http://127.0.0.1:11434/v1"
    shared_llm_model: str = "sme-copilot"  # Ollama alias with the app's context size
    llm_timeout_seconds: float = 60
    llm_max_retries: int = 2
    tool_result_budget_chars: int = 5000  # max size of one tool result as the model sees it (UI keeps full data)
    prompt_variant: str = "finance"  # base | finance (adds Bangladesh terms, tool map and a Banglish example)

    # Fixed "today" for reproducible demos/benchmarks (YYYY-MM-DD). Empty = real date (Asia/Dhaka).
    as_of_date: str = ""

    # --- Telemetry / background ---------------------------------------------------------
    interaction_log_enabled: bool = True
    digest_scheduler: bool = False  # refresh alerts for every business hourly (proactive digest)
    pilot_sms_enabled: bool = False  # enable only after provider onboarding and delivery tests
    pilot_sms_api_token: str = ""
    pilot_sms_sid: str = ""
    pilot_source_checks: bool = False
    pilot_question_model: bool = False  # optional shared LLM ordering; deterministic fallback always available
    # Illustrative loan terms and generic compliance dates. Unset = on only for APP_ENV=demo (the seeded demo
    # business, e.g. for judges); never enable for a real pilot. "false" turns it off even in demo.
    allow_illustrative_guidance: bool | None = None
    pilot_help_contact: str = ""  # operator-supplied facilitator phone/office; never invent a helpline

    # --- Market prices (Home price drawer) ----------------------------------------------
    market_prices_enabled: bool = True
    market_refresh: bool = True  # weekly download of the public WFP/HDX file; never in local_only_mode
    market_refresh_days: int = 7
    market_data_url: str = ""  # override the HDX CSV location (operator setting)
    market_forecast_model: str = "amazon/chronos-bolt-small"  # "" = statistical estimate only

    @property
    def illustrative_guidance(self) -> bool:
        if self.allow_illustrative_guidance is not None:
            return self.allow_illustrative_guidance
        return self.app_env == "demo"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'copilot.db').as_posix()}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def interaction_log_path(self) -> Path:
        return self.data_dir / "interactions.jsonl"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s


def reset_settings_cache() -> None:
    get_settings.cache_clear()


def load_yaml(name: str | Path) -> Any:
    """Load a YAML file from config/ (or an absolute path)."""
    path = Path(name)
    if not path.is_absolute():
        path = CONFIG_DIR / path
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def env_or_none(name: str | None) -> str | None:
    if not name:
        return None
    val = os.environ.get(name, "").strip()
    return val or None
