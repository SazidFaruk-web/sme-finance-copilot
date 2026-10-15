"""Home layout onboarding: widget/nav registries, validation, rule-based defaults and LLM-suggested layouts.

The model only ever picks ids from the fixed registry. Its output is treated as untrusted: unknown ids are
dropped, counts are capped, and any failure or timeout falls back to the rule-based defaults for the
business type. The free-text business type is data inside <untrusted_data>; no tools are offered to the model.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from sme_copilot.llm_providers.base import Message
from sme_copilot.llm_providers.schema_utils import inline_schema, strip_nullable
from sme_copilot.llm_providers.structured import extract_json
from sme_copilot.security.injection import SYSTEM_GUARD, scan, wrap_untrusted

log = logging.getLogger("sme_copilot.home")

# Fixed widget ids -> label; each maps to an existing dashboard component in frontend/app.js.
WIDGETS: dict[str, str] = {
    "cash_now": "Cash you have now",
    "money_in_out": "Money in and out",
    "receivables_aging": "Customers owe you, by how late",
    "profit_month": "Profit this month",
    "expenses_by_category": "Expenses by category",
    "cash_forecast": "Cash forecast (90 days)",
    "stock_alerts": "Stock running low",
    "todo_actions": "To do: alerts and actions",
    "loan_readiness": "Loan readiness",
    "top_customers": "Top customers",
    "recent_records": "Recent records",
    "invoices_due": "Invoices due",
    "recurring_due": "Repeating items due",
}
WIDGET_IDS = list(WIDGETS)
# Existing sidebar items (frontend ROUTES). Dashboard and settings can never be hidden.
NAV = ["dashboard", "chat", "data", "invoices", "parties", "reports", "stock", "financing", "actions", "audit", "settings"]
NAV_REQUIRED = ("dashboard", "settings")
BUSINESS_TYPES = {
    "retail": "Retail shop", "garments_trims": "Garments / trims", "restaurant_food": "Restaurant / food",
    "pharmacy_grocery": "Pharmacy / grocery", "wholesale_trading": "Wholesale / trading", "service_salon": "Service / salon",
    "other": "Other",
}
SERVICE_TYPES = {"service_salon"}
STYLES = ("general", "green", "blue")
MODES = ("general", "simplified", "custom")
SIMPLIFIED = ["cash_now", "money_in_out", "receivables_aging", "todo_actions"]
MAX_LAYOUTS, MAX_LAYOUT_WIDGETS = 3, 8
LLM_TIMEOUT_S = 8.0

Layout = dict[str, Any]  # {"name", "reason", "widgets"}

_C = "cash_now"
DEFAULTS: dict[str, list[Layout]] = {
    "retail": [
        {"name": "Sales & stock", "reason": "See what sells and what is running out.",
         "widgets": [_C, "money_in_out", "stock_alerts", "recent_records", "top_customers", "expenses_by_category"]},
        {"name": "Cash focus", "reason": "Keep enough cash for rent, stock and salaries.",
         "widgets": [_C, "cash_forecast", "money_in_out", "todo_actions", "recurring_due"]}],
    "garments_trims": [
        {"name": "Orders & receivables", "reason": "Buyers pay late; track who owes and what is due.",
         "widgets": [_C, "receivables_aging", "invoices_due", "top_customers", "cash_forecast", "todo_actions"]},
        {"name": "Stock & costs", "reason": "Watch trims stock and where the money goes.",
         "widgets": [_C, "stock_alerts", "expenses_by_category", "profit_month", "money_in_out"]},
        {"name": "Loan ready", "reason": "Get ready for working-capital finance before the season.",
         "widgets": [_C, "loan_readiness", "cash_forecast", "profit_month", "receivables_aging"]}],
    "restaurant_food": [
        {"name": "Daily cash", "reason": "Daily sales and costs move fast; see them every day.",
         "widgets": [_C, "money_in_out", "expenses_by_category", "recurring_due", "todo_actions"]},
        {"name": "Stock & costs", "reason": "Ingredients spoil; keep stock and food costs in view.",
         "widgets": [_C, "stock_alerts", "expenses_by_category", "profit_month", "recent_records"]}],
    "pharmacy_grocery": [
        {"name": "Sales & stock", "reason": "Many items, thin margins: watch stock and sales.",
         "widgets": [_C, "money_in_out", "stock_alerts", "profit_month", "recent_records"]},
        {"name": "Cash focus", "reason": "Pay suppliers on time without running short.",
         "widgets": [_C, "cash_forecast", "invoices_due", "todo_actions", "recurring_due"]}],
    "wholesale_trading": [
        {"name": "Receivables", "reason": "Credit sales are most of the business; chase what is owed.",
         "widgets": [_C, "receivables_aging", "invoices_due", "top_customers", "cash_forecast", "todo_actions"]},
        {"name": "Stock & margin", "reason": "Keep fast movers in stock and margins healthy.",
         "widgets": [_C, "stock_alerts", "profit_month", "money_in_out", "expenses_by_category"]}],
    "service_salon": [
        {"name": "Cash focus", "reason": "Rent and staff are the big costs; keep cash ahead of them.",
         "widgets": [_C, "money_in_out", "recurring_due", "todo_actions", "expenses_by_category"]},
        {"name": "Customers", "reason": "Regular customers drive the business.",
         "widgets": [_C, "top_customers", "invoices_due", "receivables_aging", "recent_records"]}],
    "other": [
        {"name": "Cash focus", "reason": "Start with cash: what you have, what comes in and goes out.",
         "widgets": [_C, "money_in_out", "cash_forecast", "todo_actions"]},
        {"name": "Grow & borrow", "reason": "Profit, customers and loan readiness in one place.",
         "widgets": [_C, "profit_month", "top_customers", "loan_readiness", "receivables_aging"]}],
}


def clean_ids(ids: Any, allowed: list[str], cap: int) -> list[str]:
    """Keep known ids only, in order, without duplicates, at most ``cap``."""
    out: list[str] = []
    for i in ids if isinstance(ids, list) else []:
        if isinstance(i, str) and i in allowed and i not in out:
            out.append(i)
    return out[:cap]


def clean_text(text: str, n: int = 60) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f<>{}\[\]`]", " ", text or "")).strip()[:n]


def type_key(business_type: str, text: str = "") -> str:
    """Stored business type: a registry id, or ``other:<free text>``."""
    bt = business_type if business_type in BUSINESS_TYPES else "other"
    t = clean_text(text).lower()
    return f"other:{t}"[:80] if bt == "other" and t else bt


def base_type(key: str | None) -> str:
    return (key or "other").split(":", 1)[0] if (key or "other").split(":", 1)[0] in BUSINESS_TYPES else "other"


def default_nav(key: str | None) -> list[str]:
    return [n for n in NAV if not (n == "stock" and base_type(key) in SERVICE_TYPES)]


def clean_nav(nav: Any, key: str | None) -> list[str]:
    out = clean_ids(nav, NAV, len(NAV)) if isinstance(nav, list) and nav else default_nav(key)
    return [n for n in NAV if n in out or n in NAV_REQUIRED]


def clean_layout(raw: Any) -> Layout | None:
    if not isinstance(raw, dict):
        return None
    widgets = clean_ids(raw.get("widgets"), WIDGET_IDS, MAX_LAYOUT_WIDGETS)
    if not widgets:
        return None
    return {"name": clean_text(str(raw.get("name") or "Suggested"), 40) or "Suggested",
            "reason": clean_text(str(raw.get("reason") or ""), 140), "widgets": widgets}


def rule_layouts(key: str | None) -> list[Layout]:
    return [dict(x, widgets=list(x["widgets"])) for x in DEFAULTS[base_type(key)]]


def normalize_prefs(*, business_type: str | None, mode: str, widgets: Any = None, nav: Any = None,
                    style: str = "general") -> dict[str, Any]:
    """Validate a layout before it is stored: skip = everything, simplified = the fixed four (unless edited)."""
    mode = mode if mode in MODES else "custom"
    if mode == "general":
        w = list(WIDGET_IDS)
    else:
        w = clean_ids(widgets, WIDGET_IDS, len(WIDGET_IDS)) or (list(SIMPLIFIED) if mode == "simplified" else [])
        if not w:
            w = list(rule_layouts(business_type)[0]["widgets"])
    return {"business_type": business_type, "mode": mode, "widgets": w, "nav": clean_nav(nav, business_type),
            "style": style if style in STYLES else "general"}


# ---------------------------------------------------------------------------------------------- LLM
WidgetId = Literal[tuple(WIDGET_IDS)]  # type: ignore[valid-type]


class _LayoutOut(BaseModel):
    name: str = Field(max_length=40)
    reason: str = Field(max_length=140)
    widgets: list[WidgetId] = Field(min_length=1, max_length=MAX_LAYOUT_WIDGETS)  # type: ignore[valid-type]


class _LayoutsOut(BaseModel):
    layouts: list[_LayoutOut] = Field(min_length=1, max_length=MAX_LAYOUTS)


SCHEMA = strip_nullable(inline_schema(_LayoutsOut.model_json_schema()))
_cache: dict[str, list[Layout]] = {}
_cache_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="home-layout")


def _prompt(key: str) -> list[Message]:
    catalog = "\n".join(f"- {k}: {v}" for k, v in WIDGETS.items())
    system = ("You design the home screen of a finance app for a small business in Bangladesh. Pick up to "
              f"{MAX_LAYOUTS} named layouts. Each layout uses 3-{MAX_LAYOUT_WIDGETS} widget ids from this list ONLY, "
              f"most important first:\n{catalog}\nGive each layout a short name (2-4 words) and a one-line reason "
              "for this business. Answer with JSON matching the schema, nothing else.\n" + SYSTEM_GUARD)
    return [Message("system", system), Message("user", "Business type:\n" + wrap_untrusted("business_type", key))]


def _ask_model(provider: Any, key: str) -> list[Layout]:
    msgs = _prompt(key)
    if not provider.supports_json_mode:
        msgs[0] = Message("system", msgs[0].content + "\nJSON schema:\n" + json.dumps(SCHEMA, ensure_ascii=False))
    resp = provider.chat(msgs, json_schema=SCHEMA if provider.supports_json_mode else None, temperature=0.0, max_tokens=600)
    raw = extract_json(resp.content)
    items = raw.get("layouts") if isinstance(raw, dict) else None
    layouts = [x for x in (clean_layout(r) for r in (items or [])[:MAX_LAYOUTS]) if x]
    if not layouts:
        raise ValueError("model returned no usable layout")
    return layouts


def suggest_layouts(business_type: str, text: str = "", *, provider_factory: Callable[[], Any] | None = None,
                    timeout: float = LLM_TIMEOUT_S) -> dict[str, Any]:
    """Up to 3 layouts for this business type: cached model answer, fresh model answer, or rule-based fallback."""
    key = type_key(business_type, text)
    with _cache_lock:
        if key in _cache:
            return {"business_type": key, "layouts": [dict(x) for x in _cache[key]], "source": "cache"}
    fallback = {"business_type": key, "layouts": rule_layouts(key), "source": "rules"}
    if scan(text).suspicious:  # instruction-like free text: never sent to the model
        return fallback
    try:
        if provider_factory is None:
            from sme_copilot.llm_providers.registry import get_registry
            reg = get_registry()
            provider_factory = lambda: reg.get(reg.default_profile)  # noqa: E731
        provider = provider_factory()
        if getattr(provider, "adapter", "") == "rules":  # offline rules engine cannot design layouts
            return fallback
        layouts = _pool.submit(_ask_model, provider, key).result(timeout=timeout)
    except FutureTimeout:
        log.info("home layout suggestion timed out after %.0fs; using defaults", timeout)
        return fallback
    except Exception as e:  # noqa: BLE001 - any provider/parse failure -> defaults
        log.info("home layout suggestion failed (%s); using defaults", e)
        return fallback
    with _cache_lock:
        if len(_cache) > 256:
            _cache.clear()
        _cache[key] = layouts
    return {"business_type": key, "layouts": [dict(x) for x in layouts], "source": "llm"}


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
