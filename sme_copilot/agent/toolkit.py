"""Tool registry: every capability the agent (or a UI button) can invoke.

A tool = pydantic args model (-> JSON schema for function calling) + permission tier + handler
+ optional result model (validated on the way out).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

import pandas as pd
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from sme_copilot.llm_providers.base import ToolSpec
from sme_copilot.llm_providers.schema_utils import DROP_KEYS, inline_schema, strip_nullable

CONSTRAINT_KEYS = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength",
                   "minItems", "maxItems", "pattern"}
from sme_copilot.models import Business, User
from sme_copilot.tools import repo

PERIODS = ("this_month", "last_month", "last_30_days", "last_90_days", "last_3_months", "last_6_months",
           "last_12_months", "ytd", "fiscal_ytd", "all")
_PERIOD_RX = re.compile(r"^\d{4}-\d{2}$")


class PeriodArgs(BaseModel):
    period: str = Field("last_3_months", description=" | ".join(PERIODS) + " | YYYY-MM")

    @field_validator("period")
    @classmethod
    def _valid_period(cls, v: str) -> str:
        v = (v or "last_3_months").strip().lower()
        if v in PERIODS or _PERIOD_RX.match(v):
            return v
        raise ValueError(f"period must be one of {PERIODS} or YYYY-MM")


@dataclass
class ToolContext:
    session: Session
    business: Business
    user: User
    as_of: date
    request_id: str = ""
    language: str = "en"
    origin: str = "agent"  # agent | api | confirmation
    pending_action_id: int | None = None  # set while executing a confirmed Tier-2 action
    suspicious_input: bool = False  # user text matched instruction-override patterns (no money tools this turn)
    _txns: pd.DataFrame | None = None
    _invoices: pd.DataFrame | None = None

    @property
    def style(self) -> str:
        return (self.business.prefs or {}).get("number_style", "lakh")

    def txns(self) -> pd.DataFrame:
        if self._txns is None:
            self._txns = repo.load_transactions(self.session, self.business.id, end=self.as_of)
        return self._txns

    def invoices(self) -> pd.DataFrame:
        if self._invoices is None:
            self._invoices = repo.load_invoices(self.session, self.business.id)
        return self._invoices

    def invalidate(self) -> None:
        self._txns = None
        self._invoices = None


@dataclass
class ToolDef:
    name: str
    description: str
    args_model: type[BaseModel]
    tier: int
    handler: Callable[[ToolContext, Any], Any]
    category: str = "analysis"  # analysis | data | forecast | financing | action | money | blocked
    result_model: type[BaseModel] | None = None
    amount_field: str | None = None  # tier-2: which arg holds the amount
    recipient_field: str | None = None
    summarize: Callable[[Any], str] | None = None  # human-readable description for confirmations
    advisory: bool = False  # output needs the "not financial advice" disclaimer
    mutates: bool = False  # invalidates cached data
    prepare: Callable[[ToolContext, Any], Any] | None = None  # fill derived args (e.g. amount) before authorization
    always_confirm: bool = False  # high-risk: any call only PROPOSES; the user's confirm click executes it

    def spec(self) -> ToolSpec:
        # Range/length constraints are enforced by the executor's pydantic validation (invalid_args is fed
        # back to the model), so they are left out of the schema the model sees to keep every prompt small.
        schema = strip_nullable(inline_schema(self.args_model.model_json_schema(), drop=DROP_KEYS | CONSTRAINT_KEYS))
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        desc = self.description
        if self.tier == 2:
            desc += " (Money action: creates a request that the owner must confirm in the app.)"
        return ToolSpec(self.name, desc, schema)


REGISTRY: dict[str, ToolDef] = {}


def register(tool: ToolDef) -> ToolDef:
    if tool.name in REGISTRY:
        raise ValueError(f"duplicate tool {tool.name}")
    REGISTRY[tool.name] = tool
    return tool


def tool(name: str, description: str, args_model: type[BaseModel], tier: int, **kw: Any):
    """Decorator form of ``register``."""
    def deco(fn: Callable[[ToolContext, Any], Any]):
        register(ToolDef(name=name, description=description, args_model=args_model, tier=tier, handler=fn, **kw))
        return fn
    return deco


def load_all_tools() -> dict[str, ToolDef]:
    """Import tool modules (each registers itself). Idempotent."""
    from sme_copilot.agent import tools_analysis  # noqa: F401
    for mod in ("tools_forecast", "tools_financing", "tools_actions"):
        try:
            __import__(f"sme_copilot.agent.{mod}")
        except ModuleNotFoundError as e:
            if e.name != f"sme_copilot.agent.{mod}":
                raise
    return REGISTRY


def specs_for(user: User | None = None, *, include_blocked: bool = True) -> list[ToolSpec]:
    """Tools offered to the model. Blocked (tier-3) tools are still listed so a manipulated
    model that tries them is caught and audited by the permission layer, not silently ignored."""
    load_all_tools()
    out = []
    for t in REGISTRY.values():
        if t.tier == 3 and not include_blocked:
            continue
        out.append(t.spec())
    return out
